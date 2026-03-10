/* ========================================
   MolduBot – Taskpane Selection Event Helpers
   ======================================== */

(function initTaskpaneSelectionEvents(global) {
  function resolveOfficeEventTypeMap(windowRef) {
    const office = windowRef && windowRef.Office ? windowRef.Office : {};
    return {
      officeEventTypeMap: office.EventType || null,
      mailboxEnumEventTypeMap: office.MailboxEnums && office.MailboxEnums.EventType
        ? office.MailboxEnums.EventType
        : null,
    };
  }

  function resolveEventTypeValue(officeEventTypeMap, mailboxEnumEventTypeMap, eventName) {
    if (officeEventTypeMap && officeEventTypeMap[eventName]) return officeEventTypeMap[eventName];
    if (mailboxEnumEventTypeMap && mailboxEnumEventTypeMap[eventName]) return mailboxEnumEventTypeMap[eventName];
    return '';
  }

  function collectSelectionEventTypes(windowRef) {
    const eventTypes = [];
    const maps = resolveOfficeEventTypeMap(windowRef);
    const itemChangedValue = resolveEventTypeValue(
      maps.officeEventTypeMap,
      maps.mailboxEnumEventTypeMap,
      'ItemChanged'
    );
    const selectedItemsChangedValue = resolveEventTypeValue(
      maps.officeEventTypeMap,
      maps.mailboxEnumEventTypeMap,
      'SelectedItemsChanged'
    );
    if (itemChangedValue) eventTypes.push({ name: 'ItemChanged', value: itemChangedValue });
    if (selectedItemsChangedValue) eventTypes.push({ name: 'SelectedItemsChanged', value: selectedItemsChangedValue });
    return eventTypes;
  }

  function logSelectionContextItemChanged(logClientEvent, shortId, context) {
    logClientEvent('info', 'selection_context_item_changed', {
      email_id_present: Boolean(context.emailId),
      mailbox_user_present: Boolean(context.mailboxUser),
      reason: String(context.reason || ''),
      email_id: shortId(context.emailId),
      direct_item_id: shortId(context.directItemId || ''),
      async_item_id: shortId(context.asyncItemId || ''),
      selected_item_id: shortId(context.selectedItemId || ''),
    });
  }

  function logObserverRegistrationFailure(logClientEvent, eventTypeName, result, error) {
    const resolvedError = error || (result && result.error ? result.error : {});
    logClientEvent('warning', 'selection_observer_register_failed', {
      event_type: eventTypeName,
      status: String((result && result.status) || (error ? 'thrown' : '')),
      code: String((resolvedError && resolvedError.code) || ''),
      message: String((resolvedError && resolvedError.message) || ''),
    });
  }

  function logObserverUnavailable(logClientEvent, reason, mailbox, eventTypes) {
    logClientEvent('warning', 'selection_observer_unavailable', {
      reason: reason,
      has_mailbox: Boolean(mailbox),
      has_add_handler: Boolean(mailbox && mailbox.addHandlerAsync),
      has_event_type: Array.isArray(eventTypes) && eventTypes.length > 0,
    });
  }

  function registerSelectionObserver(options) {
    const mailbox = options.mailbox;
    const eventType = options.eventType;
    const handler = options.handler;
    const windowRef = options.windowRef;
    const logClientEvent = options.logClientEvent;
    return new Promise(function (resolve) {
      const eventTypeName = String(eventType && eventType.name ? eventType.name : '');
      logClientEvent('info', 'selection_observer_register_attempt', {
        event_type: eventTypeName,
      });
      try {
        mailbox.addHandlerAsync(eventType.value, handler, function (result) {
          const succeeded = result && result.status === windowRef.Office.AsyncResultStatus.Succeeded;
          if (succeeded) {
            logClientEvent('info', 'selection_observer_registered', {
              event_type: eventTypeName,
            });
            resolve(true);
            return;
          }
          logObserverRegistrationFailure(logClientEvent, eventTypeName, result, null);
          resolve(false);
        });
      } catch (error) {
        logObserverRegistrationFailure(logClientEvent, eventTypeName, null, error);
        resolve(false);
      }
    });
  }

  const api = {
    collectSelectionEventTypes: collectSelectionEventTypes,
    logSelectionContextItemChanged: logSelectionContextItemChanged,
    logObserverUnavailable: logObserverUnavailable,
    registerSelectionObserver: registerSelectionObserver,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneSelectionEvents = api;
})(typeof window !== 'undefined' ? window : globalThis);
