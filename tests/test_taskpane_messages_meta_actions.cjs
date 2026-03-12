const test = require('node:test');
const assert = require('node:assert/strict');

const metaActions = require('../clients/outlook-addin/taskpane.messages.meta_actions.js');

function passthrough(value) {
  return String(value || '');
}

test('meta actions renders HIL confirm block', () => {
  const renderer = metaActions.create({
    escapeHtml: passthrough,
    escapeAttr: passthrough,
  });
  const html = renderer.buildHitlConfirmHtml({
    confirm: {
      required: true,
      thread_id: 't1',
      confirm_token: 'c1',
      prompt_variant: 'quality_structured',
      actions: [{ name: 'create_outlook_todo', args: { title: '테스트', due_date: '2026-03-10' } }],
    },
  });
  assert.match(html, /실행 승인 필요/);
  assert.match(html, /Outlook 할 일 등록/);
  assert.match(html, /hitl-confirm-approve/);
  assert.match(html, /data-prompt-variant="quality_structured"/);
});

test('meta actions exposes next action renderer', () => {
  const renderer = metaActions.create({
    escapeHtml: passthrough,
    escapeAttr: passthrough,
  });
  assert.equal(typeof renderer.buildNextActionsHtml, 'function');
});
