/* ========================================
   MolduBot – Taskpane Rich Text Highlight Helpers
   ======================================== */

(function initTaskpaneMessagesRichtextHighlight(global) {
  function create(options) {
    const escapeHtml = options.escapeHtml;

    function hasHighlightTokenSpan(node) {
      if (!node || typeof node.querySelector !== 'function') return false;
      return Boolean(node.querySelector('span'));
    }

    function resolveCodeFenceLanguage(node) {
      if (!node || typeof node.className !== 'string') return '';
      const classes = String(node.className || '').split(/\s+/);
      for (let index = 0; index < classes.length; index += 1) {
        const token = String(classes[index] || '').trim().toLowerCase();
        if (token.indexOf('language-') !== 0) continue;
        return token.slice('language-'.length);
      }
      return '';
    }

    function renderMarkupFallback(source) {
      const escaped = escapeHtml(String(source || ''));
      if (!escaped) return '';
      const withComments = escaped.replace(
        /(&lt;%--[\s\S]*?--%&gt;|&lt;!--[\s\S]*?--&gt;)/g,
        '<span class="code-tok-comment">$1</span>'
      );
      return withComments.replace(/(&lt;\/?)([A-Za-z_][A-Za-z0-9:._-]*)([\s\S]*?)(&gt;)/g, function (_all, open, tagName, attrs, close) {
        const attrText = String(attrs || '').replace(
          /([A-Za-z_:][A-Za-z0-9:._-]*)(\s*=\s*)(&quot;[\s\S]*?&quot;|&#39;[\s\S]*?&#39;)/g,
          '<span class="code-tok-attr">$1</span>$2<span class="code-tok-string">$3</span>'
        );
        return open + '<span class="code-tok-tag">' + tagName + '</span>' + attrText + close;
      });
    }

    function applyMarkupHighlightFallback(node) {
      if (!node) return;
      const language = resolveCodeFenceLanguage(node);
      if (language !== 'xml' && language !== 'html' && language !== 'jsp') return;
      const source = String(node.textContent || '');
      if (!source.trim()) return;
      const highlighted = renderMarkupFallback(source);
      if (!highlighted || highlighted === escapeHtml(source)) return;
      node.innerHTML = highlighted;
      const pre = node.closest && typeof node.closest === 'function' ? node.closest('pre.rich-pre') : null;
      if (pre && pre.classList && typeof pre.classList.add === 'function') {
        pre.classList.add('fallback-highlighted');
      }
    }

    function highlightCodeBlocks(root) {
      if (!root || typeof root.querySelectorAll !== 'function') return;
      if (typeof window === 'undefined') return;
      const hljsRef = window.hljs;
      const codes = root.querySelectorAll('pre.rich-pre code.rich-code');
      codes.forEach(function (node) {
        if (!node || typeof node !== 'object') return;
        if (node.dataset && node.dataset.hljsDone === '1') return;
        if (!hljsRef || typeof hljsRef.highlightElement !== 'function') {
          applyMarkupHighlightFallback(node);
          if (node.dataset) node.dataset.hljsDone = '1';
          return;
        }
        try {
          hljsRef.highlightElement(node);
          if (!hasHighlightTokenSpan(node)) applyMarkupHighlightFallback(node);
          if (node.dataset) node.dataset.hljsDone = '1';
        } catch (_error) {
          applyMarkupHighlightFallback(node);
        }
      });
    }

    return {
      hasHighlightTokenSpan: hasHighlightTokenSpan,
      resolveCodeFenceLanguage: resolveCodeFenceLanguage,
      renderMarkupFallback: renderMarkupFallback,
      applyMarkupHighlightFallback: applyMarkupHighlightFallback,
      highlightCodeBlocks: highlightCodeBlocks,
    };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  global.TaskpaneMessagesRichtextHighlight = api;
})(typeof window !== 'undefined' ? window : globalThis);
