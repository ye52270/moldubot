/* ========================================
   MolduBot – Taskpane Helpers
   ======================================== */

(function initTaskpaneHelpers(global) {
  const QUICK_PROMPT_TEMPLATES = [
    '현재메일 요약해줘',
    '현재메일 3~5줄로 요약',
    '현재메일 주요 키워드 2~3개 할일로 등록',
    '현재메일의 주요 내용을 추출해서 할일로 등록',
    '현재메일의 주요 내용중 이슈사항을 정리해서 회의실 예약해줘',
    '현재메일에서 내가 해야할 일을 뽑아서 일정으로 등록해줘',
    '조용득 관련 1월 메일 조회수 요약해줘',
    'M365 프로젝트 진행, 일정 관련 메일을 찾아서 요약해줘. 기술적 이슈도 검색해서 같이 알려줘',
    'M365 프로젝트 진행, 일정 관련 메일에서 수신자별 역할을 표 형식으로 정리해줘',
    '현재메일에서 일정 후보 3개 제안해줘',
    '현재메일 요약 후 주요 수신자를 참석자로 해서 일정 등록해줘',
    '현재메일 주요 이슈 2개를 액션 아이템으로 정리해줘',
    '현재메일 주요 내용을 기준으로 내일 오전 회의실 예약해줘',
    '현재메일의 기술 이슈를 기준으로 할일 3개 등록해줘',
    '현재메일 핵심 내용 2줄 + 리스크 2개 요약해줘',
    'M365 관련 최근 메일 5건만 찾아줘',
    'M365 관련 메일에서 일정 언급만 추려줘',
    '조용득이 보낸 1월 메일 중 이슈만 요약해줘',
    '현재메일 기반으로 회의 안건 3개 만들어줘',
    '현재메일 주요 키워드로 일정 등록 카드 열어줘',
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

  function isCurrentMailQuery(text) {
    const normalized = String(text || '').toLowerCase().replace(/\s+/g, '');
    return normalized.indexOf('현재메일') >= 0;
  }

  function isQuickPromptTrigger(text) {
    return String(text || '').trim() === '?';
  }

  function getQuickPromptTemplates() {
    return QUICK_PROMPT_TEMPLATES.slice();
  }

  function isReportGenerationQuery(text) {
    const normalized = String(text || '').toLowerCase().replace(/\s+/g, '');
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
    const normalized = String(text || '').toLowerCase().replace(/\s+/g, '');
    if (!normalized) return false;
    return (
      normalized.indexOf('주간보고') >= 0 ||
      normalized.indexOf('주간보고작성') >= 0 ||
      normalized.indexOf('주간보고생성') >= 0 ||
      normalized.indexOf('위클리작성') >= 0 ||
      normalized.indexOf('weeklyreport') >= 0
    );
  }

  function isMeetingRoomBookingQuery(text) {
    const normalized = String(text || '').toLowerCase().replace(/\s+/g, '');
    if (!normalized) return false;
    if (normalized.indexOf('회의실') >= 0) return true;
    return (
      normalized.indexOf('미팅룸') >= 0 ||
      normalized.indexOf('meetingroom') >= 0
    );
  }

  function isCurrentMailMeetingRoomSuggestionQuery(text) {
    const normalized = String(text || '').toLowerCase().replace(/\s+/g, '');
    if (!normalized) return false;
    const hasCurrentMail = normalized.indexOf('현재메일') >= 0;
    const hasMeetingRoom = normalized.indexOf('회의실') >= 0 || normalized.indexOf('미팅룸') >= 0 || normalized.indexOf('meetingroom') >= 0;
    if (!hasCurrentMail || !hasMeetingRoom) return false;
    return (
      normalized.indexOf('예약') >= 0 ||
      normalized.indexOf('잡아') >= 0 ||
      normalized.indexOf('제안') >= 0 ||
      normalized.indexOf('요약후') >= 0 ||
      normalized.indexOf('분석') >= 0
    );
  }

  function isCalendarEventQuery(text) {
    const normalized = String(text || '').toLowerCase().replace(/\s+/g, '');
    if (!normalized) return false;
    if (normalized.indexOf('회의실') >= 0 || normalized.indexOf('미팅룸') >= 0 || normalized.indexOf('meetingroom') >= 0) {
      return false;
    }
    if (normalized.indexOf('일정') < 0) return false;
    return (
      normalized.indexOf('등록') >= 0 ||
      normalized.indexOf('추가') >= 0 ||
      normalized.indexOf('생성') >= 0 ||
      normalized.indexOf('잡아') >= 0
    );
  }

  function isCurrentMailCalendarSuggestionQuery(text) {
    const normalized = String(text || '').toLowerCase().replace(/\s+/g, '');
    if (!normalized) return false;
    if (normalized.indexOf('현재메일') < 0) return false;
    return isCalendarEventQuery(normalized);
  }

  function isPromiseBudgetQuery(text) {
    const normalized = String(text || '').toLowerCase().replace(/\s+/g, '');
    if (!normalized) return false;
    return (
      normalized.indexOf('실행예산') >= 0 ||
      normalized.indexOf('promise') >= 0
    );
  }

  function isFinanceSettlementQuery(text) {
    const normalized = String(text || '').toLowerCase().replace(/\s+/g, '');
    if (!normalized) return false;
    return (
      normalized.indexOf('비용정산') >= 0 ||
      normalized.indexOf('정산입력') >= 0 ||
      normalized.indexOf('비용정산입력') >= 0
    );
  }

  function isHrApplyQuery(text) {
    const normalized = String(text || '').toLowerCase().replace(/\s+/g, '');
    if (!normalized) return false;
    return (
      normalized.indexOf('근태') >= 0 ||
      normalized.indexOf('휴가') >= 0 ||
      normalized.indexOf('refreshplan') >= 0
    );
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
