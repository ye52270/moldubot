/* ========================================
   MolduBot – Taskpane Messages Meta Actions
   ======================================== */

(function initTaskpaneMessagesMetaActions(global) {
  function create(options) {
    var escapeHtml = options.escapeHtml;
    var escapeAttr = options.escapeAttr || options.escapeHtml;

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

    function buildNextActionsHtml(metadata) {
      var source = metadata && typeof metadata === 'object' ? metadata : {};
      var replyDraft = source.reply_draft && typeof source.reply_draft === 'object' ? source.reply_draft : null;
      if (replyDraft && replyDraft.enabled) return '';
      var items = Array.isArray(source.next_actions) ? source.next_actions : [];
      if (!items.length) return '';
      var rows = items.slice(0, 3).map(function (item, index) {
        var action = item && typeof item === 'object' ? item : {};
        var actionId = String(action.action_id || '').trim();
        var title = String(action.title || '').trim();
        var query = String(action.query || '').trim();
        if (!title || !query) return '';
        var description = String(action.description || '').trim();
        var priority = String(action.priority || '').trim().toLowerCase();
        var priorityClass = priority === 'high' ? ' priority-high' : (priority === 'low' ? ' priority-low' : '');
        return (
          '<button type="button" class="next-action-btn' + priorityClass + '" ' +
            'data-action="next-action-run" ' +
            'data-action-id="' + escapeAttr(actionId) + '" ' +
            'data-title="' + escapeAttr(title) + '" ' +
            'data-query="' + escapeAttr(query) + '">' +
            '<span class="next-action-main">' +
              '<span class="next-action-title">' + escapeHtml(title) + '</span>' +
              '<span class="next-action-arrow">→</span>' +
            '</span>' +
            (description ? '<span class="next-action-desc">' + escapeHtml(description) + '</span>' : '') +
          '</button>'
        );
      }).filter(function (row) { return Boolean(row); }).join('');
      if (!rows) return '';
      return (
        '<div class="next-actions-block">' +
          '<div class="next-actions-title">이어서 할 수 있어요</div>' +
          '<div class="next-actions-subtitle">지금 결과를 바탕으로 바로 실행할 수 있는 작업입니다.</div>' +
          '<div class="next-actions-list">' + rows + '</div>' +
        '</div>'
      );
    }

    return {
      buildHitlConfirmHtml: buildHitlConfirmHtml,
      buildReplyTonePickerHtml: buildReplyTonePickerHtml,
      buildReplyDraftActionHtml: buildReplyDraftActionHtml,
      buildNextActionsHtml: buildNextActionsHtml,
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
