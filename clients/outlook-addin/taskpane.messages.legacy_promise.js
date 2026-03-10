/* ========================================
   MolduBot – Taskpane Messages Legacy Promise Cards
   ======================================== */

(function initTaskpaneMessagesLegacyPromise(global) {
  function create(options) {
    var getChatArea = options.getChatArea;
    var appendLegacyAssistantCard = options.appendLegacyAssistantCard;
    var disableControls = options.disableControls;
    var escapeHtml = options.escapeHtml;
    var escapeAttr = options.escapeAttr;
    var toSafeText = options.toSafeText;
    var toSafeNumber = options.toSafeNumber;
    var formatKrw = options.formatKrw;
    var buildRichTable = options.buildRichTable;

    function addPromiseBudgetCard() {
      appendLegacyAssistantCard(
        'promise-confirm-card',
        '' +
            '<div class="report-confirm-title">실행예산</div>' +
            '<div class="report-confirm-actions" data-role="promise-mode-actions">' +
              '<button type="button" class="btn-download" data-action="promise-mode-view">조회</button>' +
              '<button type="button" class="btn-preview" data-action="promise-mode-register">등록</button>' +
            '</div>' +
            '<div data-role="promise-view-section" style="display:none;">' +
              '<div class="hint">등록된 프로젝트를 선택하면 월별 실행예산을 표로 확인할 수 있습니다.</div>' +
              '<div data-role="promise-view-step-list">' +
                '<div class="quick-prompt-toast__list" data-role="promise-summary-list"></div>' +
              '</div>' +
              '<div data-role="promise-view-step-detail" style="display:none;">' +
                '<div class="meeting-room-card-header">' +
                  '<div class="meeting-room-card-title">월별 실행예산 상세</div>' +
                  '<button type="button" class="meeting-room-back-btn" data-action="promise-detail-back">뒤로가기</button>' +
                '</div>' +
                '<div class="hint" data-role="promise-summary-text"></div>' +
                '<div class="quick-prompt-toast__list" data-role="promise-monthly-list"></div>' +
              '</div>' +
            '</div>' +
        ''
      );
    }

    function normalizePromiseSummaryItem(item) {
      var projectNumber = toSafeText(item && item.project_number, '');
      var projectName = toSafeText(item && item.project_name, '');
      return {
        projectNumber: projectNumber,
        projectName: projectName,
        execution: toSafeNumber(item && item.execution_total),
        finalCost: toSafeNumber(item && item.final_cost_total),
      };
    }

    function buildPromiseSummaryRow(item) {
      return (
        '<tr>' +
          '<td>' + escapeHtml(item.projectNumber || '-') + '</td>' +
          '<td>' + escapeHtml(item.projectName || '-') + '</td>' +
          '<td>' + formatKrw(item.execution) + '</td>' +
          '<td>' + formatKrw(item.finalCost) + '</td>' +
          '<td><button type="button" class="meeting-room-back-btn" data-action="promise-summary-select" data-project-number="' +
            escapeAttr(item.projectNumber) +
            '" data-project-name="' + escapeAttr(item.projectName) +
            '" data-execution-total="' + escapeAttr(String(item.execution)) +
            '" data-final-cost-total="' + escapeAttr(String(item.finalCost)) +
          '">선택</button></td>' +
        '</tr>'
      );
    }

    function buildPromiseSummaryTable(rows) {
      var headerHtml =
        '<thead><tr>' +
          '<th>프로젝트 번호</th>' +
          '<th>프로젝트명</th>' +
          '<th>실행비용</th>' +
          '<th>집행예산</th>' +
          '<th>선택</th>' +
        '</tr></thead>';
      var bodyHtml = '<tbody class="promise-table-compact">' + rows + '</tbody>';
      return buildRichTable(headerHtml, bodyHtml, '');
    }

    function renderPromiseSummaryList(items) {
      var chatArea = getChatArea();
      if (!chatArea) return;
      var listNode = chatArea.querySelector('[data-role="promise-summary-list"]');
      if (!listNode) return;
      var rows = Array.isArray(items) ? items : [];
      if (!rows.length) {
        listNode.innerHTML = '<div class="hint">조회 가능한 실행예산 항목이 없습니다.</div>';
        return;
      }
      var bodyRows = rows.map(function (item) {
        return buildPromiseSummaryRow(normalizePromiseSummaryItem(item));
      }).join('');
      listNode.innerHTML = buildPromiseSummaryTable(bodyRows);
    }

    function setPromiseViewStep(step) {
      var chatArea = getChatArea();
      if (!chatArea) return;
      var normalized = String(step || 'list').trim() === 'detail' ? 'detail' : 'list';
      var listNode = chatArea.querySelector('[data-role="promise-view-step-list"]');
      var detailNode = chatArea.querySelector('[data-role="promise-view-step-detail"]');
      if (listNode) listNode.style.display = normalized === 'list' ? '' : 'none';
      if (detailNode) detailNode.style.display = normalized === 'detail' ? '' : 'none';
    }

    function renderPromiseMonthlyBreakdown(summary) {
      var chatArea = getChatArea();
      if (!chatArea) return;
      var infoNode = chatArea.querySelector('[data-role="promise-summary-text"]');
      var monthlyNode = chatArea.querySelector('[data-role="promise-monthly-list"]');
      if (!infoNode || !monthlyNode) return;
      var projectNumber = toSafeText(summary && summary.project_number, '-');
      var projectName = toSafeText(summary && summary.project_name, '-');
      var execution = toSafeNumber(summary && summary.execution_total);
      var finalCost = toSafeNumber(summary && summary.final_cost_total);
      infoNode.innerHTML = buildRichTable(
        '',
        '<tbody>' +
          '<tr>' +
            '<th>프로젝트</th>' +
            '<td>' + escapeHtml(projectNumber + ' · ' + projectName) + '</td>' +
            '<th>실행비용</th>' +
            '<td>' + formatKrw(execution) + '</td>' +
            '<th>집행예산</th>' +
            '<td>' + formatKrw(finalCost) + '</td>' +
          '</tr>' +
        '</tbody>',
        'promise-table-compact'
      );
      var monthly = Array.isArray(summary && summary.monthly_breakdown ? summary.monthly_breakdown : [])
        ? summary.monthly_breakdown
        : [];
      if (!monthly.length) {
        monthlyNode.innerHTML = '<div class="hint">월별 데이터가 없습니다.</div>';
        return;
      }
      var bodyRows = monthly.map(function (item) {
        var month = toSafeNumber(item && item.month);
        var monthExecution = toSafeNumber(item && item.execution_total);
        var labor = toSafeNumber(item && item.labor_cost);
        var outsourcing = toSafeNumber(item && item.outsourcing_cost);
        var material = toSafeNumber(item && item.material_cost);
        var expense = toSafeNumber(item && item.expense_cost);
        return (
          '<tr>' +
            '<td>' + escapeHtml(String(month) + '월') + '</td>' +
            '<td>' + formatKrw(labor) + '</td>' +
            '<td>' + formatKrw(outsourcing) + '</td>' +
            '<td>' + formatKrw(material) + '</td>' +
            '<td>' + formatKrw(expense) + '</td>' +
            '<td>' + formatKrw(monthExecution) + '</td>' +
          '</tr>'
        );
      }).join('');
      monthlyNode.innerHTML = buildRichTable(
        '<thead><tr>' +
          '<th>월</th>' +
          '<th>인건비</th>' +
          '<th>외주비</th>' +
          '<th>자료비</th>' +
          '<th>경비</th>' +
          '<th>실행합계</th>' +
        '</tr></thead>',
        '<tbody>' + bodyRows + '</tbody>',
        'promise-table-compact'
      );
      setPromiseViewStep('detail');
    }

    function setPromiseSummaryText(text) {
      var chatArea = getChatArea();
      if (!chatArea) return;
      var node = chatArea.querySelector('[data-role="promise-summary-text"]');
      if (!node) return;
      node.textContent = String(text || '').trim();
    }

    function setPromiseMode(mode) {
      var chatArea = getChatArea();
      if (!chatArea) return;
      var normalized = String(mode || 'none').trim() === 'view' ? 'view' : 'none';
      var actionRow = chatArea.querySelector('[data-role="promise-mode-actions"]');
      var viewSection = chatArea.querySelector('[data-role="promise-view-section"]');
      var registerSection = chatArea.querySelector('[data-role="promise-register-section"]');
      if (actionRow) actionRow.style.display = normalized === 'view' ? 'none' : '';
      if (viewSection) viewSection.style.display = normalized === 'view' ? '' : 'none';
      if (registerSection) registerSection.style.display = 'none';
      if (normalized === 'view') setPromiseViewStep('list');
    }

    function getPromiseCardValues() {
      return null;
    }

    function clearPromiseMonthlyBreakdown() {
      var chatArea = getChatArea();
      if (!chatArea) return;
      var node = chatArea.querySelector('[data-role="promise-monthly-list"]');
      if (!node) return;
      node.innerHTML = '';
    }

    function disablePromiseCardControls() {
      disableControls('.promise-confirm-card [data-role], .promise-confirm-card [data-action]');
    }

    return {
      addPromiseBudgetCard: addPromiseBudgetCard,
      renderPromiseSummaryList: renderPromiseSummaryList,
      renderPromiseMonthlyBreakdown: renderPromiseMonthlyBreakdown,
      clearPromiseMonthlyBreakdown: clearPromiseMonthlyBreakdown,
      setPromiseSummaryText: setPromiseSummaryText,
      setPromiseMode: setPromiseMode,
      setPromiseViewStep: setPromiseViewStep,
      getPromiseCardValues: getPromiseCardValues,
      disablePromiseCardControls: disablePromiseCardControls,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (global) {
    global.TaskpaneMessagesLegacyPromise = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
