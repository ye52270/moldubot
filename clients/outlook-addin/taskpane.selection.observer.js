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
    const setObserverFallbackMode = options.setObserverFallbackMode;
    const startSelectionPolling = options.startSelectionPolling;

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
      return Promise.resolve({ ok: false, eventType: String((eventType && eventType.name) || ''), fallbackMode: '' });
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
        const registration = await registerSelectionObserver(mailbox, eventType, handler);
        const isObjectResult = registration && typeof registration === 'object';
        const ok = isObjectResult ? Boolean(registration.ok) : Boolean(registration);
        if (ok) {
          registeredCount += 1;
          continue;
        }
        const eventTypeName = String((isObjectResult && registration.eventType) || eventType.name || '');
        const fallbackMode = String((isObjectResult && registration.fallbackMode) || '');
        if (fallbackMode === 'polling' && eventTypeName === 'SelectedItemsChanged') {
          if (typeof setObserverFallbackMode === 'function') {
            setObserverFallbackMode('polling', {
              event_type: eventTypeName,
              reason: 'selected_items_changed_code7000',
            });
          }
          if (typeof startSelectionPolling === 'function') {
            startSelectionPolling();
          }
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
