const test = require('node:test');
const assert = require('node:assert/strict');

const composer = require('../clients/outlook-addin/taskpane.messages.composer.js');

function passthrough(value) {
  return String(value || '');
}

test('composer builds user message html with actions', () => {
  const renderer = composer.create({
    escapeHtml: passthrough,
    renderRichText: passthrough,
    renderAnswerFormatBlocks: () => '',
    formatMessageTime: () => '오전 10:00',
    actionsHtml: () => '<div class="actions"></div>',
    buildCodeReviewQualityBar: () => '',
    metaRenderer: {},
  });
  const html = renderer.buildMessageHtml('user', '테스트', {});
  assert.match(html, /message user/);
  assert.match(html, /테스트/);
  assert.match(html, /actions/);
});

test('composer builds assistant message html with metadata blocks', () => {
  const renderer = composer.create({
    escapeHtml: passthrough,
    renderRichText: (v) => '<p>' + passthrough(v) + '</p>',
    renderAnswerFormatBlocks: () => '<section>fmt</section>',
    formatMessageTime: () => '',
    actionsHtml: () => '<div class="assistant-actions"></div>',
    buildCodeReviewQualityBar: () => '<div class="quality"></div>',
    metaRenderer: {
      buildEvidenceListHtml: () => '<div class="evidence"></div>',
      buildScopeClarificationHtml: () => '<div class="clarification"></div>',
      buildHitlConfirmHtml: () => '<div class="hitl"></div>',
      buildNextActionsHtml: () => '<div class="next"></div>',
      buildReplyTonePickerHtml: () => '<div class="tone"></div>',
      buildReplyDraftActionHtml: () => '<div class="draft"></div>',
      buildWebSourcesHtml: () => '<div class="source"></div>',
      normalizeReplyDraftBodyText: (v) => passthrough(v),
    },
  });
  const html = renderer.buildMessageHtml('assistant', '내용', { reply_draft: { enabled: true } });
  assert.match(html, /message assistant/);
  assert.match(html, /quality/);
  assert.match(html, /evidence/);
  assert.match(html, /source/);
  assert.doesNotMatch(html, /clarification/);
});

test('composer embeds hidden raw answer payload for assistant cards', () => {
  const renderer = composer.create({
    escapeHtml: passthrough,
    renderRichText: (v) => '<p>' + passthrough(v) + '</p>',
    renderAnswerFormatBlocks: () => '<section>fmt</section>',
    formatMessageTime: () => '',
    actionsHtml: () => '<div class="assistant-actions"></div>',
    buildCodeReviewQualityBar: () => '',
    metaRenderer: {},
  });
  const html = renderer.buildMessageHtml('assistant', '가공 답변', { raw_answer: 'LLM 원문 텍스트' });
  assert.match(html, /msg-raw-answer/);
  assert.match(html, /LLM 원문 텍스트/);
});

test('composer embeds hidden raw model output payload for assistant cards', () => {
  const renderer = composer.create({
    escapeHtml: passthrough,
    renderRichText: (v) => '<p>' + passthrough(v) + '</p>',
    renderAnswerFormatBlocks: () => '<section>fmt</section>',
    formatMessageTime: () => '',
    actionsHtml: () => '<div class="assistant-actions"></div>',
    buildCodeReviewQualityBar: () => '',
    metaRenderer: {},
  });
  const html = renderer.buildMessageHtml('assistant', '가공 답변', { raw_model_output: '모델 직출력 텍스트' });
  assert.match(html, /msg-raw-model-output/);
  assert.match(html, /모델 직출력 텍스트/);
});

test('composer embeds hidden raw model content payload for assistant cards', () => {
  const renderer = composer.create({
    escapeHtml: passthrough,
    renderRichText: (v) => '<p>' + passthrough(v) + '</p>',
    renderAnswerFormatBlocks: () => '<section>fmt</section>',
    formatMessageTime: () => '',
    actionsHtml: () => '<div class="assistant-actions"></div>',
    buildCodeReviewQualityBar: () => '',
    metaRenderer: {},
  });
  const html = renderer.buildMessageHtml('assistant', '가공 답변', { raw_model_content: '{\"type\":\"text\"}' });
  assert.match(html, /msg-raw-model-content/);
  assert.match(html, /\"type\":\"text\"/);
});
