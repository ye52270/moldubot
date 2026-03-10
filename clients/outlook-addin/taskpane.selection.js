/* ========================================
   MolduBot – Taskpane Selection Controller
   ======================================== */

(function (globalScope) {
  function emptySelectionContext(reason) {
    return {
      emailId: '',
      mailboxUser: '',
      reason: String(reason || 'empty'),
      directItemId: '',
      asyncItemId: '',
      selectedItemId: '',
    };
  }

  function createSelectionController(deps) {
    const windowRef = deps.windowRef;
    const logClientEvent = deps.logClientEvent;
    const shortId = deps.shortId;
    const sleep = deps.sleep;
    const moduleLoaderFactory =
      (globalScope.TaskpaneModuleLoader && typeof globalScope.TaskpaneModuleLoader.create === 'function')
        ? globalScope.TaskpaneModuleLoader
        : (typeof module !== 'undefined' && module.exports ? require('./taskpane.module_loader.js') : null);
    const moduleLoader = moduleLoaderFactory && typeof moduleLoaderFactory.create === 'function'
      ? moduleLoaderFactory.create()
      : { resolveModule: function () { return null; } };
    const resolveModule = moduleLoader.resolveModule;
    const eventsModule = resolveModule('TaskpaneSelectionEvents', './taskpane.selection.events.js');
    const observerModule = resolveModule('TaskpaneSelectionObserver', './taskpane.selection.observer.js');
    const contextModule = resolveModule('TaskpaneSelectionContext', './taskpane.selection.context.js');

    const config = {
      contextRetryCount: Number(deps.contextRetryCount || 10),
      contextRetryDelayMs: Number(deps.contextRetryDelayMs || 220),
      officeReadyWaitMs: Number(deps.officeReadyWaitMs || 900),
      officeMailboxRetryCount: Number(deps.officeMailboxRetryCount || 5),
      officeMailboxRetryDelayMs: Number(deps.officeMailboxRetryDelayMs || 100),
      officeItemRetryCount: Number(deps.officeItemRetryCount || 4),
      officeItemRetryDelayMs: Number(deps.officeItemRetryDelayMs || 90),
      selectionPollIntervalMs: Number(deps.selectionPollIntervalMs || 1200),
    };

    let cachedSelectionContext = emptySelectionContext('init');
    let selectionRevision = 0;
    let lastSentCurrentMailId = '';
    let lastSentRevision = -1;
    let selectionPollTimer = null;

    function getSelectionRevision() {
      return selectionRevision;
    }

    function clearSelectionCache(reason) {
      cachedSelectionContext = emptySelectionContext(reason);
      selectionRevision += 1;
      logClientEvent('info', 'selection_cache_cleared', {
        reason: String(reason || ''),
        selection_revision: selectionRevision,
      });
    }

    const contextResolver = contextModule && typeof contextModule.createContextResolver === 'function'
      ? contextModule.createContextResolver({
        windowRef: windowRef,
        sleep: sleep,
        config: config,
        emptySelectionContext: emptySelectionContext,
      })
      : null;
    const ensureOfficeReady = contextResolver
      ? contextResolver.ensureOfficeReady
      : async function () {};
    const getOfficeMailbox = contextResolver
      ? contextResolver.getOfficeMailbox
      : function () { return null; };
    const readMailboxUser = contextResolver
      ? contextResolver.readMailboxUser
      : function () { return ''; };
    const resolveMailboxWithRetry = contextResolver
      ? contextResolver.resolveMailboxWithRetry
      : async function () { return null; };
    const resolveSelectionContextOnce = contextResolver
      ? contextResolver.resolveSelectionContextOnce
      : async function () { return emptySelectionContext('context_module_missing'); };

    async function getSelectionContext(options) {
      const allowCacheFallback = Boolean(options && options.allowCacheFallback);
      if (!allowCacheFallback) {
        clearSelectionCache('fresh_context_required');
      }
      let lastContext = emptySelectionContext('retry_exhausted');
      for (let attempt = 1; attempt <= config.contextRetryCount; attempt += 1) {
        const context = await resolveSelectionContextOnce();
        lastContext = context;
        if (context.emailId && context.mailboxUser) {
          cachedSelectionContext = context;
          return context;
        }
        if (attempt < config.contextRetryCount) {
          await sleep(config.contextRetryDelayMs);
        }
      }
      if (allowCacheFallback && cachedSelectionContext.emailId && cachedSelectionContext.mailboxUser) {
        return {
          emailId: cachedSelectionContext.emailId,
          mailboxUser: cachedSelectionContext.mailboxUser,
          reason: 'cache_fallback',
          directItemId: '',
          asyncItemId: '',
          selectedItemId: '',
        };
      }
      if (!allowCacheFallback) {
        return {
          ...emptySelectionContext(lastContext.reason || 'fresh_context_required'),
          directItemId: String(lastContext.directItemId || ''),
          asyncItemId: String(lastContext.asyncItemId || ''),
          selectedItemId: String(lastContext.selectedItemId || ''),
        };
      }
      return lastContext;
    }

    function isStaleCurrentMailSelection(isCurrentMailQuery, message, selectionContext) {
      const currentMailQuery = isCurrentMailQuery(message);
      const selectedId = String(selectionContext && selectionContext.emailId ? selectionContext.emailId : '');
      if (!currentMailQuery || !selectedId) {
        return false;
      }
      return selectedId === lastSentCurrentMailId && selectionRevision === lastSentRevision;
    }

    function markCurrentMailSent(emailId) {
      const normalized = String(emailId || '').trim();
      if (!normalized) return;
      lastSentCurrentMailId = normalized;
      lastSentRevision = selectionRevision;
    }

    async function waitForSelectionChange(previousEmailId, timeoutMs, pollMs) {
      const normalizedPreviousId = String(previousEmailId || '').trim();
      if (!normalizedPreviousId) return null;
      const startedAt = Date.now();
      while (Date.now() - startedAt < timeoutMs) {
        await sleep(pollMs);
        const context = await resolveSelectionContextOnce();
        const nextId = String(context.emailId || '').trim();
        if (!nextId) {
          continue;
        }
        if (nextId !== normalizedPreviousId) {
          cachedSelectionContext = context;
          selectionRevision += 1;
          logClientEvent('info', 'selection_context_changed_after_wait', {
            previous_email_id: shortId(normalizedPreviousId),
            next_email_id: shortId(nextId),
            reason: String(context.reason || ''),
            selection_revision: selectionRevision,
          });
          return context;
        }
      }
      return null;
    }

    async function pollSelectionContext() {
      const context = await resolveSelectionContextOnce();
      if (!context.emailId || !context.mailboxUser) {
        return;
      }
      const previousId = String(cachedSelectionContext.emailId || '').trim();
      const nextId = String(context.emailId || '').trim();
      if (!nextId || nextId === previousId) {
        return;
      }
      cachedSelectionContext = context;
      selectionRevision += 1;
      logClientEvent('info', 'selection_context_polled_changed', {
        previous_email_id: shortId(previousId),
        next_email_id: shortId(nextId),
        reason: String(context.reason || ''),
        selection_revision: selectionRevision,
      });
    }

    function startSelectionPolling() {
      if (selectionPollTimer) {
        return;
      }
      selectionPollTimer = windowRef.setInterval(function () {
        void pollSelectionContext();
      }, config.selectionPollIntervalMs);
      logClientEvent('info', 'selection_polling_started', {
        interval_ms: config.selectionPollIntervalMs,
      });
      void pollSelectionContext();
    }

    const observerOps = observerModule && typeof observerModule.createObserverOps === 'function'
      ? observerModule.createObserverOps({
        windowRef: windowRef,
        logClientEvent: logClientEvent,
        shortId: shortId,
        ensureOfficeReady: ensureOfficeReady,
        getOfficeMailbox: getOfficeMailbox,
        clearSelectionCache: clearSelectionCache,
        resolveSelectionContextOnce: resolveSelectionContextOnce,
        setCachedSelectionContext: function (context) { cachedSelectionContext = context; },
        eventsModule: eventsModule,
      })
      : {
        collectSelectionEventTypes: function () { return []; },
        createSelectionChangedHandler: function () { return function () {}; },
        observeSelectionChanges: async function () {},
        registerSelectionObserver: async function () { return false; },
      };

    function getSelectionStateSnapshot() {
      return {
        selectionRevision: selectionRevision,
        cachedEmailId: String(cachedSelectionContext.emailId || ''),
        cachedMailboxUser: String(cachedSelectionContext.mailboxUser || ''),
      };
    }

    function setCachedSelectionContextForTest(context) {
      cachedSelectionContext = {
        emailId: String((context && context.emailId) || ''),
        mailboxUser: String((context && context.mailboxUser) || ''),
        reason: String((context && context.reason) || 'test'),
        directItemId: String((context && context.directItemId) || ''),
        asyncItemId: String((context && context.asyncItemId) || ''),
        selectedItemId: String((context && context.selectedItemId) || ''),
      };
    }

    return {
      clearSelectionCache,
      collectSelectionEventTypes: observerOps.collectSelectionEventTypes,
      createSelectionChangedHandler: observerOps.createSelectionChangedHandler,
      getSelectionContext,
      getSelectionRevision,
      getSelectionStateSnapshot,
      isStaleCurrentMailSelection,
      markCurrentMailSent,
      observeSelectionChanges: observerOps.observeSelectionChanges,
      pollSelectionContext,
      readMailboxUser,
      registerSelectionObserver: observerOps.registerSelectionObserver,
      resolveMailboxWithRetry,
      resolveSelectionContextOnce,
      setCachedSelectionContextForTest,
      startSelectionPolling,
      waitForSelectionChange,
    };
  }

  const api = {
    create: createSelectionController,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
    return;
  }
  globalScope.TaskpaneSelectionController = api;
})(typeof window !== 'undefined' ? window : globalThis);
