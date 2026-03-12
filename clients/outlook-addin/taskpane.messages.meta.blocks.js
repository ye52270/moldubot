/* ========================================
   MolduBot – Taskpane Messages Meta Blocks
   ======================================== */

(function initTaskpaneMessagesMetaBlocks(global) {
  function create(options) {
    var escapeHtml = options.escapeHtml;
    var escapeAttr = options.escapeAttr || options.escapeHtml;
    var applyInlineFormatting = options.applyInlineFormatting;
    var normalizeHeadingToken = options.normalizeHeadingToken;
    var normalizeDisplayName = options.normalizeDisplayName;
    var moduleLoaderFactory =
      (global && global.TaskpaneModuleLoader && typeof global.TaskpaneModuleLoader.create === 'function')
        ? global.TaskpaneModuleLoader
        : (typeof module !== 'undefined' && module.exports ? require('./taskpane.module_loader.js') : null);
    var moduleLoader = moduleLoaderFactory && typeof moduleLoaderFactory.create === 'function'
      ? moduleLoaderFactory.create()
      : { resolveModule: function () { return null; } };
    var resolveModule = moduleLoader.resolveModule;
    var actionBlocksModule = resolveModule('TaskpaneMessagesMetaActions', './taskpane.messages.meta_actions.js');
    var basicInfoModule = resolveModule('TaskpaneMessagesMetaBasicInfo', './taskpane.messages.meta.basic_info.js');
    var actionBlocks = actionBlocksModule && typeof actionBlocksModule.create === 'function'
      ? actionBlocksModule.create({
        escapeHtml: escapeHtml,
        escapeAttr: escapeAttr,
      })
      : null;
    var basicInfoBlocks = basicInfoModule && typeof basicInfoModule.create === 'function'
      ? basicInfoModule.create({
        applyInlineFormatting: applyInlineFormatting,
        normalizeHeadingToken: normalizeHeadingToken,
        normalizeDisplayName: normalizeDisplayName,
      })
      : null;

    function normalizeReplyDraftBodyText(raw) {
      var text = String(raw || '').trim();
      if (!text) return '';
      var fencedMatch = text.match(/```[^\n]*\n([\s\S]*?)```/);
      if (fencedMatch && fencedMatch[1]) {
        text = String(fencedMatch[1] || '').trim();
      }
      text = extractReplyBodyFromJsonText(text) || text;
      text = text.replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n').replace(/\\r/g, '\n');
      var lines = text.split(/\r?\n/);
      while (lines.length) {
        var first = String(lines[0] || '').trim();
        if (!first) {
          lines.shift();
          continue;
        }
        if (/^(?:#{1,6}\s*)?회신\s*메일\s*본문\s*초안\s*[:：]?$/i.test(first)) {
          lines.shift();
          continue;
        }
        if (/^(?:#{1,6}\s*)?회신\s*본문\s*초안\s*[:：]?$/i.test(first)) {
          lines.shift();
          continue;
        }
        if (/^(?:[-=]{3,})$/.test(first)) {
          lines.shift();
          continue;
        }
        break;
      }
      var firstDraftLineIndex = -1;
      for (var idx = 0; idx < lines.length; idx += 1) {
        var line = String(lines[idx] || '').trim();
        if (!line) continue;
        if (/^(안녕하세요|안녕하십니까|감사합니다)[,.\s]?/.test(line)) {
          firstDraftLineIndex = idx;
          break;
        }
        if (/^[가-힣a-zA-Z0-9._-]+님[,.\s]*$/.test(line)) {
          firstDraftLineIndex = idx;
          break;
        }
      }
      if (firstDraftLineIndex > 0) {
        lines = lines.slice(firstDraftLineIndex);
      }
      return lines.join('\n').trim();
    }

    function extractReplyBodyFromJsonText(text) {
      var source = String(text || '').trim();
      if (!source) return '';
      if (source.indexOf('{') !== 0) return '';
      var parsed = safeJsonParse(source);
      if (!parsed || typeof parsed !== 'object') return '';
      var keys = ['reply_draft', 'draft_answer', 'additional_body', 'reply_body', 'response_body', 'answer'];
      for (var i = 0; i < keys.length; i += 1) {
        var key = keys[i];
        var value = parsed[key];
        if (typeof value === 'string' && String(value || '').trim()) {
          return String(value || '').trim();
        }
      }
      return '';
    }

    function safeJsonParse(source) {
      try {
        return JSON.parse(String(source || ''));
      } catch (_) {
        return null;
      }
    }

    function buildHitlConfirmHtml(metadata) {
      if (!actionBlocks || typeof actionBlocks.buildHitlConfirmHtml !== 'function') return '';
      return actionBlocks.buildHitlConfirmHtml(metadata);
    }

    function buildReplyDraftActionHtml(metadata) {
      if (!actionBlocks || typeof actionBlocks.buildReplyDraftActionHtml !== 'function') return '';
      return actionBlocks.buildReplyDraftActionHtml(metadata, normalizeReplyDraftBodyText);
    }

    function buildReplyTonePickerHtml(metadata) {
      if (!actionBlocks || typeof actionBlocks.buildReplyTonePickerHtml !== 'function') return '';
      return actionBlocks.buildReplyTonePickerHtml(metadata);
    }

    function buildNextActionsHtml(metadata) {
      if (!actionBlocks || typeof actionBlocks.buildNextActionsHtml !== 'function') return '';
      return actionBlocks.buildNextActionsHtml(metadata);
    }

    function renderBasicInfoRows(headers, rows) {
      if (!basicInfoBlocks || typeof basicInfoBlocks.renderBasicInfoRows !== 'function') return '';
      return basicInfoBlocks.renderBasicInfoRows(headers, rows);
    }

    return {
      buildHitlConfirmHtml: buildHitlConfirmHtml,
      buildReplyTonePickerHtml: buildReplyTonePickerHtml,
      buildReplyDraftActionHtml: buildReplyDraftActionHtml,
      buildNextActionsHtml: buildNextActionsHtml,
      normalizeReplyDraftBodyText: normalizeReplyDraftBodyText,
      renderBasicInfoRows: renderBasicInfoRows,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneMessagesMetaBlocks = api;
})(typeof window !== 'undefined' ? window : globalThis);
