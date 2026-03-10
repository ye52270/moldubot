const test = require('node:test');
const assert = require('node:assert/strict');

const uiCommon = require('../clients/outlook-addin/taskpane.messages.ui_common.js');

test('ui common renders evidence trigger icon html', () => {
  const renderer = uiCommon.create({
    escapeHtml: (v) => String(v || ''),
    escapeAttr: (v) => String(v || ''),
  });
  const html = renderer.evidenceTriggerIconHtml();
  assert.match(html, /inline-evidence-trigger-icon/);
  assert.match(html, /<svg/);
});

test('ui common renders indexed summary card', () => {
  const renderer = uiCommon.create({
    escapeHtml: (v) => String(v || ''),
    escapeAttr: (v) => String(v || ''),
  });
  const html = renderer.renderIndexedSummaryCard({
    index: 3,
    titleHtml: '타이틀',
    subtitleHtml: '요약',
  });
  assert.match(html, /major-summary-card/);
  assert.match(html, />3</);
  assert.match(html, /타이틀/);
});
