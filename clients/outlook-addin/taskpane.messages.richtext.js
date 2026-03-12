/* ========================================
   MolduBot – Taskpane Messages Rich Text
   ======================================== */

(function initTaskpaneMessagesRichText(global) {
  function create(options) {
    const escapeHtml = options.escapeHtml;
    const escapeAttr = options.escapeAttr || options.escapeHtml;
    const moduleLoaderFactory =
      (global.TaskpaneModuleLoader && typeof global.TaskpaneModuleLoader.create === 'function')
        ? global.TaskpaneModuleLoader
        : (typeof module !== 'undefined' && module.exports ? require('./taskpane.module_loader.js') : null);
    const moduleLoader = moduleLoaderFactory && typeof moduleLoaderFactory.create === 'function'
      ? moduleLoaderFactory.create()
      : { resolveModule: function () { return null; } };
    const resolveModule = moduleLoader.resolveModule;
    const highlightModule = resolveModule('TaskpaneMessagesRichtextHighlight', './taskpane.messages.richtext.highlight.js');
    const utilsModule = resolveModule('TaskpaneMessagesRichtextUtils', './taskpane.messages.richtext.utils.js');
    const highlighter = highlightModule && typeof highlightModule.create === 'function'
      ? highlightModule.create({ escapeHtml: escapeHtml })
      : null;
    const utils = utilsModule && typeof utilsModule.create === 'function'
      ? utilsModule.create({
        escapeHtml: escapeHtml,
        escapeAttr: options.escapeAttr || options.escapeHtml,
      })
      : null;
    if (!utils) {
      return {
        insertStructuralNewlines: function () { return ''; },
        normalizeRichSourceText: function () { return ''; },
        isMarkdownTableDelimiter: function () { return false; },
        splitMarkdownTableCells: function () { return []; },
        renderMarkdownTable: function () { return ''; },
        normalizeCodeFenceLanguageTag: function () { return ''; },
        formatCodeLanguageLabel: function () { return ''; },
        resolveHighlightLanguageClass: function () { return ''; },
        isNoiseStructuralToken: function () { return false; },
        isMailListMetaLine: function () { return false; },
        parseInlineMailListMeta: function () { return null; },
        isMailLinkNoiseLine: function () { return false; },
        resolveHeadingClass: function () { return 'rich-heading'; },
        renderRichText: function () { return ''; },
        consumeMarkdownTable: function () { return { html: '', nextIndex: 0 }; },
        applyInlineFormatting: function (text) { return String(text || ''); },
        parseMailOpenUrl: function () { return { webLink: '', messageId: '' }; },
        highlightCodeBlocks: function () {},
        hasHighlightTokenSpan: highlighter ? highlighter.hasHighlightTokenSpan : function () { return false; },
        resolveCodeFenceLanguage: highlighter ? highlighter.resolveCodeFenceLanguage : function () { return ''; },
        applyMarkupHighlightFallback: highlighter ? highlighter.applyMarkupHighlightFallback : function () {},
        renderMarkupFallback: highlighter ? highlighter.renderMarkupFallback : function () { return ''; },
      };
    }

    function renderRichText(text) {
      const normalized = utils.normalizeRichSourceText(text);
      if (!normalized) return '';
      const lines = normalized.split('\n');
      const htmlChunks = [];
      let listMode = '';
      let orderedItemOpen = false;
      let codeBlockOpen = false;
      let codeBlockLanguage = '';
      let codeBlockHeadIndex = -1;
      let skippingMailLinkNoise = false;
      let activeCodeReviewSection = '';

      const closeCodeReviewSectionIfNeeded = function () {
        if (!activeCodeReviewSection) return;
        htmlChunks.push('</div></section>');
        activeCodeReviewSection = '';
      };
      const closeOrderedItemIfNeeded = function () {
        if (orderedItemOpen) {
          htmlChunks.push('</li>');
          orderedItemOpen = false;
        }
      };
      const closeListIfNeeded = function () {
        closeOrderedItemIfNeeded();
        if (listMode === 'ul') htmlChunks.push('</ul>');
        if (listMode === 'ol') htmlChunks.push('</ol>');
        listMode = '';
      };

      for (let index = 0; index < lines.length; index += 1) {
        const rawLine = String(lines[index] || '');
        const trimmed = rawLine.trim();
        if (!trimmed) {
          if (listMode === 'ol' && orderedItemOpen) continue;
          closeListIfNeeded();
          continue;
        }
        if (utils.isNoiseStructuralToken(trimmed)) {
          closeListIfNeeded();
          continue;
        }
        if (skippingMailLinkNoise && (utils.isMailLinkNoiseLine(trimmed) || /^[A-Za-z0-9=&%?._\-\/]+$/.test(trimmed))) {
          continue;
        }
        skippingMailLinkNoise = false;
        const inlineMailMeta = utils.parseInlineMailListMeta(trimmed);
        if (inlineMailMeta) {
          closeListIfNeeded();
          htmlChunks.push('<p class="rich-paragraph">보낸 사람: ' + utils.applyInlineFormatting(inlineMailMeta.sender) + '</p>');
          htmlChunks.push('<p class="rich-paragraph">수신일: ' + utils.applyInlineFormatting(inlineMailMeta.receivedAt) + '</p>');
          if (inlineMailMeta.summary) {
            htmlChunks.push('<p class="rich-paragraph">요약: ' + utils.applyInlineFormatting(inlineMailMeta.summary) + '</p>');
          }
          skippingMailLinkNoise = true;
          continue;
        }
        if (utils.isMailListMetaLine(trimmed) || utils.isMailLinkNoiseLine(trimmed)) {
          closeListIfNeeded();
          continue;
        }
        if (trimmed.indexOf('```') === 0) {
          closeListIfNeeded();
          if (!codeBlockOpen) {
            const openIndex = htmlChunks.length;
            codeBlockLanguage = utils.openCodeBlock(htmlChunks, trimmed);
            codeBlockHeadIndex = openIndex;
            codeBlockOpen = true;
          } else {
            utils.closeCodeBlock(htmlChunks);
            codeBlockOpen = false;
            codeBlockLanguage = '';
            codeBlockHeadIndex = -1;
          }
          continue;
        }
        if (codeBlockOpen) {
          if (utils.shouldUpgradeFenceLanguageToJsp(codeBlockLanguage, rawLine)) {
            codeBlockLanguage = 'jsp';
            if (codeBlockHeadIndex >= 0) {
              htmlChunks[codeBlockHeadIndex] = utils.buildCodeBlockOpenHtml(codeBlockLanguage);
            }
          }
          htmlChunks.push(escapeHtml(rawLine) + '\n');
          continue;
        }
        if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
          closeListIfNeeded();
          htmlChunks.push('<hr class="rich-divider" />');
          continue;
        }
        const nextLine = String(lines[index + 1] || '').trim();
        if (trimmed.indexOf('|') >= 0 && nextLine && utils.isMarkdownTableDelimiter(nextLine)) {
          closeListIfNeeded();
          const consumed = utils.consumeMarkdownTable(lines, index, trimmed);
          htmlChunks.push(consumed.html);
          index = consumed.nextIndex;
          continue;
        }
        const bulletMatch = /^[-*]\s+(.+)$/.exec(trimmed);
        const indentedBulletMatch = /^(\s+)[-*]\s+(.+)$/.exec(rawLine);
        if (bulletMatch) {
          const bulletText = indentedBulletMatch ? indentedBulletMatch[2] : bulletMatch[1];
          if (listMode === 'ol' && orderedItemOpen) {
            htmlChunks.push('<div class="rich-subline">- ' + utils.applyInlineFormatting(bulletText) + '</div>');
            continue;
          }
          if (indentedBulletMatch && listMode === 'ul') {
            htmlChunks.push('<li class="rich-subline-item"><div class="rich-subline">- ' + utils.applyInlineFormatting(bulletText) + '</div></li>');
            continue;
          }
          if (listMode !== 'ul') {
            closeListIfNeeded();
            htmlChunks.push('<ul class="rich-list">');
            listMode = 'ul';
          }
          htmlChunks.push('<li>' + utils.applyInlineFormatting(bulletText) + '</li>');
          continue;
        }
        const orderedMatch = /^(\d+)\.\s*(\S.*)$/.exec(trimmed);
        if (orderedMatch) {
          if (listMode !== 'ol') {
            closeListIfNeeded();
            htmlChunks.push('<ol class="rich-list ordered">');
            listMode = 'ol';
          }
          closeOrderedItemIfNeeded();
          htmlChunks.push('<li><span class="rich-ol-title">' + utils.applyInlineFormatting(orderedMatch[2]) + '</span>');
          orderedItemOpen = true;
          continue;
        }
        closeListIfNeeded();
        const headingMatch = /^(#{1,6})\s*(\S.*)$/.exec(trimmed);
        if (headingMatch) {
          const headingText = String(headingMatch[2] || '').trim();
          const sectionKey = utils.resolveCodeReviewSectionKey(headingText);
          if (sectionKey) {
            closeCodeReviewSectionIfNeeded();
            const level = Math.min(headingMatch[1].length, 4);
            htmlChunks.push(
              '<section class="summary-section section-' + escapeAttr(sectionKey) + '">' +
                '<h' + level + ' class="' + utils.resolveHeadingClass(headingText) + '">' + utils.applyInlineFormatting(headingText) + '</h' + level + '>' +
                '<div class="summary-section-body">'
            );
            activeCodeReviewSection = sectionKey;
            continue;
          }
          const level = Math.min(headingMatch[1].length, 4);
          htmlChunks.push('<h' + level + ' class="' + utils.resolveHeadingClass(headingText) + '">' + utils.applyInlineFormatting(headingText) + '</h' + level + '>');
          continue;
        }
        htmlChunks.push('<p class="rich-paragraph">' + utils.applyInlineFormatting(trimmed) + '</p>');
      }
      closeListIfNeeded();
      if (codeBlockOpen) utils.closeCodeBlock(htmlChunks);
      closeCodeReviewSectionIfNeeded();
      return htmlChunks.join('');
    }

    function highlightCodeBlocks(root) {
      if (highlighter && typeof highlighter.highlightCodeBlocks === 'function') {
        highlighter.highlightCodeBlocks(root);
      }
    }

    return {
      insertStructuralNewlines: utils.insertStructuralNewlines,
      normalizeRichSourceText: utils.normalizeRichSourceText,
      isMarkdownTableDelimiter: utils.isMarkdownTableDelimiter,
      splitMarkdownTableCells: utils.splitMarkdownTableCells,
      renderMarkdownTable: utils.renderMarkdownTable,
      normalizeCodeFenceLanguageTag: utils.normalizeCodeFenceLanguageTag,
      formatCodeLanguageLabel: utils.formatCodeLanguageLabel,
      resolveHighlightLanguageClass: utils.resolveHighlightLanguageClass,
      isNoiseStructuralToken: utils.isNoiseStructuralToken,
      isMailListMetaLine: utils.isMailListMetaLine,
      parseInlineMailListMeta: utils.parseInlineMailListMeta,
      isMailLinkNoiseLine: utils.isMailLinkNoiseLine,
      resolveHeadingClass: utils.resolveHeadingClass,
      renderRichText: renderRichText,
      consumeMarkdownTable: utils.consumeMarkdownTable,
      applyInlineFormatting: utils.applyInlineFormatting,
      parseMailOpenUrl: utils.parseMailOpenUrl,
      highlightCodeBlocks: highlightCodeBlocks,
      hasHighlightTokenSpan: highlighter ? highlighter.hasHighlightTokenSpan : function () { return false; },
      resolveCodeFenceLanguage: highlighter ? highlighter.resolveCodeFenceLanguage : function () { return ''; },
      applyMarkupHighlightFallback: highlighter ? highlighter.applyMarkupHighlightFallback : function () {},
      renderMarkupFallback: highlighter ? highlighter.renderMarkupFallback : function () { return ''; },
    };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  global.TaskpaneMessagesRichText = api;
})(typeof window !== 'undefined' ? window : globalThis);
