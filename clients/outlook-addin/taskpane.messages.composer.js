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
      var renderMode = String(metadata && metadata.ui_render_mode ? metadata.ui_render_mode : '').trim().toLowerCase();
      if (renderMode === 'plain_lists') return false;
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

    function buildWebSourcePopoverHtml(metadata) {
      var data = metadata && typeof metadata === 'object' ? metadata : {};
      var sources = Array.isArray(data.web_sources) ? data.web_sources : [];
      if (!sources.length) return '';
      var previewIcons = sources.slice(0, 3).map(function (item, index) {
        var source = item && typeof item === 'object' ? item : {};
        var faviconUrl = String(source.favicon_url || '').trim();
        var iconText = String(source.icon_text || source.site_name || '?').trim().slice(0, 1).toUpperCase() || '?';
        var stackIndex = String(index + 1);
        if (faviconUrl) {
          return (
            '<span class="web-source-icon" style="--stack-index:' + stackIndex + '">' +
              '<img class="web-source-icon-img" src="' + escapeHtml(faviconUrl) + '" alt="" loading="lazy" referrerpolicy="no-referrer" />' +
            '</span>'
          );
        }
        return '<span class="web-source-icon" style="--stack-index:' + stackIndex + '">' + escapeHtml(iconText) + '</span>';
      }).join('');
      var sourceRows = sources.slice(0, 5).map(function (item) {
        var source = item && typeof item === 'object' ? item : {};
        var title = String(source.title || '').trim() || '제목 없음';
        var siteName = String(source.site_name || '').trim() || '-';
        var snippet = String(source.snippet || '').trim();
        var url = String(source.url || '').trim();
        if (!url) return '';
        var shortUrl = url.length > 90 ? (url.slice(0, 87) + '...') : url;
        return (
          '<li class="web-source-item">' +
            '<a class="web-source-link" href="' + escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">' +
              '<span class="web-source-site">' + escapeHtml(siteName) + '</span>' +
              '<span class="web-source-title">' + escapeHtml(title) + '</span>' +
              '<span class="web-source-snippet">' + escapeHtml(shortUrl) + '</span>' +
              (snippet ? '<span class="web-source-snippet">' + escapeHtml(snippet) + '</span>' : '') +
            '</a>' +
          '</li>'
        );
      }).filter(function (row) { return Boolean(row); }).join('');
      if (!sourceRows) return '';
      return (
        '<details class="web-source-popover">' +
          '<summary class="web-source-trigger" title="외부 출처 보기" aria-label="외부 출처 보기">' +
            '<span class="web-source-stack">' + previewIcons + '</span>' +
            '<span class="web-source-label">출처 ' + escapeHtml(String(sources.length)) + '건</span>' +
          '</summary>' +
          '<div class="web-source-panel">' +
            '<div class="web-source-panel-title">외부 검색 출처</div>' +
            '<ul class="web-source-list">' + sourceRows + '</ul>' +
          '</div>' +
        '</details>'
      );
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
      var webSourcePopoverHtml = buildWebSourcePopoverHtml(data);
      var assistantBodyHtml = '<div class="' + assistantBodyClass + '">' + buildCodeReviewQualityBar(data, bodyText) + renderedBody + webSourcePopoverHtml + '</div>';
      if (safeRole !== 'assistant') {
        return '<div class="message ' + safeRole + '"><div class="msg-content"><div class="msg-body">' + escapeHtml(text) + '</div>' + actionsHtml(safeRole, sentAtLabel) + '</div></div>';
      }
      var hitlConfirmHtml = metaRenderer && metaRenderer.buildHitlConfirmHtml ? metaRenderer.buildHitlConfirmHtml(data) : '';
      var replyTonePickerHtml = metaRenderer && metaRenderer.buildReplyTonePickerHtml ? metaRenderer.buildReplyTonePickerHtml(data) : '';
      var replyDraftActionHtml = metaRenderer && metaRenderer.buildReplyDraftActionHtml ? metaRenderer.buildReplyDraftActionHtml(data) : '';
      var nextActionsHtml = metaRenderer && metaRenderer.buildNextActionsHtml ? metaRenderer.buildNextActionsHtml(data) : '';
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
      var assistantContentHtml = assistantBodyHtml + rawAnswerHtml + rawModelOutputHtml + rawModelContentHtml + actionHtml;
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
