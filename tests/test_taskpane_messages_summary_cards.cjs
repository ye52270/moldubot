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

test('summary cards links external summary title to web source url', () => {
  const renderer = summaryCards.create({
    escapeHtml: passthrough,
    escapeAttr: passthrough,
    applyInlineFormatting: passthrough,
    evidenceUi: {
      normalizeEvidenceToken: (v) => String(v || '').replace(/\s+/g, '').toLowerCase(),
      buildInlineEvidencePopover: () => '',
    },
    renderIndexedSummaryCard: ({ index, titleHtml }) => `<li>${index}:${titleHtml}</li>`,
  });
  const html = renderer.buildMajorSummaryListHtml(
    ['Microsoft Learn - LDAP Signing (learn.microsoft.com)'],
    [],
    {
      web_sources: [
        {
          title: 'Microsoft Learn - LDAP Signing',
          site_name: 'learn.microsoft.com',
          url: 'https://learn.microsoft.com/test',
        },
      ],
    },
    1
  );
  assert.match(html, /major-summary-link/);
  assert.match(html, /href="https:\/\/learn\.microsoft\.com\/test"/);
  assert.match(html, /target="_blank"/);
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
