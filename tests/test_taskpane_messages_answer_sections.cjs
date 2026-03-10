const test = require('node:test');
const assert = require('node:assert/strict');

const answerSections = require('../clients/outlook-addin/taskpane.messages.answer_sections.js');

function passthrough(value) {
  return String(value || '');
}

test('answer sections resolves section key and executive heading', () => {
  const renderer = answerSections.create({
    escapeAttr: passthrough,
    applyInlineFormatting: passthrough,
    buildInlineEvidencePopover: () => '',
  });
  assert.equal(renderer.resolveSummarySectionKey('### 📌 주요 내용'), 'major');
  assert.equal(renderer.resolveSummarySectionKey('### 🛠 기술 이슈'), 'tech-issue');
  assert.equal(renderer.isExecutiveBriefHeading('핵심 이슈 요약'), true);
});

test('answer sections builds executive brief html with severity', () => {
  const renderer = answerSections.create({
    escapeAttr: passthrough,
    applyInlineFormatting: passthrough,
    buildInlineEvidencePopover: () => '<span>evidence</span>',
  });
  const html = renderer.buildExecutiveBriefHtml('긴급 점검 필요', {});
  assert.match(html, /executive-brief-card/);
  assert.match(html, /tone-high/);
  assert.match(html, /evidence/);
});
