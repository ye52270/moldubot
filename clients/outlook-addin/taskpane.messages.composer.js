/* ========================================
   MolduBot – Taskpane Messages Composer
   ======================================== */

(function initTaskpaneMessagesComposer(global) {
  function create(options) {
    var escapeHtml = options.escapeHtml;
    var renderRichText = options.renderRichText;
    var renderAnswerFormatBlocks = options.renderAnswerFormatBlocks;
    var formatMessageTime = options.formatMessageTime;
    var actionsHtml = options.actionsHtml;
    var buildCodeReviewQualityBar = options.buildCodeReviewQualityBar;
    var metaRenderer = options.metaRenderer && typeof options.metaRenderer === 'object'
      ? options.metaRenderer
      : null;

    function renderAssistantBody(text, metadata) {
      var normalizedText = String(text || '');
      if (normalizedText.indexOf('```') >= 0) return renderRichText(normalizedText);
      var answerFormat = metadata && typeof metadata.answer_format === 'object' ? metadata.answer_format : null;
      var blocks = answerFormat && Array.isArray(answerFormat.blocks) ? answerFormat.blocks : [];
      var rendered = renderAnswerFormatBlocks(blocks, metadata || {});
      if (rendered) return rendered;
      if (shouldWrapCurrentMailFreeformBullets(normalizedText, metadata || {})) {
        return (
          '<section class="summary-section section-major">' +
            '<h3 class="rich-heading major-summary-heading">주요 문의사항</h3>' +
            '<div class="summary-section-body">' +
              renderRichText(normalizedText) +
            '</div>' +
          '</section>'
        );
      }
      return renderRichText(normalizedText);
    }

    function shouldWrapCurrentMailFreeformBullets(text, metadata) {
      var normalizedText = String(text || '').trim();
      if (!normalizedText) return false;
      var queryType = String(metadata && metadata.query_type ? metadata.query_type : '').trim().toLowerCase();
      var scopeLabel = String(metadata && metadata.scope_label ? metadata.scope_label : '').trim();
      var isCurrentMailScope = queryType === 'current_mail' || scopeLabel.indexOf('현재 선택 메일') >= 0;
      if (!isCurrentMailScope) return false;
      if (/^#{1,6}\s+/m.test(normalizedText)) return false;
      if (/\|.+\|/.test(normalizedText)) return false;
      if (/^\d+\.\s+/m.test(normalizedText)) return false;
      var lines = normalizedText.split('\n').map(function (line) { return String(line || '').trim(); }).filter(Boolean);
      if (!lines.length) return false;
      var bulletCount = lines.filter(function (line) { return /^[-*•]\s+/.test(line); }).length;
      return bulletCount >= 2;
    }

    function renderReplyDraftBody(text) {
      var normalized = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim();
      if (!normalized) return '';
      var paragraphs = normalized.split(/\n{2,}/).map(function (chunk) { return String(chunk || '').trim(); }).filter(Boolean);
      if (!paragraphs.length) return '';
      return paragraphs.map(function (paragraph) {
        var withBreaks = paragraph.split('\n').map(function (line) { return escapeHtml(String(line || '').trim()); }).join('<br/>');
        return '<p class="rich-paragraph">' + withBreaks + '</p>';
      }).join('');
    }

    function buildMessageHtml(role, text, metadata) {
      var safeRole = role === 'user' ? 'user' : 'assistant';
      var sentAtLabel = safeRole === 'user' ? formatMessageTime() : '';
      var data = metadata || {};
      var isReplyDraftResult = Boolean(data && data.reply_draft && data.reply_draft.enabled);
      var replyDraftRawText = (isReplyDraftResult && data.reply_draft && data.reply_draft.body)
        ? String(data.reply_draft.body || '')
        : String(text || '');
      var normalizedReplyText = (metaRenderer && typeof metaRenderer.normalizeReplyDraftBodyText === 'function')
        ? metaRenderer.normalizeReplyDraftBodyText(replyDraftRawText)
        : replyDraftRawText;
      var bodyText = isReplyDraftResult ? normalizedReplyText : String(text || '');
      var assistantBodyClass = 'msg-body rich-body';
      if (isReplyDraftResult) assistantBodyClass += ' reply-mail-body-card';
      var renderedBody = isReplyDraftResult ? renderReplyDraftBody(bodyText) : renderAssistantBody(bodyText, data);
      var assistantBodyHtml = '<div class="' + assistantBodyClass + '">' + buildCodeReviewQualityBar(data, bodyText) + renderedBody + '</div>';
      if (safeRole !== 'assistant') {
        return '<div class="message ' + safeRole + '"><div class="msg-content"><div class="msg-body">' + escapeHtml(text) + '</div>' + actionsHtml(safeRole, sentAtLabel) + '</div></div>';
      }
      var evidenceHtml = metaRenderer && metaRenderer.buildEvidenceListHtml ? metaRenderer.buildEvidenceListHtml(data) : '';
      var scopeStatusHtml = metaRenderer && metaRenderer.buildScopeStatusHtml ? metaRenderer.buildScopeStatusHtml(data) : '';
      var hitlConfirmHtml = metaRenderer && metaRenderer.buildHitlConfirmHtml ? metaRenderer.buildHitlConfirmHtml(data) : '';
      var nextActionsHtml = metaRenderer && metaRenderer.buildNextActionsHtml ? metaRenderer.buildNextActionsHtml(data) : '';
      var replyTonePickerHtml = metaRenderer && metaRenderer.buildReplyTonePickerHtml ? metaRenderer.buildReplyTonePickerHtml(data) : '';
      var replyDraftActionHtml = metaRenderer && metaRenderer.buildReplyDraftActionHtml ? metaRenderer.buildReplyDraftActionHtml(data) : '';
      var webSourcesHtml = metaRenderer && metaRenderer.buildWebSourcesHtml ? metaRenderer.buildWebSourcesHtml(data) : '';
      var actionHtml = hitlConfirmHtml + replyTonePickerHtml + replyDraftActionHtml + nextActionsHtml;
      var rawAnswer = String(data && data.raw_answer ? data.raw_answer : '').trim();
      var rawAnswerHtml = rawAnswer ? '<div class="msg-raw-answer" hidden>' + escapeHtml(rawAnswer) + '</div>' : '';
      var rawModelOutput = String(data && data.raw_model_output ? data.raw_model_output : '').trim();
      var rawModelOutputHtml = rawModelOutput
        ? '<div class="msg-raw-model-output" hidden>' + escapeHtml(rawModelOutput) + '</div>'
        : '';
      var rawModelContent = String(data && data.raw_model_content ? data.raw_model_content : '').trim();
      var rawModelContentHtml = rawModelContent
        ? '<div class="msg-raw-model-content" hidden>' + escapeHtml(rawModelContent) + '</div>'
        : '';
      var assistantContentHtml = scopeStatusHtml + assistantBodyHtml + rawAnswerHtml + rawModelOutputHtml + rawModelContentHtml + evidenceHtml + webSourcesHtml + actionHtml;
      return '<div class="message ' + safeRole + '"><div class="msg-content">' + assistantContentHtml + actionsHtml(safeRole, sentAtLabel) + '</div></div>';
    }

    return {
      buildMessageHtml: buildMessageHtml,
      renderAssistantBody: renderAssistantBody,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (global) {
    global.TaskpaneMessagesComposer = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
