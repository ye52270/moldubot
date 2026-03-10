const test = require('node:test');
const assert = require('node:assert/strict');

const modulePath = '../clients/outlook-addin/taskpane.bootstrap.js';

function loadModule() {
  delete require.cache[require.resolve(modulePath)];
  return require(modulePath);
}

function createBaseDeps(overrides = {}) {
  const sendBtn = {
    addEventListener(eventName) {
      if (eventName === 'click') this.clickBound = (this.clickBound || 0) + 1;
    },
    clickBound: 0,
  };
  const deps = {
    windowRef: {
      setInterval() { return 1; },
    },
    documentRef: {
      addEventListener() {},
    },
    byId(id) {
      if (id === 'sendBtn') return sendBtn;
      return null;
    },
    sender: { sendMessage() {} },
    messageUi: {
      addMessage() {},
      resetSession() {},
      syncWelcomeLayoutState() {},
      renderSelectedMailBanner() {},
    },
    chatApi: { resetThread() {} },
    state: { clearExecutedNextActions() {} },
    quickPrompts: null,
    chatActions: { bindChatAreaActions() {} },
    interactions: { bindMessageActions() {} },
    runtimeHelpers: {
      openEvidenceMail: async function () {},
    },
    selectionController: {
      observeSelectionChanges: async function () {},
      startSelectionPolling() {},
      clearSelectionCache() {},
      resolveSelectionContextOnce: async function () {
        return {
          emailId: '',
          mailboxUser: '',
          reason: 'no_context',
          directItemId: '',
          asyncItemId: '',
          selectedItemId: '',
        };
      },
      setCachedSelectionContextForTest() {},
      getSelectionStateSnapshot() {
        return { cachedEmailId: '', cachedMailboxUser: '' };
      },
    },
    shortId(value) {
      return String(value || '');
    },
    logClientEvent() {},
    uiBuild: 'build-test',
    selectedMailSyncMs: 900,
    openEvalPage() {},
    fetchImpl: async function () {
      return { ok: false, json: async function () { return {}; } };
    },
  };
  return { ...deps, ...overrides, _sendBtn: sendBtn };
}

test('bootstrap runs only once even when called repeatedly', async () => {
  const moduleRef = loadModule();
  let observeCount = 0;
  let pollCount = 0;
  let clearCount = 0;
  let bindChatCount = 0;
  let bindMsgCount = 0;
  const events = [];
  const deps = createBaseDeps({
    chatActions: {
      bindChatAreaActions() {
        bindChatCount += 1;
      },
    },
    interactions: {
      bindMessageActions() {
        bindMsgCount += 1;
      },
    },
    selectionController: {
      observeSelectionChanges: async function () { observeCount += 1; },
      startSelectionPolling() { pollCount += 1; },
      clearSelectionCache() { clearCount += 1; },
      resolveSelectionContextOnce: async function () {
        return {
          emailId: '',
          mailboxUser: '',
          reason: 'no_context',
          directItemId: '',
          asyncItemId: '',
          selectedItemId: '',
        };
      },
      setCachedSelectionContextForTest() {},
      getSelectionStateSnapshot() {
        return { cachedEmailId: '', cachedMailboxUser: '' };
      },
    },
    logClientEvent(level, event, payload) {
      events.push({ level, event, payload });
    },
  });

  const runner = moduleRef.create(deps);
  runner.bootstrap();
  runner.bootstrap();
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(observeCount, 1);
  assert.equal(pollCount, 1);
  assert.equal(clearCount, 1);
  assert.equal(bindChatCount, 1);
  assert.equal(bindMsgCount, 1);
  assert.equal(deps._sendBtn.clickBound, 1);
  assert.equal(events.some((item) => item.event === 'ui_build_loaded'), true);
});

test('fetchSelectedMailContext renders banner when context fetch succeeds', async () => {
  const moduleRef = loadModule();
  const rendered = [];
  const runner = moduleRef.create(createBaseDeps({
    messageUi: {
      addMessage() {},
      resetSession() {},
      syncWelcomeLayoutState() {},
      renderSelectedMailBanner(payload) {
        rendered.push(payload);
      },
    },
    fetchImpl: async function () {
      return {
        ok: true,
        json: async function () {
          return {
            mail: {
              message_id: 'mail-1',
              subject: 'subject',
              from_address: 'a@b.com',
              from_display_name: 'sender',
              to_recipients: [{ email: 'x@y.com' }],
              received_date: '2026-03-08T00:00:00Z',
              body_text: 'body',
              web_link: 'https://outlook.example/item/1',
              importance: '긴급',
              category: '긴급',
            },
          };
        },
      };
    },
  }));

  await runner.fetchSelectedMailContext({
    emailId: 'mail-1',
    mailboxUser: 'dev@outlook.com',
  });

  assert.equal(rendered.length, 1);
  assert.equal(rendered[0].messageId, 'mail-1');
  assert.equal(rendered[0].subject, 'subject');
  assert.equal(rendered[0].importance, '긴급');
  assert.equal(rendered[0].category, '긴급');
});
