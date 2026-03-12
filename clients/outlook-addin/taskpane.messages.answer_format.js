/* ========================================
   MolduBot – Taskpane Messages Answer Format
   ======================================== */

(function initTaskpaneMessagesAnswerFormat(global) {
  function create(options) {
    const escapeHtml = options.escapeHtml;
    const escapeAttr = options.escapeAttr || options.escapeHtml;
    const applyInlineFormatting = options.applyInlineFormatting;
    const renderMarkdownTable = options.renderMarkdownTable;
    const renderBasicInfoRows = options.renderBasicInfoRows;
    const resolveHeadingClass = options.resolveHeadingClass;
    const isNoiseStructuralToken = options.isNoiseStructuralToken;
    const summaryCardsModule = options && options.summaryCardsModule && typeof options.summaryCardsModule === 'object'
      ? options.summaryCardsModule
      : null;
    const answerSectionsModule = options && options.answerSectionsModule && typeof options.answerSectionsModule === 'object'
      ? options.answerSectionsModule
      : null;
    const evidenceUiModule = options && options.evidenceUiModule && typeof options.evidenceUiModule === 'object'
      ? options.evidenceUiModule
      : null;
    const moduleLoaderFactory =
      (global.TaskpaneModuleLoader && typeof global.TaskpaneModuleLoader.create === 'function')
        ? global.TaskpaneModuleLoader
        : (typeof module !== 'undefined' && module.exports ? require('./taskpane.module_loader.js') : null);
    const moduleLoader = moduleLoaderFactory && typeof moduleLoaderFactory.create === 'function'
      ? moduleLoaderFactory.create()
      : { resolveModule: function () { return null; } };
    const resolveModule = moduleLoader.resolveModule;
    const uiCommon = options && options.uiCommon && typeof options.uiCommon === 'object'
      ? options.uiCommon
      : resolveModule('TaskpaneMessagesUiCommon', './taskpane.messages.ui_common.js');
    const answerBlocksModule = options && options.answerBlocksModule && typeof options.answerBlocksModule === 'object'
      ? options.answerBlocksModule
      : resolveModule('TaskpaneMessagesAnswerBlocks', './taskpane.messages.answer_blocks.js');
    const evidenceUi = options && options.evidenceUi && typeof options.evidenceUi === 'object'
      ? options.evidenceUi
      : (
        evidenceUiModule && typeof evidenceUiModule.create === 'function'
          ? evidenceUiModule.create({
            escapeHtml: escapeHtml,
            escapeAttr: escapeAttr,
            uiCommon: uiCommon,
          })
          : null
      );
    const answerSections = options && options.answerSections && typeof options.answerSections === 'object'
      ? options.answerSections
      : (
        answerSectionsModule && typeof answerSectionsModule.create === 'function'
          ? answerSectionsModule.create({
            escapeAttr: escapeAttr,
            applyInlineFormatting: applyInlineFormatting,
            buildInlineEvidencePopover: buildInlineEvidencePopover,
          })
          : null
      );

    function normalizeHeadingToken(text) {
      if (answerSections && typeof answerSections.normalizeHeadingToken === 'function') {
        return answerSections.normalizeHeadingToken(text);
      }
      return '';
    }

    function resolveSummarySectionKey(headingText) {
      if (answerSections && typeof answerSections.resolveSummarySectionKey === 'function') {
        return answerSections.resolveSummarySectionKey(headingText);
      }
      return '';
    }

    function isExecutiveBriefHeading(text) {
      if (answerSections && typeof answerSections.isExecutiveBriefHeading === 'function') {
        return answerSections.isExecutiveBriefHeading(text);
      }
      return false;
    }

    function resolveExecutiveSeverity(text) {
      if (answerSections && typeof answerSections.resolveExecutiveSeverity === 'function') {
        return answerSections.resolveExecutiveSeverity(text);
      }
      return { tone: 'low', label: '낮음' };
    }

    function buildInlineEvidencePopover(metadata, titleText, optionsArg) {
      if (!evidenceUi || typeof evidenceUi.buildInlineEvidencePopover !== 'function') return '';
      return evidenceUi.buildInlineEvidencePopover(metadata, titleText, optionsArg);
    }

    function buildExecutiveBriefHtml(summaryText, metadata) {
      if (answerSections && typeof answerSections.buildExecutiveBriefHtml === 'function') {
        return answerSections.buildExecutiveBriefHtml(summaryText, metadata);
      }
      return '';
    }

    let summaryCardsRenderer = null;
    function getSummaryCardsRenderer() {
      if (summaryCardsRenderer) return summaryCardsRenderer;
      if (!summaryCardsModule || typeof summaryCardsModule.create !== 'function') return null;
      summaryCardsRenderer = summaryCardsModule.create({
        escapeHtml: escapeHtml,
        escapeAttr: escapeAttr,
        applyInlineFormatting: applyInlineFormatting,
        buildInlineEvidencePopover: buildInlineEvidencePopover,
        evidenceUi: evidenceUi,
        renderIndexedSummaryCard: renderIndexedSummaryCard,
      });
      return summaryCardsRenderer;
    }

    function buildMajorSummaryListHtml(items, subtitles, metadata, startIndex) {
      const renderer = getSummaryCardsRenderer();
      if (!renderer || typeof renderer.buildMajorSummaryListHtml !== 'function') return '';
      return renderer.buildMajorSummaryListHtml(items, subtitles, metadata, startIndex);
    }

    function buildTechIssueListHtml(items, metadata, startIndex) {
      const renderer = getSummaryCardsRenderer();
      if (!renderer || typeof renderer.buildTechIssueListHtml !== 'function') return '';
      return renderer.buildTechIssueListHtml(items, metadata, startIndex);
    }

    function buildRecipientRoleListHtml(items, subtitles, metadata, startIndex) {
      const renderer = getSummaryCardsRenderer();
      if (!renderer || typeof renderer.buildRecipientRoleListHtml !== 'function') return '';
      return renderer.buildRecipientRoleListHtml(items, subtitles, metadata, startIndex);
    }

    function renderIndexedSummaryCard(options) {
      if (!uiCommon || typeof uiCommon.renderIndexedSummaryCard !== 'function') return '';
      return uiCommon.renderIndexedSummaryCard(options);
    }

    const answerBlocks = answerBlocksModule && typeof answerBlocksModule.create === 'function'
      ? answerBlocksModule.create({
        escapeAttr: escapeAttr,
        applyInlineFormatting: applyInlineFormatting,
        renderMarkdownTable: renderMarkdownTable,
        renderBasicInfoRows: renderBasicInfoRows,
        resolveHeadingClass: resolveHeadingClass,
        isNoiseStructuralToken: isNoiseStructuralToken,
        resolveSummarySectionKey: resolveSummarySectionKey,
        normalizeHeadingToken: normalizeHeadingToken,
        isExecutiveBriefHeading: isExecutiveBriefHeading,
        resolveExecutiveSeverity: resolveExecutiveSeverity,
        buildExecutiveBriefHtml: buildExecutiveBriefHtml,
        buildMajorSummaryListHtml: buildMajorSummaryListHtml,
        buildTechIssueListHtml: buildTechIssueListHtml,
        buildRecipientRoleListHtml: buildRecipientRoleListHtml,
        renderIndexedSummaryCard: renderIndexedSummaryCard,
        buildInlineEvidencePopover: buildInlineEvidencePopover,
      })
      : null;

    function renderAnswerFormatBlocks(blocks, metadata) {
      if (!answerBlocks || typeof answerBlocks.renderAnswerFormatBlocks !== 'function') return '';
      return answerBlocks.renderAnswerFormatBlocks(blocks, metadata);
    }

    return {
      resolveSummarySectionKey: resolveSummarySectionKey,
      normalizeHeadingToken: normalizeHeadingToken,
      isExecutiveBriefHeading: isExecutiveBriefHeading,
      resolveExecutiveSeverity: resolveExecutiveSeverity,
      buildInlineEvidencePopover: buildInlineEvidencePopover,
      buildExecutiveBriefHtml: buildExecutiveBriefHtml,
      buildMajorSummaryListHtml: buildMajorSummaryListHtml,
      renderAnswerFormatBlocks: renderAnswerFormatBlocks,
    };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  global.TaskpaneMessagesAnswerFormat = api;
})(typeof window !== 'undefined' ? window : globalThis);
