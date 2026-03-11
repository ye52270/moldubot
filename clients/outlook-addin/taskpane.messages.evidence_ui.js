/* ========================================
   MolduBot – Taskpane Messages Evidence UI
   ======================================== */

(function initTaskpaneMessagesEvidenceUi(global) {
  function create(options) {
    var escapeHtml = options && typeof options.escapeHtml === 'function'
      ? options.escapeHtml
      : function passthrough(value) { return String(value || ''); };
    var escapeAttr = options && typeof options.escapeAttr === 'function'
      ? options.escapeAttr
      : escapeHtml;
    var uiCommon = options && options.uiCommon && typeof options.uiCommon === 'object'
      ? options.uiCommon
      : null;

    function normalizeEvidenceToken(text) {
      return String(text || '')
        .toLowerCase()
        .replace(/\s+/g, '')
        .replace(/[^a-z0-9가-힣]/g, '');
    }

    function resolveMajorPointEvidence(metadata, titleText, preferredIndex) {
      var rows = metadata && Array.isArray(metadata.major_point_evidence) ? metadata.major_point_evidence : [];
      if (!rows.length) return null;
      var preferred = Number(preferredIndex);
      if (Number.isInteger(preferred) && preferred >= 0 && preferred < rows.length) {
        var preferredRow = rows[preferred];
        if (preferredRow && typeof preferredRow === 'object') return preferredRow;
      }
      var target = normalizeEvidenceToken(titleText);
      if (!target) return null;
      for (var index = 0; index < rows.length; index += 1) {
        var row = rows[index];
        if (!row || typeof row !== 'object') continue;
        var point = normalizeEvidenceToken(row.point || '');
        if (!point) continue;
        if (point === target || point.indexOf(target) >= 0 || target.indexOf(point) >= 0) {
          return row;
        }
      }
      return null;
    }

    function buildInlineEvidenceListHtml(evidenceList) {
      var sources = Array.isArray(evidenceList) ? evidenceList : [];
      if (!sources.length) return '';
      var items = sources.slice(0, 3).map(function (item) {
        var source = item && typeof item === 'object' ? item : {};
        var messageId = String(source.message_id || '').trim();
        var title = String(source.subject || '').trim() || '제목 없음';
        var receivedDate = String(source.received_date || '').trim();
        var senderNames = String(source.sender_names || '').trim();
        var snippet = String(source.snippet || source.summary_text || '').trim();
        if (!messageId) return '';
        return (
          '<li class="inline-evidence-item">' +
            '<button type="button" class="inline-evidence-open-btn" data-action="open-evidence-mail" data-message-id="' + escapeAttr(messageId) + '">' +
              '<span class="inline-evidence-subject">' + escapeHtml(title) + '</span>' +
              '<span class="inline-evidence-meta">' + escapeHtml((receivedDate || '-') + (senderNames ? ' · ' + senderNames : '')) + '</span>' +
              (snippet ? '<span class="inline-evidence-related-snippet">' + escapeHtml(snippet) + '</span>' : '') +
            '</button>' +
          '</li>'
        );
      }).filter(function (value) { return Boolean(value); }).join('');
      if (!items) return '';
      return '<ul class="inline-evidence-list">' + items + '</ul>';
    }

    function buildInlineRelatedMailEvidenceHtml(relatedMails) {
      var sources = Array.isArray(relatedMails) ? relatedMails : [];
      if (!sources.length) return '';
      var items = sources.slice(0, 2).map(function (item) {
        var source = item && typeof item === 'object' ? item : {};
        var title = String(source.subject || '').trim() || '제목 없음';
        var senderNames = String(source.sender_names || '').trim() || '-';
        var receivedDate = String(source.received_date || '').trim() || '-';
        var snippet = String(source.snippet || '').trim();
        var messageId = String(source.message_id || '').trim();
        if (!messageId) return '';
        return (
          '<li class="inline-evidence-related-item">' +
            '<button type="button" class="inline-evidence-open-btn evidence-open-btn" data-action="open-evidence-mail" data-message-id="' + escapeAttr(messageId) + '">' +
              '<span class="inline-evidence-subject">' + escapeHtml(title) + '</span>' +
              '<span class="inline-evidence-meta">' + escapeHtml(receivedDate + ' · ' + senderNames) + '</span>' +
              (snippet ? '<span class="inline-evidence-related-snippet">' + escapeHtml(snippet) + '</span>' : '') +
            '</button>' +
          '</li>'
        );
      }).filter(function (value) { return Boolean(value); }).join('');
      if (!items) return '';
      return (
        '<div class="inline-evidence-section">' +
          '<div class="inline-evidence-section-title">관련 메일 근거</div>' +
          '<ul class="inline-evidence-related-list">' + items + '</ul>' +
        '</div>'
      );
    }

    function resolveEvidenceTriggerIconHtml() {
      if (uiCommon && typeof uiCommon.evidenceTriggerIconHtml === 'function') {
        return uiCommon.evidenceTriggerIconHtml();
      }
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

    function buildInlineEvidencePopover(metadata, titleText, optionsArg) {
      var options = optionsArg && typeof optionsArg === 'object' ? optionsArg : {};
      var pointEvidence = resolveMajorPointEvidence(metadata, titleText, options.preferredIndex);
      var evidenceList = metadata && Array.isArray(metadata.evidence_mails) ? metadata.evidence_mails : [];
      var pointRelatedMails = pointEvidence && Array.isArray(pointEvidence.related_mails) ? pointEvidence.related_mails : [];
      var scopedEvidence = pointRelatedMails.length ? pointRelatedMails : evidenceList;
      var evidenceListHtml = buildInlineEvidenceListHtml(scopedEvidence);
      if (!evidenceListHtml) return '';
      var quote = String(pointEvidence && pointEvidence.mail_quote ? pointEvidence.mail_quote : '').trim();
      var location = String(pointEvidence && pointEvidence.mail_location ? pointEvidence.mail_location : '').trim();
      var quoteHtml = quote
        ? (
          '<div class="inline-evidence-section">' +
            '<div class="inline-evidence-section-title">메일 근거 문구</div>' +
            '<div class="inline-evidence-quote">"' + escapeHtml(quote) + '"</div>' +
            (location ? '<div class="inline-evidence-quote-meta">' + escapeHtml(location) + '</div>' : '') +
          '</div>'
        )
        : '';
      var relatedMailEvidenceHtml = pointRelatedMails.length
        ? ''
        : buildInlineRelatedMailEvidenceHtml(pointEvidence && pointEvidence.related_mails);
      return (
        '<details class="inline-evidence-popover inline-evidence-popover-compact">' +
          '<summary class="inline-evidence-trigger" title="근거 보기" aria-label="근거 보기">' +
            resolveEvidenceTriggerIconHtml() +
          '</summary>' +
          '<div class="inline-evidence-panel">' +
            '<div class="inline-evidence-panel-title">근거 메일</div>' +
            quoteHtml +
            relatedMailEvidenceHtml +
            evidenceListHtml +
          '</div>' +
        '</details>'
      );
    }

    function buildTechIssueDetailPopover(cluster, optionsArg) {
      var row = cluster && typeof cluster === 'object' ? cluster : null;
      if (!row) return '';
      var related = Array.isArray(row.related_mails) ? row.related_mails : [];
      if (!related.length) return '';
      var relatedHtml = buildInlineEvidenceListHtml(related);
      if (!relatedHtml) return '';
      var options = optionsArg && typeof optionsArg === 'object' ? optionsArg : {};
      var triggerTitle = String(options.triggerTitle || '기술 근거 보기');
      var panelTitle = String(options.panelTitle || '기술 근거 상세');
      return (
        '<details class="inline-evidence-popover inline-evidence-popover-compact">' +
          '<summary class="inline-evidence-trigger" title="' + escapeAttr(triggerTitle) + '" aria-label="' + escapeAttr(triggerTitle) + '">' +
            resolveEvidenceTriggerIconHtml() +
          '</summary>' +
          '<div class="inline-evidence-panel">' +
            '<div class="inline-evidence-panel-title">' + escapeHtml(panelTitle) + '</div>' +
            relatedHtml +
          '</div>' +
        '</details>'
      );
    }

    return {
      normalizeEvidenceToken: normalizeEvidenceToken,
      resolveMajorPointEvidence: resolveMajorPointEvidence,
      buildInlineEvidenceListHtml: buildInlineEvidenceListHtml,
      buildInlineRelatedMailEvidenceHtml: buildInlineRelatedMailEvidenceHtml,
      resolveEvidenceTriggerIconHtml: resolveEvidenceTriggerIconHtml,
      buildInlineEvidencePopover: buildInlineEvidencePopover,
      buildTechIssueDetailPopover: buildTechIssueDetailPopover,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (global) {
    global.TaskpaneMessagesEvidenceUi = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
