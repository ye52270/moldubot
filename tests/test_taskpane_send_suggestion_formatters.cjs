const test = require('node:test');
const assert = require('node:assert/strict');

const modulePath = '../clients/outlook-addin/taskpane.send.suggestion_formatters.js';

function loadModule() {
  delete require.cache[require.resolve(modulePath)];
  return require(modulePath);
}

test('send suggestion formatter normalizes attendee strings into name/email', () => {
  const moduleRef = loadModule();
  const fmt = moduleRef.create();
  const metadata = fmt.buildMeetingSuggestionMetadata({
    attendees: ['이상수(LEE Sangsoo)/AX팀/SK &lt;ssl@skcc.com&gt;, 김태호 &lt;kimth@cnthoth.com&gt;'],
    attendee_count: 2,
  });

  const blocks = metadata && metadata.answer_format && Array.isArray(metadata.answer_format.blocks)
    ? metadata.answer_format.blocks
    : [];
  const attendeeList = blocks.find((block) => block.type === 'unordered_list' && Array.isArray(block.items) && block.items[0] === '참석 인원: 2명');
  assert.equal(Boolean(attendeeList), true);
  assert.equal(attendeeList.items[1], '후보: 이상수 <ssl@skcc.com>, 김태호 <kimth@cnthoth.com>');
});

test('send suggestion formatter returns schedule defaults from first candidate', () => {
  const moduleRef = loadModule();
  const fmt = moduleRef.create();
  const defaults = fmt.buildSuggestedScheduleDefaults({
    attendee_count: 3,
    meeting_subject: '테스트 회의',
    time_candidates: [{ date: '2026-03-10', start_time: '09:00', end_time: '10:00' }],
    room_candidates: [{ building: 'A', floor: 1, room_name: '101' }, { building: 'B', floor: 2, room_name: '201' }],
  });

  assert.equal(defaults.date, '2026-03-10');
  assert.equal(defaults.start_time, '09:00');
  assert.equal(defaults.end_time, '10:00');
  assert.equal(defaults.attendee_count, 3);
  assert.equal(defaults.subject, '테스트 회의');
  assert.equal(defaults.room_candidates.length, 2);
});
