const test = require('node:test');
const assert = require('node:assert/strict');

const modulePath = '../clients/outlook-addin/taskpane.interactions.js';

function loadModule() {
  delete require.cache[require.resolve(modulePath)];
  return require(modulePath);
}

function createBoundInteractions(openImpl) {
  let clickHandler = null;
  let toastClickHandler = null;
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const toastHost = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') toastClickHandler = handler;
    },
  };
  global.window = {};
  global.window.open = openImpl;
  if (global.URL) {
    global.window.URL = global.URL;
  }
  const moduleRef = loadModule();
  const interactions = moduleRef.create({
    byId: (id) => {
      if (id === 'chatArea') return chatArea;
      if (id === 'clarificationToastHost') return toastHost;
      return null;
    },
    logClientEvent: () => {},
    copiedResetMs: 10,
    addMessage: () => {},
    showClarificationToast: () => {},
    clearClarificationToast: () => {},
    setSendingState: () => {},
    requestAssistantReply: async () => ({ answer: 'ok', metadata: {} }),
    openEvidenceMail: async () => {},
  });
  interactions.bindMessageActions();
  return {
    dispatchClick(action, extraDataset) {
      const button = {
        dataset: Object.assign({ action }, extraDataset || {}),
        classList: { contains: () => false },
        closest: () => null,
      };
      clickHandler({
        target: {
          closest: () => button,
        },
      });
    },
    dispatchToastClick(action, extraDataset) {
      const button = {
        dataset: Object.assign({ action }, extraDataset || {}),
        classList: { contains: () => false },
        closest: () => null,
      };
      toastClickHandler({
        target: {
          closest: () => button,
        },
      });
    },
  };
}

test('report open file action opens preview url in new tab', () => {
  const openCalls = [];
  const harness = createBoundInteractions((url) => {
    openCalls.push(url);
    return {};
  });
  harness.dispatchClick('report-open-file', {
    previewUrl: '/report/preview/a.docx',
    docxUrl: '/report/download/a.docx',
  });
  assert.equal(openCalls.length, 1);
  assert.equal(openCalls[0], '/report/preview/a.docx');
});

test('report open file action does nothing when docx url is empty', () => {
  const openCalls = [];
  const harness = createBoundInteractions((url) => {
    openCalls.push(url);
    return {};
  });
  harness.dispatchClick('report-open-file', { docxUrl: '' });
  assert.equal(openCalls.length, 0);
});

test('section toggle action collapses and expands major summary section', () => {
  let clickHandler = null;
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const sectionNode = {
    classList: {
      _state: false,
      toggle() {
        this._state = !this._state;
        return this._state;
      },
    },
  };
  const button = {
    dataset: { action: 'section-toggle' },
    textContent: '',
    setAttribute(name, value) {
      this[name] = value;
    },
    closest(selector) {
      if (selector === '.summary-section.section-major') return sectionNode;
      return null;
    },
  };
  global.window = {};
  const moduleRef = loadModule();
  const interactions = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    logClientEvent: () => {},
    copiedResetMs: 10,
    addMessage: () => {},
    setSendingState: () => {},
    requestAssistantReply: async () => ({ answer: 'ok', metadata: {} }),
    openEvidenceMail: async () => {},
  });
  interactions.bindMessageActions();

  clickHandler({
    target: { closest: () => button },
  });
  assert.equal(button.textContent, '펼치기');
  assert.equal(button['aria-expanded'], 'false');

  clickHandler({
    target: { closest: () => button },
  });
  assert.equal(button.textContent, '접기');
  assert.equal(button['aria-expanded'], 'true');
});

test('selected mail open action calls openEvidenceMail with message id only', async () => {
  let clickHandler = null;
  let openedMessageId = '';
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const button = {
    dataset: {
      action: 'selected-mail-open',
      messageId: 'mail-123',
      webLink: 'https://outlook.live.com/owa/?ItemID=123',
    },
    classList: { contains: () => false },
    closest: () => null,
  };
  global.window = {};
  const moduleRef = loadModule();
  const interactions = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    logClientEvent: () => {},
    copiedResetMs: 10,
    addMessage: () => {},
    setSendingState: () => {},
    requestAssistantReply: async () => ({ answer: 'ok', metadata: {} }),
    openEvidenceMail: async (messageId) => {
      openedMessageId = messageId;
    },
  });
  interactions.bindMessageActions();

  clickHandler({
    target: { closest: () => button },
    preventDefault: () => {},
  });
  await Promise.resolve();

  assert.equal(openedMessageId, 'mail-123');
});

test('selected mail open action ignores button without message id', async () => {
  let clickHandler = null;
  let called = false;
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const button = {
    dataset: {
      action: 'selected-mail-open',
      messageId: '',
      webLink: 'https://outlook.live.com/owa/?ItemID=123',
    },
    classList: { contains: () => false },
    closest: () => null,
  };
  global.window = {};
  const moduleRef = loadModule();
  const interactions = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    logClientEvent: () => {},
    copiedResetMs: 10,
    addMessage: () => {},
    setSendingState: () => {},
    requestAssistantReply: async () => ({ answer: 'ok', metadata: {} }),
    openEvidenceMail: async () => {
      called = true;
    },
  });
  interactions.bindMessageActions();

  clickHandler({
    target: { closest: () => button },
    preventDefault: () => {},
  });
  await Promise.resolve();

  assert.equal(called, false);
});

