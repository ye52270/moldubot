/* ========================================
   MolduBot – Taskpane Send Branch Handlers
   ======================================== */

(function initTaskpaneSendHandlers(global) {
  function create(options) {
    const chatApi = options.chatApi;
    const messageUi = options.messageUi;
    const state = options.state;
    const selectionController = options.selectionController;
    const clearProgressWithMinimumVisibility = options.clearProgressWithMinimumVisibility;
    const moduleLoaderFactory =
      (global.TaskpaneModuleLoader && typeof global.TaskpaneModuleLoader.create === 'function')
        ? global.TaskpaneModuleLoader
        : (typeof module !== 'undefined' && module.exports ? require('./taskpane.module_loader.js') : null);
    const moduleLoader = moduleLoaderFactory && typeof moduleLoaderFactory.create === 'function'
      ? moduleLoaderFactory.create()
      : { resolveModule: function () { return null; } };
    const resolveModule = moduleLoader.resolveModule;
    const formatterModule = resolveModule(
      'TaskpaneSendSuggestionFormatters',
      './taskpane.send.suggestion_formatters.js'
    );
    const formatters = formatterModule && typeof formatterModule.create === 'function'
      ? formatterModule.create()
      : null;
    if (!formatters) {
      return {};
    }

    function showAssistantError(message) {
      messageUi.addMessage('assistant', message);
      clearProgressWithMinimumVisibility();
    }

    async function handleReportGenerationQuery(text) {
      const selectionContext = await selectionController.getSelectionContext({ allowCacheFallback: true });
      if (!selectionContext || !selectionContext.emailId || !selectionContext.mailboxUser) {
        messageUi.addMessage('assistant', '보고서 생성은 메일 선택 후 실행할 수 있습니다. 메일을 먼저 선택해 주세요.');
        clearProgressWithMinimumVisibility();
        return;
      }
      const contextResp = await fetch('/mail/context', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message_id: selectionContext.emailId,
          mailbox_user: selectionContext.mailboxUser,
        }),
      });
      const contextPayload = contextResp.ok ? await contextResp.json() : {};
      const mail = contextPayload && contextPayload.mail ? contextPayload.mail : null;
      const emailContent = mail && mail.body_text ? String(mail.body_text || '') : '';
      const emailSubject = mail && mail.subject ? String(mail.subject || '') : '메일 보고서';
      if (!emailContent) {
        messageUi.addMessage('assistant', '선택 메일 본문을 찾지 못해 보고서를 생성할 수 없습니다.');
        clearProgressWithMinimumVisibility();
        return;
      }
      state.pendingReportContext = {
        emailContent: emailContent,
        emailSubject: emailSubject,
        emailReceivedDate: mail && mail.received_date ? String(mail.received_date || '') : '',
        emailSender: mail && (mail.from_address || mail.from_display_name)
          ? String(mail.from_address || mail.from_display_name || '')
          : '',
      };
      messageUi.addReportConfirmCard(emailSubject);
      clearProgressWithMinimumVisibility();
    }

    function handleWeeklyReportGenerationQuery() {
      state.pendingWeeklyReportContext = { reportAuthor: '' };
      messageUi.addWeeklyReportConfirmCard();
      clearProgressWithMinimumVisibility();
    }

    async function handleCurrentMailMeetingSuggestionQuery(text) {
      const selectionContext = await selectionController.getSelectionContext({ allowCacheFallback: false });
      if (!selectionContext || !selectionContext.emailId || !selectionContext.mailboxUser) {
        messageUi.addMessage('assistant', '현재메일 기반 회의 제안은 메일 선택 후 실행할 수 있습니다. 메일을 먼저 선택해 주세요.');
        clearProgressWithMinimumVisibility();
        return;
      }
      const suggestionPayload = await chatApi.suggestMeetingFromCurrentMail(selectionContext.emailId, selectionContext.mailboxUser);
      const proposal = suggestionPayload && suggestionPayload.proposal && typeof suggestionPayload.proposal === 'object'
        ? suggestionPayload.proposal
        : {};
      if (String(suggestionPayload && suggestionPayload.status ? suggestionPayload.status : '').trim() !== 'completed') {
        messageUi.addMessage('assistant', '현재메일 기반 회의 제안을 생성하지 못했습니다. 일반 회의실 예약으로 진행해 주세요.');
        clearProgressWithMinimumVisibility();
        return;
      }
      messageUi.addMessage(
        'assistant',
        formatters.buildMeetingSuggestionMessage(proposal),
        formatters.buildMeetingSuggestionMetadata(proposal)
      );
      const buildings = await chatApi.listMeetingRoomBuildings();
      if (!Array.isArray(buildings) || !buildings.length) {
        showAssistantError('조회 가능한 회의실 건물이 없습니다.');
        return;
      }
      const roomCandidates = Array.isArray(proposal.room_candidates) ? proposal.room_candidates : [];
      const firstRoom = roomCandidates[0] && typeof roomCandidates[0] === 'object' ? roomCandidates[0] : {};
      state.pendingMeetingRoomContext = {
        sourceQuery: text,
        buildings: buildings.slice(),
        selectedBuilding: String(firstRoom.building || '').trim(),
        selectedFloor: Number(firstRoom.floor || 0),
        selectedRoom: String(firstRoom.room_name || '').trim(),
        suggested: proposal,
      };
      if (state.pendingMeetingRoomContext.selectedBuilding && state.pendingMeetingRoomContext.selectedFloor > 0 && state.pendingMeetingRoomContext.selectedRoom) {
        messageUi.addMeetingRoomScheduleCard(
          state.pendingMeetingRoomContext.selectedBuilding,
          state.pendingMeetingRoomContext.selectedFloor,
          state.pendingMeetingRoomContext.selectedRoom,
          formatters.buildSuggestedScheduleDefaults(proposal)
        );
      } else {
        messageUi.addMeetingRoomBuildingCard(buildings);
      }
      clearProgressWithMinimumVisibility();
    }

    async function handleMeetingRoomBookingQuery(text) {
      const buildings = await chatApi.listMeetingRoomBuildings();
      if (!Array.isArray(buildings) || !buildings.length) {
        showAssistantError('조회 가능한 회의실 건물이 없습니다.');
        return;
      }
      state.pendingMeetingRoomContext = {
        sourceQuery: text,
        buildings: buildings.slice(),
        selectedBuilding: '',
        selectedFloor: 0,
        selectedRoom: '',
      };
      messageUi.addMeetingRoomBuildingCard(buildings);
      clearProgressWithMinimumVisibility();
    }

    async function handleCurrentMailCalendarSuggestionQuery(text) {
      const selectionContext = await selectionController.getSelectionContext({ allowCacheFallback: false });
      if (!selectionContext || !selectionContext.emailId || !selectionContext.mailboxUser) {
        messageUi.addMessage('assistant', '현재메일 기반 일정 등록은 메일 선택 후 실행할 수 있습니다. 메일을 먼저 선택해 주세요.');
        clearProgressWithMinimumVisibility();
        return;
      }
      const suggestionPayload = await chatApi.suggestCalendarFromCurrentMail(selectionContext.emailId, selectionContext.mailboxUser);
      const proposal = suggestionPayload && suggestionPayload.proposal && typeof suggestionPayload.proposal === 'object'
        ? suggestionPayload.proposal
        : {};
      if (String(suggestionPayload && suggestionPayload.status ? suggestionPayload.status : '').trim() !== 'completed') {
        messageUi.addMessage('assistant', '현재메일 기반 일정 제안을 생성하지 못했습니다. 일정 등록 카드로 다시 진행해 주세요.');
        clearProgressWithMinimumVisibility();
        return;
      }
      messageUi.addMessage(
        'assistant',
        formatters.buildCalendarSuggestionMessage(proposal),
        formatters.buildCalendarSuggestionMetadata(proposal)
      );
      state.pendingCalendarContext = {
        sourceQuery: text,
        suggestion: proposal,
      };
      messageUi.addCalendarEventCard(proposal);
      clearProgressWithMinimumVisibility();
    }

    function handleCalendarEventQuery(text) {
      state.pendingCalendarContext = {
        sourceQuery: text,
        suggestion: null,
      };
      messageUi.addCalendarEventCard({
        subject: '',
        date: '',
        start_time: '10:00',
        end_time: '11:00',
        body: '',
        attendees: [],
      });
      clearProgressWithMinimumVisibility();
    }

    function handlePromiseBudgetQuery(text) {
      state.pendingPromiseContext = { sourceQuery: text };
      messageUi.addPromiseBudgetCard();
      clearProgressWithMinimumVisibility();
    }

    async function handleFinanceSettlementQuery(text) {
      const projects = await chatApi.listFinanceProjects();
      if (!Array.isArray(projects) || !projects.length) {
        showAssistantError('비용정산 대상 프로젝트가 없습니다.');
        return;
      }
      state.pendingFinanceContext = { sourceQuery: text };
      messageUi.addFinanceSettlementCard(projects);
      const firstProject = String(projects[0] && projects[0].project_number ? projects[0].project_number : '').trim();
      if (firstProject) {
        const budget = await chatApi.getFinanceProjectBudget(firstProject);
        messageUi.setFinanceBudgetText(
          '총액 ' + String(Number(budget.expense_budget_total || 0).toLocaleString('ko-KR')) +
          '원 / 잔여 ' + String(Number(budget.remaining_amount || 0).toLocaleString('ko-KR')) + '원'
        );
      }
      clearProgressWithMinimumVisibility();
    }

    function handleHrApplyQuery(text) {
      state.pendingHrContext = { sourceQuery: text };
      messageUi.addHrApplyCard();
      clearProgressWithMinimumVisibility();
    }

    return {
      handleReportGenerationQuery: handleReportGenerationQuery,
      handleWeeklyReportGenerationQuery: handleWeeklyReportGenerationQuery,
      handleCurrentMailMeetingSuggestionQuery: handleCurrentMailMeetingSuggestionQuery,
      handleMeetingRoomBookingQuery: handleMeetingRoomBookingQuery,
      handleCurrentMailCalendarSuggestionQuery: handleCurrentMailCalendarSuggestionQuery,
      handleCalendarEventQuery: handleCalendarEventQuery,
      handlePromiseBudgetQuery: handlePromiseBudgetQuery,
      handleFinanceSettlementQuery: handleFinanceSettlementQuery,
      handleHrApplyQuery: handleHrApplyQuery,
    };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneSendHandlers = api;
})(typeof window !== 'undefined' ? window : globalThis);
