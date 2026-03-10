const test = require('node:test');
const assert = require('node:assert/strict');

const evidenceUi = require('../clients/outlook-addin/taskpane.messages.evidence_ui.js');

function passthrough(value) {
  return String(value || '');
}

test('evidence ui normalizes tokens and resolves point evidence', () => {
  const renderer = evidenceUi.create({
    escapeHtml: passthrough,
    escapeAttr: passthrough,
  });
  const row = renderer.resolveMajorPointEvidence(
    { major_point_evidence: [{ point: 'Cloud PC API 오류', message_id: 'm1' }] },
    'cloud pc api',
    null,
  );
  assert.equal(renderer.normalizeEvidenceToken('Cloud PC API'), 'cloudpcapi');
  assert.ok(row);
  assert.equal(row.point, 'Cloud PC API 오류');
});

test('evidence ui builds evidence list and tech detail popover', () => {
  const renderer = evidenceUi.create({
    escapeHtml: passthrough,
    escapeAttr: passthrough,
    uiCommon: { evidenceTriggerIconHtml: () => '<i>+</i>' },
  });
  const listHtml = renderer.buildInlineEvidenceListHtml([
    { message_id: 'm1', web_link: 'https://x', subject: '메일1', received_date: '2026-03-07', sender_names: '홍길동', snippet: '요약' },
  ]);
  assert.match(listHtml, /inline-evidence-list/);
  assert.match(listHtml, /메일1/);

  const popoverHtml = renderer.buildTechIssueDetailPopover({
    related_mails: [{ message_id: 'm1', web_link: 'https://x', subject: '근거메일' }],
  });
  assert.match(popoverHtml, /기술 근거 상세/);
  assert.match(popoverHtml, /근거메일/);
});
