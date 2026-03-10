/* ========================================
   MolduBot – Taskpane Runtime State
   ======================================== */

(function initTaskpaneState(global) {
  function create(options) {
    const getIsSending = typeof options.getIsSending === 'function'
      ? options.getIsSending
      : function () { return false; };
    const setProgressShownAtMs = typeof options.setProgressShownAtMs === 'function'
      ? options.setProgressShownAtMs
      : function () {};

    return {
      pendingReportContext: null,
      pendingWeeklyReportContext: null,
      pendingMeetingRoomContext: null,
      pendingCalendarContext: null,
      pendingPromiseContext: null,
      pendingFinanceContext: null,
      pendingHrContext: null,
      executedNextActionIds: {},
      markNextActionExecuted: function (actionId) {
        const normalized = String(actionId || '').trim().toLowerCase();
        if (!normalized) return;
        this.executedNextActionIds[normalized] = true;
      },
      filterNextActionsMetadata: function (metadata) {
        const source = metadata && typeof metadata === 'object' ? metadata : {};
        const actions = Array.isArray(source.next_actions) ? source.next_actions : [];
        if (!actions.length) return source;
        const executed = this.executedNextActionIds && typeof this.executedNextActionIds === 'object'
          ? this.executedNextActionIds
          : {};
        const filtered = actions.filter(function (item) {
          const actionId = String(item && item.action_id ? item.action_id : '').trim().toLowerCase();
          if (!actionId) return true;
          return !Boolean(executed[actionId]);
        });
        if (filtered.length === actions.length) return source;
        const nextMetadata = Object.assign({}, source);
        nextMetadata.next_actions = filtered;
        return nextMetadata;
      },
      clearExecutedNextActions: function () {
        this.executedNextActionIds = {};
      },
      isSendingRef: function () {
        return Boolean(getIsSending());
      },
      setProgressShownAtMs: function (value) {
        setProgressShownAtMs(Number(value || 0));
      },
    };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  global.TaskpaneState = api;
})(typeof window !== 'undefined' ? window : globalThis);
