/* ========================================
   MolduBot – Taskpane Helpers
   ======================================== */

(function initTaskpaneHelpers(global) {
  const QUICK_PROMPT_TEMPLATES = [
    '현재메일 요약해줘',
    '현재메일 3~5줄로 요약해줘',
    '현재메일의 이슈가 뭐야?',
    '메일에서 언급한 LDAP 쿼리가 어떤것인지 보여줘',
    '지금 메일의 LDAP쿼리가 어떤 내용인지 인터넷 검색을 통해 알려줘',
  ];

  function byId(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function escapeAttr(value) {
    return escapeHtml(value);
  }

  function shortId(value) {
    const normalized = String(value || '').trim();
    if (!normalized) return '';
    if (normalized.length <= 20) return normalized;
    return normalized.slice(0, 10) + '...' + normalized.slice(-8);
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  function normalizeQuery(text) {
    return String(text || '').toLowerCase().replace(/\s+/g, '');
  }

  function hasAnyToken(text, tokens) {
    if (!text) return false;
    return tokens.some(function (token) { return text.indexOf(token) >= 0; });
  }

  function isCurrentMailQuery(text) {
    const normalized = normalizeQuery(text);
    return normalized.indexOf('현재메일') >= 0;
  }

  function isQuickPromptTrigger(text) {
    return String(text || '').trim() === '?';
  }

  function getQuickPromptTemplates() {
    return QUICK_PROMPT_TEMPLATES.slice();
  }

  function isReportGenerationQuery(text) {
    const normalized = normalizeQuery(text);
    if (!normalized) return false;
    if (
      normalized === '보고서' ||
      normalized.indexOf('/보고서') === 0 ||
      normalized.indexOf('보고서') === 0 ||
      normalized === '리포트' ||
      normalized.indexOf('/리포트') === 0 ||
      normalized.indexOf('리포트') === 0
    ) {
      return true;
    }
    if (normalized.indexOf('보고서') < 0 && normalized.indexOf('리포트') < 0) {
      return false;
    }
    return (
      normalized.indexOf('보고서생성') >= 0 ||
      normalized.indexOf('보고서작성') >= 0 ||
      normalized.indexOf('보고서만들') >= 0 ||
      normalized.indexOf('리포트작성') >= 0 ||
      normalized.indexOf('리포트생성') >= 0
    );
  }

  function isWeeklyReportGenerationQuery(text) {
    const normalized = normalizeQuery(text);
    return hasAnyToken(normalized, ['주간보고', '주간보고작성', '주간보고생성', '위클리작성', 'weeklyreport']);
  }

  function isMeetingRoomBookingQuery(text) {
    const normalized = normalizeQuery(text);
    return hasAnyToken(normalized, ['회의실', '미팅룸', 'meetingroom']);
  }

  function isCurrentMailMeetingRoomSuggestionQuery(text) {
    const normalized = normalizeQuery(text);
    const hasCurrentMail = normalized.indexOf('현재메일') >= 0;
    const hasMeetingRoom = hasAnyToken(normalized, ['회의실', '미팅룸', 'meetingroom']);
    if (!hasCurrentMail || !hasMeetingRoom) return false;
    return hasAnyToken(normalized, ['예약', '잡아', '제안', '요약후', '분석']);
  }

  function isCalendarEventQuery(text) {
    const normalized = normalizeQuery(text);
    if (hasAnyToken(normalized, ['회의실', '미팅룸', 'meetingroom'])) {
      return false;
    }
    if (normalized.indexOf('일정') < 0) return false;
    return hasAnyToken(normalized, ['등록', '추가', '생성', '잡아']);
  }

  function isCurrentMailCalendarSuggestionQuery(text) {
    const normalized = normalizeQuery(text);
    if (normalized.indexOf('현재메일') < 0) return false;
    return isCalendarEventQuery(normalized);
  }

  function isPromiseBudgetQuery(text) {
    const normalized = normalizeQuery(text);
    return hasAnyToken(normalized, ['실행예산', 'promise']);
  }

  function isFinanceSettlementQuery(text) {
    const normalized = normalizeQuery(text);
    return hasAnyToken(normalized, ['비용정산', '정산입력', '비용정산입력']);
  }

  function isHrApplyQuery(text) {
    const normalized = normalizeQuery(text);
    return hasAnyToken(normalized, ['근태', '휴가', 'refreshplan']);
  }

  function logClientEvent(level, eventName, payload) {
    try {
      fetch('/addin/client-logs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          level: String(level || 'info'),
          event: String(eventName || 'unknown'),
          payload: payload || {},
        }),
      }).catch(function () {
        return null;
      });
    } catch (error) {
      void error;
    }
  }

  const api = {
    byId: byId,
    escapeHtml: escapeHtml,
    escapeAttr: escapeAttr,
    shortId: shortId,
    sleep: sleep,
    isQuickPromptTrigger: isQuickPromptTrigger,
    getQuickPromptTemplates: getQuickPromptTemplates,
    isCurrentMailQuery: isCurrentMailQuery,
    isReportGenerationQuery: isReportGenerationQuery,
    isWeeklyReportGenerationQuery: isWeeklyReportGenerationQuery,
    isMeetingRoomBookingQuery: isMeetingRoomBookingQuery,
    isCurrentMailMeetingRoomSuggestionQuery: isCurrentMailMeetingRoomSuggestionQuery,
    isCalendarEventQuery: isCalendarEventQuery,
    isCurrentMailCalendarSuggestionQuery: isCurrentMailCalendarSuggestionQuery,
    isPromiseBudgetQuery: isPromiseBudgetQuery,
    isFinanceSettlementQuery: isFinanceSettlementQuery,
    isHrApplyQuery: isHrApplyQuery,
    logClientEvent: logClientEvent,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }

  global.TaskpaneHelpers = api;
})(typeof window !== 'undefined' ? window : globalThis);
