(function initTaskpaneMessagesReportCards(global) {
  var cardDomApi = global.TaskpaneMessagesCardDom || null;
  if (!cardDomApi && typeof module !== 'undefined' && module.exports && typeof require === 'function') {
    try {
      cardDomApi = require('./taskpane.messages.card_dom.js');
    } catch (error) {
      cardDomApi = null;
    }
  }

  function create(options) {
    var byId = options.byId;
    var escapeHtml = options.escapeHtml;
    var escapeAttr = options.escapeAttr;
    var scrollToBottom = options.scrollToBottom;
    var removeWelcomeStateIfExists = options.removeWelcomeStateIfExists;

    var cardDom = cardDomApi && typeof cardDomApi.create === 'function'
      ? cardDomApi.create({ byId: byId })
      : null;
    if (!cardDom) return {};

    function appendReadyCard(chatArea, titleHtml, subtitleHtml, actionHtml) {
      cardDom.appendAssistantCard(
        chatArea,
        'report-ready-message',
        'report-ready-card',
        '<div class="report-file-card">' +
          '<div class="report-file-thumb" aria-hidden="true"><span class="report-doc-icon"></span></div>' +
          '<div class="report-file-meta">' +
            titleHtml +
            subtitleHtml +
          '</div>' +
          (actionHtml ? ('<div class="report-file-actions">' + actionHtml + '</div>') : '') +
        '</div>'
      );
    }

    function ensureReportProgressCard() {
      return cardDom.withChatArea(function (chatArea) {
        removeWelcomeStateIfExists();
        var existing = byId('reportProgressCard');
        if (existing) return existing;
        chatArea.insertAdjacentHTML(
          'beforeend',
          '<div id="reportProgressCard" class="message assistant report-progress-message">' +
            '<div class="msg-content report-progress-card">' +
              '<div class="report-progress-title">보고서 생성중입니다...</div>' +
              '<div class="report-step-list">' +
                '<div class="report-step-item" data-step-id="1">⏳ Step 1 이메일 분석</div>' +
                '<div class="report-step-item" data-step-id="2">⏳ Step 2 핵심 내용 정리</div>' +
                '<div class="report-step-item" data-step-id="3">⏳ Step 3 보고서 작성</div>' +
                '<div class="report-step-item" data-step-id="DONE">⏳ Step 4 DOCX 변환</div>' +
              '</div>' +
            '</div>' +
          '</div>'
        );
        scrollToBottom();
        return byId('reportProgressCard');
      });
    }

    function updateReportStep(step, status, label) {
      var card = ensureReportProgressCard();
      if (!card) return;
      var target = card.querySelector('[data-step-id="' + String(step || '') + '"]');
      if (!target) return;
      target.classList.remove('running', 'done');
      if (status === 'running') {
        target.classList.add('running');
        target.textContent = '진행 Step ' + (step === 'DONE' ? '4' : String(step || '')) + ' ' + String(label || '');
      } else if (status === 'done') {
        target.classList.add('done');
        target.textContent = '완료 Step ' + (step === 'DONE' ? '4' : String(step || '')) + ' ' + String(label || '완료');
      }
      scrollToBottom();
    }

    function removeReportTransientCards() {
      var chatArea = cardDom.getChatArea();
      if (!chatArea || !chatArea.querySelectorAll) return;
      cardDom.removeCardsBySelector('.report-confirm-message, .report-progress-message');
    }

    function buildReportPreviewUrl(docxUrl) {
      var raw = String(docxUrl || '').trim();
      var matched = /\/report\/download\/([^/?#]+)/.exec(raw);
      if (!matched) return '';
      return '/report/preview/' + String(matched[1] || '');
    }

    function addReportReadyCard(docxUrl, previewUrl, reportTitle) {
      cardDom.withChatArea(function (chatArea) {
        var safeDocxUrl = String(docxUrl || '').trim();
        var resolvedPreviewUrl = String(previewUrl || '').trim() || buildReportPreviewUrl(safeDocxUrl);
        var safeReportTitle = String(reportTitle || '').trim() || '보고서가 생성되었습니다.';
        appendReadyCard(
          chatArea,
          '<div class="report-file-title">' + escapeHtml(safeReportTitle) + '</div>',
          '<div class="report-file-subtitle">문서 · docx</div>',
          '<button type="button" class="report-open-btn report-file-open-btn" ' +
            'data-action="report-open-file" ' +
            'data-preview-url="' + escapeAttr(resolvedPreviewUrl) + '" ' +
            'data-docx-url="' + escapeAttr(safeDocxUrl) + '">' +
            '<span class="report-file-open-label">미리보기</span>' +
          '</button>'
        );
      });
    }

    function completeReportProgress(docxUrl, previewUrl, reportTitle) {
      var card = ensureReportProgressCard();
      if (!card) return;
      removeReportTransientCards();
      addReportReadyCard(docxUrl, previewUrl, reportTitle);
      scrollToBottom();
    }

    function addMeetingBookingReadyCard(answerText, eventId) {
      cardDom.withChatArea(function (chatArea) {
        var safeText = String(answerText || '').trim() || '회의실 예약이 완료되었습니다.';
        var safeEventId = String(eventId || '').trim();
        appendReadyCard(
          chatArea,
          '<div class="report-file-title">' + escapeHtml(safeText) + '</div>',
          '<div class="report-file-subtitle">캘린더 일정</div>',
          '<button type="button" class="report-open-btn report-file-open-btn" data-action="meeting-open-event" data-event-id="' +
            escapeAttr(safeEventId) + '">' +
            '<span class="report-file-open-label">일정 열기</span>' +
          '</button>'
        );
        scrollToBottom();
      });
    }

    function addTodoReadyCard(answerText, todoTitle, dueDate, webLink, taskId) {
      cardDom.withChatArea(function (chatArea) {
        var safeText = '할 일 등록이 완료되었습니다.';
        var safeTitle = String(todoTitle || '').trim() || '등록된 할 일';
        var safeDueDate = String(dueDate || '').trim();
        var subtitle = safeDueDate ? ('마감: ' + safeDueDate) : 'Outlook 할 일';
        appendReadyCard(
          chatArea,
          '<div class="report-file-title">' + escapeHtml(safeText) + '</div>',
          '<div class="report-file-subtitle">' + escapeHtml(subtitle) + '</div>' +
            '<div class="report-file-subtitle">' + escapeHtml(safeTitle) + '</div>',
          ''
        );
        scrollToBottom();
      });
    }

    function addReportConfirmCard(subject) {
      cardDom.withChatArea(function (chatArea) {
        removeWelcomeStateIfExists();
        cardDom.appendAssistantCard(
          chatArea,
          'report-confirm-message',
          'report-confirm-card',
          '<div class="report-confirm-title">보고서 생성 준비</div>' +
          '<div class="report-confirm-desc">현재 메일: <strong>' + escapeHtml(String(subject || '제목 없음')) + '</strong><br>보고서를 생성하시겠습니까?</div>' +
          '<div class="report-confirm-actions">' +
            '<button type="button" class="btn-preview" data-action="report-generate-cancel">취소</button>' +
            '<button type="button" class="btn-download" data-action="report-generate-confirm">확인</button>' +
          '</div>'
        );
        scrollToBottom();
      });
    }

    function addWeeklyReportConfirmCard() {
      cardDom.withChatArea(function (chatArea) {
        removeWelcomeStateIfExists();
        cardDom.appendAssistantCard(
          chatArea,
          'report-confirm-message weekly-report-confirm-message',
          'report-confirm-card',
          '<div class="report-confirm-title">주간보고 생성 준비</div>' +
          '<div class="report-confirm-desc">현재 날짜 기준으로 생성할 주차를 선택해 주세요.</div>' +
          '<div class="weekly-offset-row">' +
            '<label class="weekly-offset-label" for="weeklyOffsetSelect">기준 주차</label>' +
            '<select id="weeklyOffsetSelect" class="weekly-offset-select" data-role="weekly-offset-select">' +
              '<option value="1" selected>지난주 (1주 전)</option>' +
              '<option value="2">지지난주 (2주 전)</option>' +
              '<option value="3">3주 전</option>' +
              '<option value="4">4주 전</option>' +
            '</select>' +
          '</div>' +
          '<div class="report-confirm-actions">' +
            '<button type="button" class="btn-preview" data-action="weekly-report-generate-cancel">취소</button>' +
            '<button type="button" class="btn-download" data-action="weekly-report-generate-confirm">확인</button>' +
          '</div>'
        );
        scrollToBottom();
      });
    }

    function getSelectedWeeklyOffset() {
      var chatArea = cardDom.getChatArea();
      if (!chatArea) return 1;
      var select = chatArea.querySelector('[data-role="weekly-offset-select"]');
      if (!select) return 1;
      var value = Number(select.value || 1);
      if (!Number.isFinite(value)) return 1;
      return Math.max(1, Math.min(8, Math.round(value)));
    }

    function disableReportConfirmControls() {
      cardDom.disableControls(
        '.report-confirm-card [data-action="report-generate-cancel"], ' +
        '.report-confirm-card [data-action="report-generate-confirm"], ' +
        '.report-confirm-card [data-action="weekly-report-generate-cancel"], ' +
        '.report-confirm-card [data-action="weekly-report-generate-confirm"], ' +
        '.report-confirm-card [data-role="weekly-offset-select"]'
      );
    }

    function disableHitlConfirmControls() {
      cardDom.disableControls(
        '.hitl-confirm-block [data-action="hitl-confirm-approve"], ' +
        '.hitl-confirm-block [data-action="hitl-confirm-reject"]'
      );
    }

    function showHitlConfirmPendingStatus(labelText) {
      var chatArea = cardDom.getChatArea();
      if (!chatArea || typeof chatArea.querySelectorAll !== 'function') return;
      var blocks = chatArea.querySelectorAll('.hitl-confirm-block');
      blocks.forEach(function (block) {
        if (!block || typeof block.querySelector !== 'function') return;
        var progress = block.querySelector('[data-role="hitl-confirm-progress"]');
        if (!progress) return;
        progress.hidden = false;
        progress.textContent = String(labelText || '').trim() || '승인 처리 중입니다...';
      });
    }

    return {
      ensureReportProgressCard: ensureReportProgressCard,
      updateReportStep: updateReportStep,
      completeReportProgress: completeReportProgress,
      addMeetingBookingReadyCard: addMeetingBookingReadyCard,
      addTodoReadyCard: addTodoReadyCard,
      addReportConfirmCard: addReportConfirmCard,
      addWeeklyReportConfirmCard: addWeeklyReportConfirmCard,
      getSelectedWeeklyOffset: getSelectedWeeklyOffset,
      disableReportConfirmControls: disableReportConfirmControls,
      disableHitlConfirmControls: disableHitlConfirmControls,
      showHitlConfirmPendingStatus: showHitlConfirmPendingStatus,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneMessagesReportCards = api;
})(typeof window !== 'undefined' ? window : globalThis);
