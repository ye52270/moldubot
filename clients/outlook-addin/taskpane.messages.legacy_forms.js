/* ========================================
   MolduBot – Taskpane Messages Legacy Form Cards
   ======================================== */

(function initTaskpaneMessagesLegacyForms(global) {
  function create(options) {
    var getChatArea = options.getChatArea;
    var appendLegacyAssistantCard = options.appendLegacyAssistantCard;
    var disableControls = options.disableControls;
    var escapeHtml = options.escapeHtml;
    var escapeAttr = options.escapeAttr;
    var toSafeText = options.toSafeText;

    function buildFinanceProjectOptions(projects) {
      return (Array.isArray(projects) ? projects : [])
        .map(function (item, index) {
          var projectNumber = toSafeText(item && item.project_number, '');
          var projectName = toSafeText(item && item.project_name, projectNumber);
          if (!projectNumber) return '';
          var selected = index === 0 ? ' selected' : '';
          return '<option value="' + escapeAttr(projectNumber) + '"' + selected + '>' + escapeHtml(projectName) + '</option>';
        })
        .filter(function (item) { return Boolean(item); })
        .join('');
    }

    function addFinanceSettlementCard(projects) {
      var options = buildFinanceProjectOptions(projects);
      appendLegacyAssistantCard(
        'finance-confirm-card',
        '' +
            '<div class="report-confirm-title">비용정산 입력</div>' +
            '<label class="meeting-room-label">프로젝트' +
              '<select class="meeting-room-select" data-role="finance-project-select" data-action="finance-project-change">' + options + '</select>' +
            '</label>' +
            '<div class="hint" data-role="finance-budget-text">예산 정보를 불러오는 중입니다.</div>' +
            '<label class="meeting-room-label">비용 항목' +
              '<input class="meeting-room-input" data-role="finance-category-input" type="text" placeholder="예: 식비">' +
            '</label>' +
            '<label class="meeting-room-label">금액(원)' +
              '<input class="meeting-room-input" data-role="finance-amount-input" type="text" inputmode="numeric" placeholder="예: 50000">' +
            '</label>' +
            '<label class="meeting-room-label">비고' +
              '<textarea class="meeting-room-input" data-role="finance-desc-input" rows="2" placeholder="정산 메모"></textarea>' +
            '</label>' +
            '<div class="report-confirm-actions">' +
              '<button type="button" class="btn-preview" data-action="finance-card-cancel">취소</button>' +
              '<button type="button" class="btn-download" data-action="finance-card-submit">기안</button>' +
            '</div>' +
        ''
      );
    }

    function setFinanceBudgetText(text) {
      var chatArea = getChatArea();
      if (!chatArea) return;
      var node = chatArea.querySelector('[data-role="finance-budget-text"]');
      if (!node) return;
      node.textContent = String(text || '').trim();
    }

    function getFinanceCardValues() {
      var chatArea = getChatArea();
      if (!chatArea) return null;
      var project = chatArea.querySelector('[data-role="finance-project-select"]');
      var category = chatArea.querySelector('[data-role="finance-category-input"]');
      var amount = chatArea.querySelector('[data-role="finance-amount-input"]');
      var description = chatArea.querySelector('[data-role="finance-desc-input"]');
      return {
        project_number: String(project && project.value ? project.value : '').trim(),
        expense_category: String(category && category.value ? category.value : '').trim(),
        amount: Number(String(amount && amount.value ? amount.value : '').replace(/[^0-9-]/g, '')) || 0,
        description: String(description && description.value ? description.value : '').trim(),
      };
    }

    function disableFinanceCardControls() {
      disableControls('.finance-confirm-card [data-role], .finance-confirm-card [data-action]');
    }

    function addHrApplyCard() {
      appendLegacyAssistantCard(
        'hr-confirm-card',
        '' +
            '<div class="report-confirm-title">근태/휴가 신청</div>' +
            '<label class="meeting-room-label">신청 유형' +
              '<select class="meeting-room-select" data-role="hr-type-select">' +
                '<option value="근태신청">근태신청</option>' +
                '<option value="휴가신청">휴가신청</option>' +
              '</select>' +
            '</label>' +
            '<label class="meeting-room-label">신청일' +
              '<input class="meeting-room-input" data-role="hr-date-input" type="date">' +
            '</label>' +
            '<label class="meeting-room-label">사유' +
              '<textarea class="meeting-room-input" data-role="hr-reason-input" rows="2" placeholder="신청 사유"></textarea>' +
            '</label>' +
            '<div class="report-confirm-actions">' +
              '<button type="button" class="btn-preview" data-action="hr-card-cancel">취소</button>' +
              '<button type="button" class="btn-download" data-action="hr-card-submit">신청</button>' +
            '</div>' +
        ''
      );
    }

    function getHrCardValues() {
      var chatArea = getChatArea();
      if (!chatArea) return null;
      var requestType = chatArea.querySelector('[data-role="hr-type-select"]');
      var requestDate = chatArea.querySelector('[data-role="hr-date-input"]');
      var reason = chatArea.querySelector('[data-role="hr-reason-input"]');
      return {
        request_type: String(requestType && requestType.value ? requestType.value : '').trim(),
        request_date: String(requestDate && requestDate.value ? requestDate.value : '').trim(),
        reason: String(reason && reason.value ? reason.value : '').trim(),
      };
    }

    function disableHrCardControls() {
      disableControls('.hr-confirm-card [data-role], .hr-confirm-card [data-action]');
    }

    return {
      addFinanceSettlementCard: addFinanceSettlementCard,
      setFinanceBudgetText: setFinanceBudgetText,
      getFinanceCardValues: getFinanceCardValues,
      disableFinanceCardControls: disableFinanceCardControls,
      addHrApplyCard: addHrApplyCard,
      getHrCardValues: getHrCardValues,
      disableHrCardControls: disableHrCardControls,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (global) {
    global.TaskpaneMessagesLegacyForms = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
