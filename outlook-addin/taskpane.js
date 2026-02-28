/* ========================================
   MolduBot – Taskpane Logic
   ======================================== */

const API_BASE = (() => {
  try {
    const fromQuery = new URLSearchParams(window.location.search).get('api_base');
    if (fromQuery && /^https?:\/\//i.test(fromQuery)) {
      return fromQuery.replace(/\/+$/, '');
    }
  } catch (error) {
    console.warn('[MolduBot][api.base.resolve.failed]', error);
  }
  if (window.location && window.location.origin) {
    return window.location.origin.replace(/\/+$/, '');
  }
  return 'https://localhost:8000';
})();
const API_TIMEOUT_MS = 20000;
const API_TIMEOUT_DEEP_MS = 45000;
const API_TIMEOUT_CODE_REVIEW_MS = 90000;
const API_TIMEOUT_INTENT_RESOLVE_MS = 2500;
const ENABLE_WEB_OPEN_FALLBACK = false;
const TASKPANE_BUILD = '20260226-21';
const TaskpaneMarkdownUtils = window.TaskpaneMarkdownUtils;
if (!TaskpaneMarkdownUtils) {
  throw new Error('taskpane.markdown-utils.js failed to load');
}
const {
  escapeHtml,
  escapeAttr,
  renderMarkdown,
} = TaskpaneMarkdownUtils;
let STICKY_CURRENT_MAIL_TTL_MS = 10 * 60 * 1000;
let STICKY_CURRENT_MAIL_MAX_TURNS = 4;

