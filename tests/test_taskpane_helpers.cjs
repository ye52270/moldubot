const test = require('node:test');
const assert = require('node:assert/strict');

const helpersPath = '../clients/outlook-addin/taskpane.helpers.js';

function loadHelpers() {
  global.window = {};
  delete require.cache[require.resolve(helpersPath)];
  return require(helpersPath);
}

test('report query detector accepts 보고서 생성 variants', () => {
  const helpers = loadHelpers();
  assert.equal(helpers.isReportGenerationQuery('보고서 생성'), true);
  assert.equal(helpers.isReportGenerationQuery('현재 메일 보고서 생성해줘'), true);
  assert.equal(helpers.isReportGenerationQuery('보고서생성'), true);
});

test('report query detector accepts 보고서 작성 variants', () => {
  const helpers = loadHelpers();
  assert.equal(helpers.isReportGenerationQuery('보고서 작성'), true);
  assert.equal(helpers.isReportGenerationQuery('현재메일 보고서 작성해줘'), true);
  assert.equal(helpers.isReportGenerationQuery('리포트 작성 부탁'), true);
});

test('report query detector accepts slash and bare skill-style variants', () => {
  const helpers = loadHelpers();
  assert.equal(helpers.isReportGenerationQuery('/보고서'), true);
  assert.equal(helpers.isReportGenerationQuery('보고서'), true);
  assert.equal(helpers.isReportGenerationQuery('/리포트'), true);
});

test('report query detector rejects unrelated phrases', () => {
  const helpers = loadHelpers();
  assert.equal(helpers.isReportGenerationQuery('현재메일 요약'), false);
  assert.equal(helpers.isReportGenerationQuery('회의실 예약'), false);
});

test('weekly report query detector accepts 주간보고 variants', () => {
  const helpers = loadHelpers();
  assert.equal(helpers.isWeeklyReportGenerationQuery('주간보고'), true);
  assert.equal(helpers.isWeeklyReportGenerationQuery('주간보고 작성'), true);
  assert.equal(helpers.isWeeklyReportGenerationQuery('주간보고생성'), true);
  assert.equal(helpers.isWeeklyReportGenerationQuery('위클리 작성 부탁'), true);
});

test('weekly report query detector rejects unrelated phrases', () => {
  const helpers = loadHelpers();
  assert.equal(helpers.isWeeklyReportGenerationQuery('현재메일 요약'), false);
  assert.equal(helpers.isWeeklyReportGenerationQuery('보고서 작성'), false);
});

test('meeting room query detector accepts 회의실 variants', () => {
  const helpers = loadHelpers();
  assert.equal(helpers.isMeetingRoomBookingQuery('회의실'), true);
  assert.equal(helpers.isMeetingRoomBookingQuery('회의실 입력해줘'), true);
  assert.equal(helpers.isMeetingRoomBookingQuery('미팅룸 예약'), true);
});

test('meeting room query detector rejects unrelated phrases', () => {
  const helpers = loadHelpers();
  assert.equal(helpers.isMeetingRoomBookingQuery('현재메일 요약'), false);
  assert.equal(helpers.isMeetingRoomBookingQuery('주간보고'), false);
});

test('current mail meeting suggestion detector accepts mixed intent phrases', () => {
  const helpers = loadHelpers();
  assert.equal(helpers.isCurrentMailMeetingRoomSuggestionQuery('현재메일 분석해서 회의실 예약해줘'), true);
  assert.equal(helpers.isCurrentMailMeetingRoomSuggestionQuery('현재메일 요약 후 회의실 예약'), true);
});

test('current mail meeting suggestion detector rejects general meeting-room queries', () => {
  const helpers = loadHelpers();
  assert.equal(helpers.isCurrentMailMeetingRoomSuggestionQuery('회의실 예약해줘'), false);
  assert.equal(helpers.isCurrentMailMeetingRoomSuggestionQuery('현재메일 요약해줘'), false);
});

test('calendar query detector accepts 일정 등록 variants', () => {
  const helpers = loadHelpers();
  assert.equal(helpers.isCalendarEventQuery('일정 등록해줘'), true);
  assert.equal(helpers.isCalendarEventQuery('일정 추가'), true);
  assert.equal(helpers.isCalendarEventQuery('회의실 예약'), false);
});

test('current mail calendar query detector accepts current mail variants', () => {
  const helpers = loadHelpers();
  assert.equal(helpers.isCurrentMailCalendarSuggestionQuery('현재메일 요약해서 주요 내용 일정 등록'), true);
  assert.equal(helpers.isCurrentMailCalendarSuggestionQuery('현재메일 요약 후 주요 수신자를 참석자로 해서 일정 등록해줘'), true);
  assert.equal(helpers.isCurrentMailCalendarSuggestionQuery('일정 등록해줘'), false);
});

test('promise query detector accepts 실행예산 variants', () => {
  const helpers = loadHelpers();
  assert.equal(helpers.isPromiseBudgetQuery('실행예산'), true);
  assert.equal(helpers.isPromiseBudgetQuery('실행예산 조회'), true);
  assert.equal(helpers.isPromiseBudgetQuery('promise 입력'), true);
});

test('finance query detector accepts 비용정산 variants', () => {
  const helpers = loadHelpers();
  assert.equal(helpers.isFinanceSettlementQuery('비용정산'), true);
  assert.equal(helpers.isFinanceSettlementQuery('비용 정산 입력'), true);
});

test('hr query detector accepts 근태/휴가 variants', () => {
  const helpers = loadHelpers();
  assert.equal(helpers.isHrApplyQuery('근태 신청'), true);
  assert.equal(helpers.isHrApplyQuery('휴가신청'), true);
});

test('quick prompt trigger detects only single question mark', () => {
  const helpers = loadHelpers();
  assert.equal(helpers.isQuickPromptTrigger('?'), true);
  assert.equal(helpers.isQuickPromptTrigger(' ? '), true);
  assert.equal(helpers.isQuickPromptTrigger('??'), false);
  assert.equal(helpers.isQuickPromptTrigger('현재메일 요약 ?'), false);
});

test('quick prompt templates returns requested presets', () => {
  const helpers = loadHelpers();
  const prompts = helpers.getQuickPromptTemplates();
  assert.equal(Array.isArray(prompts), true);
  assert.equal(prompts.length, 20);
  assert.equal(prompts[0], '현재메일 요약해줘');
  assert.equal(prompts[1], '현재메일 3~5줄로 요약');
  assert.equal(prompts[2], '현재메일 주요 키워드 2~3개 할일로 등록');
  assert.equal(prompts[3], '현재메일의 주요 내용을 추출해서 할일로 등록');
  assert.equal(prompts[4], '현재메일의 주요 내용중 이슈사항을 정리해서 회의실 예약해줘');
  assert.equal(prompts[5], '현재메일에서 내가 해야할 일을 뽑아서 일정으로 등록해줘');
  assert.equal(prompts[6], '조용득 관련 1월 메일 조회수 요약해줘');
  assert.equal(
    prompts[7],
    'M365 프로젝트 진행, 일정 관련 메일을 찾아서 요약해줘. 기술적 이슈도 검색해서 같이 알려줘'
  );
  assert.equal(
    prompts[8],
    'M365 프로젝트 진행, 일정 관련 메일에서 수신자별 역할을 표 형식으로 정리해줘'
  );
});
