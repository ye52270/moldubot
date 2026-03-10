const test = require('node:test');
const assert = require('node:assert/strict');

const messagesModulePath = '../clients/outlook-addin/taskpane.messages.js';

function loadMessagesModule() {
  global.window = {};
  delete require.cache[require.resolve(messagesModulePath)];
  return require(messagesModulePath);
}

test('taskpane messages shows clarification toast outside assistant card', () => {
  const moduleRef = loadMessagesModule();
  const toastHost = { innerHTML: '', hidden: true };
  const instance = moduleRef.create({
    byId: (id) => (id === 'clarificationToastHost' ? toastHost : null),
    escapeHtml: (value) => String(value || ''),
  });

  instance.showClarificationToast({
    clarification: {
      required: true,
      question: '범위를 선택해 주세요.',
      original_query: '문제가 되는 메일주소가 뭐야?',
      options: [{ scope: 'current_mail', label: '현재 메일', description: '현재 선택 메일만' }],
    },
  });

  assert.equal(toastHost.hidden, false);
  assert.match(toastHost.innerHTML, /scope-clarification-block/);
  assert.match(toastHost.innerHTML, /범위를 선택해 주세요/);
});

test('taskpane messages clears clarification toast when metadata has no clarification', () => {
  const moduleRef = loadMessagesModule();
  const toastHost = { innerHTML: '<div>filled</div>', hidden: false };
  const instance = moduleRef.create({
    byId: (id) => (id === 'clarificationToastHost' ? toastHost : null),
    escapeHtml: (value) => String(value || ''),
  });

  instance.showClarificationToast({});
  assert.equal(toastHost.hidden, true);
  assert.equal(toastHost.innerHTML, '');

  toastHost.innerHTML = '<div>filled</div>';
  toastHost.hidden = false;
  instance.clearClarificationToast();
  assert.equal(toastHost.hidden, true);
  assert.equal(toastHost.innerHTML, '');
});
