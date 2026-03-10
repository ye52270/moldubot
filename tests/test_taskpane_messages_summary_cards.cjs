const test = require('node:test');
const assert = require('node:assert/strict');

const summaryCards = require('../clients/outlook-addin/taskpane.messages.summary_cards.js');

function passthrough(value) {
  return String(value || '');
}

test('summary cards renders major summary list', () => {
  const renderer = summaryCards.create({
    escapeHtml: passthrough,
    applyInlineFormatting: passthrough,
    evidenceUi: {
      normalizeEvidenceToken: (v) => String(v || '').toLowerCase(),
      buildInlineEvidencePopover: () => '',
    },
    renderIndexedSummaryCard: ({ index, titleHtml }) => `<li>${index}:${titleHtml}</li>`,
  });
  const html = renderer.buildMajorSummaryListHtml(['A', 'B'], [], {}, 1);
  assert.match(html, /major-summary-list/);
  assert.match(html, /1:A/);
  assert.match(html, /2:B/);
});

test('summary cards renders tech issue list', () => {
  const renderer = summaryCards.create({
    escapeHtml: passthrough,
    applyInlineFormatting: passthrough,
    evidenceUi: {
      normalizeEvidenceToken: (v) => String(v || '').replace(/\s+/g, '').toLowerCase(),
      buildTechIssueDetailPopover: () => '<details>tech</details>',
    },
    renderIndexedSummaryCard: ({ index, titleHtml }) => `<li>${index}:${titleHtml}</li>`,
  });
  const metadata = {
    context_enrichment: {
      tech_issue_clusters: [{ summary: 'api 오류', keywords: ['api'], issue_type: 'integration', related_mails: [{ message_id: 'm1' }] }],
    },
  };
  const html = renderer.buildTechIssueListHtml(['api 오류'], metadata, 1);
  assert.match(html, /tech-issue-list/);
  assert.match(html, /1:api 오류/);
});
