/* ========================================
   MolduBot – Input Utils Module
   ======================================== */

(function (global) {
  function isShortcutMenuVisible(items, menuEl) {
    return Boolean(Array.isArray(items) && items.length && menuEl && !menuEl.classList.contains('hidden'));
  }

  function callIfFunction(fn, ...args) {
    if (typeof fn !== 'function') return undefined;
    return fn(...args);
  }

  function handleShortcutMenuKeyDown(event, options = {}) {
    const opts = options && typeof options === 'object' ? options : {};
    const items = Array.isArray(opts.items) ? opts.items : [];
    const menuEl = opts.menuEl || null;
    if (!isShortcutMenuVisible(items, menuEl)) return false;

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      callIfFunction(opts.onArrowDown);
      return true;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      callIfFunction(opts.onArrowUp);
      return true;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      callIfFunction(opts.onEscape);
      return true;
    }
    if (event.key === 'Enter' || (event.key === 'Tab' && !event.shiftKey)) {
      if (callIfFunction(opts.onConfirm)) {
        event.preventDefault();
        return true;
      }
    }
    return false;
  }

  function handleComposerKeyDown(event, options = {}) {
    if (!event || typeof event !== 'object') return;
    const opts = options && typeof options === 'object' ? options : {};
    if (Boolean(opts.isImeComposing) || event.isComposing) return;
    if (callIfFunction(opts.onHandleScopeShortcut, event)) return;
    if (callIfFunction(opts.onHandleVerbShortcut, event)) return;
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      callIfFunction(opts.onEnter);
    }
  }

  function autoResizeComposer(textarea, options = {}) {
    if (!textarea || !textarea.style) return;
    const opts = options && typeof options === 'object' ? options : {};
    const maxHeight = Number.isFinite(Number(opts.maxHeight)) ? Number(opts.maxHeight) : 100;
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, maxHeight) + 'px';
    if (String(textarea.value || '').trim()) {
      callIfFunction(opts.onNonEmptyInput);
    }
    callIfFunction(opts.onAfterResize);
  }

  function setButtonEnabled(buttonEl, enabled) {
    if (!buttonEl) return;
    buttonEl.disabled = !enabled;
  }

  global.TaskpaneInputUtils = {
    isShortcutMenuVisible,
    handleShortcutMenuKeyDown,
    handleComposerKeyDown,
    autoResizeComposer,
    setButtonEnabled,
  };
})(window);
