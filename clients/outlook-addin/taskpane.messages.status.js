/* ========================================
   MolduBot – Taskpane Messages Status UI
   ======================================== */

(function initTaskpaneMessagesStatus(global) {
  function create(options) {
    var byId = options.byId;
    var escapeHtml = options.escapeHtml;
    var escapeAttr = options.escapeAttr || options.escapeHtml;
    var removeWelcomeStateIfExists = options.removeWelcomeStateIfExists;
    var scrollToBottom = options.scrollToBottom;
    var syncWelcomeLayoutState = options.syncWelcomeLayoutState;

    function formatElapsedLabel(elapsedMs) {
      var raw = Number(elapsedMs);
      if (!Number.isFinite(raw) || raw <= 0) return '';
      var totalSec = Math.max(1, Math.round(raw / 1000));
      var minutes = Math.floor(totalSec / 60);
      var seconds = totalSec % 60;
      if (minutes <= 0) return String(seconds) + 's';
      return String(minutes) + 'm ' + String(seconds) + 's';
    }

    function addElapsedDivider(elapsedMs) {
      var chatArea = byId('chatArea');
      if (!chatArea) return;
      var label = formatElapsedLabel(elapsedMs);
      if (!label) return;
      removeWelcomeStateIfExists();
      chatArea.insertAdjacentHTML(
        'beforeend',
        '<div class="msg-elapsed"><span class="msg-elapsed-line"></span><span class="msg-elapsed-text">' + escapeHtml(label) + '</span><span class="msg-elapsed-line"></span></div>'
      );
      scrollToBottom();
    }

    function setProgressStatus(text, phase, optionsArg) {
      var label = String(text || '').trim();
      var options = optionsArg && typeof optionsArg === 'object' ? optionsArg : {};
      var detail = typeof options.detail === 'string' ? String(options.detail).trim() : '';
      var step = Number(options.step || 0);
      var total = Number(options.total || 0);
      var safeStep = Number.isFinite(step) && step > 0 ? Math.max(1, Math.floor(step)) : 0;
      var safeTotal = Number.isFinite(total) && total > 0 ? Math.max(1, Math.floor(total)) : 0;
      var progressPercent = safeStep > 0 && safeTotal > 0
        ? Math.max(8, Math.min(100, Math.round((safeStep / safeTotal) * 100)))
        : 0;
      var chatArea = byId('chatArea');
      if (!chatArea) return;
      var existing = byId('chatProgressInline');
      if (!label) {
        if (existing) existing.remove();
        return;
      }
      var normalizedPhase = String(phase || 'processing').trim() || 'processing';
      var progressStepHtml = safeStep > 0 && safeTotal > 0
        ? '<span class="progress-inline-step">단계 ' + escapeHtml(String(safeStep)) + '/' + escapeHtml(String(safeTotal)) + '</span>'
        : '';
      var progressDetailHtml = detail
        ? '<div class="progress-inline-detail">' + escapeHtml(detail) + '</div>'
        : '';
      var progressBarHtml = progressPercent > 0
        ? '<div class="progress-inline-track" aria-hidden="true"><span class="progress-inline-fill" style="width:' + escapeAttr(String(progressPercent)) + '%"></span></div>'
        : '';
      var progressHtml = (
        '<div id="chatProgressInline" class="message assistant progress-inline-message">' +
          '<div class="msg-content">' +
            '<div class="progress-inline-label" data-phase="' + escapeAttr(normalizedPhase) + '">' +
              '<span class="progress-inline-title">' + escapeHtml(label) + '</span>' +
              progressStepHtml +
            '</div>' +
            progressDetailHtml +
            progressBarHtml +
          '</div>' +
        '</div>'
      );
      if (existing) {
        existing.outerHTML = progressHtml;
      } else {
        var userMessages = chatArea.querySelectorAll('.message.user');
        var lastUser = userMessages.length ? userMessages[userMessages.length - 1] : null;
        if (lastUser && lastUser.insertAdjacentHTML) {
          lastUser.insertAdjacentHTML('afterend', progressHtml);
        } else {
          chatArea.insertAdjacentHTML('beforeend', progressHtml);
        }
      }
      scrollToBottom();
    }

    function clearProgressStatus() {
      setProgressStatus('', '', {});
    }

    function resetSession() {
      var chatArea = byId('chatArea');
      if (!chatArea) return;
      chatArea.innerHTML = '<div id="welcomeState" class="welcome-state"><div class="welcome-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></div><h2 class="welcome-title">안녕하세요.무엇을 도와 드릴까요?</h2><p class="welcome-desc">메일 요약, 일정 등록, 회의실 예약 등 다양한 업무를 지원합니다.</p></div>';
      syncWelcomeLayoutState();
    }

    return {
      addElapsedDivider: addElapsedDivider,
      setProgressStatus: setProgressStatus,
      clearProgressStatus: clearProgressStatus,
      resetSession: resetSession,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (global) {
    global.TaskpaneMessagesStatus = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
