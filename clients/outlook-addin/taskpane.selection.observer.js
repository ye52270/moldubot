(function initTaskpaneSelectionObserver(globalScope) {
  function createObserverOps(options) {
    const windowRef = options.windowRef;
    const logClientEvent = options.logClientEvent;
    const shortId = options.shortId;
    const ensureOfficeReady = options.ensureOfficeReady;
    const getOfficeMailbox = options.getOfficeMailbox;
    const clearSelectionCache = options.clearSelectionCache;
    const resolveSelectionContextOnce = options.resolveSelectionContextOnce;
    const setCachedSelectionContext = options.setCachedSelectionContext;
    const bumpSelectionRevision = options.bumpSelectionRevision;
    const eventsModule = options.eventsModule;

    let selectionObserverRegistered = false;
    let selectionObserverRegistering = false;

    function collectSelectionEventTypes() {
      if (eventsModule && typeof eventsModule.collectSelectionEventTypes === 'function') {
        return eventsModule.collectSelectionEventTypes(windowRef);
      }
      return [];
    }

    function createSelectionChangedHandler() {
      return function () {
        clearSelectionCache('item_changed');
        resolveSelectionContextOnce()
          .then(function (context) {
            if (context.emailId || context.mailboxUser) {
              setCachedSelectionContext(context);
            }
            if (eventsModule && typeof eventsModule.logSelectionContextItemChanged === 'function') {
              eventsModule.logSelectionContextItemChanged(logClientEvent, shortId, context);
            }
          })
          .catch(function () {
            return null;
          });
      };
    }

    function registerSelectionObserver(mailbox, eventType, handler) {
      if (eventsModule && typeof eventsModule.registerSelectionObserver === 'function') {
        return eventsModule.registerSelectionObserver({
          mailbox: mailbox,
          eventType: eventType,
          handler: handler,
          windowRef: windowRef,
          logClientEvent: logClientEvent,
        });
      }
      return Promise.resolve(false);
    }

    function logObserverUnavailable(reason, mailbox, eventTypes) {
      if (eventsModule && typeof eventsModule.logObserverUnavailable === 'function') {
        eventsModule.logObserverUnavailable(logClientEvent, reason, mailbox, eventTypes);
        return;
      }
      logClientEvent('warning', 'selection_observer_unavailable', {
        reason: String(reason || ''),
      });
    }

    async function observeSelectionChanges() {
      if (selectionObserverRegistered || selectionObserverRegistering) {
        return;
      }
      selectionObserverRegistering = true;
      await ensureOfficeReady();
      const mailbox = getOfficeMailbox();
      const eventTypes = collectSelectionEventTypes();
      if (!mailbox) {
        logObserverUnavailable('office_mailbox_unavailable', mailbox, eventTypes);
        selectionObserverRegistering = false;
        return;
      }
      if (!mailbox.addHandlerAsync || !eventTypes.length) {
        logObserverUnavailable('item_changed_api_unavailable', mailbox, eventTypes);
        selectionObserverRegistering = false;
        return;
      }

      const handler = createSelectionChangedHandler();
      let registeredCount = 0;
      for (const eventType of eventTypes) {
        const ok = await registerSelectionObserver(mailbox, eventType, handler);
        if (ok) {
          registeredCount += 1;
        }
      }
      selectionObserverRegistered = registeredCount > 0;
      if (selectionObserverRegistered && typeof bumpSelectionRevision === 'function') {
        bumpSelectionRevision(0);
      }
      selectionObserverRegistering = false;
    }

    return {
      collectSelectionEventTypes: collectSelectionEventTypes,
      createSelectionChangedHandler: createSelectionChangedHandler,
      observeSelectionChanges: observeSelectionChanges,
      registerSelectionObserver: registerSelectionObserver,
    };
  }

  const api = { createObserverOps: createObserverOps };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
    return;
  }
  globalScope.TaskpaneSelectionObserver = api;
})(typeof window !== 'undefined' ? window : globalThis);
