/* ========================================
   MolduBot – Taskpane Chat Action Handlers
   ======================================== */

(function initTaskpaneChatActionHandlers(global) {
  function create(options) {
    const windowRef = options.windowRef;
    const byId = options.byId;
    const chatApi = options.chatApi;
    const messageUi = options.messageUi;
    const state = options.state;
    const setSendingState = options.setSendingState;
    const handleProgress = options.handleProgress;
    const runReportGeneration = options.runReportGeneration;
    const runWeeklyReportGeneration = options.runWeeklyReportGeneration;
    const sanitizeMeetingHilMetadata = options.sanitizeMeetingHilMetadata;
    const setMeetingRoomBookingButtonLabel = options.setMeetingRoomBookingButtonLabel;
    const buildMeetingRoomHilMessage = options.buildMeetingRoomHilMessage;
    const buildCalendarEventHilMessage = typeof options.buildCalendarEventHilMessage === 'function'
      ? options.buildCalendarEventHilMessage
      : function () { return ''; };
    const openReplyCompose = options.openReplyCompose;
    const moduleLoaderFactory =
      (global.TaskpaneModuleLoader && typeof global.TaskpaneModuleLoader.create === 'function')
        ? global.TaskpaneModuleLoader
        : (typeof module !== 'undefined' && module.exports ? require('./taskpane.module_loader.js') : null);
    const moduleLoader = moduleLoaderFactory && typeof moduleLoaderFactory.create === 'function'
      ? moduleLoaderFactory.create()
      : { resolveModule: function () { return null; } };
    const resolveModule = moduleLoader.resolveModule;
    const nextActionsModule = resolveModule('TaskpaneChatActionNextActions', './taskpane.chat_actions.next_actions.js');
    const hitlModule = resolveModule('TaskpaneChatActionHitl', './taskpane.chat_actions.hitl.js');
    const nextActions = nextActionsModule && typeof nextActionsModule.create === 'function'
      ? nextActionsModule.create({
        chatApi: chatApi,
        messageUi: messageUi,
        state: state,
        setSendingState: setSendingState,
        handleProgress: handleProgress,
        openReplyCompose: openReplyCompose,
        focusInput: focusInput,
      })
      : null;

    function focusInput() {
      const input = byId('chatInput');
      if (input) input.focus();
    }

    function moveMeetingRoomToFloor(building) {
      if (!state.pendingMeetingRoomContext) return Promise.resolve();
      const normalizedBuilding = String(building || '').trim();
      if (!normalizedBuilding) return Promise.resolve();
      state.pendingMeetingRoomContext.selectedBuilding = normalizedBuilding;
      state.pendingMeetingRoomContext.selectedFloor = 0;
      state.pendingMeetingRoomContext.selectedRoom = '';
      setSendingState(true);
      return chatApi.listMeetingRoomFloors(normalizedBuilding).then(function (floors) {
        if (!Array.isArray(floors) || !floors.length) {
          messageUi.addMessage('assistant', '선택한 건물에 조회 가능한 층이 없습니다.');
          return;
        }
        messageUi.addMeetingRoomFloorCard(normalizedBuilding, floors);
      }).catch(function () {
        messageUi.addMessage('assistant', '층 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.');
      }).finally(function () {
        setSendingState(false);
        focusInput();
      });
    }

    function moveMeetingRoomToRoom(building, floor) {
      if (!state.pendingMeetingRoomContext) return Promise.resolve();
      const normalizedBuilding = String(building || '').trim();
      const normalizedFloor = Number(floor || 0);
      if (!normalizedBuilding || !normalizedFloor) return Promise.resolve();
      state.pendingMeetingRoomContext.selectedBuilding = normalizedBuilding;
      state.pendingMeetingRoomContext.selectedFloor = normalizedFloor;
      state.pendingMeetingRoomContext.selectedRoom = '';
      setSendingState(true);
      return chatApi.listMeetingRooms(normalizedBuilding, normalizedFloor).then(function (rooms) {
        if (!Array.isArray(rooms) || !rooms.length) {
          messageUi.addMessage('assistant', '선택한 층에 조회 가능한 회의실이 없습니다.');
          return;
        }
        messageUi.addMeetingRoomDetailCard(normalizedBuilding, normalizedFloor, rooms);
      }).catch(function () {
        messageUi.addMessage('assistant', '회의실 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.');
      }).finally(function () {
        setSendingState(false);
        focusInput();
      });
    }

    function moveMeetingRoomToSchedule(building, floor, roomName) {
      if (!state.pendingMeetingRoomContext) return;
      const normalizedBuilding = String(building || '').trim();
      const normalizedFloor = Number(floor || 0);
      const normalizedRoom = String(roomName || '').trim();
      if (!normalizedBuilding || !normalizedFloor || !normalizedRoom) return;
      state.pendingMeetingRoomContext.selectedBuilding = normalizedBuilding;
      state.pendingMeetingRoomContext.selectedFloor = normalizedFloor;
      state.pendingMeetingRoomContext.selectedRoom = normalizedRoom;
      const suggested = state.pendingMeetingRoomContext.suggested && typeof state.pendingMeetingRoomContext.suggested === 'object'
        ? state.pendingMeetingRoomContext.suggested
        : {};
      messageUi.disableMeetingRoomBookingControls();
      messageUi.addMeetingRoomScheduleCard(normalizedBuilding, normalizedFloor, normalizedRoom, {
        attendee_count: Number(suggested.attendee_count || 0),
        subject: String(suggested.meeting_subject || '').trim(),
        time_candidates: Array.isArray(suggested.time_candidates) ? suggested.time_candidates : [],
        room_candidates: Array.isArray(suggested.room_candidates) ? suggested.room_candidates : [],
      });
    }

    const hitlHandlers = hitlModule && typeof hitlModule.create === 'function'
      ? hitlModule.create({
        windowRef: windowRef,
        chatApi: chatApi,
        messageUi: messageUi,
        state: state,
        setSendingState: setSendingState,
        handleProgress: handleProgress,
        sanitizeMeetingHilMetadata: sanitizeMeetingHilMetadata,
        setMeetingRoomBookingButtonLabel: setMeetingRoomBookingButtonLabel,
        buildMeetingRoomHilMessage: buildMeetingRoomHilMessage,
        buildCalendarEventHilMessage: buildCalendarEventHilMessage,
        focusInput: focusInput,
        filterNextActionsMetadata: filterNextActionsMetadata,
      })
      : {
        openMeetingEvent: function () {},
        handleHilConfirm: function () {},
        handleMeetingRoomBookConfirm: function () {},
        handleCalendarEventSubmit: function () {},
      };

    function openPromiseRegisterPage() {
      const opened = windowRef.open('/promise', '_blank');
      if (!opened) windowRef.location.href = '/promise';
      messageUi.addMessage('assistant', '실행예산 등록 페이지를 열었습니다.');
    }

    function handleFinanceSubmit() {
      if (!state.pendingFinanceContext) {
        messageUi.addMessage('assistant', '진행할 비용정산 요청을 찾지 못했습니다.');
        return;
      }
      const form = messageUi.getFinanceCardValues();
      if (!form || !form.project_number || !form.expense_category || !form.amount) {
        messageUi.addMessage('assistant', '프로젝트/비용항목/금액을 입력해 주세요.');
        return;
      }
      messageUi.disableFinanceCardControls();
      setSendingState(true);
      chatApi.submitFinanceClaim(form).then(function (payload) {
        if (payload && payload.status === 'completed') {
          const budget = payload && payload.budget ? payload.budget : {};
          messageUi.setFinanceBudgetText(
            '저장 완료 - 사용 ' + String(Number(budget.used_amount || 0).toLocaleString('ko-KR')) +
            '원 / 잔여 ' + String(Number(budget.remaining_amount || 0).toLocaleString('ko-KR')) + '원'
          );
          messageUi.addMessage('assistant', '비용정산 입력(기안)을 저장했습니다.');
          state.pendingFinanceContext = null;
          return;
        }
        messageUi.addMessage('assistant', String(payload && payload.reason ? payload.reason : '비용정산 처리에 실패했습니다.'));
      }).catch(function () {
        messageUi.addMessage('assistant', '비용정산 처리 중 오류가 발생했습니다.');
      }).finally(function () {
        setSendingState(false);
        focusInput();
      });
    }

    function handleHrSubmit() {
      if (!state.pendingHrContext) {
        messageUi.addMessage('assistant', '진행할 근태/휴가 요청을 찾지 못했습니다.');
        return;
      }
      const form = messageUi.getHrCardValues();
      if (!form || !form.request_type || !form.request_date) {
        messageUi.addMessage('assistant', '신청 유형과 신청일을 입력해 주세요.');
        return;
      }
      messageUi.disableHrCardControls();
      setSendingState(true);
      chatApi.submitHrRequest(form).then(function (payload) {
        if (payload && payload.status === 'completed') {
          messageUi.addMessage('assistant', '근태/휴가 신청을 저장했습니다.');
          state.pendingHrContext = null;
          return;
        }
        messageUi.addMessage('assistant', String(payload && payload.reason ? payload.reason : '근태 신청 처리에 실패했습니다.'));
      }).catch(function () {
        messageUi.addMessage('assistant', '근태 신청 처리 중 오류가 발생했습니다.');
      }).finally(function () {
        setSendingState(false);
        focusInput();
      });
    }

    function handleWeeklyReportConfirm() {
      if (!state.pendingWeeklyReportContext) {
        messageUi.addMessage('assistant', '진행할 주간보고 요청을 찾지 못했습니다.');
        return;
      }
      messageUi.disableReportConfirmControls();
      const weekOffset = messageUi.getSelectedWeeklyOffset();
      const weeklyContext = state.pendingWeeklyReportContext;
      state.pendingWeeklyReportContext = null;
      setSendingState(true);
      runWeeklyReportGeneration(weekOffset, weeklyContext.reportAuthor || '').catch(function () {
        messageUi.addMessage('assistant', '주간보고 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
      }).finally(function () {
        setSendingState(false);
        focusInput();
      });
    }

    async function handleScopeSelect(button) {
      const scope = String(button && button.getAttribute('data-scope') ? button.getAttribute('data-scope') : '').trim();
      const originalQuery = String(button && button.getAttribute('data-original-query') ? button.getAttribute('data-original-query') : '').trim();
      if (!scope || !originalQuery) {
        messageUi.addMessage('assistant', '범위 선택 정보를 확인하지 못했습니다. 다시 시도해 주세요.');
        return;
      }
      setSendingState(true);
      try {
        const assistantPayload = await chatApi.requestAssistantReply(
          originalQuery,
          null,
          { scope: scope, skip_intent_clarification: true }
        );
        const assistantReply = assistantPayload && assistantPayload.answer
          ? assistantPayload.answer
          : '응답을 생성하지 못했습니다.';
        const assistantMetadata = filterNextActionsMetadata(
          assistantPayload && assistantPayload.metadata ? assistantPayload.metadata : {}
        );
        messageUi.addMessage('assistant', assistantReply, assistantMetadata);
      } catch (_error) {
        messageUi.addMessage('assistant', '범위 선택 후 재조회 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
      } finally {
        setSendingState(false);
        focusInput();
      }
    }

    function filterNextActionsMetadata(metadata) {
      if (nextActions && typeof nextActions.filterNextActionsMetadata === 'function') {
        return nextActions.filterNextActionsMetadata(metadata);
      }
      if (!state || typeof state.filterNextActionsMetadata !== 'function') {
        return metadata && typeof metadata === 'object' ? metadata : {};
      }
      return state.filterNextActionsMetadata(metadata);
    }

    return {
      moveMeetingRoomToFloor: moveMeetingRoomToFloor,
      moveMeetingRoomToRoom: moveMeetingRoomToRoom,
      moveMeetingRoomToSchedule: moveMeetingRoomToSchedule,
      openMeetingEvent: hitlHandlers.openMeetingEvent,
      handleHilConfirm: hitlHandlers.handleHilConfirm,
      handleMeetingRoomBookConfirm: hitlHandlers.handleMeetingRoomBookConfirm,
      handleCalendarEventSubmit: hitlHandlers.handleCalendarEventSubmit,
      openPromiseRegisterPage: openPromiseRegisterPage,
      handleFinanceSubmit: handleFinanceSubmit,
      handleHrSubmit: handleHrSubmit,
      handleWeeklyReportConfirm: handleWeeklyReportConfirm,
      handleScopeSelect: handleScopeSelect,
      handleNextActionRun: nextActions && typeof nextActions.handleNextActionRun === 'function'
        ? nextActions.handleNextActionRun
        : function () {},
      handleReplyToneGenerate: nextActions && typeof nextActions.handleReplyToneGenerate === 'function'
        ? nextActions.handleReplyToneGenerate
        : function () {},
      handleReplyDraftOpen: nextActions && typeof nextActions.handleReplyDraftOpen === 'function'
        ? nextActions.handleReplyDraftOpen
        : function () {},
      focusInput: focusInput,
    };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  global.TaskpaneChatActionHandlers = api;
})(typeof window !== 'undefined' ? window : globalThis);
