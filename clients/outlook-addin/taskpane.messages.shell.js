/* ========================================
   MolduBot – Taskpane Messages Shell
   ======================================== */

(function initTaskpaneMessagesShell(global) {
  function create(options) {
    var escapeHtml = options.escapeHtml;

    function iconSvg(name) {
      if (name === 'copy') {
        return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
      }
      if (name === 'up') {
        return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 10v10"/><path d="M15 5.88L14 10h5.83a2 2 0 0 1 1.92 2.56l-1.4 5A2 2 0 0 1 18.43 19H7a2 2 0 0 1-2-2v-7a2 2 0 0 1 .59-1.41l4.83-4.83A2 2 0 0 1 13.83 5z"/></svg>';
      }
      if (name === 'refresh') {
        return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15.3-6.36L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15.3 6.36L3 16"/></svg>';
      }
      if (name === 'edit') {
        return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>';
      }
      if (name === 'raw') {
        return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 4H4v4"/><path d="M16 4h4v4"/><path d="M8 20H4v-4"/><path d="M16 20h4v-4"/><path d="M9 9h6v6H9z"/></svg>';
      }
      return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 14V4"/><path d="M9 18.12L10 14H4.17a2 2 0 0 1-1.92-2.56l1.4-5A2 2 0 0 1 5.57 5H17a2 2 0 0 1 2 2v7a2 2 0 0 1-.59 1.41l-4.83 4.83A2 2 0 0 1 10.17 19z"/></svg>';
    }

    function actionsHtml(role, sentAtLabel) {
      if (role === 'user') {
        return '<div class="msg-actions user-actions"><span class="msg-meta-time">' + escapeHtml(sentAtLabel || '') + '</span><button class="msg-action-btn user-copy-btn" type="button" data-action="retry" title="다시 생성">' + iconSvg('refresh') + '</button><button class="msg-action-btn user-copy-btn" type="button" data-action="edit" title="수정">' + iconSvg('edit') + '</button><button class="msg-action-btn user-copy-btn" type="button" data-action="copy" title="복사">' + iconSvg('copy') + '</button></div>';
      }
      return '<div class="msg-actions assistant-actions"><button class="msg-action-btn" type="button" data-action="copy" title="복사">' + iconSvg('copy') + '</button><button class="msg-action-btn" type="button" data-action="raw" title="원문 보기">' + iconSvg('raw') + '</button><button class="msg-action-btn" type="button" data-action="up" title="좋아요">' + iconSvg('up') + '</button><button class="msg-action-btn" type="button" data-action="down" title="싫어요">' + iconSvg('down') + '</button></div>';
    }

    function formatMessageTime() {
      return new Intl.DateTimeFormat('ko-KR', {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
      }).format(new Date());
    }

    function buildCodeReviewQualityBar(metadata, text) {
      var quality = metadata && typeof metadata.code_review_quality === 'object'
        ? metadata.code_review_quality
        : null;
      if (!quality || !quality.enabled) return '';
      var answerText = String(text || '');
      if (answerText.indexOf('코드 리뷰') < 0 && answerText.indexOf('```') < 0) return '';
      var chips = [];
      if (quality.critic_used) chips.push('<span class="quality-badge quality-badge-critic">Critic 검증</span>');
      chips.push(
        quality.revise_applied
          ? '<span class="quality-badge quality-badge-revise">Revise 적용</span>'
          : '<span class="quality-badge quality-badge-draft">원본 유지</span>'
      );
      var sourceCount = Number(quality.web_source_count || 0);
      if (Number.isFinite(sourceCount) && sourceCount > 0) {
        chips.push('<span class="quality-badge quality-badge-source">출처 ' + escapeHtml(String(sourceCount)) + '건</span>');
      }
      return chips.length ? '<div class="quality-badge-row">' + chips.join('') + '</div>' : '';
    }

    return {
      actionsHtml: actionsHtml,
      formatMessageTime: formatMessageTime,
      buildCodeReviewQualityBar: buildCodeReviewQualityBar,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (global) {
    global.TaskpaneMessagesShell = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
