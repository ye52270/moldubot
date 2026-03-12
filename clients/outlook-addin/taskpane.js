(function () {
  const UI_BUILD = '20260304-17';
  const MIN_PROGRESS_VISIBLE_MS = 800;
  const BOOTSTRAP_FALLBACK_MS = 1200;
  const COPIED_RESET_MS = 1300;
  const FRESH_ID_WAIT_MS = 1800;
  const FRESH_ID_POLL_MS = 250;
  const EVAL_PAGE_PATH = '/addin/chat-eval.html';
  const SELECTED_MAIL_SYNC_MS = 900;

  let isSending = false;
  let bootstrapFallbackTimer = null;
  let progressShownAtMs = 0;

  const moduleLoaderFactory =
    (typeof window !== 'undefined' && window.TaskpaneModuleLoader && typeof window.TaskpaneModuleLoader.create === 'function')
      ? window.TaskpaneModuleLoader
      : (typeof module !== 'undefined' && module.exports ? require('./taskpane.module_loader.js') : null);
  const moduleLoader = moduleLoaderFactory && typeof moduleLoaderFactory.create === 'function'
    ? moduleLoaderFactory.create()
    : { resolveModule: function () { return null; } };
  const resolveModule = moduleLoader.resolveModule;
  function resolveSelectionModule() {
    const moduleRef = resolveModule('TaskpaneSelectionController', './taskpane.selection.js');
    if (moduleRef && typeof moduleRef.create === 'function') return moduleRef;
    return null;
  }
  function createNoopSelectionController() {
    const empty = {
      emailId: '',
      mailboxUser: '',
      reason: 'selection_module_missing',
      directItemId: '',
      asyncItemId: '',
      selectedItemId: '',
    };
    const controller = {
      clearSelectionCache: function () {},
      getSelectionContext: async function () { return empty; },
      getSelectionRevision: function () { return 0; },
      getSelectionStateSnapshot: function () { return { selectionRevision: 0, cachedEmailId: '', cachedMailboxUser: '' }; },
      isStaleCurrentMailSelection: function () { return false; },
      readMailboxUser: function () { return ''; },
      resolveMailboxWithRetry: async function () { return null; },
      resolveSelectionContextOnce: async function () { return empty; },
      setCachedSelectionContextForTest: function () {},
    };
    ['markCurrentMailSent', 'startSelectionPolling', 'clearSelectionCache', 'setCachedSelectionContextForTest']
      .forEach(function (name) {
        controller[name] = function () {};
      });
    ['observeSelectionChanges', 'pollSelectionContext', 'registerSelectionObserver']
      .forEach(function (name) {
        controller[name] = async function () { return false; };
      });
    controller.waitForSelectionChange = async function () { return null; };
    controller.collectSelectionEventTypes = function () { return []; };
    controller.createSelectionChangedHandler = function () { return function () {}; };
    return controller;
  }
  const helpersModule = resolveModule('TaskpaneHelpers', './taskpane.helpers.js');
  const messagesModule = resolveModule('TaskpaneMessages', './taskpane.messages.js');
  const interactionsModule = resolveModule('TaskpaneInteractions', './taskpane.interactions.js');
  const apiModule = resolveModule('TaskpaneApi', './taskpane.api.js');
  const sendModule = resolveModule('TaskpaneSend', './taskpane.send.js');
  const chatActionsModule = resolveModule('TaskpaneChatActions', './taskpane.chat_actions.js');
  const runtimeHelpersModule = resolveModule('TaskpaneRuntimeHelpers', './taskpane.runtime_helpers.js');
  const quickPromptsModule = resolveModule('TaskpaneQuickPrompts', './taskpane.quick_prompts.js');
  const stateModule = resolveModule('TaskpaneState', './taskpane.state.js');
  const bootstrapModule = resolveModule('TaskpaneBootstrap', './taskpane.bootstrap.js');
  const selectionModule = resolveSelectionModule();
  const state = stateModule && typeof stateModule.create === 'function'
    ? stateModule.create({
      getIsSending: function () { return isSending; },
      setProgressShownAtMs: function (value) { progressShownAtMs = Number(value || 0); },
    })
    : null;
  if (!helpersModule || !messagesModule || !interactionsModule || !apiModule || !sendModule || !chatActionsModule || !runtimeHelpersModule || !bootstrapModule || !state) {
    return;
  }
  const byId = helpersModule.byId;
  const shortId = helpersModule.shortId;
  const sleep = helpersModule.sleep;
  const escapeHtml = helpersModule.escapeHtml;
  const escapeAttr = helpersModule.escapeAttr || escapeHtml;
  const isCurrentMailQuery = helpersModule.isCurrentMailQuery;
  const isQuickPromptTrigger = helpersModule.isQuickPromptTrigger || function () { return false; };
  const getQuickPromptTemplates = helpersModule.getQuickPromptTemplates || function () { return []; };
  const isReportGenerationQuery = helpersModule.isReportGenerationQuery || function () { return false; };
  const isWeeklyReportGenerationQuery = helpersModule.isWeeklyReportGenerationQuery || function () { return false; };
  const isMeetingRoomBookingQuery = helpersModule.isMeetingRoomBookingQuery || function () { return false; };
  const isCurrentMailMeetingRoomSuggestionQuery = helpersModule.isCurrentMailMeetingRoomSuggestionQuery || function () { return false; };
  const isCalendarEventQuery = helpersModule.isCalendarEventQuery || function () { return false; };
  const isCurrentMailCalendarSuggestionQuery = helpersModule.isCurrentMailCalendarSuggestionQuery || function () { return false; };
  const isPromiseBudgetQuery = helpersModule.isPromiseBudgetQuery || function () { return false; };
  const isFinanceSettlementQuery = helpersModule.isFinanceSettlementQuery || function () { return false; };
  const isHrApplyQuery = helpersModule.isHrApplyQuery || function () { return false; };
  const logClientEvent = helpersModule.logClientEvent;
  const selectionController = selectionModule
    ? selectionModule.create({
      windowRef: window,
      logClientEvent: logClientEvent,
      shortId: shortId,
      sleep: sleep,
      contextRetryCount: 10,
      contextRetryDelayMs: 220,
      officeReadyWaitMs: 900,
      officeMailboxRetryCount: 5,
      officeMailboxRetryDelayMs: 100,
      officeItemRetryCount: 4,
      officeItemRetryDelayMs: 90,
      selectionPollIntervalMs: 1200,
    })
    : createNoopSelectionController();
  const messageUi = messagesModule.create({ byId: byId, escapeHtml: escapeHtml, escapeAttr: escapeAttr });
  const chatApi = apiModule.create({
    selectionController: selectionController,
    isCurrentMailQuery: isCurrentMailQuery,
    logClientEvent: logClientEvent,
    shortId: shortId,
    freshIdWaitMs: FRESH_ID_WAIT_MS,
    freshIdPollMs: FRESH_ID_POLL_MS,
  });
  const runtimeHelpers = runtimeHelpersModule.create({
    byId: byId,
    shortId: shortId,
    logClientEvent: logClientEvent,
    windowRef: window,
  });

  function handleProgress(progressEvent) {
    const mapped = runtimeHelpers.mapProgressMessage(progressEvent || {});
    if (!mapped.text) return;
    messageUi.setProgressStatus(mapped.text, mapped.phase, {
      detail: mapped.detail,
      step: mapped.step,
      total: mapped.total,
    });
    progressShownAtMs = Date.now();
  }

  function clearProgressWithMinimumVisibility() {
    const now = Date.now();
    const elapsedMs = progressShownAtMs > 0 ? now - progressShownAtMs : MIN_PROGRESS_VISIBLE_MS;
    const delayMs = elapsedMs >= MIN_PROGRESS_VISIBLE_MS ? 0 : MIN_PROGRESS_VISIBLE_MS - elapsedMs;
    setTimeout(function () {
      messageUi.clearProgressStatus();
      progressShownAtMs = 0;
    }, delayMs);
  }

  function setSendingState(nextState) {
    isSending = Boolean(nextState);
    messageUi.setSendingState(isSending);
  }

  function openEvalPage() {
    const opened = window.open(EVAL_PAGE_PATH, '_blank');
    if (!opened) window.location.href = EVAL_PAGE_PATH;
  }

  const sender = sendModule.create({
    byId: byId,
    chatApi: chatApi,
    messageUi: messageUi,
    state: state,
    handleProgress: handleProgress,
    selectionController: selectionController,
    setSendingState: setSendingState,
    clearProgressWithMinimumVisibility: clearProgressWithMinimumVisibility,
    logClientEvent: logClientEvent,
    isReportGenerationQuery: isReportGenerationQuery,
    isWeeklyReportGenerationQuery: isWeeklyReportGenerationQuery,
    isMeetingRoomBookingQuery: isMeetingRoomBookingQuery,
    isCurrentMailMeetingRoomSuggestionQuery: isCurrentMailMeetingRoomSuggestionQuery,
    isCalendarEventQuery: isCalendarEventQuery,
    isCurrentMailCalendarSuggestionQuery: isCurrentMailCalendarSuggestionQuery,
    isPromiseBudgetQuery: isPromiseBudgetQuery,
    isFinanceSettlementQuery: isFinanceSettlementQuery,
    isHrApplyQuery: isHrApplyQuery,
    buildMeetingRoomHilMessage: runtimeHelpers.buildMeetingRoomHilMessage,
  });

  const chatActions = chatActionsModule.create({
    windowRef: window,
    byId: byId,
    chatApi: chatApi,
    messageUi: messageUi,
    state: state,
    setSendingState: setSendingState,
    handleProgress: handleProgress,
    runReportGeneration: sender.runReportGeneration,
    runWeeklyReportGeneration: sender.runWeeklyReportGeneration,
    sanitizeMeetingHilMetadata: runtimeHelpers.sanitizeMeetingHilMetadata,
    setMeetingRoomBookingButtonLabel: runtimeHelpers.setMeetingRoomBookingButtonLabel,
    buildMeetingRoomHilMessage: sender.buildMeetingRoomHilMessage,
    buildCalendarEventHilMessage: runtimeHelpers.buildCalendarEventHilMessage,
    openReplyCompose: runtimeHelpers.openReplyCompose,
  });

  const interactions = interactionsModule.create({
    byId: byId,
    logClientEvent: logClientEvent,
    copiedResetMs: COPIED_RESET_MS,
    addMessage: messageUi.addMessage,
    setSendingState: setSendingState,
    requestAssistantReply: chatApi.requestAssistantReply,
    openEvidenceMail: runtimeHelpers.openEvidenceMail,
  });
  const quickPrompts = quickPromptsModule
    ? quickPromptsModule.create({
      escapeHtml: escapeHtml,
      escapeAttr: escapeAttr,
      isQuickPromptTrigger: isQuickPromptTrigger,
      getQuickPromptTemplates: getQuickPromptTemplates,
      maxVisible: 20,
    })
    : null;

  const bootstrapRunner = bootstrapModule.create({
    windowRef: window,
    documentRef: typeof document !== 'undefined' ? document : null,
    byId: byId,
    sender: sender,
    messageUi: messageUi,
    chatApi: chatApi,
    state: state,
    quickPrompts: quickPrompts,
    chatActions: chatActions,
    interactions: interactions,
    runtimeHelpers: runtimeHelpers,
    selectionController: selectionController,
    shortId: shortId,
    logClientEvent: logClientEvent,
    uiBuild: UI_BUILD,
    selectedMailSyncMs: SELECTED_MAIL_SYNC_MS,
    openEvalPage: openEvalPage,
    setSendingState: setSendingState,
    fetchImpl: typeof fetch === 'function' ? fetch : null,
  });

  function bootstrap() {
    if (bootstrapFallbackTimer) {
      clearTimeout(bootstrapFallbackTimer);
      bootstrapFallbackTimer = null;
    }
    bootstrapRunner.bootstrap();
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      _buildMessageHtml: messageUi.buildMessageHtml,
      _shortId: shortId,
      _isCurrentMailQuery: isCurrentMailQuery,
      _isStaleCurrentMailSelection: function (message, selectionContext) {
        return selectionController.isStaleCurrentMailSelection(isCurrentMailQuery, message, selectionContext);
      },
      _readMailboxUser: selectionController.readMailboxUser,
      _resolveMailboxWithRetry: selectionController.resolveMailboxWithRetry,
      _resolveSelectionContextOnce: selectionController.resolveSelectionContextOnce,
      _waitForSelectionChange: selectionController.waitForSelectionChange,
      _observeSelectionChanges: selectionController.observeSelectionChanges,
      _pollSelectionContext: selectionController.pollSelectionContext,
      _getSelectionStateSnapshot: selectionController.getSelectionStateSnapshot,
      _setCachedSelectionContextForTest: selectionController.setCachedSelectionContextForTest,
      _collectSelectionEventTypes: selectionController.collectSelectionEventTypes,
      _mapProgressMessage: runtimeHelpers.mapProgressMessage,
      _openEvalPagePath: EVAL_PAGE_PATH,
    };
    return;
  }

  if (window.Office && typeof window.Office.onReady === 'function') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', bootstrap, { once: true });
    } else {
      bootstrap();
    }
    bootstrapFallbackTimer = setTimeout(bootstrap, BOOTSTRAP_FALLBACK_MS);
    window.Office.onReady(function () {
      bootstrap();
    });
  } else if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap, { once: true });
  } else {
    bootstrap();
  }
})();
