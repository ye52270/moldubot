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

test('meta actions renders next action and web sources block', () => {
  const renderer = metaActions.create({
    escapeHtml: passthrough,
    escapeAttr: passthrough,
  });
  const actionsHtml = renderer.buildNextActionsHtml({
    next_actions: [{ title: '추가 조회', query: '관련 메일 조회', action_id: 'a1', priority: 'high' }],
  });
  assert.match(actionsHtml, /next-action-btn/);
  assert.match(actionsHtml, /priority-high/);

  const sourcesHtml = renderer.buildWebSourcesHtml({
    web_sources: [{ site_name: 'OpenAI', title: 'Docs', url: 'https://example.com', snippet: 's' }],
  });
  assert.match(sourcesHtml, /web-source-popover/);
  assert.match(sourcesHtml, /OpenAI/);
});

test('meta actions normalizes long source snippet', () => {
  const renderer = metaActions.create({
    escapeHtml: passthrough,
    escapeAttr: passthrough,
  });
  const longSnippet = 'a'.repeat(220);
  const sourcesHtml = renderer.buildWebSourcesHtml({
    web_sources: [{ site_name: 'AWS', title: 'Aurora', url: 'https://aws.amazon.com', snippet: longSnippet }],
  });
  assert.match(sourcesHtml, /web-source-snippet/);
  assert.equal(sourcesHtml.includes('a'.repeat(200)), false);
  assert.equal(sourcesHtml.includes('...'), true);
});
