const test = require('node:test');
const assert = require('node:assert/strict');

const modulePath = '../clients/outlook-addin/taskpane.state.js';

function loadModule() {
  delete require.cache[require.resolve(modulePath)];
  return require(modulePath);
}

test('taskpane state filters already executed next actions', () => {
  let sending = false;
  let progress = 0;
  const moduleRef = loadModule();
  const state = moduleRef.create({
    getIsSending() { return sending; },
    setProgressShownAtMs(value) { progress = Number(value || 0); },
  });

  state.markNextActionExecuted('create_todo');
  const filtered = state.filterNextActionsMetadata({
    next_actions: [
      { action_id: 'create_todo', title: 'todo' },
      { action_id: 'search_related_mails', title: 'search' },
    ],
  });

  assert.equal(Array.isArray(filtered.next_actions), true);
  assert.equal(filtered.next_actions.length, 1);
  assert.equal(filtered.next_actions[0].action_id, 'search_related_mails');

  state.setProgressShownAtMs(1234);
  assert.equal(progress, 1234);
  sending = true;
  assert.equal(state.isSendingRef(), true);
});
