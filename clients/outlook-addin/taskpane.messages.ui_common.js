/* ========================================
   MolduBot – Taskpane Messages UI Common
   ======================================== */

(function initTaskpaneMessagesUiCommon(global) {
  function create(options) {
    var escapeAttr = options && (options.escapeAttr || options.escapeHtml)
      ? (options.escapeAttr || options.escapeHtml)
      : function passthrough(value) { return String(value || ''); };

    function evidenceTriggerIconHtml() {
      return (
        '<span class="inline-evidence-trigger-icon" aria-hidden="true">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M9 9h6v6H9z"/>' +
            '<path d="M4 10V7a3 3 0 0 1 3-3h3"/>' +
            '<path d="M20 14v3a3 3 0 0 1-3 3h-3"/>' +
            '<path d="M14 4h3a3 3 0 0 1 3 3v3"/>' +
            '<path d="M10 20H7a3 3 0 0 1-3-3v-3"/>' +
          '</svg>' +
        '</span>'
      );
    }

    function renderIndexedSummaryCard(optionsArg) {
      var options = optionsArg && typeof optionsArg === 'object' ? optionsArg : {};
      var index = Number(options.index || 0);
      var titleHtml = String(options.titleHtml || '').trim();
      if (!titleHtml) return '';
      var subtitleDateHtml = String(options.subtitleDateHtml || '').trim();
      var subtitleHtml = String(options.subtitleHtml || '').trim();
      var subtitleExtraHtml = String(options.subtitleExtraHtml || '').trim();
      var rightAddonHtml = String(options.rightAddonHtml || '').trim();
      var hasSubline = Boolean(subtitleDateHtml || subtitleHtml || subtitleExtraHtml);
      var cardClassName = String(options.cardClassName || '').trim();
      var textBlockClassName = String(options.textBlockClassName || '').trim();
      var textsClassName = ['major-summary-texts', textBlockClassName]
        .filter(function (value) { return Boolean(value); })
        .join(' ');
      return (
        '<li class="major-summary-item">' +
          '<div class="major-summary-card' + (cardClassName ? ' ' + escapeAttr(cardClassName) : '') + '">' +
            '<div class="major-summary-line">' +
              '<span class="major-summary-index">' + String(index) + '</span>' +
              '<div class="major-summary-main">' +
                '<div class="major-summary-title-row">' +
                  '<div class="major-summary-card-title">' + titleHtml + '</div>' +
                  rightAddonHtml +
                '</div>' +
                (hasSubline
                  ? (
                    '<div class="major-summary-subline">' +
                      '<div class="' + escapeAttr(textsClassName) + '">' +
                        (subtitleDateHtml ? '<div class="major-summary-card-date">' + subtitleDateHtml + '</div>' : '') +
                        (subtitleHtml ? '<div class="major-summary-card-sub">' + subtitleHtml + '</div>' : '') +
                        subtitleExtraHtml +
                      '</div>' +
                    '</div>'
                  )
                  : '') +
              '</div>' +
            '</div>' +
          '</div>' +
        '</li>'
      );
    }

    return {
      evidenceTriggerIconHtml: evidenceTriggerIconHtml,
      renderIndexedSummaryCard: renderIndexedSummaryCard,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (global) {
    global.TaskpaneMessagesUiCommon = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
