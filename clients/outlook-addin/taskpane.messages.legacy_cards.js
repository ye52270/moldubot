(function initTaskpaneMessagesLegacyCards(global) {
  function create(options) {
    var byId = options.byId;
    var escapeHtml = options.escapeHtml;
    var escapeAttr = options.escapeAttr;
    var scrollToBottom = options.scrollToBottom;
    var removeWelcomeStateIfExists = options.removeWelcomeStateIfExists;

    var moduleLoaderFactory =
      (global && global.TaskpaneModuleLoader && typeof global.TaskpaneModuleLoader.create === 'function')
        ? global.TaskpaneModuleLoader
        : (typeof module !== 'undefined' && module.exports ? require('./taskpane.module_loader.js') : null);
    var moduleLoader = moduleLoaderFactory && typeof moduleLoaderFactory.create === 'function'
      ? moduleLoaderFactory.create()
      : { resolveModule: function () { return null; } };
    var resolveModule = moduleLoader.resolveModule;
    var cardDomModule = resolveModule('TaskpaneMessagesCardDom', './taskpane.messages.card_dom.js');
    var promiseModule = resolveModule('TaskpaneMessagesLegacyPromise', './taskpane.messages.legacy_promise.js');
    var formsModule = resolveModule('TaskpaneMessagesLegacyForms', './taskpane.messages.legacy_forms.js');
    var cardDom = cardDomModule && typeof cardDomModule.create === 'function'
      ? cardDomModule.create({ byId: byId })
      : null;

    function getChatArea() {
      if (cardDom && typeof cardDom.getChatArea === 'function') return cardDom.getChatArea();
      return byId('chatArea');
    }

    function withChatArea(render) {
      if (cardDom && typeof cardDom.withChatArea === 'function') return cardDom.withChatArea(render);
      var chatArea = getChatArea();
      if (!chatArea) return null;
      return render(chatArea);
    }

    function appendLegacyAssistantCard(cardClassName, innerHtml) {
      withChatArea(function (chatArea) {
        removeWelcomeStateIfExists();
        if (cardDom && typeof cardDom.appendAssistantCard === 'function') {
          cardDom.appendAssistantCard(
            chatArea,
            '',
            'report-confirm-card legacy-confirm-card ' + String(cardClassName || ''),
            innerHtml
          );
        } else {
          chatArea.insertAdjacentHTML(
            'beforeend',
            '<div class="message assistant">' +
              '<div class="msg-content report-confirm-card legacy-confirm-card ' + String(cardClassName || '') + '">' +
                String(innerHtml || '') +
              '</div>' +
            '</div>'
          );
        }
        scrollToBottom();
      });
    }

    function disableControls(selector) {
      if (cardDom && typeof cardDom.disableControls === 'function') {
        cardDom.disableControls(selector);
        return;
      }
      var chatArea = getChatArea();
      if (!chatArea || typeof chatArea.querySelectorAll !== 'function') return;
      var controls = chatArea.querySelectorAll(String(selector || ''));
      controls.forEach(function (node) {
        if (node && typeof node === 'object') node.disabled = true;
      });
    }

    function toSafeText(value, fallback) {
      var text = String(value || '').trim();
      if (text) return text;
      return String(fallback || '').trim();
    }

    function toSafeNumber(value) {
      var numeric = Number(value || 0);
      return Number.isFinite(numeric) ? numeric : 0;
    }

    function formatKrw(value) {
      return escapeHtml(Number(value || 0).toLocaleString('ko-KR')) + '원';
    }

    function buildRichTable(headerHtml, bodyHtml, extraClassName) {
      var tableClassName = String(extraClassName || '').trim();
      var className = tableClassName ? ('rich-table ' + tableClassName) : 'rich-table';
      return '' +
        '<div class="rich-table-wrap">' +
          '<table class="' + className + '">' +
            headerHtml +
            bodyHtml +
          '</table>' +
        '</div>';
    }

    var sharedDeps = {
      getChatArea: getChatArea,
      appendLegacyAssistantCard: appendLegacyAssistantCard,
      disableControls: disableControls,
      escapeHtml: escapeHtml,
      escapeAttr: escapeAttr,
      toSafeText: toSafeText,
      toSafeNumber: toSafeNumber,
      formatKrw: formatKrw,
      buildRichTable: buildRichTable,
    };

    var promiseRenderer = promiseModule && typeof promiseModule.create === 'function'
      ? promiseModule.create(sharedDeps)
      : null;
    var formsRenderer = formsModule && typeof formsModule.create === 'function'
      ? formsModule.create(sharedDeps)
      : null;

    return {
      addPromiseBudgetCard: promiseRenderer ? promiseRenderer.addPromiseBudgetCard : function noop() {},
      renderPromiseSummaryList: promiseRenderer ? promiseRenderer.renderPromiseSummaryList : function noop() {},
      renderPromiseMonthlyBreakdown: promiseRenderer ? promiseRenderer.renderPromiseMonthlyBreakdown : function noop() {},
      clearPromiseMonthlyBreakdown: promiseRenderer ? promiseRenderer.clearPromiseMonthlyBreakdown : function noop() {},
      setPromiseSummaryText: promiseRenderer ? promiseRenderer.setPromiseSummaryText : function noop() {},
      setPromiseMode: promiseRenderer ? promiseRenderer.setPromiseMode : function noop() {},
      setPromiseViewStep: promiseRenderer ? promiseRenderer.setPromiseViewStep : function noop() {},
      getPromiseCardValues: promiseRenderer ? promiseRenderer.getPromiseCardValues : function noop() { return null; },
      disablePromiseCardControls: promiseRenderer ? promiseRenderer.disablePromiseCardControls : function noop() {},
      addFinanceSettlementCard: formsRenderer ? formsRenderer.addFinanceSettlementCard : function noop() {},
      setFinanceBudgetText: formsRenderer ? formsRenderer.setFinanceBudgetText : function noop() {},
      getFinanceCardValues: formsRenderer ? formsRenderer.getFinanceCardValues : function noop() { return null; },
      disableFinanceCardControls: formsRenderer ? formsRenderer.disableFinanceCardControls : function noop() {},
      addHrApplyCard: formsRenderer ? formsRenderer.addHrApplyCard : function noop() {},
      getHrCardValues: formsRenderer ? formsRenderer.getHrCardValues : function noop() { return null; },
      disableHrCardControls: formsRenderer ? formsRenderer.disableHrCardControls : function noop() {},
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneMessagesLegacyCards = api;
})(typeof window !== 'undefined' ? window : globalThis);
