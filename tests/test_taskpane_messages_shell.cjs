const test = require('node:test');
const assert = require('node:assert/strict');

const shell = require('../clients/outlook-addin/taskpane.messages.shell.js');

function passthrough(value) {
  return String(value || '');
}

test('messages shell renders actions html for user and assistant', () => {
  const renderer = shell.create({ escapeHtml: passthrough });
  const userHtml = renderer.actionsHtml('user', '오전 9:00');
  const assistantHtml = renderer.actionsHtml('assistant', '');
  assert.match(userHtml, /data-action="retry"/);
  assert.match(userHtml, /오전 9:00/);
  assert.match(assistantHtml, /data-action="up"/);
  assert.match(assistantHtml, /data-action="raw"/);
});

test('messages shell renders quality badge row', () => {
  const renderer = shell.create({ escapeHtml: passthrough });
  const html = renderer.buildCodeReviewQualityBar(
    { code_review_quality: { enabled: true, critic_used: true, revise_applied: true, web_source_count: 2 } },
    '코드 리뷰 결과',
  );
  assert.match(html, /quality-badge-row/);
  assert.match(html, /Critic 검증/);
  assert.match(html, /출처 2건/);
});
