/* ========================================
   MolduBot – Taskpane Chat API
   ======================================== */

(function initTaskpaneApi(global) {
  function create(options) {
    const selectionController = options.selectionController;
    const isCurrentMailQuery = options.isCurrentMailQuery;
    const logClientEvent = options.logClientEvent;
    const shortId = options.shortId;
    const freshIdWaitMs = Number(options.freshIdWaitMs || 1800);
    const freshIdPollMs = Number(options.freshIdPollMs || 250);
    const moduleLoaderFactory =
      (global.TaskpaneModuleLoader && typeof global.TaskpaneModuleLoader.create === 'function')
        ? global.TaskpaneModuleLoader
        : (typeof module !== 'undefined' && module.exports ? require('./taskpane.module_loader.js') : null);
    const moduleLoader = moduleLoaderFactory && typeof moduleLoaderFactory.create === 'function'
      ? moduleLoaderFactory.create()
      : { resolveModule: function () { return null; } };
    const resolveModule = moduleLoader.resolveModule;
    const endpointModule = resolveModule('TaskpaneApiEndpoints', './taskpane.api.endpoints.js');
    const streamModule = resolveModule('TaskpaneApiStream', './taskpane.api.stream.js');
    const endpointApi = endpointModule && typeof endpointModule.createEndpointApi === 'function'
      ? endpointModule.createEndpointApi({
        fetchRef: fetch,
        buildJsonHeaders: buildJsonHeaders,
      })
      : null;
    const streamApi = streamModule && typeof streamModule.create === 'function'
      ? streamModule.create(fetch)
      : null;
    let activeThreadId = '';

    function buildJsonHeaders(includeContentType) {
      const headers = {
        Accept: 'application/json',
        'ngrok-skip-browser-warning': 'true',
      };
      if (includeContentType) headers['Content-Type'] = 'application/json';
      return headers;
    }

    function buildChatRequestBody(message, selectionContext, threadId, runtimeOptions) {
      const payload = {
        message: message,
        thread_id: String(threadId || '').trim() || null,
        email_id: selectionContext.emailId,
        mailbox_user: selectionContext.mailboxUser,
      };
      if (runtimeOptions && typeof runtimeOptions === 'object') {
        payload.runtime_options = runtimeOptions;
      }
      return payload;
    }

    async function requestAssistantReply(message, onProgress, runtimeOptions, onToken) {
      let selectionContext = await selectionController.getSelectionContext({
        allowCacheFallback: !isCurrentMailQuery(message),
      });

      logClientEvent('info', 'selection_context_before_send', {
        query_type: isCurrentMailQuery(message) ? 'current_mail' : 'general',
        reason: String(selectionContext.reason || ''),
        email_id: shortId(selectionContext.emailId),
        mailbox_user: String(selectionContext.mailboxUser || ''),
        direct_item_id: shortId(selectionContext.directItemId || ''),
        async_item_id: shortId(selectionContext.asyncItemId || ''),
        selected_item_id: shortId(selectionContext.selectedItemId || ''),
        selection_revision: selectionController.getSelectionRevision(),
      });

      if (selectionController.isStaleCurrentMailSelection(isCurrentMailQuery, message, selectionContext)) {
        const awaitedContext = await selectionController.waitForSelectionChange(
          String(selectionContext.emailId || ''),
          freshIdWaitMs,
          freshIdPollMs
        );
        if (awaitedContext) {
          selectionContext = awaitedContext;
        } else {
          logClientEvent('warning', 'selection_context_stale_detected', {
            email_id: shortId(selectionContext.emailId),
            selection_revision: selectionController.getSelectionRevision(),
          });
          throw new Error('stale-selection-context');
        }
      }

      logClientEvent('info', 'selection_context_effective_send', {
        query_type: isCurrentMailQuery(message) ? 'current_mail' : 'general',
        email_id: shortId(selectionContext.emailId),
        mailbox_user: String(selectionContext.mailboxUser || ''),
        reason: String(selectionContext.reason || ''),
        selection_revision: selectionController.getSelectionRevision(),
      });

      if (!selectionContext.emailId || !selectionContext.mailboxUser) {
        logClientEvent('warning', 'selection_context_empty', {
          email_id_present: Boolean(selectionContext.emailId),
          mailbox_user_present: Boolean(selectionContext.mailboxUser),
          reason: String(selectionContext.reason || ''),
        });
      }

      const requestBody = buildChatRequestBody(message, selectionContext, activeThreadId, runtimeOptions || null);
      let payload = null;
      let usedStream = false;
      const streamResponse = await fetch('/search/chat/stream', {
        method: 'POST',
        headers: buildJsonHeaders(true),
        body: JSON.stringify(requestBody),
      });
      if (streamResponse.ok && streamApi && typeof streamApi.readCompletionPayload === 'function') {
        payload = await streamApi.readCompletionPayload(streamResponse, onProgress, onToken);
        usedStream = Boolean(payload);
      }
      if (!usedStream) {
        const response = await fetch('/search/chat', {
          method: 'POST',
          headers: buildJsonHeaders(true),
          body: JSON.stringify(requestBody),
        });
        if (!response.ok) {
          throw new Error('chat request failed: ' + response.status);
        }
        payload = await response.json();
      }
      if (payload && typeof payload.thread_id === 'string' && payload.thread_id.trim()) {
        activeThreadId = payload.thread_id.trim();
      }

      if (isCurrentMailQuery(message) && selectionContext.emailId) {
        selectionController.markCurrentMailSent(selectionContext.emailId);
      }
      const answerText = String(payload && payload.answer ? payload.answer : '').trim() || '응답을 생성하지 못했습니다.';
      const metadata = payload && typeof payload.metadata === 'object' && payload.metadata ? payload.metadata : {};
      return {
        answer: answerText,
        metadata: metadata,
      };
    }

    async function requestReportReply(emailContent, emailSubject, onEvent, options) {
      const requestBody = {
        email_content: String(emailContent || '').trim(),
        email_subject: String(emailSubject || '메일 보고서').trim() || '메일 보고서',
        email_received_date: String(options && options.emailReceivedDate ? options.emailReceivedDate : '').trim(),
        email_sender: String(options && options.emailSender ? options.emailSender : '').trim(),
      };
      if (!streamApi || typeof streamApi.streamEvents !== 'function') {
        throw new Error('api-stream-module-missing:report');
      }
      await streamApi.streamEvents(
        '/report/generate',
        requestBody,
        onEvent,
        'report request failed',
        'report-stream-body-unavailable'
      );
    }

    async function requestWeeklyReportReply(weekOffset, reportAuthor, onEvent) {
      const requestBody = {
        week_offset: Number(weekOffset || 1),
        report_author: String(reportAuthor || '').trim(),
      };
      if (!streamApi || typeof streamApi.streamEvents !== 'function') {
        throw new Error('api-stream-module-missing:weekly-report');
      }
      await streamApi.streamEvents(
        '/report/weekly/generate',
        requestBody,
        onEvent,
        'weekly report request failed',
        'weekly-report-stream-body-unavailable'
      );
    }

    function resetThread() {
      activeThreadId = '';
    }

    function resolveEndpointMethod(name) {
      if (endpointApi && typeof endpointApi[name] === 'function') return endpointApi[name];
      return async function () {
        throw new Error('api-endpoint-module-missing:' + String(name || 'unknown'));
      };
    }

    return {
      requestAssistantReply: requestAssistantReply,
      requestReportReply: requestReportReply,
      requestWeeklyReportReply: requestWeeklyReportReply,
      listMeetingRoomBuildings: resolveEndpointMethod('listMeetingRoomBuildings'),
      listMeetingRoomFloors: resolveEndpointMethod('listMeetingRoomFloors'),
      listMeetingRooms: resolveEndpointMethod('listMeetingRooms'),
      bookMeetingRoom: resolveEndpointMethod('bookMeetingRoom'),
      suggestMeetingFromCurrentMail: resolveEndpointMethod('suggestMeetingFromCurrentMail'),
      suggestCalendarFromCurrentMail: resolveEndpointMethod('suggestCalendarFromCurrentMail'),
      createCalendarEvent: resolveEndpointMethod('createCalendarEvent'),
      requestChatConfirm: resolveEndpointMethod('requestChatConfirm'),
      listPromiseProjects: resolveEndpointMethod('listPromiseProjects'),
      listPromiseSummaries: resolveEndpointMethod('listPromiseSummaries'),
      getPromiseProjectSummary: resolveEndpointMethod('getPromiseProjectSummary'),
      listPromiseDrafts: resolveEndpointMethod('listPromiseDrafts'),
      submitPromiseDraft: resolveEndpointMethod('submitPromiseDraft'),
      listFinanceProjects: resolveEndpointMethod('listFinanceProjects'),
      getFinanceProjectBudget: resolveEndpointMethod('getFinanceProjectBudget'),
      submitFinanceClaim: resolveEndpointMethod('submitFinanceClaim'),
      submitHrRequest: resolveEndpointMethod('submitHrRequest'),
      resetThread: resetThread,
      _parseSseChunk: streamApi && typeof streamApi.parseSseChunk === 'function'
        ? streamApi.parseSseChunk
        : function () { return null; },
    };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneApi = api;
})(typeof window !== 'undefined' ? window : globalThis);
