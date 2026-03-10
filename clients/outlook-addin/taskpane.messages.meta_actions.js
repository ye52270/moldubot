/* ========================================
   MolduBot – Taskpane Messages Meta Actions
   ======================================== */

(function initTaskpaneMessagesMetaActions(global) {
  function create(options) {
    var escapeHtml = options.escapeHtml;
    var escapeAttr = options.escapeAttr || options.escapeHtml;

    function normalizeSourceSnippet(rawSnippet) {
      var text = String(rawSnippet || '').replace(/\s+/g, ' ').trim();
      if (!text) return '';
      return text.length > 180 ? (text.slice(0, 177) + '...') : text;
    }

    function resolveHitlActionTitle(actionName) {
      var normalized = String(actionName || '').trim();
      if (normalized === 'book_meeting_room') return '회의실 예약 실행';
      if (normalized === 'create_outlook_todo') return 'Outlook 할 일 등록';
      return normalized ? ('실행 승인: ' + normalized) : '실행 승인';
    }

    function buildHitlActionSummary(actionName, args) {
      var normalized = String(actionName || '').trim();
      var payload = args && typeof args === 'object' ? args : {};
      if (normalized === 'book_meeting_room') {
        return [
          String(payload.date || '').trim(),
          String(payload.start_time || '').trim() + '~' + String(payload.end_time || '').trim(),
          String(payload.building || '').trim() + ' ' + String(payload.floor || '') + '층 ' + String(payload.room_name || '').trim(),
        ].filter(function (v) { return Boolean(v && !/^~$/.test(v)); }).join(' | ');
      }
      if (normalized === 'create_outlook_todo') {
        return String(payload.title || '').trim() + ' (마감: ' + String(payload.due_date || '').trim() + ')';
      }
      return '';
    }

    function buildHitlConfirmHtml(metadata) {
      var confirm = metadata && metadata.confirm && typeof metadata.confirm === 'object' ? metadata.confirm : null;
      if (!confirm || !confirm.required) return '';
      var actions = Array.isArray(confirm.actions) ? confirm.actions : [];
      if (!actions.length) return '';
      var firstAction = actions[0] && typeof actions[0] === 'object' ? actions[0] : {};
      var actionName = String(firstAction.name || '').trim();
      var args = firstAction && typeof firstAction.args === 'object' ? firstAction.args : {};
      var summary = buildHitlActionSummary(actionName, args);
      var description = String(firstAction.description || '').trim() || '실행 전 승인 확인이 필요합니다.';
      var threadId = String(confirm.thread_id || '').trim();
      var confirmToken = String(confirm.confirm_token || '').trim();
      var promptVariant = String(confirm.prompt_variant || '').trim();
      return (
        '<div class="hitl-confirm-block">' +
          '<div class="hitl-confirm-badge">실행 승인 필요</div>' +
          '<div class="hitl-confirm-title">' + escapeHtml(resolveHitlActionTitle(actionName)) + '</div>' +
          '<div class="hitl-confirm-desc">' + escapeHtml(summary || description) + '</div>' +
          '<div class="hitl-confirm-progress" data-role="hitl-confirm-progress" hidden></div>' +
          '<div class="hitl-confirm-actions">' +
            '<button type="button" class="hitl-action-btn approve" data-action="hitl-confirm-approve" data-thread-id="' + escapeAttr(threadId) + '" data-confirm-token="' + escapeAttr(confirmToken) + '" data-prompt-variant="' + escapeAttr(promptVariant) + '" data-hitl-action-name="' + escapeAttr(actionName) + '">승인</button>' +
            '<button type="button" class="hitl-action-btn reject" data-action="hitl-confirm-reject" data-thread-id="' + escapeAttr(threadId) + '" data-confirm-token="' + escapeAttr(confirmToken) + '" data-prompt-variant="' + escapeAttr(promptVariant) + '" data-hitl-action-name="' + escapeAttr(actionName) + '">거절</button>' +
          '</div>' +
        '</div>'
      );
    }

    function buildNextActionsHtml(metadata) {
      var actions = metadata && Array.isArray(metadata.next_actions) ? metadata.next_actions : [];
      if (!actions.length) return '';
      var actionButtons = actions.map(function (item) {
        var action = item && typeof item === 'object' ? item : {};
        var title = String(action.title || '').trim();
        var description = String(action.description || '').trim();
        var query = String(action.query || '').trim();
        var actionId = String(action.action_id || '').trim();
        var priority = String(action.priority || 'medium').trim().toLowerCase();
        if (!query) return '';
        var safePriority = (priority === 'high' || priority === 'low') ? priority : 'medium';
        return (
          '<button type="button" class="next-action-btn priority-' + escapeAttr(safePriority) + '" ' +
          'data-action="next-action-run" data-query="' + escapeAttr(query) + '" data-title="' + escapeAttr(title || query) + '" data-action-id="' + escapeAttr(actionId) + '">' +
          '<span class="next-action-main"><span class="next-action-title">' + escapeHtml(title || query) + '</span><span class="next-action-arrow" aria-hidden="true">→</span></span>' +
          (description ? '<span class="next-action-desc">' + escapeHtml(description) + '</span>' : '') +
          '</button>'
        );
      }).filter(function (value) { return Boolean(value); }).join('');
      if (!actionButtons) return '';
      return '<div class="next-actions-block"><div class="next-actions-title">💡 이어서 할 수 있어요</div><div class="next-actions-subtitle">지금 결과를 바탕으로 바로 실행할 수 있는 작업입니다.</div><div class="next-actions-list">' + actionButtons + '</div></div>';
    }

    function buildReplyDraftActionHtml(metadata, normalizeReplyDraftBodyText) {
      var draft = metadata && metadata.reply_draft && typeof metadata.reply_draft === 'object' ? metadata.reply_draft : null;
      if (!draft || !draft.enabled) return '';
      var body = normalizeReplyDraftBodyText(String(draft.body || ''));
      if (!body) return '';
      var label = String(draft.button_label || '').trim() || '답변 메일 보내기';
      return (
        '<div class="reply-draft-action-block" data-role="reply-draft-block">' +
          '<button type="button" class="reply-draft-open-btn" data-action="reply-draft-open" data-draft-body="' + escapeAttr(body) + '">' + escapeHtml(label) + '</button>' +
        '</div>'
      );
    }

    function buildReplyTonePickerHtml(metadata) {
      var picker = metadata && metadata.reply_tone_picker && typeof metadata.reply_tone_picker === 'object'
        ? metadata.reply_tone_picker
        : null;
      if (!picker || !picker.enabled) return '';
      var baseQuery = String(picker.base_query || '').trim();
      if (!baseQuery) return '';
      return (
        '<div class="reply-tone-picker-block">' +
          '<div class="reply-tone-picker-title">회신 톤을 먼저 선택해 주세요.</div>' +
          '<div class="reply-tone-picker-subtitle">선택한 톤으로 초안을 생성한 뒤, 답변 메일 보내기 버튼이 노출됩니다.</div>' +
          '<div class="reply-tone-picker-row" role="group" aria-label="회신 톤 선택">' +
            '<button type="button" class="reply-tone-picker-btn" data-action="reply-tone-generate" data-tone="neutral" data-base-query="' + escapeAttr(baseQuery) + '">기본</button>' +
            '<button type="button" class="reply-tone-picker-btn" data-action="reply-tone-generate" data-tone="formal" data-base-query="' + escapeAttr(baseQuery) + '">공손</button>' +
            '<button type="button" class="reply-tone-picker-btn" data-action="reply-tone-generate" data-tone="concise" data-base-query="' + escapeAttr(baseQuery) + '">간결</button>' +
          '</div>' +
        '</div>'
      );
    }

    function buildWebSourcesHtml(metadata) {
      var sources = metadata && Array.isArray(metadata.web_sources) ? metadata.web_sources : [];
      if (!sources.length) return '';
      var iconStack = sources.slice(0, 4).map(function (item, index) {
        var source = item && typeof item === 'object' ? item : {};
        var iconText = String(source.icon_text || source.site_name || '•').trim().slice(0, 1).toUpperCase() || '•';
        var faviconUrl = String(source.favicon_url || '').trim();
        var iconInner = faviconUrl
          ? '<img class="web-source-icon-img" src="' + escapeAttr(faviconUrl) + '" alt="" loading="lazy" />'
          : escapeHtml(iconText);
        return '<span class="web-source-icon" style="--stack-index:' + String(index) + '">' + iconInner + '</span>';
      }).join('');
      var sourceItems = sources.map(function (item) {
        var source = item && typeof item === 'object' ? item : {};
        var siteName = String(source.site_name || '').trim() || '출처';
        var title = String(source.title || '').trim() || '제목 없음';
        var snippet = normalizeSourceSnippet(source.snippet || '');
        var url = String(source.url || '').trim();
        if (!url) return '';
        return '<li class="web-source-item"><a class="web-source-link" href="' + escapeAttr(url) + '" target="_blank" rel="noopener noreferrer"><span class="web-source-site">' + escapeHtml(siteName) + '</span><span class="web-source-title">' + escapeHtml(title) + '</span>' + (snippet ? '<span class="web-source-snippet">' + escapeHtml(snippet) + '</span>' : '') + '</a></li>';
      }).filter(function (value) { return Boolean(value); }).join('');
      if (!sourceItems) return '';
      return '<details class="web-source-popover"><summary class="web-source-trigger"><span class="web-source-stack">' + iconStack + '</span><span class="web-source-label">출처</span></summary><div class="web-source-panel"><div class="web-source-panel-title">출처</div><ul class="web-source-list">' + sourceItems + '</ul></div></details>';
    }

    return {
      buildHitlConfirmHtml: buildHitlConfirmHtml,
      buildNextActionsHtml: buildNextActionsHtml,
      buildReplyTonePickerHtml: buildReplyTonePickerHtml,
      buildReplyDraftActionHtml: buildReplyDraftActionHtml,
      buildWebSourcesHtml: buildWebSourcesHtml,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (global) {
    global.TaskpaneMessagesMetaActions = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
