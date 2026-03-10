/* MolduBot – Taskpane Message UI */
(function initTaskpaneMessages(global) {
  function create(options) {
    var byId = options.byId;
    var escapeHtml = options.escapeHtml;
    var escapeAttr = options.escapeAttr || escapeHtml;
    var moduleLoaderFactory =
      (global.TaskpaneModuleLoader && typeof global.TaskpaneModuleLoader.create === 'function')
        ? global.TaskpaneModuleLoader
        : (typeof module !== 'undefined' && module.exports ? require('./taskpane.module_loader.js') : null);
    var moduleLoader = moduleLoaderFactory && typeof moduleLoaderFactory.create === 'function'
      ? moduleLoaderFactory.create()
      : {
          resolveModule: function () { return null; },
          createRenderer: function (_moduleObj, _moduleOptions, fallback) { return fallback || {}; },
          delegate: function (_moduleObj, _methodName, fallback) { return fallback || function () { return null; }; },
        };
    var resolveModule = moduleLoader.resolveModule;
    var createRenderer = moduleLoader.createRenderer;
    var delegate = moduleLoader.delegate;
    function scrollToBottom() {
      var chatArea = byId('chatArea');
      if (!chatArea) return;
      chatArea.scrollTop = chatArea.scrollHeight;
    }

    function syncWelcomeLayoutState() {
      var appRoot = document.querySelector('.app');
      if (!appRoot) return;
      var welcome = byId('welcomeState');
      if (welcome) {
        appRoot.classList.add('welcome-layout');
        return;
      }
      appRoot.classList.remove('welcome-layout');
    }

    function removeWelcomeStateIfExists() {
      var welcome = byId('welcomeState');
      if (welcome) welcome.remove();
      syncWelcomeLayoutState();
    }

    var richTextModule = resolveModule('TaskpaneMessagesRichText', './taskpane.messages.richtext.js');
    var richTextRenderer = createRenderer(richTextModule, { escapeHtml: escapeHtml, escapeAttr: escapeAttr }, null);
    var richBridgeModule = resolveModule('TaskpaneMessagesRichBridge', './taskpane.messages.rich_bridge.js');
    var richBridge = createRenderer(richBridgeModule, { richTextRenderer: richTextRenderer, escapeHtml: escapeHtml }, null);

    function isNoiseStructuralToken(text) {
      return richBridge && richBridge.isNoiseStructuralToken ? richBridge.isNoiseStructuralToken(text) : false;
    }

    function resolveHeadingClass(text) {
      return richBridge && richBridge.resolveHeadingClass ? richBridge.resolveHeadingClass(text) : 'rich-heading';
    }

    function renderMarkdownTable(headerLine, rowLines) {
      return richBridge && richBridge.renderMarkdownTable ? richBridge.renderMarkdownTable(headerLine, rowLines) : '';
    }

    function renderRichText(text) {
      return richBridge && richBridge.renderRichText ? richBridge.renderRichText(text) : escapeHtml(String(text || ''));
    }

    function applyInlineFormatting(text) {
      return richBridge && richBridge.applyInlineFormatting ? richBridge.applyInlineFormatting(text) : escapeHtml(String(text || ''));
    }

    function highlightCodeBlocks(root) {
      if (richBridge && typeof richBridge.highlightCodeBlocks === 'function') {
        richBridge.highlightCodeBlocks(root);
      }
    }

    var answerFormatRenderer = null;
    function normalizeHeadingToken(text) {
      return answerFormatRenderer && answerFormatRenderer.normalizeHeadingToken
        ? answerFormatRenderer.normalizeHeadingToken(text)
        : '';
    }

    var metaModule = resolveModule('TaskpaneMessagesMeta', './taskpane.messages.meta.js');
    var metaRenderer = createRenderer(metaModule, {
      byId: byId,
      escapeHtml: escapeHtml,
      escapeAttr: escapeAttr,
      applyInlineFormatting: applyInlineFormatting,
      normalizeHeadingToken: normalizeHeadingToken,
    }, null);

    function renderBasicInfoRows(headers, rows) {
      return metaRenderer && metaRenderer.renderBasicInfoRows
        ? metaRenderer.renderBasicInfoRows(headers, rows)
        : '';
    }

    var uiCommonModule = resolveModule('TaskpaneMessagesUiCommon', './taskpane.messages.ui_common.js');
    var uiCommonRenderer = createRenderer(uiCommonModule, { escapeHtml: escapeHtml, escapeAttr: escapeAttr }, null);
    var evidenceUiModule = resolveModule('TaskpaneMessagesEvidenceUi', './taskpane.messages.evidence_ui.js');
    var evidenceUiRenderer = createRenderer(evidenceUiModule, {
      escapeHtml: escapeHtml,
      escapeAttr: escapeAttr,
      uiCommon: uiCommonRenderer,
    }, null);
    var answerSectionsModule = resolveModule('TaskpaneMessagesAnswerSections', './taskpane.messages.answer_sections.js');
    var summaryCardsModule = resolveModule('TaskpaneMessagesSummaryCards', './taskpane.messages.summary_cards.js');

    var answerFormatModule = resolveModule('TaskpaneMessagesAnswerFormat', './taskpane.messages.answer_format.js');
    answerFormatRenderer = createRenderer(answerFormatModule, {
      escapeHtml: escapeHtml,
      escapeAttr: escapeAttr,
      applyInlineFormatting: applyInlineFormatting,
      renderMarkdownTable: renderMarkdownTable,
      renderBasicInfoRows: renderBasicInfoRows,
      resolveHeadingClass: resolveHeadingClass,
      isNoiseStructuralToken: isNoiseStructuralToken,
      uiCommon: uiCommonRenderer,
      summaryCardsModule: summaryCardsModule,
      evidenceUiModule: evidenceUiModule,
      evidenceUi: evidenceUiRenderer,
      answerSectionsModule: answerSectionsModule,
    }, null);

    function renderAnswerFormatBlocks(blocks, metadata) {
      return answerFormatRenderer && answerFormatRenderer.renderAnswerFormatBlocks
        ? answerFormatRenderer.renderAnswerFormatBlocks(blocks, metadata)
        : '';
    }

    var shellModule = resolveModule('TaskpaneMessagesShell', './taskpane.messages.shell.js');
    var shellRenderer = createRenderer(shellModule, { escapeHtml: escapeHtml }, null);

    function actionsHtml(role, sentAtLabel) {
      return shellRenderer && shellRenderer.actionsHtml ? shellRenderer.actionsHtml(role, sentAtLabel) : '';
    }

    function formatMessageTime() {
      return shellRenderer && shellRenderer.formatMessageTime ? shellRenderer.formatMessageTime() : '';
    }

    function buildCodeReviewQualityBar(metadata, text) {
      return shellRenderer && shellRenderer.buildCodeReviewQualityBar
        ? shellRenderer.buildCodeReviewQualityBar(metadata, text)
        : '';
    }

    var composerModule = resolveModule('TaskpaneMessagesComposer', './taskpane.messages.composer.js');
    var composerRenderer = createRenderer(composerModule, {
      escapeHtml: escapeHtml,
      renderRichText: renderRichText,
      renderAnswerFormatBlocks: renderAnswerFormatBlocks,
      formatMessageTime: formatMessageTime,
      actionsHtml: actionsHtml,
      buildCodeReviewQualityBar: buildCodeReviewQualityBar,
      metaRenderer: metaRenderer,
    }, null);

    function buildMessageHtml(role, text, metadata) {
      return composerRenderer && composerRenderer.buildMessageHtml
        ? composerRenderer.buildMessageHtml(role, text, metadata)
        : '';
    }

    function addMessage(role, text, metadata) {
      var chatArea = byId('chatArea');
      if (!chatArea) return;
      removeWelcomeStateIfExists();
      chatArea.insertAdjacentHTML('beforeend', buildMessageHtml(role, text, metadata));
      highlightCodeBlocks(chatArea.lastElementChild || chatArea);
      scrollToBottom();
    }

    function getClarificationToastHost() {
      return byId('clarificationToastHost');
    }

    function clearClarificationToast() {
      var toastHost = getClarificationToastHost();
      if (!toastHost) return;
      toastHost.innerHTML = '';
      toastHost.hidden = true;
    }

    function showClarificationToast(metadata) {
      var toastHost = getClarificationToastHost();
      if (!toastHost) return;
      var clarificationHtml = metaRenderer && metaRenderer.buildScopeClarificationHtml
        ? metaRenderer.buildScopeClarificationHtml(metadata || {})
        : '';
      if (!clarificationHtml) {
        clearClarificationToast();
        return;
      }
      toastHost.innerHTML = clarificationHtml;
      toastHost.hidden = false;
    }

    var statusModule = resolveModule('TaskpaneMessagesStatus', './taskpane.messages.status.js');
    var statusRenderer = createRenderer(statusModule, {
      byId: byId,
      escapeHtml: escapeHtml,
      escapeAttr: escapeAttr,
      removeWelcomeStateIfExists: removeWelcomeStateIfExists,
      scrollToBottom: scrollToBottom,
      syncWelcomeLayoutState: syncWelcomeLayoutState,
    }, null);

    function addElapsedDivider(elapsedMs) {
      if (statusRenderer && statusRenderer.addElapsedDivider) statusRenderer.addElapsedDivider(elapsedMs);
    }

    function resetSession() {
      if (statusRenderer && statusRenderer.resetSession) statusRenderer.resetSession();
    }

    function setProgressStatus(text, phase, progressOptions) {
      if (statusRenderer && statusRenderer.setProgressStatus) {
        statusRenderer.setProgressStatus(text, phase, progressOptions);
      }
    }

    function clearProgressStatus() {
      if (statusRenderer && statusRenderer.clearProgressStatus) statusRenderer.clearProgressStatus();
    }

    var cardFactoryOptions = {
      byId: byId,
      escapeHtml: escapeHtml,
      escapeAttr: escapeAttr,
      scrollToBottom: scrollToBottom,
      removeWelcomeStateIfExists: removeWelcomeStateIfExists,
    };
    var reportRenderer = createRenderer(resolveModule('TaskpaneMessagesReportCards', './taskpane.messages.report_cards.js'), cardFactoryOptions, {});
    var meetingRenderer = createRenderer(resolveModule('TaskpaneMessagesMeetingCards', './taskpane.messages.meeting_cards.js'), cardFactoryOptions, {});
    var legacyRenderer = createRenderer(resolveModule('TaskpaneMessagesLegacyCards', './taskpane.messages.legacy_cards.js'), cardFactoryOptions, {});

    function setSendingState(nextState) {
      var sendBtn = byId('sendBtn');
      var input = byId('chatInput');
      var isSending = Boolean(nextState);
      if (sendBtn) sendBtn.disabled = isSending;
      if (input) input.disabled = isSending;
    }
    function attachDelegates(target, source, methodNames) {
      methodNames.forEach(function (name) {
        target[name] = delegate(source, name);
      });
    }

    var api = {
      scrollToBottom: scrollToBottom,
      syncWelcomeLayoutState: syncWelcomeLayoutState,
      removeWelcomeStateIfExists: removeWelcomeStateIfExists,
      buildMessageHtml: buildMessageHtml,
      addMessage: addMessage,
      showClarificationToast: showClarificationToast,
      clearClarificationToast: clearClarificationToast,
      addElapsedDivider: addElapsedDivider,
      getSelectedWeeklyOffset: delegate(reportRenderer, 'getSelectedWeeklyOffset', function () { return 1; }),
      resetSession: resetSession,
      setProgressStatus: setProgressStatus,
      clearProgressStatus: clearProgressStatus,
      showThinkingIndicator: function () { return; },
      clearThinkingIndicator: function () { return; },
      setSendingState: setSendingState,
      renderSelectedMailBanner: delegate(metaRenderer, 'renderSelectedMailBanner'),
    };

    attachDelegates(api, reportRenderer, [
      'ensureReportProgressCard',
      'updateReportStep',
      'completeReportProgress',
      'addMeetingBookingReadyCard',
      'addTodoReadyCard',
      'addReportConfirmCard',
      'addWeeklyReportConfirmCard',
      'disableHitlConfirmControls',
      'showHitlConfirmPendingStatus',
      'disableReportConfirmControls',
    ]);
    attachDelegates(api, meetingRenderer, [
      'clearMeetingBookingTransientMessages',
      'clearCalendarEventCards',
      'addMeetingRoomBuildingCard',
      'addMeetingRoomFloorCard',
      'addMeetingRoomDetailCard',
      'addMeetingRoomScheduleCard',
      'addMeetingRoomBookingCard',
      'setMeetingRoomFloorOptions',
      'setMeetingRoomOptions',
      'getMeetingRoomBookingFormValues',
      'disableMeetingRoomBookingControls',
      'addCalendarEventCard',
      'getCalendarEventFormValues',
      'disableCalendarEventControls',
    ]);
    attachDelegates(api, legacyRenderer, [
      'addPromiseBudgetCard',
      'renderPromiseSummaryList',
      'renderPromiseMonthlyBreakdown',
      'clearPromiseMonthlyBreakdown',
      'setPromiseSummaryText',
      'setPromiseMode',
      'setPromiseViewStep',
      'getPromiseCardValues',
      'disablePromiseCardControls',
      'addFinanceSettlementCard',
      'setFinanceBudgetText',
      'getFinanceCardValues',
      'disableFinanceCardControls',
      'addHrApplyCard',
      'getHrCardValues',
      'disableHrCardControls',
    ]);

    return api;
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneMessages = api;
})(typeof window !== 'undefined' ? window : globalThis);
