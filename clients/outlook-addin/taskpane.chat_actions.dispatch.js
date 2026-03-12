(function initTaskpaneChatActionDispatch(global) {
  function create(options) {
    const byId = options.byId;
    const chatApi = options.chatApi;
    const messageUi = options.messageUi;
    const state = options.state;
    const setSendingState = options.setSendingState;
    const runReportGeneration = options.runReportGeneration;
    const helperActions = options.helperActions;
    const moduleLoaderFactory =
      (global.TaskpaneModuleLoader && typeof global.TaskpaneModuleLoader.create === 'function')
        ? global.TaskpaneModuleLoader
        : (typeof module !== 'undefined' && module.exports ? require('./taskpane.module_loader.js') : null);
    const moduleLoader = moduleLoaderFactory && typeof moduleLoaderFactory.create === 'function'
      ? moduleLoaderFactory.create()
      : { resolveModule: function () { return null; }, createRenderer: function (_m, _o, fallback) { return fallback || {}; } };
    const changeHandlersModule = moduleLoader.resolveModule(
      'TaskpaneChatActionChangeHandlers',
      './taskpane.chat_actions.change_handlers.js'
    );
    const changeHandlers = moduleLoader.createRenderer(changeHandlersModule, {
      byId: byId,
      chatApi: chatApi,
      messageUi: messageUi,
      state: state,
      helperActions: helperActions,
    }, { handleChatAreaChange: function () {} });
    const MISSING_MEETING_CONTEXT_MESSAGE = '진행할 회의실 예약 요청을 찾지 못했습니다.';

    function cancelAction(contextKey, message, afterReset) {
      if (contextKey) state[contextKey] = null;
      if (typeof afterReset === 'function') afterReset();
      messageUi.addMessage('assistant', message);
    }

    function resetPromiseViewToList() {
      if (typeof messageUi.setPromiseViewStep === 'function') {
        messageUi.setPromiseViewStep('list');
      }
      if (typeof messageUi.setPromiseSummaryText === 'function') {
        messageUi.setPromiseSummaryText('목록에서 실행예산 항목을 선택해 주세요.');
      }
      if (typeof messageUi.clearPromiseMonthlyBreakdown === 'function') {
        messageUi.clearPromiseMonthlyBreakdown();
      }
    }

    function hasPendingMeetingRoomContext() {
      if (state.pendingMeetingRoomContext) return true;
      messageUi.addMessage('assistant', MISSING_MEETING_CONTEXT_MESSAGE);
      return false;
    }

    function handleMeetingBackToBuilding() {
      if (!hasPendingMeetingRoomContext()) return;
      const buildings = Array.isArray(state.pendingMeetingRoomContext.buildings)
        ? state.pendingMeetingRoomContext.buildings
        : [];
      state.pendingMeetingRoomContext.selectedFloor = 0;
      state.pendingMeetingRoomContext.selectedRoom = '';
      messageUi.addMeetingRoomBuildingCard(buildings);
    }

    function handleMeetingBackToFloor() {
      if (!hasPendingMeetingRoomContext()) return;
      const building = String(state.pendingMeetingRoomContext.selectedBuilding || '').trim();
      if (!building) {
        const buildings = Array.isArray(state.pendingMeetingRoomContext.buildings)
          ? state.pendingMeetingRoomContext.buildings
          : [];
        messageUi.addMeetingRoomBuildingCard(buildings);
        return;
      }
      void helperActions.moveMeetingRoomToFloor(building);
    }

    function handleMeetingBackToRoom() {
      if (!hasPendingMeetingRoomContext()) return;
      const building = String(state.pendingMeetingRoomContext.selectedBuilding || '').trim();
      const floor = Number(state.pendingMeetingRoomContext.selectedFloor || 0);
      void helperActions.moveMeetingRoomToRoom(building, floor);
    }

    function handleReportGenerateConfirm() {
      if (!state.pendingReportContext) {
        messageUi.addMessage('assistant', '진행할 보고서 요청을 찾지 못했습니다.');
        return;
      }
      messageUi.disableReportConfirmControls();
      const context = state.pendingReportContext;
      state.pendingReportContext = null;
      setSendingState(true);
      runReportGeneration(
        context.emailContent,
        context.emailSubject,
        context.emailReceivedDate,
        context.emailSender
      ).catch(function () {
        messageUi.addMessage('assistant', '보고서 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
      }).finally(function () {
        setSendingState(false);
        helperActions.focusInput();
      });
    }

    function handlePromiseModeView() {
      if (!state.pendingPromiseContext) {
        messageUi.addMessage('assistant', '진행할 실행예산 요청을 찾지 못했습니다.');
        return;
      }
      if (typeof messageUi.setPromiseMode === 'function') messageUi.setPromiseMode('view');
      if (typeof messageUi.setPromiseSummaryText === 'function') {
        messageUi.setPromiseSummaryText('조회 목록을 불러오는 중입니다.');
      }
      if (typeof messageUi.clearPromiseMonthlyBreakdown === 'function') {
        messageUi.clearPromiseMonthlyBreakdown();
      }
      setSendingState(true);
      chatApi.listPromiseSummaries().then(function (items) {
        if (typeof messageUi.renderPromiseSummaryList === 'function') {
          messageUi.renderPromiseSummaryList(items);
        }
        if (typeof messageUi.setPromiseSummaryText === 'function') {
          messageUi.setPromiseSummaryText('목록에서 실행예산 항목을 선택해 주세요.');
        }
      }).catch(function () {
        if (typeof messageUi.renderPromiseSummaryList === 'function') {
          messageUi.renderPromiseSummaryList([]);
        }
        if (typeof messageUi.setPromiseSummaryText === 'function') {
          messageUi.setPromiseSummaryText('실행예산 조회 목록을 불러오지 못했습니다.');
        }
      }).finally(function () {
        setSendingState(false);
        helperActions.focusInput();
      });
    }

    function handlePromiseSummarySelect(button) {
      const projectNumber = String(button.getAttribute('data-project-number') || '').trim();
      const projectName = String(button.getAttribute('data-project-name') || '').trim();
      const executionTotal = Number(button.getAttribute('data-execution-total') || 0);
      const finalCostTotal = Number(button.getAttribute('data-final-cost-total') || 0);
      if (!projectNumber) {
        messageUi.setPromiseSummaryText('선택한 실행예산 상세를 찾지 못했습니다.');
        return;
      }
      const loadingLabel = projectName
        ? (projectNumber + ' · ' + projectName + ' 월별 데이터를 불러오는 중입니다.')
        : (projectNumber + ' 월별 데이터를 불러오는 중입니다.');
      messageUi.setPromiseSummaryText(loadingLabel);
      if (typeof messageUi.clearPromiseMonthlyBreakdown === 'function') {
        messageUi.clearPromiseMonthlyBreakdown();
      }
      setSendingState(true);
      chatApi.getPromiseProjectSummary(projectNumber).then(function (summary) {
        if (typeof messageUi.renderPromiseMonthlyBreakdown === 'function') {
          const payload = Object.assign({}, summary || {});
          payload.project_number = String(payload.project_number || projectNumber).trim();
          payload.project_name = String(payload.project_name || projectName).trim();
          payload.execution_total = Number(payload.execution_total || executionTotal || 0);
          payload.final_cost_total = Number(payload.final_cost_total || finalCostTotal || 0);
          messageUi.renderPromiseMonthlyBreakdown(payload);
        }
      }).catch(function () {
        messageUi.setPromiseSummaryText('월별 실행예산 상세를 불러오지 못했습니다.');
      }).finally(function () {
        setSendingState(false);
        helperActions.focusInput();
      });
    }

    function handleChatAreaClick(event) {
      const button = event.target && event.target.closest ? event.target.closest(
        '[data-action="report-generate-confirm"], [data-action="report-generate-cancel"], [data-action="weekly-report-generate-confirm"], ' +
        '[data-action="weekly-report-generate-cancel"], [data-action="meeting-room-back-to-building"], [data-action="meeting-room-back-to-floor"], ' +
        '[data-action="meeting-room-back-to-room"], [data-action="meeting-open-event"], ' +
        '[data-action="meeting-room-book-confirm"], [data-action="meeting-room-book-cancel"], [data-action="calendar-event-submit"], [data-action="calendar-event-cancel"], ' +
        '[data-action="promise-mode-view"], [data-action="promise-mode-register"], [data-action="promise-summary-select"], ' +
        '[data-action="promise-detail-back"], ' +
        '[data-action="promise-card-cancel"], [data-action="finance-card-submit"], [data-action="finance-card-cancel"], ' +
        '[data-action="hr-card-submit"], [data-action="hr-card-cancel"], [data-action="hitl-confirm-approve"], [data-action="hitl-confirm-reject"], ' +
        '[data-action="next-action-run"], [data-action="reply-tone-generate"], [data-action="reply-draft-open"]'
      ) : null;
      if (!button) return;
      const action = String(button.dataset.action || '').trim();
      const cancelMap = {
        'report-generate-cancel': { key: 'pendingReportContext', message: '보고서 생성을 취소했습니다.' },
        'weekly-report-generate-cancel': { key: 'pendingWeeklyReportContext', message: '주간보고 생성을 취소했습니다.' },
        'meeting-room-book-cancel': { key: 'pendingMeetingRoomContext', message: '회의실 예약을 취소했습니다.' },
      };
      if (cancelMap[action]) {
        return cancelAction(cancelMap[action].key, cancelMap[action].message);
      }
      if (action === 'calendar-event-cancel') {
        return cancelAction('pendingCalendarContext', '일정 등록을 취소했습니다.', function () {
          if (typeof messageUi.clearCalendarEventCards === 'function') {
            messageUi.clearCalendarEventCards();
          }
        });
      }
      const clickActionHandlers = {
        'meeting-open-event': function () { return helperActions.openMeetingEvent(button); },
        'next-action-run': function () { return helperActions.handleNextActionRun(button); },
        'reply-tone-generate': function () { return helperActions.handleReplyToneGenerate(button); },
        'reply-draft-open': function () { return helperActions.handleReplyDraftOpen(button); },
        'meeting-room-back-to-building': handleMeetingBackToBuilding,
        'meeting-room-back-to-floor': handleMeetingBackToFloor,
        'meeting-room-back-to-room': handleMeetingBackToRoom,
        'promise-card-cancel': function () { return cancelAction('pendingPromiseContext', '실행예산 작업을 취소했습니다.'); },
        'finance-card-cancel': function () { return cancelAction('pendingFinanceContext', '비용정산 작업을 취소했습니다.'); },
        'hr-card-cancel': function () { return cancelAction('pendingHrContext', '근태/휴가 신청을 취소했습니다.'); },
      };
      if (clickActionHandlers[action]) {
        return clickActionHandlers[action]();
      }
      if (action === 'hitl-confirm-approve' || action === 'hitl-confirm-reject') return helperActions.handleHilConfirm(button, action);
      if (action === 'report-generate-confirm') return handleReportGenerateConfirm();
      if (action === 'meeting-room-book-confirm') return helperActions.handleMeetingRoomBookConfirm();
      if (action === 'calendar-event-submit') return helperActions.handleCalendarEventSubmit();
      if (action === 'promise-mode-view') return handlePromiseModeView();
      if (action === 'promise-mode-register') return helperActions.openPromiseRegisterPage();
      if (action === 'promise-detail-back') return resetPromiseViewToList();
      if (action === 'promise-summary-select') return handlePromiseSummarySelect(button);
      if (action === 'finance-card-submit') return helperActions.handleFinanceSubmit();
      if (action === 'hr-card-submit') return helperActions.handleHrSubmit();
      if (action === 'weekly-report-generate-confirm') return helperActions.handleWeeklyReportConfirm();
    }

    function bindChatAreaActions() {
      const chatArea = byId('chatArea');
      if (!chatArea) return;
      chatArea.addEventListener('click', handleChatAreaClick);
      chatArea.addEventListener('change', changeHandlers.handleChatAreaChange);
    }

    return { bindChatAreaActions: bindChatAreaActions };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  global.TaskpaneChatActionDispatch = api;
})(typeof window !== 'undefined' ? window : globalThis);
