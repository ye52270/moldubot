/* ========================================
   MolduBot – Taskpane Messages Meta UI
   ======================================== */

(function initTaskpaneMessagesMeta(global) {
  function create(options) {
    var byId = options.byId;
    var escapeHtml = options.escapeHtml;
    var escapeAttr = options.escapeAttr || options.escapeHtml;
    var applyInlineFormatting = options.applyInlineFormatting;
    var normalizeHeadingToken = options.normalizeHeadingToken;

    var moduleLoaderFactory =
      (global.TaskpaneModuleLoader && typeof global.TaskpaneModuleLoader.create === 'function')
        ? global.TaskpaneModuleLoader
        : (typeof module !== 'undefined' && module.exports ? require('./taskpane.module_loader.js') : null);
    var moduleLoader = moduleLoaderFactory && typeof moduleLoaderFactory.create === 'function'
      ? moduleLoaderFactory.create()
      : { resolveModule: function () { return null; } };
    var resolveModule = moduleLoader.resolveModule;
    function normalizeDisplayName(raw) {
      var source = String(raw || '').trim();
      var text = source.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
      if (!text) return '';
      var token = text.split(/[;,]/)[0].trim();
      if (!token) return '';
      var korean = /[가-힣]{2,4}/.exec(token);
      if (korean && korean[0]) return String(korean[0]).trim();
      var slashHead = token.split('/')[0].trim();
      if (slashHead && slashHead.indexOf('@') < 0) {
        return slashHead.replace(/^["']+|["']+$/g, '').trim();
      }
      var sourceKorean = /[가-힣]{2,4}/.exec(source);
      if (sourceKorean && sourceKorean[0]) return String(sourceKorean[0]).trim();
      if (token.indexOf('@') >= 0) {
        var emailMatched = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/.exec(token);
        if (emailMatched && emailMatched[0]) return String(emailMatched[0]).trim();
      }
      var anyEmailMatched = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/.exec(source);
      if (anyEmailMatched && anyEmailMatched[0]) return String(anyEmailMatched[0]).trim();
      return token.replace(/^["']+|["']+$/g, '').trim();
    }

    var bannerModule = resolveModule('TaskpaneMessagesMetaBanner', './taskpane.messages.meta.banner.js');
    var bannerRenderer = bannerModule && typeof bannerModule.create === 'function'
      ? bannerModule.create({
        byId: byId,
        escapeHtml: escapeHtml,
        escapeAttr: escapeAttr,
        normalizeDisplayName: normalizeDisplayName,
      })
      : {};

    var blocksModule = resolveModule('TaskpaneMessagesMetaBlocks', './taskpane.messages.meta.blocks.js');
    var blocksRenderer = blocksModule && typeof blocksModule.create === 'function'
      ? blocksModule.create({
        escapeHtml: escapeHtml,
        escapeAttr: escapeAttr,
        applyInlineFormatting: applyInlineFormatting,
        normalizeHeadingToken: normalizeHeadingToken,
        normalizeDisplayName: normalizeDisplayName,
      })
      : {};

    return {
      renderSelectedMailBanner: bannerRenderer.renderSelectedMailBanner || function () { return; },
      buildHitlConfirmHtml: blocksRenderer.buildHitlConfirmHtml || function () { return ''; },
      buildReplyTonePickerHtml: blocksRenderer.buildReplyTonePickerHtml || function () { return ''; },
      buildReplyDraftActionHtml: blocksRenderer.buildReplyDraftActionHtml || function () { return ''; },
      buildNextActionsHtml: blocksRenderer.buildNextActionsHtml || function () { return ''; },
      normalizeReplyDraftBodyText: blocksRenderer.normalizeReplyDraftBodyText || function (text) { return String(text || '').trim(); },
      renderBasicInfoRows: blocksRenderer.renderBasicInfoRows || function () { return ''; },
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneMessagesMeta = api;
})(typeof window !== 'undefined' ? window : globalThis);