test('outside click and escape close evidence popovers', () => {
  let chatClickHandler = null;
  const docHandlers = {};
  const popoverA = { removed: false, removeAttribute: () => { popoverA.removed = true; } };
  const popoverB = { removed: false, removeAttribute: () => { popoverB.removed = true; } };
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') chatClickHandler = handler;
    },
  };
  global.window = {};
  global.document = {
    addEventListener(eventName, handler) {
      docHandlers[eventName] = handler;
    },
    querySelectorAll(selector) {
      if (selector.indexOf('inline-evidence-popover') >= 0) {
        return [popoverA, popoverB];
      }
      return [];
    },
  };
  const moduleRef = loadModule();
  const interactions = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    logClientEvent: () => {},
    copiedResetMs: 10,
    addMessage: () => {},
    setSendingState: () => {},
    requestAssistantReply: async () => ({ answer: 'ok', metadata: {} }),
    openEvidenceMail: async () => {},
  });
  interactions.bindMessageActions();
  assert.equal(typeof docHandlers.click, 'function');
  assert.equal(typeof docHandlers.keydown, 'function');

  const activePopover = {
    closest: (selector) => (selector.indexOf('details.inline-evidence-popover') >= 0 ? popoverA : null),
  };
  docHandlers.click({ target: activePopover });
  assert.equal(popoverA.removed, false);
  assert.equal(popoverB.removed, true);

  popoverA.removed = false;
  popoverB.removed = false;
  chatClickHandler({
    target: { closest: () => null },
  });
  assert.equal(popoverA.removed, true);
  assert.equal(popoverB.removed, true);

  popoverA.removed = false;
  popoverB.removed = false;
  docHandlers.keydown({ key: 'Escape' });
  assert.equal(popoverA.removed, true);
  assert.equal(popoverB.removed, true);
});

test('raw action opens fallback alert with raw model content when modal dom is unavailable', () => {
  let clickHandler = null;
  const alerts = [];
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const messageNode = {
    querySelector(selector) {
      if (selector === '.msg-body') {
        return { textContent: '가공 답변' };
      }
      if (selector === '.msg-raw-answer') {
        return { textContent: '후단 raw_answer' };
      }
      if (selector === '.msg-raw-model-output') {
        return { textContent: '모델 직출력 raw' };
      }
      if (selector === '.msg-raw-model-content') {
        return { textContent: '{"type":"text","text":"모델 원본"}' };
      }
      return null;
    },
  };
  const button = {
    dataset: { action: 'raw' },
    classList: { contains: () => false },
    closest(selector) {
      if (selector === '.message') return messageNode;
      return null;
    },
  };
  global.window = { alert: (text) => alerts.push(String(text || '')) };
  global.document = undefined;
  const moduleRef = loadModule();
  const interactions = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    logClientEvent: () => {},
    copiedResetMs: 10,
    addMessage: () => {},
    setSendingState: () => {},
    requestAssistantReply: async () => ({ answer: 'ok', metadata: {} }),
    openEvidenceMail: async () => {},
  });
  interactions.bindMessageActions();

  clickHandler({
    target: {
      closest: () => button,
    },
  });

  assert.equal(alerts.length, 1);
  assert.equal(alerts[0], '{"type":"text","text":"모델 원본"}');
});

test('scope-select click from clarification toast reruns original query with selected scope', async () => {
  let toastClickHandler = null;
  const calls = {
    addMessage: [],
    requestAssistantReply: [],
    setSendingState: [],
    clearClarificationToast: 0,
    showClarificationToast: [],
  };
  const chatArea = { addEventListener: () => {} };
  const toastHost = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') toastClickHandler = handler;
    },
  };
  global.window = {};
  const moduleRef = loadModule();
  const interactions = moduleRef.create({
    byId: (id) => {
      if (id === 'chatArea') return chatArea;
      if (id === 'clarificationToastHost') return toastHost;
      if (id === 'chatInput') return { focus: () => {} };
      return null;
    },
    logClientEvent: () => {},
    copiedResetMs: 10,
    addMessage: (role, text, metadata) => calls.addMessage.push({ role, text, metadata }),
    showClarificationToast: (metadata) => calls.showClarificationToast.push(metadata),
    clearClarificationToast: () => { calls.clearClarificationToast += 1; },
    setSendingState: (value) => calls.setSendingState.push(Boolean(value)),
    requestAssistantReply: async (query, _progress, runtimeOptions) => {
      calls.requestAssistantReply.push({ query, runtimeOptions });
      return { answer: '응답', metadata: { clarification: { required: false } } };
    },
    openEvidenceMail: async () => {},
  });
  interactions.bindMessageActions();

  const button = {
    dataset: {
      action: 'scope-select',
      scope: 'current_mail',
      scopeLabel: '현재 메일',
      originalQuery: '문제가 되는 메일주소가 뭐야?',
    },
    disabled: false,
    classList: { contains: () => false },
    closest: () => null,
  };
  toastClickHandler({
    target: { closest: () => button },
  });
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(calls.clearClarificationToast, 1);
  assert.equal(calls.requestAssistantReply.length, 1);
  assert.equal(calls.requestAssistantReply[0].query, '문제가 되는 메일주소가 뭐야?');
  assert.equal(calls.requestAssistantReply[0].runtimeOptions.scope, 'current_mail');
  assert.equal(calls.addMessage.some((item) => item.role === 'user' && item.text.includes('질문 범위 선택')), true);
  assert.equal(calls.addMessage.some((item) => item.role === 'assistant' && item.text === '응답'), true);
  assert.equal(calls.showClarificationToast.length, 1);
});