// ── State ────────────────────────────────
let currentMode = 'email';          // 'email' | 'assistant'
let currentScope = 'email';         // 'email' | 'all' | 'systems'
let currentScopeLabelOverride = '';
let chatThreadId = 'outlook_' + Date.now();
let emailContext = null;             // { subject, body, from, itemId }
let isProcessing = false;
let pendingHrDraft = null;           // { leaveDate, leaveType, reason }
let pendingPromiseContext = null;    // { projectNumber, projectName, projectType, status }
let pendingRoomSelection = null;     // { step, building, floor, room }
let pendingQuickAction = null;       // { label, mode }
let chatHistory = [];                // [{ role, text, options? }]
let restoredInputDraft = '';
let lastTurnStartedAtMs = 0;
let lastCompletedTurnElapsedMs = Number.NaN;
let chatInputImeComposing = false;
let scopeShortcutMenuEl = null;
let scopeShortcutItems = [];
let scopeShortcutActiveIndex = -1;
let verbShortcutMenuEl = null;
let verbShortcutItems = [];
let verbShortcutActiveIndex = -1;
let structuredSelectionRowEl = null;
let clarificationPopupEl = null;
let marketToastEl = null;
let marketToastMode = 'menu';
let marketInstalledAppIds = new Set();
let marketInstalledSkillIds = new Set();
let marketInstalledAgentIds = new Set();
let marketRegistrationProgress = new Map();
let marketRegistrationTimers = new Map();
let pendingEmailIdResolve = null;
let lastAutoBootstrapContextKey = '';
try {
  document.documentElement.classList.add('theme-dark');
} catch (error) {
  console.warn('[MolduBot][theme.default_dark.failed]', error);
}
const TASKPANE_STATE_VERSION = 2;
const MAX_PERSISTED_MESSAGES = 80;
let stickyCurrentMailContext = {
  threadId: '',
  emailMessageId: '',
  turnsRemaining: 0,
  expiresAt: 0,
  updatedAt: 0,
  source: '',
};
const EMAIL_NOT_FOUND_PATTERNS = [
  /메일을\s*찾을\s*수\s*없/i,
  /메일이\s*동기화되지\s*않/i,
  /해당\s*메일.*조회할\s*수\s*없/i,
  /메일.*확인해\s*주세요/i,
];
const PROMISE_ANALYSIS_KEYWORDS = [
  '분석',
  '추세',
  '증가',
  '감소',
  '비율',
  '비교',
  '얼마',
  '합계',
  '총액',
  'gap',
  '인건비',
  '외주비',
  '재료비',
  '경비',
  '비용',
];
const MARKET_STORAGE_KEY = 'moldubot_market_registry_v1';
const MARKET_APP_CATALOG = Object.freeze([
  { id: 'promise', token: '@실행예산', label: '실행예산', hint: '예산 조회/입력 워크플로우', domain: 'promise' },
  { id: 'procurement', token: '@구매정보', label: '구매정보', hint: '구매 요청/진행 상태 조회', domain: 'procurement' },
  { id: 'hr_apply', token: '@근태신청', label: '근태신청', hint: '근태 신청/결재 업무', domain: 'hr' },
  { id: 'finance', token: '@비용정산', label: '비용정산', hint: '비용 정산 조회/신청', domain: 'finance' },
]);
const MARKET_SKILL_CATALOG = Object.freeze([
  { id: 'code_analysis', token: '/코드분석', label: '코드 분석', hint: '코드 품질/리스크/개선 포인트 분석' },
  { id: 'report_writer', token: '/보고서작성', label: '보고서 작성', hint: '요약 기반 보고서 자동 작성' },
  { id: 'trend_analysis', token: '/트렌드분석', label: '트렌드 분석', hint: '기간별 변화 분석 및 인사이트' },
  { id: 'weekly_report', token: '/주간보고', label: '주간보고 작성', hint: '주간 성과/이슈 템플릿 정리' },
  { id: 'proposal_review', token: '/제안서리뷰', label: '제안서 리뷰', hint: '리스크/개선 포인트 점검' },
]);
const MARKET_AGENT_CATALOG = Object.freeze([
  { id: 'meeting_copilot', token: '@회의코디', label: '회의 코디', hint: '회의 준비/아젠다/후속 작업 정리' },
  { id: 'mail_guard', token: '@메일가드', label: '메일 가드', hint: '중요 메일 분류와 응답 우선순위 점검' },
  { id: 'report_coach', token: '@리포트코치', label: '리포트 코치', hint: '보고서 구조화와 문장 개선 가이드' },
  { id: 'ops_automator', token: '@업무자동화', label: '업무 자동화', hint: '반복 업무 단계 점검 및 실행 제안' },
]);
const handledMyHREventKeys = new Set();
const deepProgressTrackerRegistry = new Map();
const TaskpaneStructuredUtils = window.TaskpaneStructuredUtils;
if (!TaskpaneStructuredUtils) {
  throw new Error('taskpane.structured-utils.js failed to load');
}
const TaskpaneThemeUtils = window.TaskpaneThemeUtils;
if (!TaskpaneThemeUtils) {
  console.warn('[MolduBot][bootstrap] taskpane.theme-utils.js failed to load; fallback mode');
}
const TaskpaneInputUtils = window.TaskpaneInputUtils;
if (!TaskpaneInputUtils) {
  console.warn('[MolduBot][bootstrap] taskpane.input-utils.js failed to load; fallback mode');
}
const TaskpaneAutoScheduleUtils = window.TaskpaneAutoScheduleUtils;
if (!TaskpaneAutoScheduleUtils) {
  console.warn('[MolduBot][bootstrap] taskpane.auto-schedule-utils.js failed to load; fallback mode');
}
const TaskpaneIntentUtils = window.TaskpaneIntentUtils;
if (!TaskpaneIntentUtils) {
  console.warn('[MolduBot][bootstrap] taskpane.intent-utils.js failed to load; fallback mode');
}
const TaskpaneRendererUtils = window.TaskpaneRendererUtils;
if (!TaskpaneRendererUtils) {
  console.warn('[MolduBot][bootstrap] taskpane.renderer-utils.js failed to load; fallback mode');
}
const TaskpaneMailOpenUtils = window.TaskpaneMailOpenUtils;
if (!TaskpaneMailOpenUtils) {
  console.warn('[MolduBot][bootstrap] taskpane.mail-open-utils.js failed to load; fallback mode');
}
const {
  SCOPE_SHORTCUTS,
  STRUCTURED_INPUT_MAX_CHIPS,
  STRUCTURED_CHIP_TOKEN_BY_ID,
  STRUCTURED_VERB_TOKEN_BY_ID,
  STRUCTURED_COMBOS_BY_CHIPS_KEY,
  toBool,
  normalizeScope,
  normalizeShortcutDomain,
  modeFromScope,
  scopeFromMode,
  parseScopeFromMessagePrefix,
  parseNaturalLanguageIntentProbe,
  parseDomainShortcutFromPrefix,
  resolveSystemScopeLabelOverride,
  normalizeCompactToken,
  resolveStructuredChipId,
  extractStructuredChipIdsFromText,
  extractStructuredVerbIdsFromText,
  hasStructuredForbiddenPair,
  resolveAllowedNextStructuredChipIds,
  resolveStructuredScopeFromChips,
  resolveStructuredDomainFromChips,
  buildStructuredLegacyMessage,
  buildIntentProbeResultText,
  toStructuredChipKey,
} = TaskpaneStructuredUtils;
const {
  initializeOutlookThemeSync,
} = TaskpaneThemeUtils || {
  initializeOutlookThemeSync: () => {},
};
const {
  handleShortcutMenuKeyDown,
  autoResizeComposer,
  setButtonEnabled,
} = TaskpaneInputUtils || {
  handleShortcutMenuKeyDown: () => false,
  autoResizeComposer: (textarea) => {
    if (!textarea || !textarea.style) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight || 0, 100)}px`;
  },
  setButtonEnabled: (buttonEl, enabled) => {
    if (!buttonEl) return;
    buttonEl.disabled = !enabled;
  },
};
const {
  buildAutoScheduleRegistrationMessage: buildAutoScheduleRegistrationMessageFromUtils,
} = TaskpaneAutoScheduleUtils || {
  buildAutoScheduleRegistrationMessage: ({ emailCtx } = {}) => {
    if (!emailCtx || typeof emailCtx !== 'object') return '';
    const title = String(emailCtx.subject || '메일 후속 조치').trim() || '메일 후속 조치';
    return `${new Date().toISOString().slice(0, 10)} 09:00부터 10:00까지 "${title}" 일정 등록해줘`;
  },
};
const ENABLE_PARTIAL_ANSWER_STREAM = false;
const STATUS_LINE_MAX_LOG_ITEMS = 12;
const STATUS_LINE_RENDER_THROTTLE_MS = 250;
const STATUS_LINE_FALLBACK_NOTICE_TASK_KEY = 'system:fallback_notice';
// 완료/오류 상태 카드는 지연 없이 즉시 제거한다.
const STATUS_LINE_AUTO_DISMISS_MS = 0;
const STATUS_LINE_HEADLINE = Object.freeze({
  analyzing: '요청을 처리하고 있습니다...',
  finalizing: '답변을 작성하고 있습니다...',
  waiting: '확인 대기 중입니다.',
  done: '처리가 완료되었습니다.',
  error: '처리 중 오류가 발생했습니다.',
});
const ASSISTANT_PROMPT_ALIASES = [
  { patterns: ['일정등록', '일정등록해줘', '일정등록해주세요'], canonical: '일정 등록해줘' },
  { patterns: ['회의실예약', '회의실예약해줘', '회의실예약해주세요'], canonical: '회의실 예약해줘' },
  { patterns: ['일정확인', '일정확인해줘', '일정확인해주세요'], canonical: '이번 주 일정을 확인해줘' },
  { patterns: ['회의실확인', '회의실확인해줘', '회의실확인해주세요'], canonical: '예약한 회의실을 확인해줘' },
  { patterns: ['할일확인', '할일확인해줘', 'todo확인'], canonical: '할 일 목록을 보여줘' },
];
const SMALLTALK_PROMPT_SET = new Set([
  '안녕',
  '안녕하세요',
  'ㅎㅇ',
  '하이',
  'hi',
  'hello',
  'hey',
  '반가워',
  '반가워요',
  '고마워',
  '고마워요',
  '감사',
  '감사해요',
  '감사합니다',
  'thanks',
  'thankyou',
]);
const TURN_KIND = Object.freeze({
  TASK: 'task',
  FOLLOWUP_REFINE: 'followup_refine',
  EXPLICIT_SMALLTALK: 'explicit_smalltalk',
});
const TASK_SIGNAL_RE =
  /(조회|검색|예약|등록|생성|작성|분석|요약|번역|답변|회신|도와줘|해주세요|해줘|메일|이메일|회의실|근태|일정|할\s*일|todo|calendar|room|hr|promise|비용정산|구매시스템|실행예산)/i;
const EXPLICIT_SMALLTALK_SIGNAL_RE =
  /(뭐해|뭐\s*하고|잘\s*지내|어때|점심|저녁|아침|식사|밥\s*먹|배고파|졸려|심심|주말|퇴근|너\s*(누구|이름)|반가워|고마워|감사|알아\?)/i;
const FOLLOWUP_REFINE_SIGNAL_RE =
  /(다시|재작성|다듬|간단(?:하게)?|짧(?:게|은)|축약|요약(?:으로)?|정리(?:해)?|한\s*줄|두\s*줄|세\s*줄|[2-9]\s*줄|줄로|핵심만|요점만|자세히|더\s*자세히|why|근거)/i;
const FOLLOWUP_CONTEXT_SHORT_QUERY_RE =
  /^(?:어떤\s*내용(?:이야|인가요|인지)?\??|무슨\s*내용(?:이야|인지)?\??|자세히|더\s*자세히|왜|근거(?:는)?|요약해|정리해|다시)$/i;
const ASSISTANT_RESTART_HINT_RE =
  /(요청\s*처리를\s*진행하려면|요청\s*대상\s*정보가\s*필요|대상\s*정보가\s*필요|다시\s*시도해|다시\s*질문해|원하시는\s*요청을\s*한\s*번에\s*알려)/i;
const ASSISTANT_ERROR_HINT_RE =
  /(응답을\s*받지\s*못했습니다|서버에\s*연결할\s*수\s*없습니다|네트워크\s*상태를\s*확인해주세요|응답\s*시간이\s*길어\s*요청이\s*종료되었습니다|처리\s*중\s*오류가\s*발생했습니다)/i;
const CLARIFICATION_SLOT_LABELS = Object.freeze({
  target_mail_id: '대상 메일',
  reply_tone: '답변 톤',
  query_keyword: '조회 키워드',
  intent_priority: '진행 우선순위',
  date: '날짜',
  time: '시간',
  project_number: '프로젝트 번호',
  intent_target: '요청 대상',
});
const REPLY_TONE_PRESETS = [
  {
    id: 'formal',
    label: '공식/격식체',
  },
  {
    id: 'business_friendly',
    label: '비즈니스 친화적',
  },
  {
    id: 'concise',
    label: '간결/요점 중심',
  },
  {
    id: 'empathetic',
    label: '공감/배려형',
  },
];

// ── SVG icon fragments (reused in JS) ───
const ICONS = {
  sparkles: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/></svg>',
  fileText: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 13H8"/><path d="M16 17H8"/><path d="M16 13h-2"/></svg>',
  calendar: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/></svg>',
  calendarPlus: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/><path d="M12 14v6"/><path d="M9 17h6"/></svg>',
  calendarCheck: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/><path d="m9 16 2 2 4-4"/></svg>',
  listChecks: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/></svg>',
  listPlus: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 6h10"/><path d="M11 12h10"/><path d="M11 18h10"/><path d="M3 12h4"/><path d="M5 10v4"/></svg>',
  building: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="16" height="20" x="4" y="2" rx="2" ry="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/><path d="M8 14h.01"/></svg>',
  buildingPlus: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="20" x="3" y="2" rx="2"/><path d="M8 22v-4h4v4"/><path d="M7 6h.01"/><path d="M13 6h.01"/><path d="M10 6h.01"/><path d="M10 10h.01"/><path d="M10 14h.01"/><path d="M13 10h.01"/><path d="M13 14h.01"/><path d="M7 10h.01"/><path d="M7 14h.01"/><path d="M20 8v6"/><path d="M17 11h6"/></svg>',
  buildingCheck: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="20" x="3" y="2" rx="2"/><path d="M8 22v-4h4v4"/><path d="M7 6h.01"/><path d="M13 6h.01"/><path d="M10 6h.01"/><path d="M10 10h.01"/><path d="M10 14h.01"/><path d="M13 10h.01"/><path d="M13 14h.01"/><path d="M7 10h.01"/><path d="M7 14h.01"/><path d="m17 16 2 2 4-4"/></svg>',
  search: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>',
  code: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18-6-6 6-6"/><path d="m15 6 6 6-6 6"/></svg>',
  mail: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a2 2 0 0 1-2.06 0L2 7"/></svg>',
  reply: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 17 4 12 9 7"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/></svg>',
  languages: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="m22 22-5-10-5 10"/><path d="M14 18h6"/></svg>',
  users: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
  megaphone: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 11 18-5v12L3 13v-2Z"/><path d="M11.6 16.8a3 3 0 1 1-5.6-2.6"/><path d="M6 10v4"/></svg>',
  wallet: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/><path d="M3 10h18"/><path d="M17 14h.01"/><path d="M17 14a2 2 0 1 1 0 4 2 2 0 0 1 0-4Z"/></svg>',
  notebook: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20"/><path d="M6 2h12a2 2 0 0 1 2 2v18H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z"/><path d="M8 7h8"/><path d="M8 11h8"/><path d="M8 15h5"/></svg>',
  shoppingCart: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/><path d="M2.05 2h2l2.6 12.4a2 2 0 0 0 2 1.6h8.9a2 2 0 0 0 2-1.6L22 6H6.3"/><path d="M16 10h.01"/></svg>',
  badgeCheck: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="15" rx="2"/><path d="M7 9h5"/><path d="M7 13h4"/><circle cx="17" cy="11" r="2.5"/><path d="m15.8 15.7 1.2 1.2 2.2-2.2"/></svg>',
  check: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>',
  x: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
  refreshCw: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15.5-6.36L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15.5 6.36L3 16"/></svg>',
  copy: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
  thumbsUp: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10v12"/><path d="M15 5.88 14 10h6a2 2 0 0 1 1.95 2.44l-1.5 7A2 2 0 0 1 18.5 21H7a2 2 0 0 1-2-2v-9.5a2 2 0 0 1 .59-1.41l4.83-4.83A2 2 0 0 1 11.83 3H14a1 1 0 0 1 1 1v1.88Z"/></svg>',
  thumbsDown: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 14V2"/><path d="M9 18.12 10 14H4a2 2 0 0 1-1.95-2.44l1.5-7A2 2 0 0 1 5.5 3H17a2 2 0 0 1 2 2v9.5a2 2 0 0 1-.59 1.41l-4.83 4.83A2 2 0 0 1 12.17 21H10a1 1 0 0 1-1-1v-1.88Z"/></svg>',
  alertTriangle: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
  clock: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
  moon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a8.5 8.5 0 1 0 8.5 8.5A6.5 6.5 0 0 1 12 3z"/></svg>',
  sun: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>',
};

// ── Tool labels for approval UI ──────────
const TOOL_LABELS = {
  intent_confirm: '요청 실행 확인',
  search_emails: '메일 조회',
  create_calendar_event: '일정 등록',
  update_calendar_event: '일정 수정',
  delete_calendar_event: '일정 삭제',
  create_todo_task: 'To Do 생성',
  update_todo_task: 'To Do 수정',
  delete_todo_task: 'To Do 삭제',
  complete_todo_task: 'To Do 완료',
  book_meeting_room: '회의실 예약',
  list_hr_leave_events: '근태 조회',
};

const ARG_LABELS = {
  intent: '의도',
  confidence: '신뢰도',
  clarification_reason: '확인 사유',
  clarification_tier: '확인 단계',
  subject: '제목',
  title: '제목',
  start_time: '시작',
  end_time: '종료',
  body: '내용',
  building: '건물',
  floor: '층',
  room_name: '회의실',
  importance: '중요도',
  due_date: '마감일',
};

function logEvent(event, status = 'ok', meta = {}) {
  try {
    if (typeof globalThis.molduLogEvent === 'function') {
      globalThis.molduLogEvent(event, status, meta);
      return;
    }
  } catch (error) {
    console.warn('[MolduBot][logEvent.fallback]', event, status, error);
  }
  const writer = status === 'error' ? console.error : status === 'warn' ? console.warn : console.log;
  writer(`[MolduBot][${event}][${status}]`, meta || {});
}

function logError(event, error, meta = {}) {
  try {
    if (typeof globalThis.molduLogError === 'function') {
      globalThis.molduLogError(event, error, meta);
      return;
    }
  } catch (bridgeError) {
    console.warn('[MolduBot][logError.fallback]', event, bridgeError);
  }
  console.error(`[MolduBot][${event}][error]`, meta || {}, error);
}

function toUserFacingRequestErrorMessage(error) {
  if (error?.name === 'AbortError') {
    return '응답 시간이 길어 요청이 종료되었습니다. 잠시 후 다시 시도해주세요.';
  }
  return '서버에 연결할 수 없습니다. 네트워크 상태를 확인해주세요.';
}

async function copyTextToClipboard(text) {
  const value = String(text || '');
  if (!value) return false;
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch (error) {
    logError('ui.copy.clipboard_api_failed', error);
  }
  try {
    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    textarea.style.pointerEvents = 'none';
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand('copy');
    document.body.removeChild(textarea);
    return Boolean(copied);
  } catch (error) {
    logError('ui.copy.exec_command_failed', error);
    return false;
  }
}

function flashIconActionFeedback(buttonEl, {
  okLabel = '완료',
  failLabel = '실패',
  success = true,
  durationMs = 1200,
} = {}) {
  if (!buttonEl) return;
  const label = success ? okLabel : failLabel;
  const originalLabel = String(buttonEl.getAttribute('aria-label') || '').trim();
  buttonEl.classList.toggle('is-success', Boolean(success));
  buttonEl.classList.toggle('is-failed', !success);
  buttonEl.setAttribute('aria-label', label);
  buttonEl.setAttribute('title', label);
  window.setTimeout(() => {
    buttonEl.classList.remove('is-success', 'is-failed');
    if (originalLabel) {
      buttonEl.setAttribute('aria-label', originalLabel);
      buttonEl.setAttribute('title', originalLabel);
    }
  }, Math.max(600, Number(durationMs) || 1200));
}

function bindMyHREventBridge() {
  if (window.__moldubot_myhr_bridge_bound) return;
  window.__moldubot_myhr_bridge_bound = true;

  window.addEventListener('message', (event) => {
    if (event.origin !== window.location.origin) return;
    const data = event.data || {};
    if (data.type === 'MYHR_APPROVAL_COMPLETED') {
      handleMyHRApprovalEvent(data);
    }
  });

  window.addEventListener('storage', (event) => {
    if (event.key !== 'myhr_approval_event' || !event.newValue) return;
    try {
      const data = JSON.parse(event.newValue);
      if (data?.type === 'MYHR_APPROVAL_COMPLETED') {
        handleMyHRApprovalEvent(data);
      }
    } catch (error) {
      logError('myhr.storage_event_parse.failed', error);
    }
  });
}

function formatMyHRCompletionMessage(payload) {
  const leaveDate = payload?.leave_date
    ? new Date(`${payload.leave_date}T00:00:00`).toLocaleDateString('ko-KR')
    : '-';
  const leaveType = payload?.leave_type || '-';
  const reason = payload?.reason || '-';
  return [
    '✅ 근태 결재가 완료되었습니다.',
    '',
    `- 근태 날짜: ${leaveDate}`,
    `- 근태 종류: ${leaveType}`,
    `- 사유: ${reason}`,
  ].join('\n');
}

function handleMyHRApprovalEvent(data) {
  const eventKey = `${data.thread_id || 'default'}::${data.timestamp || ''}`;
  if (handledMyHREventKeys.has(eventKey)) return;
  handledMyHREventKeys.add(eventKey);
  addAssistantMessage(formatMyHRCompletionMessage(data.payload || {}));
}

function inferSystemScopeDomainFromLabelOverride() {
  if (normalizeScope(currentScope) !== 'systems') return '';
  const label = String(currentScopeLabelOverride || '').trim();
  if (!label) return '';
  if (/실행\s*예산|promise/i.test(label)) return 'promise';
  if (/비용\s*정산|경비\s*정산|finance/i.test(label)) return 'finance';
  if (/회의실|미팅룸|room/i.test(label)) return 'room';
  if (/근태|휴가|연차|hr/i.test(label)) return 'hr';
  if (/일정|캘린더|스케줄|calendar/i.test(label)) return 'schedule';
  if (/할\s*일|todo/i.test(label)) return 'todo';
  return '';
}

function resolveActiveAssistantShortcutDomain(explicitDomain = '') {
  const direct = normalizeShortcutDomain(explicitDomain);
  if (direct) return direct;
  return inferSystemScopeDomainFromLabelOverride();
}

function extractVerbShortcutQuery(inputEl) {
  if (!inputEl) return null;
  const value = String(inputEl.value || '');
  const caretStart = Number.isFinite(inputEl.selectionStart) ? inputEl.selectionStart : value.length;
  const caretEnd = Number.isFinite(inputEl.selectionEnd) ? inputEl.selectionEnd : value.length;
  if (caretStart !== caretEnd || caretEnd !== value.length) return null;
  const beforeCaret = value.slice(0, caretEnd);
  const matched = /^(\s*(?:@[^\s]+\s+)*)\/([^\s]*)$/.exec(beforeCaret);
  if (!matched) return null;
  const leading = matched[1] || '';
  const query = matched[2] || '';
  const chipIds = extractStructuredChipIdsFromText(leading);
  if (chipIds.length > STRUCTURED_INPUT_MAX_CHIPS) return null;
  if (hasStructuredForbiddenPair(chipIds)) return null;
  return {
    leading,
    query,
    chipIds,
  };
}

function buildVerbShortcutItems(chipIds = [], query = '') {
  const normalizedQuery = normalizeCompactToken(String(query || '').replace(/^\/+/, ''));
  void chipIds;
  const skillItems = getRegisteredSkillShortcuts()
    .map((item) => ({
      token: String(item.token || '').trim(),
      hint: String(item.hint || '').trim(),
      combo: null,
    }))
    .filter((item) => item.token)
    .filter((item) => {
      if (!normalizedQuery) return true;
      return (
        normalizeCompactToken(item.token).includes(normalizedQuery) ||
        normalizeCompactToken(item.hint).includes(normalizedQuery)
      );
    })
    .sort((a, b) => String(a.token || '').localeCompare(String(b.token || ''), 'ko-KR'));
  return skillItems;
}

function ensureScopeShortcutMenu() {
  if (scopeShortcutMenuEl && scopeShortcutMenuEl.isConnected) return scopeShortcutMenuEl;
  const wrapper = document.querySelector('.input-wrapper');
  if (!wrapper) return null;
  const menu = document.createElement('div');
  menu.className = 'scope-shortcut-menu hidden';
  menu.id = 'scopeShortcutMenu';
  menu.setAttribute('role', 'listbox');
  menu.setAttribute('aria-label', '범위 단축어');
  wrapper.appendChild(menu);
  scopeShortcutMenuEl = menu;
  return scopeShortcutMenuEl;
}

function ensureStructuredSelectionRow() {
  if (structuredSelectionRowEl && structuredSelectionRowEl.isConnected) return structuredSelectionRowEl;
  const inputArea = document.querySelector('.input-area');
  const inputWrapper = document.querySelector('.input-wrapper');
  if (!inputArea || !inputWrapper) return null;
  const row = document.createElement('div');
  row.id = 'structuredSelectionRow';
  row.className = 'structured-selection-row hidden';
  row.setAttribute('aria-live', 'polite');
  inputArea.insertBefore(row, inputWrapper);
  structuredSelectionRowEl = row;
  return structuredSelectionRowEl;
}

function ensureClarificationPopup() {
  if (clarificationPopupEl && clarificationPopupEl.isConnected) return clarificationPopupEl;
  const inputArea = document.querySelector('.input-area');
  const inputWrapper = document.querySelector('.input-wrapper');
  if (!inputArea || !inputWrapper) return null;
  const popup = document.createElement('div');
  popup.id = 'clarificationPopup';
  popup.className = 'clarification-popup hidden';
  popup.setAttribute('aria-live', 'polite');
  inputArea.insertBefore(popup, inputWrapper);
  clarificationPopupEl = popup;
  return clarificationPopupEl;
}

function hideClarificationPromptCard() {
  const popup = ensureClarificationPopup();
  if (!popup) return;
  popup.classList.add('hidden');
  popup.innerHTML = '';
}

function _normalizeClarificationOptions(values) {
  if (!Array.isArray(values)) return [];
  const normalized = [];
  for (const item of values) {
    const text = String(item || '').trim();
    if (!text || normalized.includes(text)) continue;
    normalized.push(text);
    if (normalized.length >= 4) break;
  }
  return normalized;
}

function _buildFallbackClarificationOptions(metadata = null) {
  const meta = metadata && typeof metadata === 'object' ? metadata : {};
  const intentDecision =
    meta.intent_decision && typeof meta.intent_decision === 'object' ? meta.intent_decision : {};
  const clarification =
    meta.clarification && typeof meta.clarification === 'object' ? meta.clarification : {};
  const intent = String(intentDecision.intent || intentDecision.primary_intent || '').trim().toLowerCase();
  const missingSlots = Array.isArray(clarification.missing_slots) ? clarification.missing_slots : [];
  const hasMissingQuery =
    missingSlots.map((slot) => String(slot || '').trim().toLowerCase()).includes('query_keyword') ||
    missingSlots.map((slot) => String(slot || '').trim().toLowerCase()).includes('intent_target');

  if (intent === 'mail_search' && hasMissingQuery) {
    return [
      '최근 1주 메일에서 중요/긴급 건을 먼저 찾아줘',
      '최근 1달 메일을 제목·본문 키워드 기준으로 찾아줘',
      '발신자 이름을 입력해서 검색할게',
      '현재 선택한 메일 기준으로만 진행해줘',
    ];
  }
  if (intent === 'schedule_create') {
    return [
      '오늘 오후 3시에 일정 등록해줘',
      '내일 오전 10시에 일정 등록해줘',
      '이번 주 금요일 오후 2시에 일정 등록해줘',
      '날짜만 먼저 정해서 일정 등록해줘',
    ];
  }
  if (intent === 'room_booking') {
    return [
      '오늘 오후 3시에 1시간 회의실 예약해줘',
      '내일 오전 10시에 소회의실 예약해줘',
      '이번 주 금요일 오후 2시에 1시간 예약해줘',
      '날짜와 시간부터 정해서 예약해줘',
    ];
  }
  if (intent === 'hr_apply') {
    return [
      '내일 연차 1일 신청해줘',
      '오늘 반차(오전) 신청해줘',
      '이번 주 금요일 연차 신청해줘',
      '날짜와 휴가 종류부터 정해서 신청해줘',
    ];
  }
  if (intent === 'promise_analysis' || intent === 'promise_menu') {
    return [
      '실행예산 프로젝트번호를 지정해서 분석해줘',
      '실행예산 요약 보고서로 진행해줘',
      '실행예산 화면 열기로 진행해줘',
      '실행예산 업무로 분류해서 진행해줘',
    ];
  }
  if (intent === 'finance_workflow') {
    return [
      '비용정산 처리 화면으로 진행해줘',
      '비용정산 작성으로 진행해줘',
      '비용정산 수정으로 진행해줘',
      '비용정산 조회로 진행해줘',
    ];
  }
  if (intent === 'procurement_workflow') {
    return [
      '구매시스템 처리로 진행해줘',
      '구매요청 작성으로 진행해줘',
      '구매요청 조회로 진행해줘',
      '구매시스템 업무로 분류해서 진행해줘',
    ];
  }
  return [
    '메일 조회로 진행해줘',
    '일정 등록으로 진행해줘',
    '회의실 예약으로 진행해줘',
    '근태 신청으로 진행해줘',
  ];
}

function _extractClarificationPromptPayload(responseData = null) {
  const data = responseData && typeof responseData === 'object' ? responseData : {};
  const metadata = data.metadata && typeof data.metadata === 'object' ? data.metadata : {};
  const clarification =
    metadata.clarification && typeof metadata.clarification === 'object' ? metadata.clarification : {};
  const intentDecision =
    metadata.intent_decision && typeof metadata.intent_decision === 'object' ? metadata.intent_decision : {};
  const contextContract =
    metadata.context_contract && typeof metadata.context_contract === 'object' ? metadata.context_contract : {};
  const mode = String(clarification.mode || '').trim().toLowerCase();
  const tier = String(
    clarification.clarification_tier || intentDecision.clarification_tier || contextContract.clarification_tier || ''
  )
    .trim()
    .toLowerCase();
  const needsClarification = Boolean(
    toBool(clarification.needs_clarification) ||
      toBool(intentDecision.needs_clarification) ||
      toBool(contextContract.needs_clarification)
  );
  const isPrompt = mode === 'prompt' || (needsClarification && tier === 'clarify');
  if (!isPrompt) return null;

  const question = String(
    clarification.clarification_question || data.answer || intentDecision.clarification_question || ''
  ).trim();
  const options =
    _normalizeClarificationOptions(clarification.suggested_answers).length > 0
      ? _normalizeClarificationOptions(clarification.suggested_answers)
      : _buildFallbackClarificationOptions(metadata);
  const missingSlots = Array.isArray(clarification.missing_slots)
    ? clarification.missing_slots.map((slot) => String(slot || '').trim()).filter(Boolean)
    : [];
  const intent = String(intentDecision.intent || intentDecision.primary_intent || '').trim().toLowerCase();

  return {
    question,
    options: options.slice(0, 4),
    missingSlots,
    intent,
  };
}

function _dispatchClarificationOption(optionText) {
  const inputEl = document.getElementById('chatInput');
  const choiceText = String(optionText || '').trim();
  if (!inputEl || !choiceText) return;
  hideClarificationPromptCard();
  inputEl.value = choiceText;
  autoResize(inputEl);
  updateStructuredSelectionBadges();
  logEvent('ui.clarification.option_selected', 'ok', { chars: choiceText.length });

  const attemptSend = (retry = 0) => {
    if (!isProcessing || retry >= 20) {
      if (typeof sendMessage === 'function') sendMessage();
      return;
    }
    window.setTimeout(() => attemptSend(retry + 1), 80);
  };
  attemptSend(0);
}

function _dispatchClarificationSenderLookup(senderText) {
  const inputEl = document.getElementById('chatInput');
  const sender = String(senderText || '').trim();
  if (!inputEl || !sender) return;
  hideClarificationPromptCard();
  inputEl.value = `발신자 ${sender} 기준으로 메일 찾아줘`;
  autoResize(inputEl);
  updateStructuredSelectionBadges();
  logEvent('ui.clarification.sender_selected', 'ok', { chars: sender.length });

  const attemptSend = (retry = 0) => {
    if (!isProcessing || retry >= 20) {
      if (typeof sendMessage === 'function') sendMessage();
      return;
    }
    window.setTimeout(() => attemptSend(retry + 1), 80);
  };
  attemptSend(0);
}

function showClarificationPromptCard(payload = null) {
  const popup = ensureClarificationPopup();
  if (!popup) return;
  const prompt = payload && typeof payload === 'object' ? payload : {};
  const options = _normalizeClarificationOptions(prompt.options);
  if (!options.length) {
    hideClarificationPromptCard();
    return;
  }
  const question = String(prompt.question || '').trim();
  const missingSlots = Array.isArray(prompt.missingSlots) ? prompt.missingSlots : [];
  const intent = String(prompt.intent || '').trim().toLowerCase();
  const missingSlotLabel = missingSlots
    .map((slot) => CLARIFICATION_SLOT_LABELS[String(slot || '').trim().toLowerCase()] || String(slot || '').trim())
    .filter(Boolean)
    .slice(0, 3)
    .join(', ');
  const needsSenderInlineInput =
    intent === 'mail_search' && missingSlots.map((slot) => String(slot || '').trim().toLowerCase()).includes('query_keyword');

  const optionsHtml = options
    .map(
      (text, idx) => `
        <button type="button" class="clarification-popup-option" data-option="${escapeAttr(text)}">
          <span class="clarification-popup-option-index">${idx + 1}.</span>
          <span class="clarification-popup-option-text">${escapeHtml(text)}</span>
        </button>
      `
    )
    .join('');

  popup.innerHTML = `
    <div class="clarification-popup-head">
      ${ICONS.sparkles}
      <span>진행하기 위해 추가 질문이 필요합니다</span>
    </div>
    ${question ? `<div class="clarification-popup-question">${escapeHtml(question)}</div>` : ''}
    ${missingSlotLabel ? `<div class="clarification-popup-slots">확인 항목: ${escapeHtml(missingSlotLabel)}</div>` : ''}
    ${
      needsSenderInlineInput
        ? `
      <div class="clarification-popup-inline-form">
        <input
          type="text"
          class="clarification-popup-inline-input"
          id="clarificationSenderInput"
          placeholder="발신자 이름 입력 (예: 박재영)"
          autocomplete="off"
        />
        <button type="button" class="clarification-popup-inline-submit" id="clarificationSenderSubmit">
          발신자 기준 검색
        </button>
      </div>
    `
        : ''
    }
    <div class="clarification-popup-options">${optionsHtml}</div>
  `;
  popup.classList.remove('hidden');

  popup.querySelectorAll('.clarification-popup-option').forEach((buttonEl) => {
    buttonEl.addEventListener('click', () => {
      const optionText = String(buttonEl.getAttribute('data-option') || '').trim();
      _dispatchClarificationOption(optionText);
    });
  });

  if (needsSenderInlineInput) {
    const senderInput = popup.querySelector('#clarificationSenderInput');
    const senderSubmit = popup.querySelector('#clarificationSenderSubmit');
    const submit = () => {
      const sender = String(senderInput?.value || '').trim();
      if (!sender) return;
      _dispatchClarificationSenderLookup(sender);
    };
    if (senderSubmit) senderSubmit.addEventListener('click', submit);
    if (senderInput) {
      senderInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          submit();
        }
      });
    }
  }
}

function syncClarificationPromptFromResponse(responseData = null) {
  const payload = _extractClarificationPromptPayload(responseData);
  if (!payload) {
    hideClarificationPromptCard();
    return null;
  }
  showClarificationPromptCard(payload);
  return payload;
}

function loadMarketRegistry() {
  try {
    const raw = localStorage.getItem(MARKET_STORAGE_KEY);
    if (!raw) {
      marketInstalledSkillIds = new Set(['code_analysis']);
      return;
    }
    const parsed = JSON.parse(raw);
    const apps = Array.isArray(parsed?.apps) ? parsed.apps.map((id) => String(id || '').trim()).filter(Boolean) : [];
    const skills = Array.isArray(parsed?.skills) ? parsed.skills.map((id) => String(id || '').trim()).filter(Boolean) : [];
    const agents = Array.isArray(parsed?.agents) ? parsed.agents.map((id) => String(id || '').trim()).filter(Boolean) : [];
    marketInstalledAppIds = new Set(apps);
    marketInstalledSkillIds = new Set(skills);
    marketInstalledAgentIds = new Set(agents);
  } catch (error) {
    logError('ui.market.restore_failed', error);
  }
}

function persistMarketRegistry() {
  try {
    localStorage.setItem(
      MARKET_STORAGE_KEY,
      JSON.stringify({
        apps: Array.from(marketInstalledAppIds),
        skills: Array.from(marketInstalledSkillIds),
        agents: Array.from(marketInstalledAgentIds),
      })
    );
  } catch (error) {
    logError('ui.market.persist_failed', error);
  }
}

function getRegisteredAppShortcuts() {
  const installed = MARKET_APP_CATALOG.filter((item) => marketInstalledAppIds.has(item.id));
  return installed.map((item) => ({
    scope: 'systems',
    token: item.token,
    label: item.label,
    aliases: [item.label, item.token.replace(/^@+/, '')],
    hint: `${item.hint} · 등록 앱`,
    domain: String(item.domain || '').trim().toLowerCase(),
  }));
}

function getRegisteredSkillShortcuts() {
  return MARKET_SKILL_CATALOG.filter((item) => marketInstalledSkillIds.has(item.id)).map((item) => ({
    token: item.token,
    label: item.label,
    hint: `${item.hint} · 등록 스킬`,
  }));
}

function getRegisteredAgentShortcuts() {
  return MARKET_AGENT_CATALOG.filter((item) => marketInstalledAgentIds.has(item.id)).map((item) => ({
    scope: 'systems',
    token: item.token,
    label: item.label,
    aliases: [item.label, item.token.replace(/^@+/, '')],
    hint: `${item.hint} · 등록 에이전트`,
    domain: 'agent',
  }));
}

function getMergedScopeShortcutPool() {
  return [...getRegisteredAppShortcuts(), ...getRegisteredAgentShortcuts()];
}

function ensureMarketToast() {
  if (marketToastEl && marketToastEl.isConnected) return marketToastEl;
  const inputWrapper = document.querySelector('.input-wrapper');
  if (!inputWrapper) return null;
  const popup = document.createElement('div');
  popup.id = 'marketToast';
  popup.className = 'market-toast hidden';
  inputWrapper.appendChild(popup);
  marketToastEl = popup;
  return marketToastEl;
}

function hideMarketToast() {
  const popup = ensureMarketToast();
  if (!popup) return;
  popup.classList.add('hidden');
  popup.innerHTML = '';
  marketToastMode = 'menu';
}

function renderAgentDesigner(agentId) {
  const popup = ensureMarketToast();
  if (!popup) return;
  const item = MARKET_AGENT_CATALOG.find((candidate) => String(candidate?.id || '').trim() === String(agentId || '').trim());
  if (!item) {
    renderMarketCatalog('agent');
    return;
  }
  const defaultTitle = `${item.label} 자율형 에이전트`;
  const defaultActions = [
    '요청 데이터 수집 및 정합성 검사',
    '핵심 작업 단계별 실행',
    '실행 결과 요약 및 후속 액션 생성',
  ].join('\n');
  popup.innerHTML = `
    <div class="market-toast-head">
      <button type="button" class="market-toast-back" id="agentDesignerBack">뒤로</button>
      <span class="market-toast-title">에이전트 설계</span>
      <span class="market-toast-meta">${escapeHtml(item.token)}</span>
    </div>
    <div class="market-agent-designer">
      <div class="market-agent-field">
        <label class="market-agent-label" for="agentDesignerTitle">제목</label>
        <input id="agentDesignerTitle" class="market-agent-input" type="text" value="${escapeAttr(defaultTitle)}" />
      </div>
      <div class="market-agent-field">
        <label class="market-agent-label" for="agentDesignerActions">원하는 액션</label>
        <textarea id="agentDesignerActions" class="market-agent-textarea" rows="4" placeholder="한 줄에 하나씩 입력">${escapeHtml(defaultActions)}</textarea>
      </div>
      <div class="market-agent-field market-agent-field-inline">
        <div>
          <label class="market-agent-label" for="agentDesignerTrigger">실행 방식</label>
          <select id="agentDesignerTrigger" class="market-agent-select">
            <option value="manual">수동 실행</option>
            <option value="batch">배치 실행</option>
            <option value="daily">매일 실행</option>
          </select>
        </div>
        <div>
          <label class="market-agent-label" for="agentDesignerTarget">대상 범위</label>
          <input id="agentDesignerTarget" class="market-agent-input" type="text" value="전체 사서함/업무 데이터" />
        </div>
      </div>
      <div class="market-agent-runner">
        <div class="market-agent-runner-head">
          <span>실행 미리보기</span>
          <span id="agentDesignerRunState" class="market-agent-runner-state">대기</span>
        </div>
        <div id="agentDesignerLogs" class="market-agent-runner-logs"></div>
      </div>
      <div class="market-agent-actions">
        <button type="button" class="market-toast-item-btn" id="agentDesignerRunBtn">실행 미리보기</button>
        <button type="button" class="market-toast-item-btn is-installed" id="agentDesignerSaveBtn">에이전트 등록</button>
      </div>
    </div>
  `;
  popup.classList.remove('hidden');

  const backBtn = popup.querySelector('#agentDesignerBack');
  const runBtn = popup.querySelector('#agentDesignerRunBtn');
  const saveBtn = popup.querySelector('#agentDesignerSaveBtn');
  const titleInput = popup.querySelector('#agentDesignerTitle');
  const actionsInput = popup.querySelector('#agentDesignerActions');
  const triggerInput = popup.querySelector('#agentDesignerTrigger');
  const targetInput = popup.querySelector('#agentDesignerTarget');
  const runStateEl = popup.querySelector('#agentDesignerRunState');
  const logsEl = popup.querySelector('#agentDesignerLogs');

  backBtn?.addEventListener('click', () => renderMarketCatalog('agent'));

  runBtn?.addEventListener('click', () => {
    const title = String(titleInput?.value || '').trim();
    const actionLines = String(actionsInput?.value || '')
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .slice(0, 8);
    const triggerLabel =
      triggerInput?.value === 'batch'
        ? '배치 실행'
        : triggerInput?.value === 'daily'
          ? '매일 실행'
          : '수동 실행';
    const target = String(targetInput?.value || '').trim() || '기본 대상';
    if (!logsEl || !runStateEl) return;
    if (!title || !actionLines.length) {
      runStateEl.textContent = '입력 필요';
      logsEl.innerHTML = `<div class="market-agent-log-item is-error">제목과 원하는 액션을 입력해 주세요.</div>`;
      return;
    }
    const steps = [
      `에이전트 "${title}" 설계를 로드합니다.`,
      `실행 방식: ${triggerLabel} / 대상: ${target}`,
      ...actionLines.map((line, index) => `액션 ${index + 1}: ${line}`),
      '결과 리포트를 생성하고 후속 액션을 정리합니다.',
    ];
    runBtn.disabled = true;
    runStateEl.textContent = '실행 중';
    logsEl.innerHTML = '';
    const tick = (index = 0) => {
      if (!logsEl || !runStateEl) return;
      if (index >= steps.length) {
        runStateEl.textContent = '완료';
        runBtn.disabled = false;
        return;
      }
      const row = document.createElement('div');
      row.className = 'market-agent-log-item';
      row.textContent = steps[index];
      logsEl.appendChild(row);
      logsEl.scrollTop = logsEl.scrollHeight;
      window.setTimeout(() => tick(index + 1), 380);
    };
    tick(0);
  });

  saveBtn?.addEventListener('click', () => {
    marketInstalledAgentIds.add(item.id);
    persistMarketRegistry();
    refreshStructuredShortcutUi();
    renderMarketCatalog('agent');
  });
}

function renderMarketCatalog(mode) {
  const popup = ensureMarketToast();
  if (!popup) return;
  const currentMode = mode === 'skill' || mode === 'agent' ? mode : 'app';
  const isApp = currentMode === 'app';
  const isSkill = currentMode === 'skill';
  const catalog = isApp ? MARKET_APP_CATALOG : isSkill ? MARKET_SKILL_CATALOG : MARKET_AGENT_CATALOG;
  const installedSet = isApp ? marketInstalledAppIds : isSkill ? marketInstalledSkillIds : marketInstalledAgentIds;
  const progressKeyFor = (itemId) => `${currentMode}:${String(itemId || '').trim()}`;
  const resolveProgress = (itemId) => marketRegistrationProgress.get(progressKeyFor(itemId)) || null;
  const clearRegistrationTimer = (itemId) => {
    const key = progressKeyFor(itemId);
    const timer = marketRegistrationTimers.get(key);
    if (timer) {
      window.clearTimeout(timer);
      marketRegistrationTimers.delete(key);
    }
  };
  const startRegistrationProgress = (itemId) => {
    const key = progressKeyFor(itemId);
    clearRegistrationTimer(itemId);
    const steps = isApp
      ? [
          '커넥터 보안 점검 중...',
          '사내 시스템 스키마 동기화 중...',
          '에이전트 툴 체인 연결 중...',
          'MCP 레지스트리 반영 중...',
          '앱 등록 완료',
        ]
      : isSkill
        ? [
          '스킬 프롬프트 패키징 중...',
          '실행 가드레일 검증 중...',
          '에이전트 라우팅 슬롯 반영 중...',
          'MCP 스킬 인덱스 갱신 중...',
          '스킬 등록 완료',
        ]
        : [
          '에이전트 프로필 동기화 중...',
          '도구 권한/가드레일 점검 중...',
          '워크플로우 실행 그래프 연결 중...',
          'MCP 에이전트 레지스트리 갱신 중...',
          '에이전트 등록 완료',
        ];
    const delaysMs = [900, 900, 900, 900, 700];
    const tick = (index = 0) => {
      const done = index >= steps.length - 1;
      marketRegistrationProgress.set(key, {
        text: steps[index],
        done,
      });
      renderMarketCatalog(currentMode);
      if (done) {
        installedSet.add(itemId);
        persistMarketRegistry();
        refreshStructuredShortcutUi();
        const cleanupTimer = window.setTimeout(() => {
          marketRegistrationProgress.delete(key);
          marketRegistrationTimers.delete(key);
          renderMarketCatalog(currentMode);
        }, 900);
        marketRegistrationTimers.set(key, cleanupTimer);
        return;
      }
      const nextTimer = window.setTimeout(() => tick(index + 1), delaysMs[index] || 800);
      marketRegistrationTimers.set(key, nextTimer);
    };
    tick(0);
  };
  const resolveMarketIconSvg = (itemId, itemMode) => {
    if (itemMode === 'app') {
      if (itemId === 'promise') return ICONS.notebook;
      if (itemId === 'procurement') return ICONS.shoppingCart;
      if (itemId === 'hr_apply') return ICONS.badgeCheck;
      if (itemId === 'finance') return ICONS.wallet;
      return ICONS.sparkles;
    }
    if (itemMode === 'agent') {
      if (itemId === 'meeting_copilot') return ICONS.users;
      if (itemId === 'mail_guard') return ICONS.mail;
      if (itemId === 'report_coach') return ICONS.fileText;
      if (itemId === 'ops_automator') return ICONS.refreshCw;
      return ICONS.sparkles;
    }
    if (itemId === 'report_writer') return ICONS.fileText;
    if (itemId === 'code_analysis') return ICONS.code;
    if (itemId === 'trend_analysis') return ICONS.search;
    if (itemId === 'weekly_report') return ICONS.calendar;
    if (itemId === 'proposal_review') return ICONS.megaphone;
    return ICONS.sparkles;
  };
  const rows = catalog
    .map((item) => {
      const installed = installedSet.has(item.id);
      const progress = resolveProgress(item.id);
      const inProgress = Boolean(progress && !progress.done);
      const statusText = progress ? String(progress.text || '').trim() : '';
      return `
        <div class="market-toast-item">
          <div class="market-toast-item-main">
            <span class="market-toast-item-icon">${resolveMarketIconSvg(item.id, currentMode)}</span>
            <div class="market-toast-item-text">
              <div class="market-toast-item-token">${escapeHtml(item.token)} · ${escapeHtml(item.label)}</div>
              <div class="market-toast-item-desc">${escapeHtml(item.hint)}</div>
              ${statusText ? `<div class="market-toast-item-status ${progress.done ? 'is-done' : 'is-running'}">${escapeHtml(statusText)}</div>` : ''}
            </div>
          </div>
          <button type="button" class="market-toast-item-btn${installed ? ' is-installed' : ''}" data-market-id="${escapeAttr(item.id)}" ${inProgress ? 'disabled' : ''}>
            ${inProgress ? '등록중' : installed ? '해제' : '등록'}
          </button>
        </div>
      `;
    })
    .join('');
  popup.innerHTML = `
    <div class="market-toast-head">
      <button type="button" class="market-toast-back" id="marketToastBack">뒤로</button>
      <span class="market-toast-title">${isApp ? '앱 마켓 등록' : isSkill ? '스킬 마켓 등록' : '에이전트 마켓 등록'}</span>
      <span class="market-toast-meta">등록 ${installedSet.size}개</span>
    </div>
    <div class="market-toast-list">${rows}</div>
  `;
  popup.classList.remove('hidden');
  popup.querySelector('#marketToastBack')?.addEventListener('click', () => {
    renderMarketToastMenu();
  });
  popup.querySelectorAll('.market-toast-item-btn[data-market-id]').forEach((buttonEl) => {
    buttonEl.addEventListener('click', () => {
      const id = String(buttonEl.getAttribute('data-market-id') || '').trim();
      if (!id) return;
      const progress = resolveProgress(id);
      if (progress && !progress.done) return;
      if (installedSet.has(id)) {
        clearRegistrationTimer(id);
        marketRegistrationProgress.delete(progressKeyFor(id));
        installedSet.delete(id);
        persistMarketRegistry();
        renderMarketCatalog(currentMode);
      } else {
        if (currentMode === 'agent') {
          renderAgentDesigner(id);
          return;
        }
        startRegistrationProgress(id);
      }
      refreshStructuredShortcutUi();
    });
  });
}

function renderMarketToastMenu() {
  const popup = ensureMarketToast();
  if (!popup) return;
  marketToastMode = 'menu';
  popup.innerHTML = `
    <div class="market-toast-head">
      <span class="market-toast-title">마켓 등록</span>
      <span class="market-toast-meta">앱 ${marketInstalledAppIds.size} · 스킬 ${marketInstalledSkillIds.size} · 에이전트 ${marketInstalledAgentIds.size}</span>
    </div>
    <div class="market-toast-actions">
      <button type="button" class="market-toast-action-btn" id="marketAppBtn">
        <span class="market-toast-action-title">
          <span class="market-toast-action-title-row">
            <span class="market-toast-action-icon">${ICONS.shoppingCart}</span>
            <span>앱 등록</span>
          </span>
        </span>
        <span class="market-toast-action-desc">@칩에 사내 시스템 추가</span>
      </button>
      <button type="button" class="market-toast-action-btn" id="marketSkillBtn">
        <span class="market-toast-action-title">
          <span class="market-toast-action-title-row">
            <span class="market-toast-action-icon">${ICONS.sparkles}</span>
            <span>스킬 등록</span>
          </span>
        </span>
        <span class="market-toast-action-desc">/명령 스킬 바로 실행</span>
      </button>
      <button type="button" class="market-toast-action-btn" id="marketAgentBtn">
        <span class="market-toast-action-title">
          <span class="market-toast-action-title-row">
            <span class="market-toast-action-icon">${ICONS.users}</span>
            <span>에이전트 등록</span>
          </span>
        </span>
        <span class="market-toast-action-desc">설계 화면에서 자율형 에이전트 생성</span>
      </button>
    </div>
  `;
  popup.classList.remove('hidden');
  popup.querySelector('#marketAppBtn')?.addEventListener('click', () => {
    marketToastMode = 'app';
    renderMarketCatalog('app');
  });
  popup.querySelector('#marketSkillBtn')?.addEventListener('click', () => {
    marketToastMode = 'skill';
    renderMarketCatalog('skill');
  });
  popup.querySelector('#marketAgentBtn')?.addEventListener('click', () => {
    marketToastMode = 'agent';
    renderMarketCatalog('agent');
  });
}

function toggleMarketToast() {
  const popup = ensureMarketToast();
  if (!popup) return;
  if (!popup.classList.contains('hidden')) {
    hideMarketToast();
    return;
  }
  hideScopeShortcutMenu();
  hideVerbShortcutMenu();
  renderMarketToastMenu();
}

function updateStructuredSelectionBadges() {
  const row = ensureStructuredSelectionRow();
  const inputEl = document.getElementById('chatInput');
  if (!row || !inputEl) return;
  const value = String(inputEl.value || '').trim();
  if (!value) {
    row.classList.add('hidden');
    row.innerHTML = '';
    return;
  }
  const chipIds = extractStructuredChipIdsFromText(value);
  const verbIds = extractStructuredVerbIdsFromText(value);
  if (!chipIds.length && !verbIds.length) {
    row.classList.add('hidden');
    row.innerHTML = '';
    return;
  }
  const nounBadges = chipIds
    .map((chipId) => STRUCTURED_CHIP_TOKEN_BY_ID.get(chipId))
    .filter(Boolean)
    .map((token) => `<span class="structured-badge structured-badge-noun">${escapeHtml(token)}</span>`)
    .join('');
  const verbBadges = verbIds
    .map((verbId) => STRUCTURED_VERB_TOKEN_BY_ID.get(verbId))
    .filter(Boolean)
    .map((token) => `<span class="structured-badge structured-badge-verb">${escapeHtml(token)}</span>`)
    .join('');
  row.innerHTML = `${nounBadges}${verbBadges}`;
  row.classList.remove('hidden');
}

function hideScopeShortcutMenu() {
  const menu = ensureScopeShortcutMenu();
  if (!menu) return;
  menu.classList.add('hidden');
  menu.innerHTML = '';
  scopeShortcutItems = [];
  scopeShortcutActiveIndex = -1;
}

function ensureVerbShortcutMenu() {
  if (verbShortcutMenuEl && verbShortcutMenuEl.isConnected) return verbShortcutMenuEl;
  const wrapper = document.querySelector('.input-wrapper');
  if (!wrapper) return null;
  const menu = document.createElement('div');
  menu.className = 'scope-shortcut-menu hidden';
  menu.id = 'verbShortcutMenu';
  menu.setAttribute('role', 'listbox');
  menu.setAttribute('aria-label', '동사 단축어');
  wrapper.appendChild(menu);
  verbShortcutMenuEl = menu;
  return verbShortcutMenuEl;
}

function hideVerbShortcutMenu() {
  const menu = ensureVerbShortcutMenu();
  if (!menu) return;
  menu.classList.add('hidden');
  menu.innerHTML = '';
  verbShortcutItems = [];
  verbShortcutActiveIndex = -1;
}

function renderScopeShortcutMenu() {
  const menu = ensureScopeShortcutMenu();
  if (!menu || !scopeShortcutItems.length) {
    hideScopeShortcutMenu();
    return;
  }
  menu.innerHTML = scopeShortcutItems
    .map((item, idx) => {
      const activeClass = idx === scopeShortcutActiveIndex ? ' active' : '';
      return (
        `<button type="button" class="scope-shortcut-item${activeClass}" data-idx="${idx}" role="option" ` +
        `aria-selected="${idx === scopeShortcutActiveIndex ? 'true' : 'false'}">` +
        `<span class="scope-shortcut-token">${escapeHtml(item.token)}</span>` +
        `<span class="scope-shortcut-meta">${escapeHtml(item.label)} · ${escapeHtml(item.hint)}</span>` +
        `</button>`
      );
    })
    .join('');
  menu.classList.remove('hidden');
}

function extractScopeShortcutQuery(inputEl) {
  if (!inputEl) return null;
  const value = String(inputEl.value || '');
  const caretStart = Number.isFinite(inputEl.selectionStart) ? inputEl.selectionStart : value.length;
  const caretEnd = Number.isFinite(inputEl.selectionEnd) ? inputEl.selectionEnd : value.length;
  if (caretStart !== caretEnd) return null;
  if (caretEnd !== value.length) return null;
  const beforeCaret = value.slice(0, caretEnd);
  const matched = /@([^\s]*)\s*$/.exec(beforeCaret);
  if (!matched) return null;
  const atIndex = Number(matched.index ?? -1);
  if (atIndex < 0) return null;
  const leading = beforeCaret.slice(0, atIndex);
  if (leading && !/\s$/.test(leading)) return null;
  return {
    leading: leading || '',
    query: matched[1] || '',
  };
}

function updateScopeShortcutMenu(forcedQuery = null) {
  const inputEl = document.getElementById('chatInput');
  const state = extractScopeShortcutQuery(inputEl);
  if (!state) {
    hideScopeShortcutMenu();
    return;
  }
  const querySource = forcedQuery === null ? state.query : String(forcedQuery || '');
  const normalizedQuery = normalizeCompactToken(querySource);
  const selectedChips = extractStructuredChipIdsFromText(state.leading);
  const allowedNextChips = resolveAllowedNextStructuredChipIds(selectedChips);
  const allowUnstructuredRegisteredApps = selectedChips.length === 0;
  if (selectedChips.length >= STRUCTURED_INPUT_MAX_CHIPS || !allowedNextChips.size) {
    hideScopeShortcutMenu();
    return;
  }
  const shortcutPool = getMergedScopeShortcutPool();
  const filtered = shortcutPool.filter((item) => {
    const chipId = resolveStructuredChipId(item.token);
    if (!chipId) {
      if (!allowUnstructuredRegisteredApps) return false;
    } else if (!allowedNextChips.has(chipId)) {
      return false;
    }
    if (!normalizedQuery) return true;
    const rawCandidates = [item.token, item.label, ...(Array.isArray(item.aliases) ? item.aliases : [])];
    return rawCandidates.some((candidate) => {
      const normalized = normalizeCompactToken(candidate);
      const normalizedNoAt = normalized.replace(/^@+/, '');
      return normalized.startsWith(normalizedQuery) || normalizedNoAt.startsWith(normalizedQuery);
    });
  });
  scopeShortcutItems = filtered
    .slice()
    .sort((a, b) => {
      const aKey = String(a.token || '').replace(/^@/, '');
      const bKey = String(b.token || '').replace(/^@/, '');
      return aKey.localeCompare(bKey, 'ko-KR');
    });
  if (!scopeShortcutItems.length) {
    hideScopeShortcutMenu();
    return;
  }
  hideMarketToast();
  hideVerbShortcutMenu();
  scopeShortcutActiveIndex = 0;
  renderScopeShortcutMenu();
}

function moveScopeShortcutFocus(direction) {
  if (!scopeShortcutItems.length) return;
  const total = scopeShortcutItems.length;
  if (scopeShortcutActiveIndex < 0) {
    scopeShortcutActiveIndex = 0;
  } else {
    scopeShortcutActiveIndex = (scopeShortcutActiveIndex + direction + total) % total;
  }
  renderScopeShortcutMenu();
}

function applyScopeShortcut(item) {
  if (!item) return false;
  const inputEl = document.getElementById('chatInput');
  const state = extractScopeShortcutQuery(inputEl);
  if (!inputEl || !state) {
    hideScopeShortcutMenu();
    return false;
  }
  inputEl.value = `${state.leading}${item.token} `;
  autoResize(inputEl);
  updateStructuredSelectionBadges();
  const existingChips = extractStructuredChipIdsFromText(state.leading);
  const selectedChip = resolveStructuredChipId(item.token);
  const mergedChips = Array.from(new Set([...existingChips, selectedChip].filter(Boolean)));
  const mergedScope = mergedChips.length ? resolveStructuredScopeFromChips(mergedChips) : item.scope;
  const mergedDomain = mergedChips.length
    ? resolveStructuredDomainFromChips(mergedChips)
    : String(item.domain || parseDomainShortcutFromPrefix(String(item.token || '').trim()).domain || '')
        .trim()
        .toLowerCase();
  const labelOverride = resolveSystemScopeLabelOverride(mergedDomain) || String(item.label || '').trim();
  switchScope(mergedScope, { labelOverride });
  hideScopeShortcutMenu();
  inputEl.focus();
  const end = inputEl.value.length;
  inputEl.setSelectionRange(end, end);
  restoredInputDraft = inputEl.value || '';
  persistTaskpaneState();
  return true;
}

function confirmActiveScopeShortcut() {
  if (!scopeShortcutItems.length) {
    return false;
  }
  const idx =
    scopeShortcutActiveIndex >= 0 && scopeShortcutActiveIndex < scopeShortcutItems.length
      ? scopeShortcutActiveIndex
      : 0;
  return applyScopeShortcut(scopeShortcutItems[idx]);
}

function renderVerbShortcutMenu() {
  const menu = ensureVerbShortcutMenu();
  if (!menu || !verbShortcutItems.length) {
    hideVerbShortcutMenu();
    return;
  }
  menu.innerHTML = verbShortcutItems
    .map((item, idx) => {
      const activeClass = idx === verbShortcutActiveIndex ? ' active' : '';
      return (
        `<button type="button" class="scope-shortcut-item${activeClass}" data-idx="${idx}" role="option" ` +
        `aria-selected="${idx === verbShortcutActiveIndex ? 'true' : 'false'}">` +
        `<span class="scope-shortcut-token">${escapeHtml(item.token)}</span>` +
        `<span class="scope-shortcut-meta">${escapeHtml(item.hint)}</span>` +
        `</button>`
      );
    })
    .join('');
  menu.classList.remove('hidden');
}

function updateVerbShortcutMenu() {
  const inputEl = document.getElementById('chatInput');
  const state = extractVerbShortcutQuery(inputEl);
  if (!state) {
    hideVerbShortcutMenu();
    return;
  }
  verbShortcutItems = buildVerbShortcutItems(state.chipIds, state.query);
  if (!verbShortcutItems.length) {
    hideVerbShortcutMenu();
    return;
  }
  hideMarketToast();
  hideScopeShortcutMenu();
  verbShortcutActiveIndex = 0;
  renderVerbShortcutMenu();
}

function moveVerbShortcutFocus(direction) {
  if (!verbShortcutItems.length) return;
  const total = verbShortcutItems.length;
  if (verbShortcutActiveIndex < 0) {
    verbShortcutActiveIndex = 0;
  } else {
    verbShortcutActiveIndex = (verbShortcutActiveIndex + direction + total) % total;
  }
  renderVerbShortcutMenu();
}

function applyVerbShortcut(item) {
  if (!item) return false;
  const inputEl = document.getElementById('chatInput');
  const state = extractVerbShortcutQuery(inputEl);
  if (!inputEl || !state) {
    hideVerbShortcutMenu();
    return false;
  }
  const token = String(item.token || '').trim();
  if (!token) {
    hideVerbShortcutMenu();
    return false;
  }
  inputEl.value = `${state.leading}${token} `;
  autoResize(inputEl);
  updateStructuredSelectionBadges();
  hideVerbShortcutMenu();
  inputEl.focus();
  const end = inputEl.value.length;
  inputEl.setSelectionRange(end, end);
  restoredInputDraft = inputEl.value || '';
  persistTaskpaneState();
  return true;
}

function confirmActiveVerbShortcut() {
  if (!verbShortcutItems.length) {
    return false;
  }
  const idx =
    verbShortcutActiveIndex >= 0 && verbShortcutActiveIndex < verbShortcutItems.length
      ? verbShortcutActiveIndex
      : 0;
  return applyVerbShortcut(verbShortcutItems[idx]);
}

function refreshStructuredShortcutUi(forcedScopeQuery = null) {
  updateStructuredSelectionBadges();
  if (forcedScopeQuery === null) updateScopeShortcutMenu();
  else updateScopeShortcutMenu(forcedScopeQuery);
  updateVerbShortcutMenu();
}

function handleScopeBeforeInput(inputEl, event) {
  const data = String(event?.data || '').trim();
  if (!data) {
    refreshStructuredShortcutUi();
    return;
  }
  const state = extractScopeShortcutQuery(inputEl);
  if (!state) {
    refreshStructuredShortcutUi();
    return;
  }
  updateScopeShortcutMenu(`${state.query || ''}${data}`);
  updateVerbShortcutMenu();
}

function handleScopeCompositionUpdate(inputEl, event) {
  const data = String(event?.data || '').trim();
  if (!data) {
    refreshStructuredShortcutUi();
    return;
  }
  const state = extractScopeShortcutQuery(inputEl);
  const base = String(state?.query || '');
  updateScopeShortcutMenu(base ? `${base}${data}` : data);
  updateVerbShortcutMenu();
}

function isShortcutNavigationKey(event) {
  const key = String(event?.key || '');
  return ['ArrowDown', 'ArrowUp', 'Enter', 'Tab', 'Escape'].includes(key);
}

function bindShortcutMenuItemMouseDown(menu, getItems, applyFn) {
  if (!menu) return;
  menu.addEventListener('mousedown', (event) => {
    event.preventDefault();
    const items = typeof getItems === 'function' ? getItems() : [];
    const target =
      event.target instanceof Element ? event.target.closest('.scope-shortcut-item[data-idx]') : null;
    if (!target) return;
    const idx = Number(target.getAttribute('data-idx'));
    if (!Number.isFinite(idx) || idx < 0 || idx >= items.length) return;
    applyFn(items[idx]);
  });
}

function bindScopeShortcutInputEvents(inputEl) {
  inputEl.addEventListener('input', () => {
    refreshStructuredShortcutUi();
  });
  inputEl.addEventListener('beforeinput', (event) => {
    handleScopeBeforeInput(inputEl, event);
  });
  inputEl.addEventListener('compositionstart', () => {
    chatInputImeComposing = true;
  });
  // Korean IME composition can delay committed text until space/next key.
  // Refresh suggestions during and right after composition so "@근" also surfaces shortcuts.
  inputEl.addEventListener('compositionupdate', (event) => {
    handleScopeCompositionUpdate(inputEl, event);
  });
  inputEl.addEventListener('compositionend', () => {
    chatInputImeComposing = false;
    refreshStructuredShortcutUi();
  });
  inputEl.addEventListener('keyup', (event) => {
    if (!event || isShortcutNavigationKey(event)) return;
    refreshStructuredShortcutUi();
  });
  inputEl.addEventListener('blur', () => {
    window.setTimeout(() => {
      hideScopeShortcutMenu();
      hideVerbShortcutMenu();
    }, 80);
  });
}

function bindScopeShortcutOutsideClickHandler() {
  document.addEventListener('mousedown', (event) => {
    const menu = ensureScopeShortcutMenu();
    const wrapper = document.querySelector('.input-wrapper');
    if (!menu || !wrapper) return;
    if (wrapper.contains(event.target)) return;
    hideScopeShortcutMenu();
    hideVerbShortcutMenu();
    hideMarketToast();
  });
}

function bindMarketToastHandlers() {
  const plusBtn = document.getElementById('marketPlusBtn');
  if (!plusBtn || plusBtn.dataset.marketBound === '1') return;
  plusBtn.dataset.marketBound = '1';
  plusBtn.addEventListener('click', (event) => {
    event.preventDefault();
    toggleMarketToast();
  });
}

function bindScopeShortcutHandlers() {
  const inputEl = document.getElementById('chatInput');
  if (!inputEl || inputEl.dataset.scopeShortcutBound === '1') return;
  inputEl.dataset.scopeShortcutBound = '1';
  ensureScopeShortcutMenu();
  ensureVerbShortcutMenu();
  ensureMarketToast();
  ensureStructuredSelectionRow();
  bindScopeShortcutInputEvents(inputEl);
  bindScopeShortcutOutsideClickHandler();
  bindMarketToastHandlers();
  bindShortcutMenuItemMouseDown(ensureScopeShortcutMenu(), () => scopeShortcutItems, applyScopeShortcut);
  bindShortcutMenuItemMouseDown(ensureVerbShortcutMenu(), () => verbShortcutItems, applyVerbShortcut);
}

function applyScopeUiState() {
  const normalizedScope = normalizeScope(currentScope);
  currentScope = normalizedScope;
  const chatInput = document.getElementById('chatInput');
  if (chatInput) {
    chatInput.placeholder = '';
  }
}

function normalizePositiveConfigInt(value, fallbackValue, { min = 1, max = Number.MAX_SAFE_INTEGER } = {}) {
  const parsed = Number.parseInt(String(value ?? '').trim(), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) return fallbackValue;
  return Math.max(min, Math.min(parsed, max));
}

async function syncChatRuntimeConfig() {
  try {
    const response = await apiFetch('/search/chat/runtime-config', { method: 'GET' }, 2500);
    if (!response?.ok) {
      logEvent('chat.runtime_config.fetch_skipped', 'warn', {
        status_code: Number(response?.status || 0),
      });
      return;
    }
    const payload = await response.json().catch(() => ({}));
    const nextStickyTtlMs = normalizePositiveConfigInt(
      payload?.sticky_current_mail_ttl_ms,
      STICKY_CURRENT_MAIL_TTL_MS,
      { min: 60 * 1000, max: 60 * 60 * 1000 }
    );
    const nextStickyMaxTurns = normalizePositiveConfigInt(
      payload?.sticky_current_mail_max_turns,
      STICKY_CURRENT_MAIL_MAX_TURNS,
      { min: 1, max: 10 }
    );
    STICKY_CURRENT_MAIL_TTL_MS = nextStickyTtlMs;
    STICKY_CURRENT_MAIL_MAX_TURNS = nextStickyMaxTurns;
    logEvent('chat.runtime_config.synced', 'ok', {
      sticky_ttl_ms: STICKY_CURRENT_MAIL_TTL_MS,
      sticky_max_turns: STICKY_CURRENT_MAIL_MAX_TURNS,
      followup_ttl_sec: normalizePositiveConfigInt(payload?.followup_state_ttl_sec, 0, { min: 0, max: 86400 }),
    });
  } catch (error) {
    logError('chat.runtime_config.sync_failed', error);
  }
}

function clearStickyCurrentMailContext(reason = '') {
  const hasState = Boolean(stickyCurrentMailContext?.emailMessageId);
  const previousThreadId = String(stickyCurrentMailContext?.threadId || '').trim();
  stickyCurrentMailContext = {
    threadId: '',
    emailMessageId: '',
    turnsRemaining: 0,
    expiresAt: 0,
    updatedAt: 0,
    source: '',
  };
  if (!hasState) return;
  logEvent('mail.context.sticky.cleared', 'ok', {
    reason: String(reason || '').trim() || 'manual',
    thread_id: previousThreadId.slice(0, 42),
  });
}

function resolveStickyCurrentMailSnapshot({ threadId = chatThreadId } = {}) {
  const normalizedThreadId = String(threadId || '').trim() || String(chatThreadId || '').trim();
  const state = stickyCurrentMailContext && typeof stickyCurrentMailContext === 'object'
    ? stickyCurrentMailContext
    : null;
  if (!state || !String(state.emailMessageId || '').trim()) return null;
  if (normalizedThreadId && String(state.threadId || '').trim() && String(state.threadId || '').trim() !== normalizedThreadId) {
    return null;
  }
  const now = Date.now();
  const expiresAt = Number(state.expiresAt || 0);
  if (Number.isFinite(expiresAt) && expiresAt > 0 && now >= expiresAt) {
    clearStickyCurrentMailContext('expired');
    return null;
  }
  const turnsRemaining = Number(state.turnsRemaining || 0);
  if (!Number.isFinite(turnsRemaining) || turnsRemaining <= 0) {
    clearStickyCurrentMailContext('turns_exhausted');
    return null;
  }
  return {
    threadId: String(state.threadId || '').trim(),
    emailMessageId: String(state.emailMessageId || '').trim(),
    turnsRemaining,
    expiresAt,
    updatedAt: Number(state.updatedAt || 0),
    source: String(state.source || '').trim(),
  };
}

function setStickyCurrentMailContext({
  emailMessageId = '',
  source = '',
  turns = STICKY_CURRENT_MAIL_MAX_TURNS,
  ttlMs = STICKY_CURRENT_MAIL_TTL_MS,
} = {}) {
  const normalizedEmailMessageId = String(emailMessageId || '').trim();
  if (!normalizedEmailMessageId) return false;

  const boundedTurnsRaw = Number(turns || 0);
  const boundedTurns = Number.isFinite(boundedTurnsRaw) && boundedTurnsRaw > 0
    ? Math.max(1, Math.min(Math.trunc(boundedTurnsRaw), 10))
    : STICKY_CURRENT_MAIL_MAX_TURNS;
  const boundedTtlRaw = Number(ttlMs || 0);
  const boundedTtlMs = Number.isFinite(boundedTtlRaw) && boundedTtlRaw > 0
    ? Math.max(60 * 1000, Math.min(Math.trunc(boundedTtlRaw), 60 * 60 * 1000))
    : STICKY_CURRENT_MAIL_TTL_MS;
  const now = Date.now();
  const normalizedThreadId = String(chatThreadId || '').trim();

  stickyCurrentMailContext = {
    threadId: normalizedThreadId,
    emailMessageId: normalizedEmailMessageId,
    turnsRemaining: boundedTurns,
    expiresAt: now + boundedTtlMs,
    updatedAt: now,
    source: String(source || '').trim().toLowerCase(),
  };

  logEvent('mail.context.sticky.set', 'ok', {
    thread_id: normalizedThreadId.slice(0, 42),
    has_email_id: true,
    turns: boundedTurns,
    ttl_ms: boundedTtlMs,
    source: String(source || '').trim().toLowerCase() || 'runtime',
  });
  return true;
}

function maybeSeedStickyCurrentMailContextFromRuntime(runtimePayload, options = {}) {
  const payload = runtimePayload && typeof runtimePayload === 'object' ? runtimePayload : null;
  if (!payload) return false;
  const shouldClear = toBool(options?.clearWhenDisabled);
  if (shouldClear) {
    clearStickyCurrentMailContext(String(options?.clearReason || 'scope_changed'));
    return false;
  }
  const currentMailOnly = toBool(payload.current_mail_only);
  const emailMessageId = String(payload.email_message_id || '').trim();
  if (!currentMailOnly || !emailMessageId) return false;
  return setStickyCurrentMailContext({
    emailMessageId,
    source: String(options?.source || '').trim().toLowerCase() || 'runtime',
    turns: Number(options?.turns || 0) || STICKY_CURRENT_MAIL_MAX_TURNS,
    ttlMs: Number(options?.ttlMs || 0) || STICKY_CURRENT_MAIL_TTL_MS,
  });
}

function hasStructuredCurrentMailChip(runtimePayload) {
  const payload = runtimePayload && typeof runtimePayload === 'object' ? runtimePayload : null;
  if (!payload) return false;
  const structuredInput = payload.structured_input;
  if (!structuredInput || typeof structuredInput !== 'object') return false;
  const chips = Array.isArray(structuredInput.chips) ? structuredInput.chips : [];
  return chips.some((chip) => String(chip || '').trim().toLowerCase() === 'current_mail');
}

function applyStickyCurrentMailContextToRuntime(runtimePayload, options = {}) {
  const payload = runtimePayload && typeof runtimePayload === 'object' ? runtimePayload : null;
  if (!payload) return false;
  if (toBool(options?.allow) === false) return false;
  // "@현재메일" 명시 요청은 현재 선택 메일 ID를 우선으로 사용해야 한다.
  if (hasStructuredCurrentMailChip(payload)) return false;
  const hasExplicitEmailId = Boolean(String(payload.email_message_id || '').trim());
  const hasExplicitCurrentMailOnly = toBool(payload.current_mail_only);
  if (hasExplicitEmailId || hasExplicitCurrentMailOnly) return false;
  const snapshot = resolveStickyCurrentMailSnapshot({
    threadId: String(options?.threadId || chatThreadId || '').trim(),
  });
  if (!snapshot) return false;

  payload.current_mail_only = true;
  payload.email_message_id = snapshot.emailMessageId;
  payload.scope = 'email';
  payload.__sticky_current_mail_applied = true;

  logEvent('mail.context.sticky.applied', 'ok', {
    thread_id: String(snapshot.threadId || '').slice(0, 42),
    turns_left_before_consume: snapshot.turnsRemaining,
    source: snapshot.source || 'runtime',
  });
  return true;
}

function hasExplicitCurrentMailPhraseInText(text) {
  const raw = String(text || '').trim();
  if (!raw) return false;
  return /(?:@현재메일|현재\s*(?:선택한\s*)?메일|이\s*메일|current\s*mail|selected\s*mail|this\s*(?:mail|email))/i.test(raw);
}

function hasExplicitMailboxSearchPhraseInText(text) {
  const raw = String(text || '').trim();
  if (!raw) return false;
  return /(?:지난|최근)\s*(?:\d+\s*)?(?:일|주|개월|달|년)|지난\s*주|이번\s*주|지난\s*달|이번\s*달|전체\s*(?:메일|이메일|사서함)|사서함\s*전체|(?:메일|이메일)\s*(?:조회|검색|찾(?:아|기))|\bsearch\b|\bfind\b/i.test(raw);
}

function consumeStickyCurrentMailContextTurn(options = {}) {
  const snapshot = resolveStickyCurrentMailSnapshot({
    threadId: String(options?.threadId || chatThreadId || '').trim(),
  });
  if (!snapshot) return false;
  const remaining = Math.max(0, Number(snapshot.turnsRemaining || 0) - 1);
  if (remaining <= 0) {
    clearStickyCurrentMailContext('turn_consumed');
    return true;
  }
  stickyCurrentMailContext = {
    ...stickyCurrentMailContext,
    turnsRemaining: remaining,
    updatedAt: Date.now(),
  };
  logEvent('mail.context.sticky.consume', 'ok', {
    thread_id: String(snapshot.threadId || '').slice(0, 42),
    turns_left: remaining,
    reason: String(options?.reason || '').trim() || 'request_sent',
  });
  return true;
}

function consumeStickyCurrentMailContextFromPayload(runtimePayload, options = {}) {
  const payload = runtimePayload && typeof runtimePayload === 'object' ? runtimePayload : null;
  if (!payload) return false;
  const stickyApplied = toBool(payload.__sticky_current_mail_applied);
  if (!stickyApplied) return false;
  const consumed = consumeStickyCurrentMailContextTurn({
    threadId: String(options?.threadId || chatThreadId || '').trim(),
    reason: String(options?.reason || '').trim() || 'request_sent',
  });
  delete payload.__sticky_current_mail_applied;
  return consumed;
}

function getRuntimeOptionsPayload() {
  const payload = {
    surface: 'outlook_addin',
    scope: normalizeScope(currentScope),
    mode: String(currentMode || '').toLowerCase(),
  };
  const pendingPromiseProjectNumber = String(pendingPromiseContext?.projectNumber || '').trim();
  if (pendingPromiseProjectNumber && String(currentMode || '').toLowerCase() === 'assistant') {
    payload.pending_promise_project_number = pendingPromiseProjectNumber;
  }
  return payload;
}


/* =========================================
   Initialization
   ========================================= */

Office.onReady((info) => {
  if (info.host === Office.HostType.Outlook) {
    logEvent('addin.ready', 'ok', {
      build: TASKPANE_BUILD,
      web_fallback: ENABLE_WEB_OPEN_FALLBACK,
      host: info.host,
    });
    initializeAddIn();
  }
});

bootstrapPrimaryUiBindings();
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => bootstrapPrimaryUiBindings());
} else {
  window.setTimeout(() => bootstrapPrimaryUiBindings(), 0);
}
window.setTimeout(() => bootstrapPrimaryUiBindings(), 300);

function initializeAddIn() {
  logEvent('addin.initialize.start');
  loadMarketRegistry();
  initializeOutlookThemeSync({ logEvent, logError });
  void syncChatRuntimeConfig();
  bindPrimaryTaskpaneUiHandlers();
  bindPrimaryTaskpaneDocumentFallbackHandlers();
  restoreTaskpaneState();
  applyModeUiState();
  applyScopeUiState();
  bindMyHREventBridge();
  loadEmailContext();
  bindOutlookItemChangedHandler();
  restoreInputDraft();
  bindStatePersistenceHandlers();
  bindScopeShortcutHandlers();
  updateScopeShortcutMenu();
  logEvent('addin.initialize.success', 'ok', { mode: currentMode, scope: currentScope });
}

function resolveSendMessageHandler() {
  if (typeof sendMessage === 'function') return sendMessage;
  if (typeof globalThis.sendMessage === 'function') return globalThis.sendMessage;
  if (typeof window.sendMessage === 'function') return window.sendMessage;
  return null;
}

function triggerSendMessageFromUi(source = 'unknown') {
  logEvent('ui.send.trigger', 'ok', {
    source: String(source || '').trim() || 'unknown',
    has_sender_symbol: typeof sendMessage === 'function',
    has_sender_global: typeof globalThis.sendMessage === 'function',
    has_sender_window: typeof window.sendMessage === 'function',
  });
  const sender = resolveSendMessageHandler();
  if (!sender) {
    logError('ui.send.handler_missing', new Error('sendMessage handler missing'), {
      source: String(source || '').trim() || 'unknown',
      typeof_sendMessage: typeof sendMessage,
      typeof_global_sendMessage: typeof globalThis.sendMessage,
      typeof_window_sendMessage: typeof window.sendMessage,
    });
    return;
  }
  Promise.resolve(sender()).catch((error) => {
    logError('ui.send.invoke_failed', error, {
      source: String(source || '').trim() || 'unknown',
    });
  });
}

function bindPrimaryTaskpaneUiHandlers() {
  const inputEl = document.getElementById('chatInput');
  if (inputEl) {
    if (inputEl.dataset.primaryBound !== '1') {
      inputEl.dataset.primaryBound = '1';
      inputEl.addEventListener('keydown', (event) => handleKeyDown(event));
      inputEl.addEventListener('input', () => autoResize(inputEl));
      logEvent('ui.bind.input_listener', 'ok');
    }
  }

  const sendBtn = document.getElementById('sendBtn');
  if (sendBtn) {
    if (sendBtn.dataset.primaryBound !== '1') {
      sendBtn.dataset.primaryBound = '1';
      sendBtn.addEventListener('click', () => {
        logEvent('ui.click.send_listener', 'ok', {
          disabled: Boolean(sendBtn.disabled),
        });
        triggerSendMessageFromUi('button_listener');
      });
      logEvent('ui.bind.send_listener', 'ok');
    }
  }

  const newSessionBtn = document.getElementById('newSessionBtn');
  if (newSessionBtn && newSessionBtn.dataset.primaryBound !== '1') {
    newSessionBtn.dataset.primaryBound = '1';
    newSessionBtn.addEventListener('click', () => {
      startNewSession();
    });
  }

  globalThis.handleKeyDown = handleKeyDown;
  globalThis.autoResize = autoResize;
  globalThis.startNewSession = startNewSession;
  logEvent('ui.bind.primary.complete', 'ok', {
    has_input: Boolean(inputEl),
    has_send_btn: Boolean(sendBtn),
    has_new_session_btn: Boolean(newSessionBtn),
  });
}

function bindPrimaryTaskpaneDocumentFallbackHandlers() {
  if (document?.body?.dataset?.primaryFallbackBound === '1') return;
  if (document?.body?.dataset) {
    document.body.dataset.primaryFallbackBound = '1';
  }

  document.addEventListener(
    'keydown',
    (event) => {
      const target = event?.target;
      const isChatInput = target && typeof target.id === 'string' && target.id === 'chatInput';
      if (!isChatInput) return;
      // 캡처 단계에서는 Enter만 보정하고, 화살표 이동은 입력창 핸들러에서 1회만 처리한다.
      if (event.key === 'Enter' && !event.shiftKey) {
        if (confirmActiveScopeShortcut() || confirmActiveVerbShortcut()) {
          event.preventDefault();
          event.stopPropagation();
          return;
        }
      }
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        logEvent('ui.keydown.document_capture_enter', 'ok');
        triggerSendMessageFromUi('document_keydown_capture');
      }
    },
    true
  );

  document.addEventListener(
    'click',
    (event) => {
      const target =
        event?.target instanceof Element ? event.target.closest('#sendBtn, #newSessionBtn') : null;
      if (!target) return;
      const id = String(target.id || '');
      if (id === 'sendBtn') {
        event.preventDefault();
        logEvent('ui.click.document_capture_send', 'ok');
        triggerSendMessageFromUi('document_click_capture');
        return;
      }
      if (id === 'newSessionBtn') {
        event.preventDefault();
        logEvent('ui.click.document_capture_new_session', 'ok');
        startNewSession();
      }
    },
    true
  );
}

function bootstrapPrimaryUiBindings() {
  try {
    bindPrimaryTaskpaneUiHandlers();
    bindPrimaryTaskpaneDocumentFallbackHandlers();
    logEvent('ui.bootstrap.bindings.success', 'ok');
  } catch (error) {
    logError('ui.bootstrap.bindings.failed', error);
  }
}


/* =========================================
   Mode Switching
   ========================================= */

function switchScope(scope, options = {}) {
  const nextScope = normalizeScope(scope);
  const nextOverride = nextScope === 'systems'
    ? String(options?.labelOverride || '').trim()
    : '';
  if (nextScope === currentScope && nextOverride === String(currentScopeLabelOverride || '').trim()) return;
  const prevScope = currentScope;
  const prevMode = currentMode;
  currentScope = nextScope;
  currentScopeLabelOverride = nextOverride;
  currentMode = modeFromScope(nextScope);
  if (nextScope !== 'email') {
    clearStickyCurrentMailContext('scope_switched');
  }
  applyModeUiState();
  applyScopeUiState();
  persistTaskpaneState();
  logEvent('ui.scope.switch', 'ok', {
    from_scope: prevScope,
    to_scope: currentScope,
    from_mode: prevMode,
    to_mode: currentMode,
  });
}

function resolveReplyToneStructuredInputMeta(options = null) {
  const opts = options && typeof options === 'object' ? options : {};
  const structuredInput =
    opts.structured_input && typeof opts.structured_input === 'object'
      ? opts.structured_input
      : null;
  if (structuredInput) {
    return {
      chips: Array.isArray(structuredInput.chips) ? structuredInput.chips.slice(0, 2) : [],
      verbs: Array.isArray(structuredInput.verbs) ? structuredInput.verbs.slice(0, 2) : [],
      extra_context: String(structuredInput.extra_context || '').trim(),
      combo_key: String(structuredInput.combo_key || '').trim(),
    };
  }
  const fallbackExtraContext = String(opts.reply_additional_context || '').trim();
  if (!fallbackExtraContext) return null;
  return {
    chips: [],
    verbs: [],
    extra_context: fallbackExtraContext,
    combo_key: '',
  };
}

function buildReplyToneOptionsHtml() {
  return REPLY_TONE_PRESETS.map(
    (tone) => `<option value="${escapeAttr(tone.id)}">${escapeHtml(tone.label)}</option>`
  ).join('');
}

function buildReplyToneCardHtml(cardId) {
  return `
    <div class="message assistant reply-tone-message" id="${cardId}">
      <div class="msg-body" style="padding:0; overflow:hidden;">
        <div class="reply-tone-card">
          <div class="reply-tone-card-header">${ICONS.reply} 답변 톤 선택</div>
          <div class="reply-tone-card-body">
            <label class="reply-tone-label" for="${cardId}_select">톤</label>
            <select class="reply-tone-select" id="${cardId}_select">
              ${buildReplyToneOptionsHtml()}
            </select>
          </div>
          <div class="reply-tone-card-footer">
            <button class="reply-tone-cancel" type="button" id="${cardId}_cancel">취소</button>
            <button class="reply-tone-submit" type="button" id="${cardId}_submit">답변 생성</button>
          </div>
        </div>
      </div>
    </div>
  `;
}

function bindReplyToneCardEvents(cardId, structuredInputMeta = null) {
  const selectEl = document.getElementById(`${cardId}_select`);
  const cancelEl = document.getElementById(`${cardId}_cancel`);
  const submitEl = document.getElementById(`${cardId}_submit`);
  const cardEl = document.getElementById(cardId);

  cancelEl?.addEventListener('click', () => {
    cardEl?.remove();
  });

  submitEl?.addEventListener('click', () => {
    const toneId = String(selectEl?.value || '').trim() || 'business_friendly';
    const extraContext = String(structuredInputMeta?.extra_context || '').trim();
    const promptBase = buildReplyPromptWithTone(toneId);
    const prompt = extraContext ? `${promptBase}\n추가 반영사항: ${extraContext}` : promptBase;
    cardEl?.remove();
    sendQuickAction(prompt, {
      label: '답변 생성',
      mode: currentMode,
      action: 'open_reply_tone_picker',
      quick_action_id: 'reply',
      source: 'ai_quick_action',
      reply_tone: toneId,
      skipReplyToneIntercept: true,
      structured_input: structuredInputMeta || undefined,
      reply_additional_context: extraContext || '',
    });
  });
}

function openReplyTonePickerCard(options = null) {
  const structuredInputMeta = resolveReplyToneStructuredInputMeta(options);
  const chatArea = document.getElementById('chatArea');
  if (!chatArea) return;
  removeWelcomeStateIfExists();
  removeReplyToneCards();

  const cardId = `reply_tone_card_${Date.now()}`;
  chatArea.insertAdjacentHTML('beforeend', buildReplyToneCardHtml(cardId));
  scrollToBottom();
  bindReplyToneCardEvents(cardId, structuredInputMeta);
}

function removeReplyToneCards() {
  document.querySelectorAll('.reply-tone-message').forEach((el) => el.remove());
}

function buildReplyPromptWithTone(toneId) {
  const tone = REPLY_TONE_PRESETS.find((item) => item.id === toneId) || REPLY_TONE_PRESETS[0];
  return `이 메일에 대한 답변 초안을 작성해줘. 톤은 ${tone.label}(${tone.id})로 해줘.`;
}


/* =========================================
   Email Context
   ========================================= */

function getLoadableMailboxMessageItem() {
  if (!Office.context.mailbox || !Office.context.mailbox.item) {
    logEvent('mail.context.load.no_item', 'warn');
    return null;
  }
  const item = Office.context.mailbox.item;
  if (item.itemType !== Office.MailboxEnums.ItemType.Message) {
    logEvent('mail.context.load.skip_non_message', 'warn', { item_type: item.itemType });
    return null;
  }
  return item;
}

function resolveEmailContextSender(item) {
  if (!item?.from) return '';
  return String(item.from.emailAddress || item.from.displayName || '').trim();
}

function buildEmailContextState(item, subject, body) {
  const rawItemId = String(item.itemId || '').trim();
  const restItemId = toRestId(rawItemId);
  const prevContext = emailContext;
  const isSameItem =
    prevContext &&
    ((prevContext.restItemId && prevContext.restItemId === restItemId) ||
      (prevContext.itemId && prevContext.itemId === rawItemId));
  return {
    context: {
      subject,
      body,
      from: resolveEmailContextSender(item),
      itemId: rawItemId,
      restItemId,
      resolvedMessageId: isSameItem ? prevContext.resolvedMessageId || null : null,
      resolvedBy: isSameItem ? prevContext.resolvedBy || null : null,
    },
    rawItemId,
    restItemId,
  };
}

function logLoadedEmailContextSuccess(subject, rawItemId, restItemId) {
  logEvent('mail.context.load.success', 'ok', {
    subject: String(subject || '').slice(0, 80),
    hasItemId: Boolean(rawItemId),
    itemId: rawItemId || '',
    itemIdPrefix: rawItemId ? rawItemId.slice(0, 24) : '',
    hasRestItemId: Boolean(restItemId),
    restItemId: restItemId || '',
    restIdPrefix: restItemId ? restItemId.slice(0, 24) : '',
  });
}

async function loadEmailContext() {
  logEvent('mail.context.load.start', 'ok', { mode: currentMode });
  const item = getLoadableMailboxMessageItem();
  if (!item) return;

  try {
    const subject = await getItemSubject(item);
    const body = await getItemBodyPreview(item);
    const nextState = buildEmailContextState(item, subject, body);
    emailContext = nextState.context;
    await runAutoEmailBootstrap();
    persistTaskpaneState();
    logLoadedEmailContextSuccess(subject, nextState.rawItemId, nextState.restItemId);
  } catch (error) {
    logError('mail.context.load.failed', error);
  }
}


/* =========================================
   Chat – Send & Receive
   ========================================= */


/* Intent-related helpers are extracted to `taskpane.intent-utils.js`. */

function buildWorkflowDispatchRuntimePayload(outbound = '') {
  const runtimePayload = getRuntimeOptionsPayload();
  const quickActionMeta = pendingQuickAction && typeof pendingQuickAction === 'object'
    ? { ...pendingQuickAction }
    : null;
  if (quickActionMeta) {
    const quickActionId = String(
      quickActionMeta.quick_action_id || quickActionMeta.id || ''
    ).trim().toLowerCase();
    const quickActionLabel = String(
      quickActionMeta.quick_action_label || quickActionMeta.label || ''
    ).trim();
    const quickActionSource = String(
      quickActionMeta.quick_action_source || quickActionMeta.source || 'quick_action'
    ).trim().toLowerCase();
    if (quickActionId) runtimePayload.quick_action_id = quickActionId;
    if (quickActionLabel) runtimePayload.quick_action_label = quickActionLabel;
    if (quickActionSource) runtimePayload.quick_action_source = quickActionSource;

    const quickActionEmailId = String(
      quickActionMeta.email_message_id || quickActionMeta.message_id || ''
    ).trim();
    if (quickActionEmailId) {
      runtimePayload.email_message_id = quickActionEmailId;
      runtimePayload.current_mail_only = true;
      runtimePayload.scope = 'email';
    }
  }
  const turnKind = classifyTurnKind(outbound, runtimePayload);
  runtimePayload.turn_kind = turnKind;
  const useThinkingProgress = shouldShowThinkingProgress(outbound, runtimePayload);
  if (quickActionMeta) {
    pendingQuickAction = null;
  }
  return { runtimePayload, useThinkingProgress, turnKind };
}

function startWorkflowDispatchVisuals(useThinkingProgress) {
  const visuals = { typingEl: null, deepProgressTracker: null, streamingAssistant: null };
  if (useThinkingProgress) {
    visuals.deepProgressTracker = startDeepProgressCard('assistant_workflow');
    if (ENABLE_PARTIAL_ANSWER_STREAM) {
      visuals.streamingAssistant = showStreamingAssistantMessage();
    }
    return visuals;
  }
  visuals.typingEl = showTyping();
  return visuals;
}

function handleWorkflowDispatchStreamEvent(visuals, eventData) {
  if (!visuals?.deepProgressTracker) return;
  applyDeepProgressEvent(visuals.deepProgressTracker, eventData);
  scheduleDeepProgressRender(visuals.deepProgressTracker);
  if (!ENABLE_PARTIAL_ANSWER_STREAM || !visuals.streamingAssistant || !eventData || typeof eventData !== 'object') {
    return;
  }
  const eventType = String(eventData.type || '').trim().toLowerCase();
  if (eventType !== 'partial_answer') return;
  const accumulated = typeof eventData.accumulated === 'string'
    ? eventData.accumulated
    : null;
  if (accumulated !== null) {
    updateStreamingAssistantMessage(visuals.streamingAssistant, accumulated, { append: false });
  } else {
    updateStreamingAssistantMessage(visuals.streamingAssistant, String(eventData.text || ''), { append: true });
  }
}

function cleanupWorkflowDispatchVisuals(visuals) {
  if (!visuals) return;
  if (visuals.typingEl) removeTyping(visuals.typingEl);
  if (visuals.streamingAssistant) {
    removeStreamingAssistantMessage(visuals.streamingAssistant);
    visuals.streamingAssistant = null;
  }
}

function finishWorkflowDispatchTracker(visuals, data) {
  if (!visuals?.deepProgressTracker) return;
  finishDeepProgressCard(visuals.deepProgressTracker, {
    finalState: data?.status === 'confirm_required' ? 'confirm' : 'done',
    trace: data?.metadata?.thinking_trace || null,
    metadata: data?.metadata || null,
  });
}

function handleWorkflowDispatchResponse(data, options = {}) {
  const replyDraft = Boolean(options.replyDraft);
  if (data?.status === 'confirm_required') {
    logEvent('workflow.dispatch.confirm_required', 'ok', {
      tool_calls: Array.isArray(data?.tool_calls) ? data.tool_calls.length : 0,
    });
    handleConfirmRequired(data);
    return;
  }
  logEvent('workflow.dispatch.completed', 'ok', {
    answer_len: String(data?.answer || '').length,
  });
  const answerText = String(data?.answer || '').trim();
  const normalizedUiOutput = normalizeUiOutputPayload(data?.metadata?.ui_output || data?.ui_output);
  addAssistantMessage(data?.answer || '응답을 받지 못했습니다.', {
    metadata: data?.metadata || null,
    uiOutput: replyDraft ? null : normalizedUiOutput,
    replyDraft,
    forceRestartAction: !answerText,
  });
}

function handleWorkflowDispatchError(error, visuals) {
  logError('workflow.dispatch.failed', error);
  cleanupWorkflowDispatchVisuals(visuals);
  if (visuals?.deepProgressTracker) {
    finishDeepProgressCard(visuals.deepProgressTracker, {
      finalState: 'error',
      note: '오류가 발생했습니다. 네트워크 또는 서버 상태를 확인해주세요.',
    });
  }
  addAssistantMessage(toUserFacingRequestErrorMessage(error), {
    forceRestartAction: true,
  });
}

async function dispatchAssistantWorkflowMessage(message) {
  const outbound = String(message || '').trim();
  if (!outbound || isProcessing) return;
  const expectsReplyDraft = isReplyDraftRequest(outbound);
  const { runtimePayload, useThinkingProgress, turnKind } = buildWorkflowDispatchRuntimePayload(outbound);
  const bypassStickyCurrentMailContext =
    hasExplicitMailboxSearchPhraseInText(outbound)
    && !hasExplicitCurrentMailPhraseInText(outbound)
    && !hasStructuredCurrentMailChip(runtimePayload);
  if (bypassStickyCurrentMailContext) {
    runtimePayload.current_mail_only = false;
    delete runtimePayload.email_message_id;
    runtimePayload.suppress_request_email_context = true;
    clearStickyCurrentMailContext('explicit_mailbox_search');
  }
  const allowStickyCurrentMailContext =
    String(currentMode || '').trim().toLowerCase() === 'email'
    && normalizeScope(runtimePayload?.scope || currentScope) === 'email'
    && !bypassStickyCurrentMailContext;
  if (typeof maybeSeedStickyCurrentMailContextFromRuntime === 'function') {
    maybeSeedStickyCurrentMailContextFromRuntime(runtimePayload, {
      source: 'workflow_dispatch',
      clearWhenDisabled: !allowStickyCurrentMailContext || bypassStickyCurrentMailContext,
      clearReason: 'scope_or_query_changed',
    });
  }
  if (typeof applyStickyCurrentMailContextToRuntime === 'function') {
    applyStickyCurrentMailContextToRuntime(runtimePayload, {
      allow: allowStickyCurrentMailContext,
    });
  }
  if (typeof consumeStickyCurrentMailContextFromPayload === 'function') {
    consumeStickyCurrentMailContextFromPayload(runtimePayload, {
      reason: 'workflow_dispatch',
    });
  }
  isProcessing = true;
  setSendButtonState(false);
  const visuals = { typingEl: null, deepProgressTracker: null, streamingAssistant: null };
  logEvent('workflow.dispatch.start', 'ok', {
    message_len: outbound.length,
    thinking_ui: useThinkingProgress,
    turn_kind: turnKind || TURN_KIND.TASK,
  });

  try {
    Object.assign(visuals, startWorkflowDispatchVisuals(useThinkingProgress));
    const requestPayload = {
      message: outbound,
      thread_id: chatThreadId,
      runtime_options: runtimePayload,
    };
    const data = useThinkingProgress
        ? await requestChatStream(requestPayload, {
          onEvent: (eventData) => handleWorkflowDispatchStreamEvent(visuals, eventData),
        })
      : await requestChat(requestPayload);
    cleanupWorkflowDispatchVisuals(visuals);
    finishWorkflowDispatchTracker(visuals, data);
    handleWorkflowDispatchResponse(data, { replyDraft: expectsReplyDraft });
  } catch (error) {
    handleWorkflowDispatchError(error, visuals);
  } finally {
    isProcessing = false;
    setSendButtonState(true);
  }
}

function sendQuickAction(message, meta = null) {
  pendingQuickAction = meta ? { ...meta } : null;
  logEvent('ui.quick_action.dispatch', 'ok', {
    mode: currentMode,
    label: String(meta?.label || ''),
    message_len: String(message || '').length,
  });
  const input = document.getElementById('chatInput');
  input.value = message;
  sendMessage();
}

function buildAutoScheduleRegistrationMessage({ emailCtx } = {}) {
  return buildAutoScheduleRegistrationMessageFromUtils({ emailCtx });
}


/* Message rendering/status-line helpers are extracted to `taskpane.renderer-utils.js`. */

/* =========================================
   Chat – Clear & Reset
   ========================================= */

function buildWelcomeStateMarkup() {
  return `
    <div id="welcomeState" class="welcome-state">
      <div class="welcome-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
      </div>
      <h2 class="welcome-title">안녕하세요.무엇을 도와 드릴까요?</h2>
      <p class="welcome-desc">메일 요약, 일정 등록, 회의실 예약 등 다양한 업무를 지원합니다.</p>
    </div>`;
}

function startNewSession() {
  clearChat();
  const input = document.getElementById('chatInput');
  if (input && typeof input.focus === 'function') {
    input.focus();
  }
}

function clearChat() {
  const chatArea = document.getElementById('chatArea');
  const input = document.getElementById('chatInput');
  hideScopeShortcutMenu();
  hideVerbShortcutMenu();
  hideClarificationPromptCard();

  // Re-render welcome state
  chatArea.innerHTML = buildWelcomeStateMarkup();

  // Reset thread
  chatThreadId = 'outlook_' + Date.now();
  pendingHrDraft = null;
  pendingPromiseContext = null;
  pendingRoomSelection = null;
  pendingQuickAction = null;
  clearStickyCurrentMailContext('chat_cleared');
  chatHistory = [];
  restoredInputDraft = '';
  lastTurnStartedAtMs = 0;
  lastCompletedTurnElapsedMs = Number.NaN;
  for (const tracker of deepProgressTrackerRegistry.values()) {
    if (Number.isFinite(tracker?.renderTimerId)) {
      window.clearTimeout(tracker.renderTimerId);
    }
    if (Number.isFinite(tracker?.removeTimerId)) {
      window.clearTimeout(tracker.removeTimerId);
    }
  }
  deepProgressTrackerRegistry.clear();
  if (input) {
    input.value = '';
    autoResize(input);
    updateStructuredSelectionBadges();
  }
  persistTaskpaneState();
  logEvent('chat.clear', 'ok', { mode: currentMode });
}


/* =========================================
   Input Handling
   ========================================= */

function handleScopeShortcutKeyDown(event) {
  return handleShortcutMenuKeyDown(event, {
    items: scopeShortcutItems,
    menuEl: scopeShortcutMenuEl,
    onArrowDown: () => moveScopeShortcutFocus(1),
    onArrowUp: () => moveScopeShortcutFocus(-1),
    onEscape: hideScopeShortcutMenu,
    onConfirm: confirmActiveScopeShortcut,
  });
}

function handleVerbShortcutKeyDown(event) {
  return handleShortcutMenuKeyDown(event, {
    items: verbShortcutItems,
    menuEl: verbShortcutMenuEl,
    onArrowDown: () => moveVerbShortcutFocus(1),
    onArrowUp: () => moveVerbShortcutFocus(-1),
    onEscape: hideVerbShortcutMenu,
    onConfirm: confirmActiveVerbShortcut,
  });
}

function handleKeyDown(event) {
  const onEnter = () => {
    logEvent('ui.keydown.enter', 'ok', {
      shift: Boolean(event?.shiftKey),
      composing: Boolean(event?.isComposing),
    });
    triggerSendMessageFromUi('keydown_handler');
  };
  if (!event || typeof event !== 'object') return;
  if (handleScopeShortcutKeyDown(event)) return;
  if (handleVerbShortcutKeyDown(event)) return;
  if (event.key === 'Enter' && !event.shiftKey) {
    if (event.isComposing) return;
    event.preventDefault();
    onEnter();
    return;
  }
  if (chatInputImeComposing || event.isComposing) return;
}

function autoResize(textarea) {
  autoResizeComposer(textarea, {
    maxHeight: 100,
    onNonEmptyInput: hideClarificationPromptCard,
    // 입력 이벤트 경로가 누락되더라도 @, / 단축어 메뉴는 항상 동기화한다.
    onAfterResize: refreshStructuredShortcutUi,
  });
}

function setSendButtonState(enabled) {
  setButtonEnabled(document.getElementById('sendBtn'), enabled);
}


/* =========================================
   Helpers
   ========================================= */


/* Parsing/render helpers and mail-open helpers are extracted to `taskpane.renderer-utils.js` and `taskpane.mail-open-utils.js`. */

async function apiFetch(path, options = {}, timeoutMs = API_TIMEOUT_MS) {
  const url = `${API_BASE}${path}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const requestPath = String(path || '');
  const isApiLikePath =
    requestPath.startsWith('/api/') ||
    requestPath.startsWith('/search/') ||
    requestPath.startsWith('/intents/');
  const mergedHeaders = new Headers(options?.headers || {});
  if (isApiLikePath) {
    // ngrok free 도메인에서 WebView 요청이 브라우저 경고 HTML(200)을 받는 문제를 회피한다.
    mergedHeaders.set('ngrok-skip-browser-warning', 'true');
    if (!mergedHeaders.has('Accept')) {
      mergedHeaders.set('Accept', 'application/json, */*');
    }
  }
  try {
    return await fetch(url, {
      ...options,
      headers: mergedHeaders,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

function bindOutlookItemChangedHandler() {
  try {
    if (!Office?.context?.mailbox?.addHandlerAsync || !Office?.EventType?.ItemChanged) return;
    Office.context.mailbox.addHandlerAsync(Office.EventType.ItemChanged, () => {
      const currentItem = Office?.context?.mailbox?.item || null;
      const rawItemId = String(currentItem?.itemId || '').trim();
      const restItemId = toRestId(rawItemId);
      logEvent('mail.item_changed', 'ok', {
        action: 'refresh_context_only',
        hasItemId: Boolean(rawItemId),
        itemId: rawItemId || '',
        itemIdPrefix: rawItemId ? rawItemId.slice(0, 24) : '',
        hasRestItemId: Boolean(restItemId),
        restItemId: restItemId || '',
        restIdPrefix: restItemId ? restItemId.slice(0, 24) : '',
      });
      if (normalizeScope(currentScope) !== 'email') {
        switchScope('email');
      }
      clearStickyCurrentMailContext('item_changed');
      emailContext = null;
      pendingEmailIdResolve = null;
      lastAutoBootstrapContextKey = '';
      loadEmailContext();
    });
  } catch (error) {
    logError('mail.item_changed.bind_failed', error);
  }
}

function getItemSubject(item) {
  return new Promise((resolve) => {
    try {
      if (typeof item?.subject === 'string') {
        resolve(item.subject || '');
        return;
      }
      if (item?.subject && typeof item.subject.getAsync === 'function') {
        item.subject.getAsync((result) => {
          if (result?.status === Office.AsyncResultStatus.Succeeded) {
            resolve(result.value || '');
            return;
          }
          resolve('');
        });
        return;
      }
      resolve('');
    } catch (error) {
      logError('mail.subject.read.failed', error);
      resolve('');
    }
  });
}

function getItemBodyPreview(item, maxLen = 500) {
  return new Promise((resolve) => {
    try {
      if (item?.body && typeof item.body.getAsync === 'function') {
        item.body.getAsync(Office.CoercionType.Text, (result) => {
          if (result?.status === Office.AsyncResultStatus.Succeeded) {
            resolve(String(result.value || '').substring(0, maxLen));
            return;
          }
          resolve('');
        });
        return;
      }
      resolve('');
    } catch (error) {
      logError('mail.body_preview.read.failed', error);
      resolve('');
    }
  });
}

function removeWelcomeStateIfExists() {
  const welcome = document.getElementById('welcomeState');
  if (welcome) welcome.remove();
}

function applyModeUiState() {
  // 상단 모드/컨텍스트 배너 UI 제거: 현재는 no-op
}

function normalizeHistoryAssistantOptions(options) {
  if (!options || typeof options !== 'object') return undefined;

  const normalized = {};
  if (typeof options.replyDraft === 'boolean') {
    normalized.replyDraft = options.replyDraft;
  }
  const normalizedUiOutput = normalizeUiOutputPayload(options.uiOutput);
  if (normalizedUiOutput) {
    normalized.uiOutput = normalizedUiOutput;
  }
  const normalizedUiOutputV2 = normalizeUiOutputV2Payload(options.uiOutputV2);
  if (normalizedUiOutputV2) {
    normalized.uiOutputV2 = normalizedUiOutputV2;
  }
  const openableItems = sanitizeOpenableMailItems(options.openableItems);
  if (openableItems.length) {
    normalized.openableItems = openableItems;
  }
  return Object.keys(normalized).length ? normalized : undefined;
}

function recordHistory(role, text, options = null) {
  const normalizedRole = role === 'user' || role === 'assistant' || role === 'system' ? role : 'assistant';
  const normalizedText = String(text || '').trim();
  if (!normalizedText) return;
  const entry = { role: normalizedRole, text: normalizedText, ts: Date.now() };
  if (normalizedRole === 'assistant') {
    const normalizedOptions = normalizeHistoryAssistantOptions(options);
    if (normalizedOptions) entry.options = normalizedOptions;
  }
  chatHistory.push(entry);
  if (chatHistory.length > MAX_PERSISTED_MESSAGES) {
    chatHistory = chatHistory.slice(-MAX_PERSISTED_MESSAGES);
  }
}

function getLatestUserMessageText() {
  if (!Array.isArray(chatHistory) || !chatHistory.length) return '';
  for (let idx = chatHistory.length - 1; idx >= 0; idx -= 1) {
    const entry = chatHistory[idx];
    if (!entry || typeof entry !== 'object') continue;
    if (String(entry.role || '').trim().toLowerCase() !== 'user') continue;
    const text = String(entry.text || '').trim();
    if (text) return text;
  }
  return '';
}

function getTaskpaneStateKey() {
  let user = 'default';
  try {
    user = Office?.context?.mailbox?.userProfile?.emailAddress || 'default';
  } catch (error) {
    logError('state.resolve_user.failed', error);
  }
  return `moldubot_taskpane_state_v${TASKPANE_STATE_VERSION}:${user}`;
}

function persistTaskpaneState() {
  try {
    const inputEl = document.getElementById('chatInput');
    const payload = {
      v: TASKPANE_STATE_VERSION,
      updated_at: Date.now(),
      mode: currentMode,
      scope: normalizeScope(currentScope),
      thread_id: chatThreadId,
      promise_context: pendingPromiseContext,
      input_draft: inputEl ? String(inputEl.value || '') : restoredInputDraft,
      history: chatHistory.slice(-MAX_PERSISTED_MESSAGES),
    };
    localStorage.setItem(getTaskpaneStateKey(), JSON.stringify(payload));
  } catch (error) {
    logError('state.persist.failed', error);
  }
}

function applyRestoredModeScope(payload) {
  if (payload.scope) {
    currentScope = normalizeScope(payload.scope);
    currentMode = modeFromScope(currentScope);
    return;
  }
  if (payload.mode === 'email' || payload.mode === 'assistant') {
    currentMode = payload.mode;
    currentScope = scopeFromMode(payload.mode);
    return;
  }
  currentScope = 'email';
  currentMode = 'email';
}

function restorePromiseContextFromPayload(payload) {
  const restoredPromiseContext = payload.promise_context;
  if (
    restoredPromiseContext &&
    typeof restoredPromiseContext === 'object' &&
    typeof restoredPromiseContext.projectNumber === 'string'
  ) {
    pendingPromiseContext = {
      projectNumber: restoredPromiseContext.projectNumber.trim(),
      projectName: String(restoredPromiseContext.projectName || '').trim(),
      projectType: String(restoredPromiseContext.projectType || '').trim(),
      status: String(restoredPromiseContext.status || '').trim(),
    };
    return;
  }
  pendingPromiseContext = null;
}

function restoreHistoryEntriesFromPayload(payload) {
  if (!Array.isArray(payload.history)) return [];
  return payload.history
    .filter((entry) => entry && typeof entry.text === 'string')
    .map((entry) => ({
      role: entry.role === 'user' || entry.role === 'assistant' || entry.role === 'system' ? entry.role : 'assistant',
      text: String(entry.text || ''),
      ts: Number.isFinite(Number(entry.ts)) ? Number(entry.ts) : undefined,
      options:
        entry.role === 'assistant'
          ? normalizeHistoryAssistantOptions(entry.options)
          : undefined,
    }))
    .filter((entry) => entry.text.trim().length > 0)
    .slice(-MAX_PERSISTED_MESSAGES);
}

function applyRestoredTaskpaneUiState() {
  restoreHistoryToChatArea();
  applyScopeUiState();
}

function restoreTaskpaneState() {
  try {
    const raw = localStorage.getItem(getTaskpaneStateKey());
    if (!raw) return;
    const payload = JSON.parse(raw);
    if (!payload || payload.v !== TASKPANE_STATE_VERSION) return;

    applyRestoredModeScope(payload);
    if (typeof payload.thread_id === 'string' && payload.thread_id.trim()) {
      chatThreadId = payload.thread_id.trim();
    }
    restorePromiseContextFromPayload(payload);
    restoredInputDraft = typeof payload.input_draft === 'string' ? payload.input_draft : '';
    chatHistory = restoreHistoryEntriesFromPayload(payload);
    applyRestoredTaskpaneUiState();
  } catch (error) {
    logError('state.restore.failed', error);
  }
}

function restoreHistoryToChatArea() {
  if (!chatHistory.length) return;
  const chatArea = document.getElementById('chatArea');
  if (!chatArea) return;

  chatArea.innerHTML = '';
  let pendingUserTs = Number.NaN;
  let pendingTurnElapsedMs = Number.NaN;
  for (const entry of chatHistory) {
    if (entry.role === 'user') {
      addUserMessage(entry.text, {
        save: false,
        separatorElapsedMs: pendingTurnElapsedMs,
      });
      pendingUserTs = Number.isFinite(Number(entry.ts)) ? Number(entry.ts) : Number.NaN;
      pendingTurnElapsedMs = Number.NaN;
    } else if (entry.role === 'system') {
      addSystemMessage(entry.text, { save: false });
    } else {
      addAssistantMessage(entry.text, { save: false, restore: true, ...(entry.options || {}) });
      const assistantTs = Number(entry.ts);
      if (
        Number.isFinite(assistantTs) &&
        Number.isFinite(pendingUserTs) &&
        assistantTs >= pendingUserTs
      ) {
        pendingTurnElapsedMs = Math.max(0, assistantTs - pendingUserTs);
      }
    }
  }
}

function restoreInputDraft() {
  const inputEl = document.getElementById('chatInput');
  if (!inputEl || !restoredInputDraft) return;
  inputEl.value = restoredInputDraft;
  autoResize(inputEl);
  updateStructuredSelectionBadges();
}

function bindStatePersistenceHandlers() {
  const inputEl = document.getElementById('chatInput');
  if (!inputEl || inputEl.dataset.stateBound === '1') return;
  inputEl.dataset.stateBound = '1';
  inputEl.addEventListener('input', () => {
    restoredInputDraft = inputEl.value || '';
    persistTaskpaneState();
  });
  window.addEventListener('beforeunload', () => {
    persistTaskpaneState();
  });
}
