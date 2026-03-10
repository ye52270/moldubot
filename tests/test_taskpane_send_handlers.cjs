const test = require('node:test');
const assert = require('node:assert/strict');

const modulePath = '../clients/outlook-addin/taskpane.send.handlers.js';

function loadModule() {
  delete require.cache[require.resolve(modulePath)];
  return require(modulePath);
}

test('meeting suggestion handler adds answer_format metadata blocks for boxed rendering', async () => {
  const moduleRef = loadModule();
  const calls = [];
  const handlers = moduleRef.create({
    chatApi: {
      suggestMeetingFromCurrentMail: async () => ({
        status: 'completed',
        proposal: {
          meeting_subject: 'Tenant Restriction 논의',
          summary_text: '크롬 URL 접근 정책 점검',
          major_issues: ['Chrome 특정 URL 접근 시 Redirect 정책 검토'],
          attendees: ['이상수(LEE Sangsoo)/AX Solution서비스4팀/SK &lt;ssl@skcc.com&gt;, 김태호 &lt;kimth@cnthoth.com&gt;'],
          attendee_count: 2,
          room_candidates: [{ building: '판교', floor: 7, room_name: 'A' }],
          time_candidates: [{ date: '2026-03-09', start_time: '10:00', end_time: '11:00' }],
        },
      }),
      listMeetingRoomBuildings: async () => ['판교'],
    },
    messageUi: {
      addMessage: (role, text, metadata) => calls.push({ role, text, metadata }),
      addMeetingRoomScheduleCard: () => {},
      addMeetingRoomBuildingCard: () => {},
    },
    state: {},
    selectionController: {
      getSelectionContext: async () => ({ emailId: 'mail-1', mailboxUser: 'user@example.com' }),
    },
    clearProgressWithMinimumVisibility: () => {},
  });

  await handlers.handleCurrentMailMeetingSuggestionQuery('현재메일 요약해서 회의실 등록');

  const assistantMessage = calls.find((item) => item.role === 'assistant');
  assert.equal(Boolean(assistantMessage), true);
  assert.equal(
    Array.isArray(assistantMessage.metadata.answer_format.blocks),
    true
  );
  const discussionBlock = assistantMessage.metadata.answer_format.blocks.find((block) => block.type === 'ordered_list');
  assert.equal(Boolean(discussionBlock), true);
  assert.equal(Array.isArray(discussionBlock.items), true);
  assert.equal(discussionBlock.items[0], 'Chrome 특정 URL 접근 시 Redirect 정책 검토');
  const headings = assistantMessage.metadata.answer_format.blocks
    .filter((block) => block.type === 'heading')
    .map((block) => block.text);
  assert.equal(headings.includes('회의 안건(요약)'), true);
  assert.equal(headings.includes('논의할 주요 내용'), true);
  assert.equal(headings.includes('참석자 제안'), true);
  const attendeeBlock = assistantMessage.metadata.answer_format.blocks.find((block) => {
    return block.type === 'unordered_list' && Array.isArray(block.items) && block.items[0] === '참석 인원: 2명';
  });
  assert.equal(Boolean(attendeeBlock), true);
  assert.equal(attendeeBlock.items[1], '후보: 이상수 <ssl@skcc.com>, 김태호 <kimth@cnthoth.com>');
});

test('calendar suggestion handler adds answer_format metadata blocks for boxed rendering', async () => {
  const moduleRef = loadModule();
  const calls = [];
  const handlers = moduleRef.create({
    chatApi: {
      suggestCalendarFromCurrentMail: async () => ({
        status: 'completed',
        proposal: {
          subject: '[일정] Tenant Restriction 방안 논의',
          summary_text: '크롬 URL 접근 시 Edge Redirect 정책 검토',
          key_points: ['정책 적용 범위 확인', '예외 URL 목록 정리'],
          attendees: ['이상수(LEE Sangsoo)/AX Solution서비스4팀/SK &lt;ssl@skcc.com&gt;, 김태호 &lt;kimth@cnthoth.com&gt;'],
        },
      }),
    },
    messageUi: {
      addMessage: (role, text, metadata) => calls.push({ role, text, metadata }),
      addCalendarEventCard: () => {},
    },
    state: {},
    selectionController: {
      getSelectionContext: async () => ({ emailId: 'mail-2', mailboxUser: 'user@example.com' }),
    },
    clearProgressWithMinimumVisibility: () => {},
  });

  await handlers.handleCurrentMailCalendarSuggestionQuery('현재메일 기반으로 일정 등록해줘');

  const assistantMessage = calls.find((item) => item.role === 'assistant');
  assert.equal(Boolean(assistantMessage), true);
  assert.equal(
    Array.isArray(assistantMessage.metadata.answer_format.blocks),
    true
  );
  const headings = assistantMessage.metadata.answer_format.blocks
    .filter((block) => block.type === 'heading')
    .map((block) => block.text);
  assert.equal(headings.includes('일정 안건(요약)'), true);
  assert.equal(headings.includes('논의할 주요 내용'), true);
  assert.equal(headings.includes('참석자 제안'), true);
  const attendeeBlock = assistantMessage.metadata.answer_format.blocks.find((block) => {
    return block.type === 'unordered_list' && Array.isArray(block.items) && block.items[0] === '이상수 <ssl@skcc.com>';
  });
  assert.equal(Boolean(attendeeBlock), true);
  assert.equal(attendeeBlock.items[1], '김태호 <kimth@cnthoth.com>');
});
