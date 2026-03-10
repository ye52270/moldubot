/* ========================================
   MolduBot – Taskpane Messages RichText Bridge
   ======================================== */

(function initTaskpaneMessagesRichBridge(global) {
  function create(options) {
    var richTextRenderer = options.richTextRenderer && typeof options.richTextRenderer === 'object'
      ? options.richTextRenderer
      : null;
    var escapeHtml = options.escapeHtml;

    function isNoiseStructuralToken(text) {
      return richTextRenderer && richTextRenderer.isNoiseStructuralToken
        ? richTextRenderer.isNoiseStructuralToken(text)
        : false;
    }

    function resolveHeadingClass(text) {
      return richTextRenderer && richTextRenderer.resolveHeadingClass
        ? richTextRenderer.resolveHeadingClass(text)
        : 'rich-heading';
    }

    function renderMarkdownTable(headerLine, rowLines) {
      return richTextRenderer && richTextRenderer.renderMarkdownTable
        ? richTextRenderer.renderMarkdownTable(headerLine, rowLines)
        : '';
    }

    function renderRichText(text) {
      return richTextRenderer && richTextRenderer.renderRichText
        ? richTextRenderer.renderRichText(text)
        : escapeHtml(String(text || ''));
    }

    function applyInlineFormatting(text) {
      return richTextRenderer && richTextRenderer.applyInlineFormatting
        ? richTextRenderer.applyInlineFormatting(text)
        : escapeHtml(String(text || ''));
    }

    function highlightCodeBlocks(root) {
      if (richTextRenderer && typeof richTextRenderer.highlightCodeBlocks === 'function') {
        richTextRenderer.highlightCodeBlocks(root);
      }
    }

    return {
      isNoiseStructuralToken: isNoiseStructuralToken,
      resolveHeadingClass: resolveHeadingClass,
      renderMarkdownTable: renderMarkdownTable,
      renderRichText: renderRichText,
      applyInlineFormatting: applyInlineFormatting,
      highlightCodeBlocks: highlightCodeBlocks,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (global) {
    global.TaskpaneMessagesRichBridge = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
