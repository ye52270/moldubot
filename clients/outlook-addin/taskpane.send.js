/* ========================================
   MolduBot – Taskpane Send Flow
   ======================================== */

(function initTaskpaneSend(global) {
  function create(options) {
    const byId = options.byId;
    const chatApi = options.chatApi;
    const messageUi = options.messageUi;
    const state = options.state;
    const handleProgress = options.handleProgress;
    const selectionController = options.selectionController;
    const setSendingState = options.setSendingState;
    const clearProgressWithMinimumVisibility = options.clearProgressWithMinimumVisibility;
    const logClientEvent = options.logClientEvent;
    const isReportGenerationQuery = options.isReportGenerationQuery;
    const isWeeklyReportGenerationQuery = options.isWeeklyReportGenerationQuery;
    const isMeetingRoomBookingQuery = options.isMeetingRoomBookingQuery;
    const isCurrentMailMeetingRoomSuggestionQuery = options.isCurrentMailMeetingRoomSuggestionQuery;
    const isCalendarEventQuery = options.isCalendarEventQuery || function () { return false; };
    const isCurrentMailCalendarSuggestionQuery = options.isCurrentMailCalendarSuggestionQuery || function () { return false; };
    const isPromiseBudgetQuery = options.isPromiseBudgetQuery;
    const isFinanceSettlementQuery = options.isFinanceSettlementQuery;
    const isHrApplyQuery = options.isHrApplyQuery;
    const buildMeetingRoomHilMessage = options.buildMeetingRoomHilMessage;
    const moduleLoaderFactory =
      (global.TaskpaneModuleLoader && typeof global.TaskpaneModuleLoader.create === 'function')
        ? global.TaskpaneModuleLoader
        : (typeof module !== 'undefined' && module.exports ? require('./taskpane.module_loader.js') : null);
    const moduleLoader = moduleLoaderFactory && typeof moduleLoaderFactory.create === 'function'
      ? moduleLoaderFactory.create()
      : { resolveModule: function () { return null; } };
    const resolveModule = moduleLoader.resolveModule;
    const handlersModule = resolveModule('TaskpaneSendHandlers', './taskpane.send.handlers.js');
    const branchHandlers = handlersModule && typeof handlersModule.create === 'function'
      ? handlersModule.create({
        chatApi: chatApi,
        messageUi: messageUi,
        state: state,
        selectionController: selectionController,
        clearProgressWithMinimumVisibility: clearProgressWithMinimumVisibility,
      })
      : null;

    function filterNextActionsMetadata(metadata) {
      if (!state || typeof state.filterNextActionsMetadata !== 'function') {
        return metadata && typeof metadata === 'object' ? metadata : {};
      }
      return state.filterNextActionsMetadata(metadata);
    }

    async function runReportGeneration(emailContent, emailSubject, emailReceivedDate, emailSender) {
      messageUi.ensureReportProgressCard();
      await chatApi.requestReportReply(emailContent, emailSubject, function (eventPayload) {
        const eventType = String(eventPayload && eventPayload.type ? eventPayload.type : '').trim();
        if (eventType === 'step') {
          messageUi.updateReportStep(eventPayload.step, eventPayload.status, eventPayload.label);
          return;
        }
        if (eventType === 'done') {
          messageUi.completeReportProgress(
            eventPayload.docx_url || '',
            eventPayload.preview_url || '',
            emailSubject || ''
          );
          return;
        }
        if (eventType === 'error') {
          messageUi.addMessage('assistant', String(eventPayload.message || '보고서 생성 중 오류가 발생했습니다.'));
        }
      }, {
        emailReceivedDate: String(emailReceivedDate || ''),
        emailSender: String(emailSender || ''),
      });
    }

    async function runWeeklyReportGeneration(weekOffset, reportAuthor) {
      messageUi.ensureReportProgressCard();
      await chatApi.requestWeeklyReportReply(weekOffset, reportAuthor, function (eventPayload) {
        const eventType = String(eventPayload && eventPayload.type ? eventPayload.type : '').trim();
        if (eventType === 'step') {
          messageUi.updateReportStep(eventPayload.step, eventPayload.status, eventPayload.label);
          return;
        }
        if (eventType === 'done') {
          messageUi.completeReportProgress(
            eventPayload.docx_url || '',
            eventPayload.preview_url || '',
            String(eventPayload.report_title || '주간보고가 생성됐습니다.')
          );
          return;
        }
        if (eventType === 'error') {
          messageUi.addMessage('assistant', String(eventPayload.message || '주간보고 생성 중 오류가 발생했습니다.'));
        }
      });
    }

    async function sendMessage() {
      const input = byId('chatInput');
      if (!input || state.isSendingRef()) return;
      const text = String(input.value || '').trim();
      if (!text) return;
      const requestStartedAt = Date.now();

      messageUi.addMessage('user', text);
      if (messageUi && typeof messageUi.clearClarificationToast === 'function') {
        messageUi.clearClarificationToast();
      }
      input.value = '';

      setSendingState(true);
      state.setProgressShownAtMs(Date.now());
      try {
        if (isReportGenerationQuery(text)) {
          if (branchHandlers && typeof branchHandlers.handleReportGenerationQuery === 'function') {
            await branchHandlers.handleReportGenerationQuery(text);
          }
          return;
        }
        if (isWeeklyReportGenerationQuery(text)) {
          if (branchHandlers && typeof branchHandlers.handleWeeklyReportGenerationQuery === 'function') {
            branchHandlers.handleWeeklyReportGenerationQuery();
          }
          return;
        }
        if (isCurrentMailMeetingRoomSuggestionQuery(text)) {
          if (branchHandlers && typeof branchHandlers.handleCurrentMailMeetingSuggestionQuery === 'function') {
            await branchHandlers.handleCurrentMailMeetingSuggestionQuery(text);
          }
          return;
        }
        if (isMeetingRoomBookingQuery(text)) {
          if (branchHandlers && typeof branchHandlers.handleMeetingRoomBookingQuery === 'function') {
            await branchHandlers.handleMeetingRoomBookingQuery(text);
          }
          return;
        }
        if (isCurrentMailCalendarSuggestionQuery(text)) {
          if (branchHandlers && typeof branchHandlers.handleCurrentMailCalendarSuggestionQuery === 'function') {
            await branchHandlers.handleCurrentMailCalendarSuggestionQuery(text);
          }
          return;
        }
        if (isCalendarEventQuery(text)) {
          if (branchHandlers && typeof branchHandlers.handleCalendarEventQuery === 'function') {
            branchHandlers.handleCalendarEventQuery(text);
          }
          return;
        }
        if (isPromiseBudgetQuery(text)) {
          if (branchHandlers && typeof branchHandlers.handlePromiseBudgetQuery === 'function') {
            branchHandlers.handlePromiseBudgetQuery(text);
          }
          return;
        }
        if (isFinanceSettlementQuery(text)) {
          if (branchHandlers && typeof branchHandlers.handleFinanceSettlementQuery === 'function') {
            await branchHandlers.handleFinanceSettlementQuery(text);
          }
          return;
        }
        if (isHrApplyQuery(text)) {
          if (branchHandlers && typeof branchHandlers.handleHrApplyQuery === 'function') {
            branchHandlers.handleHrApplyQuery(text);
          }
          return;
        }
        const assistantPayload = await chatApi.requestAssistantReply(text, handleProgress, null);
        const assistantReply = assistantPayload && assistantPayload.answer ? assistantPayload.answer : '응답을 생성하지 못했습니다.';
        const assistantMetadata = filterNextActionsMetadata(
          assistantPayload && assistantPayload.metadata ? assistantPayload.metadata : {}
        );
        messageUi.addMessage('assistant', assistantReply, assistantMetadata);
        if (messageUi && typeof messageUi.showClarificationToast === 'function') {
          messageUi.showClarificationToast(assistantMetadata);
        }
        const serverElapsedMs = Number(assistantMetadata && assistantMetadata.elapsed_ms);
        const effectiveElapsedMs = Number.isFinite(serverElapsedMs) && serverElapsedMs > 0
          ? serverElapsedMs
          : (Date.now() - requestStartedAt);
        if (typeof messageUi.addElapsedDivider === 'function') {
          messageUi.addElapsedDivider(effectiveElapsedMs);
        }
        clearProgressWithMinimumVisibility();
      } catch (error) {
        logClientEvent('error', 'send_message_failed', {
          message: text,
          error: String(error && error.message ? error.message : error),
        });
        clearProgressWithMinimumVisibility();
        if (error && String(error.message || '') === 'stale-selection-context') {
          messageUi.addMessage('assistant', '메일 변경이 아직 반영되지 않았습니다. 다른 메일을 다시 클릭한 뒤 재시도해 주세요.');
        } else {
          messageUi.addMessage('assistant', '응답을 가져오는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
        }
      } finally {
        setSendingState(false);
        input.focus();
      }
    }

    return {
      buildMeetingRoomHilMessage: buildMeetingRoomHilMessage,
      runReportGeneration: runReportGeneration,
      runWeeklyReportGeneration: runWeeklyReportGeneration,
      sendMessage: sendMessage,
    };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneSend = api;
})(typeof window !== 'undefined' ? window : globalThis);
