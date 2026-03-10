/* ========================================
   MolduBot – Taskpane Module Loader
   ======================================== */

(function initTaskpaneModuleLoader(global) {
  function create() {
    function resolveModule(globalName, requirePath) {
      if (typeof window !== 'undefined' && window[globalName]) return window[globalName];
      if (typeof module !== 'undefined' && module.exports) {
        try {
          // eslint-disable-next-line global-require
          return require(requirePath);
        } catch (_error) {
          return null;
        }
      }
      return null;
    }

    function createRenderer(moduleObj, options, fallback) {
      if (moduleObj && typeof moduleObj.create === 'function') return moduleObj.create(options || {});
      return fallback || {};
    }

    function delegate(moduleObj, methodName, fallback) {
      if (moduleObj && typeof moduleObj[methodName] === 'function') return moduleObj[methodName].bind(moduleObj);
      return fallback || function () { return null; };
    }

    return {
      resolveModule: resolveModule,
      createRenderer: createRenderer,
      delegate: delegate,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  global.TaskpaneModuleLoader = api;
})(typeof window !== 'undefined' ? window : globalThis);
