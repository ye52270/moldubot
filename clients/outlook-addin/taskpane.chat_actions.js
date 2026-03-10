/* ========================================
   MolduBot – Taskpane Chat Area Actions
   ======================================== */

(function initTaskpaneChatActions(global) {
  function create(options) {
    const moduleLoaderFactory =
      (global.TaskpaneModuleLoader && typeof global.TaskpaneModuleLoader.create === 'function')
        ? global.TaskpaneModuleLoader
        : (typeof module !== 'undefined' && module.exports ? require('./taskpane.module_loader.js') : null);
    const moduleLoader = moduleLoaderFactory && typeof moduleLoaderFactory.create === 'function'
      ? moduleLoaderFactory.create()
      : { resolveModule: function () { return null; } };
    const resolveModule = moduleLoader.resolveModule;
    const handlersModule = resolveModule('TaskpaneChatActionHandlers', './taskpane.chat_actions.handlers.js');
    const dispatchModule = resolveModule('TaskpaneChatActionDispatch', './taskpane.chat_actions.dispatch.js');
    if (!handlersModule || typeof handlersModule.create !== 'function') {
      return { bindChatAreaActions: function () {} };
    }
    if (!dispatchModule || typeof dispatchModule.create !== 'function') {
      return { bindChatAreaActions: function () {} };
    }

    const helperActions = handlersModule.create(options);
    return dispatchModule.create(Object.assign({}, options, {
      helperActions: helperActions,
    }));
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  global.TaskpaneChatActions = api;
})(typeof window !== 'undefined' ? window : globalThis);
