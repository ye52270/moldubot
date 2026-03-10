/* ========================================
   MolduBot – Taskpane Messages Answer Sections
   ======================================== */

(function initTaskpaneMessagesAnswerSections(global) {
  function create(options) {
    var escapeAttr = options && typeof options.escapeAttr === 'function'
      ? options.escapeAttr
      : function passthrough(value) { return String(value || ''); };
    var applyInlineFormatting = options && typeof options.applyInlineFormatting === 'function'
      ? options.applyInlineFormatting
      : function passthrough(value) { return String(value || ''); };
    var buildInlineEvidencePopover = options && typeof options.buildInlineEvidencePopover === 'function'
      ? options.buildInlineEvidencePopover
      : function emptyPopover() { return ''; };

    function normalizeHeadingToken(text) {
      return String(text || '')
        .toLowerCase()
        .replace(/\s+/g, '')
        .replace(/[^a-z0-9가-힣]/g, '');
    }

    function resolveSummarySectionKey(headingText) {
      var token = normalizeHeadingToken(headingText);
      if (!token) return '';
      if (token.indexOf('수신자역할') >= 0 || token.indexOf('수신자별역할') >= 0 || token.indexOf('참여자역할') >= 0) return 'recipient-role';
      if (token === '제목') return 'title';
      if (token.indexOf('핵심문제') >= 0 || token.indexOf('핵심이슈') >= 0 || token.indexOf('한줄요약') >= 0) return 'executive';
      if (token.indexOf('회의안건요약') >= 0 || token.indexOf('회의안건') >= 0) return 'executive';
      if (token.indexOf('일정안건요약') >= 0 || token.indexOf('일정안건') >= 0) return 'executive';
      if (token.indexOf('주요내용') >= 0 || token.indexOf('외부정보요약') >= 0) return 'major';
      if (token.indexOf('논의할주요내용') >= 0) return 'major';
      if (token.indexOf('조치필요') >= 0 || token.indexOf('필요조치') >= 0) return 'action';
      if (token.indexOf('기술이슈') >= 0 || token.indexOf('기술검토') >= 0 || token.indexOf('기술근거') >= 0) return 'tech-issue';
      if (token.indexOf('참석자제안') >= 0) return 'basic';
      if (token.indexOf('기본정보') >= 0) return 'basic';
      if (token.indexOf('코드분석') >= 0) return 'code-analysis';
      if (token.indexOf('코드리뷰') >= 0) return 'code-review';
      return '';
    }

    function isExecutiveBriefHeading(text) {
      var token = normalizeHeadingToken(text);
      if (!token) return false;
      return (
        token.indexOf('핵심문제요약') >= 0 ||
        token.indexOf('핵심이슈요약') >= 0 ||
        token.indexOf('핵심문제') >= 0 ||
        token.indexOf('핵심이슈') >= 0 ||
        token.indexOf('한줄요약') >= 0
      );
    }

    function resolveExecutiveSeverity(text) {
      var compact = String(text || '').replace(/\s+/g, '').toLowerCase();
      if (!compact) return { tone: 'low', label: '낮음' };
      if (/긴급|즉시|critical|치명|고위험|심각/.test(compact)) return { tone: 'high', label: '높음' };
      if (/경고|주의|필요|요청|확인|중요/.test(compact)) return { tone: 'medium', label: '중간' };
      return { tone: 'low', label: '낮음' };
    }

    function buildExecutiveBriefHtml(summaryText, metadata) {
      var normalizedSummary = String(summaryText || '').trim();
      if (!normalizedSummary) return '';
      var severity = resolveExecutiveSeverity(normalizedSummary);
      var evidencePopover = buildInlineEvidencePopover(metadata, normalizedSummary);
      return (
        '<div class="executive-brief-card tone-' + escapeAttr(severity.tone) + '">' +
          '<div class="executive-brief-header"><span class="executive-brief-kicker">한 줄 결론</span></div>' +
          '<p class="executive-brief-summary">' + applyInlineFormatting(normalizedSummary) + '</p>' +
          '<div class="executive-brief-footer"><span class="executive-brief-label">핵심 판단</span>' + evidencePopover + '</div>' +
        '</div>'
      );
    }

    return {
      normalizeHeadingToken: normalizeHeadingToken,
      resolveSummarySectionKey: resolveSummarySectionKey,
      isExecutiveBriefHeading: isExecutiveBriefHeading,
      resolveExecutiveSeverity: resolveExecutiveSeverity,
      buildExecutiveBriefHtml: buildExecutiveBriefHtml,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (global) {
    global.TaskpaneMessagesAnswerSections = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
