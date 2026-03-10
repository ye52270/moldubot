const test = require('node:test');
const assert = require('node:assert/strict');

const apiModulePath = '../clients/outlook-addin/taskpane.api.js';

function loadApiModule() {
  global.window = {};
  delete require.cache[require.resolve(apiModulePath)];
  return require(apiModulePath);
}

function createFakeStreamResponse(chunks) {
  const encoder = new TextEncoder();
  let index = 0;
  return {
    ok: true,
    body: {
      getReader() {
        return {
          async read() {
            if (index >= chunks.length) {
              return { done: true, value: undefined };
            }
            const value = encoder.encode(chunks[index]);
            index += 1;
            return { done: false, value };
          },
        };
      },
    },
  };
}

test('taskpane api parses single SSE chunk', () => {
  const api = loadApiModule();
  const instance = api.create({
    selectionController: {},
    isCurrentMailQuery: () => false,
    logClientEvent: () => {},
    shortId: (value) => value,
  });

  const parsed = instance._parseSseChunk('event: progress\ndata: {"phase":"processing"}\n\n');
  assert.equal(parsed.event, 'progress');
  assert.equal(parsed.data.phase, 'processing');
});

test('taskpane api parses CRLF and multi-line data payload', () => {
  const api = loadApiModule();
  const instance = api.create({
    selectionController: {},
    isCurrentMailQuery: () => false,
    logClientEvent: () => {},
    shortId: (value) => value,
  });

  const parsed = instance._parseSseChunk(
    'event: completed\r\n' +
    'data: {"answer":"완료","metadata":\r\n' +
    'data: {"source":"deep-agent"}}\r\n\r\n'
  );
  assert.equal(parsed.event, 'completed');
  assert.equal(parsed.data.answer, '완료');
});

test('taskpane api uses stream response and emits progress callback', async () => {
  const api = loadApiModule();
  const events = [];
  const selectionController = {
    getSelectionContext: async () => ({
      emailId: 'message-1',
      mailboxUser: 'user@example.com',
      reason: 'ok_direct',
      directItemId: '',
      asyncItemId: '',
      selectedItemId: '',
    }),
    getSelectionRevision: () => 1,
    isStaleCurrentMailSelection: () => false,
    markCurrentMailSent: () => {},
  };
  let fallbackCalled = false;
  global.fetch = async (url) => {
    if (url === '/search/chat/stream') {
      return createFakeStreamResponse([
        'event: progress\ndata: {"phase":"processing","message":"처리중"}\n\n',
        'event: token\ndata: {"phase":"token","text":"완"}\n\n',
        'event: token\ndata: {"phase":"token","text":"료"}\n\n',
        'event: completed\ndata: {"answer":"완료","metadata":{"source":"deep-agent"}}\n\n',
      ]);
    }
    fallbackCalled = true;
    return { ok: true, json: async () => ({ answer: 'fallback', metadata: {} }) };
  };

  const instance = api.create({
    selectionController,
    isCurrentMailQuery: () => false,
    logClientEvent: () => {},
    shortId: (value) => value,
  });

  const result = await instance.requestAssistantReply(
    '테스트',
    (eventPayload) => {
      events.push(eventPayload.phase);
    },
    null
  );

  assert.equal(fallbackCalled, false);
  assert.equal(result.answer, '완료');
  assert.deepEqual(events, ['processing']);
});

test('taskpane api keeps thread_id and forwards runtime scope option', async () => {
  const api = loadApiModule();
  const requestBodies = [];
  const selectionController = {
    getSelectionContext: async () => ({
      emailId: 'message-2',
      mailboxUser: 'user@example.com',
      reason: 'ok_direct',
      directItemId: '',
      asyncItemId: '',
      selectedItemId: '',
    }),
    getSelectionRevision: () => 1,
    isStaleCurrentMailSelection: () => false,
    markCurrentMailSent: () => {},
  };

  global.fetch = async (url, init) => {
    if (url === '/search/chat/stream') {
      requestBodies.push(JSON.parse(String(init && init.body ? init.body : '{}')));
      if (requestBodies.length === 1) {
        return createFakeStreamResponse([
          'event: completed\ndata: {"thread_id":"thread-abc","answer":"첫 응답","metadata":{"source":"deep-agent"}}\n\n',
        ]);
      }
      return { ok: false, body: null };
    }
    requestBodies.push(JSON.parse(String(init && init.body ? init.body : '{}')));
    return {
      ok: true,
      json: async () => ({
        thread_id: 'thread-abc',
        answer: '둘째 응답',
        metadata: { source: 'deep-agent' },
      }),
    };
  };

  const instance = api.create({
    selectionController,
    isCurrentMailQuery: () => false,
    logClientEvent: () => {},
    shortId: (value) => value,
  });

  await instance.requestAssistantReply('첫 질문');
  await instance.requestAssistantReply('범위 확정 질문', null, { scope: 'previous_results' });

  const secondRequestBody = requestBodies[2];
  assert.equal(secondRequestBody.thread_id, 'thread-abc');
  assert.equal(secondRequestBody.runtime_options.scope, 'previous_results');
});

test('taskpane api reads report SSE events', async () => {
  const api = loadApiModule();
  const events = [];
  const requestBodies = [];
  global.fetch = async (url, init) => {
    if (url === '/report/generate') {
      requestBodies.push(JSON.parse(String(init && init.body ? init.body : '{}')));
      return createFakeStreamResponse([
        'event: message\ndata: {"type":"step","step":"1","status":"running"}\n\n',
        'event: message\ndata: {"type":"done","docx_url":"/report/download/a.docx"}\n\n',
      ]);
    }
    return { ok: false, body: null };
  };

  const instance = api.create({
    selectionController: {},
    isCurrentMailQuery: () => false,
    logClientEvent: () => {},
    shortId: (value) => value,
  });
  await instance.requestReportReply(
    '본문',
    '제목',
    (eventPayload) => events.push(eventPayload.type),
    {
      emailReceivedDate: '2026-01-16T05:47:10Z',
      emailSender: '박제영',
    }
  );
  assert.deepEqual(events, ['step', 'done']);
  assert.equal(requestBodies[0].email_received_date, '2026-01-16T05:47:10Z');
  assert.equal(requestBodies[0].email_sender, '박제영');
});

test('taskpane api reads weekly report SSE events', async () => {
  const api = loadApiModule();
  const events = [];
  const requestBodies = [];
  global.fetch = async (url, init) => {
    if (url === '/report/weekly/generate') {
      requestBodies.push(JSON.parse(String(init && init.body ? init.body : '{}')));
      return createFakeStreamResponse([
        'event: message\ndata: {"type":"step","step":"1","status":"running"}\n\n',
        'event: message\ndata: {"type":"done","docx_url":"/report/download/weekly.docx"}\n\n',
      ]);
    }
    return { ok: false, body: null };
  };

  const instance = api.create({
    selectionController: {},
    isCurrentMailQuery: () => false,
    logClientEvent: () => {},
    shortId: (value) => value,
  });
  await instance.requestWeeklyReportReply(
    2,
    '박제영',
    (eventPayload) => events.push(eventPayload.type)
  );
  assert.deepEqual(events, ['step', 'done']);
  assert.equal(requestBodies[0].week_offset, 2);
  assert.equal(requestBodies[0].report_author, '박제영');
});

test('taskpane api fetches meeting room depth options and books room', async () => {
  const api = loadApiModule();
  const requestBodies = [];
  global.fetch = async (url, init) => {
    if (url === '/api/meeting-rooms') {
      return {
        ok: true,
        json: async () => ({ items: [{ building: 'sku-tower' }] }),
      };
    }
    if (String(url).startsWith('/api/meeting-rooms?building=sku-tower&floor=18')) {
      return {
        ok: true,
        json: async () => ({ items: [{ room_name: '1801', capacity: 8 }] }),
      };
    }
    if (String(url).startsWith('/api/meeting-rooms?building=sku-tower')) {
      return {
        ok: true,
        json: async () => ({ items: [{ floor: 18 }, { floor: 19 }] }),
      };
    }
    if (url === '/api/meeting-rooms/book') {
      requestBodies.push(JSON.parse(String(init && init.body ? init.body : '{}')));
      return {
        ok: true,
        json: async () => ({ status: 'completed', answer: '예약 완료' }),
      };
    }
    if (url === '/api/meeting-rooms/suggest-from-current-mail') {
      requestBodies.push(JSON.parse(String(init && init.body ? init.body : '{}')));
      return {
        ok: true,
        json: async () => ({
          status: 'completed',
          proposal: {
            meeting_subject: 'M365 구축 일정 논의',
            attendee_count: 4,
            time_candidates: [{ date: '2026-03-03', start_time: '10:00', end_time: '11:00', label: '2026-03-03 10:00-11:00' }],
          },
        }),
      };
    }
    if (url === '/api/calendar-events/suggest-from-current-mail') {
      requestBodies.push(JSON.parse(String(init && init.body ? init.body : '{}')));
      return {
        ok: true,
        json: async () => ({
          status: 'completed',
          proposal: {
            subject: '[일정] M365 구축 일정',
            date: '2026-03-03',
            start_time: '10:00',
            end_time: '11:00',
            attendees: ['a@example.com'],
          },
        }),
      };
    }
    if (url === '/api/calendar-events/create') {
      requestBodies.push(JSON.parse(String(init && init.body ? init.body : '{}')));
      return {
        ok: true,
        json: async () => ({ status: 'completed', answer: '일정 등록 완료', event: { id: 'evt-1' } }),
      };
    }
    return { ok: false, body: null };
  };

  const instance = api.create({
    selectionController: {},
    isCurrentMailQuery: () => false,
    logClientEvent: () => {},
    shortId: (value) => value,
  });
  const buildings = await instance.listMeetingRoomBuildings();
  const floors = await instance.listMeetingRoomFloors('sku-tower');
  const rooms = await instance.listMeetingRooms('sku-tower', 18);
  const suggestion = await instance.suggestMeetingFromCurrentMail('mail-1', 'user@example.com');
  const calendarSuggestion = await instance.suggestCalendarFromCurrentMail('mail-1', 'user@example.com');
  const booking = await instance.bookMeetingRoom({
    building: 'sku-tower',
    floor: 18,
    room_name: '1801',
    date: '2026-03-03',
    start_time: '10:00',
    end_time: '11:00',
    attendee_count: 4,
  });
  const calendar = await instance.createCalendarEvent({
    subject: '[일정] 점검 회의',
    date: '2026-03-03',
    start_time: '10:00',
    end_time: '11:00',
    attendees: ['a@example.com'],
  });

  assert.deepEqual(buildings, ['sku-tower']);
  assert.deepEqual(floors, [18, 19]);
  assert.deepEqual(rooms, [{ room_name: '1801', capacity: 8 }]);
  assert.equal(suggestion.status, 'completed');
  assert.equal(suggestion.proposal.meeting_subject, 'M365 구축 일정 논의');
  assert.equal(calendarSuggestion.status, 'completed');
  assert.equal(booking.status, 'completed');
  assert.equal(calendar.status, 'completed');
  assert.equal(requestBodies[0].message_id, 'mail-1');
  assert.equal(requestBodies[1].message_id, 'mail-1');
  assert.equal(requestBodies[2].room_name, '1801');
  assert.equal(requestBodies[3].subject, '[일정] 점검 회의');
});

test('taskpane api sends HIL confirm payload', async () => {
  const api = loadApiModule();
  const requestBodies = [];
  global.fetch = async (url, init) => {
    if (url === '/search/chat/confirm') {
      requestBodies.push(JSON.parse(String(init && init.body ? init.body : '{}')));
      return {
        ok: true,
        json: async () => ({ status: 'completed', answer: '승인 처리되었습니다.' }),
      };
    }
    return { ok: false, body: null };
  };

  const instance = api.create({
    selectionController: {},
    isCurrentMailQuery: () => false,
    logClientEvent: () => {},
    shortId: (value) => value,
  });
  const payload = await instance.requestChatConfirm({
    thread_id: 'thread-hitl-1',
    approved: true,
    confirm_token: 'interrupt-1',
    prompt_variant: 'quality_structured_json_strict',
  });

  assert.equal(payload.status, 'completed');
  assert.equal(requestBodies[0].thread_id, 'thread-hitl-1');
  assert.equal(requestBodies[0].approved, true);
  assert.equal(requestBodies[0].confirm_token, 'interrupt-1');
  assert.equal(requestBodies[0].prompt_variant, 'quality_structured_json_strict');
});

test('taskpane api reads promise/finance catalogs and submits legacy forms', async () => {
  const api = loadApiModule();
  const requestBodies = [];
  global.fetch = async (url, init) => {
    if (url === '/api/promise/projects') {
      return { ok: true, json: async () => ({ projects: [{ project_number: 'P-1' }] }) };
    }
    if (url === '/api/promise/summaries') {
      return { ok: true, json: async () => ({ items: [{ project_number: 'P-1', execution_total: 1000, final_cost_total: 1200 }] }) };
    }
    if (url === '/api/promise/projects/P-1/summary') {
      return { ok: true, json: async () => ({ project_number: 'P-1', execution_total: 1000 }) };
    }
    if (url === '/api/finance/projects') {
      return { ok: true, json: async () => ({ projects: [{ project_number: 'F-1' }] }) };
    }
    if (url === '/api/finance/projects/F-1/budget') {
      return { ok: true, json: async () => ({ project_number: 'F-1', remaining_amount: 800 }) };
    }
    if (url === '/api/promise/drafts' && String(init && init.method ? init.method : 'GET').toUpperCase() === 'GET') {
      return { ok: true, json: async () => ({ drafts: [{ project_number: 'P-1', reason: '초기 등록' }] }) };
    }
    if (url === '/api/promise/drafts' || url === '/api/finance/claims' || url === '/api/myhr/requests') {
      requestBodies.push({ url: url, body: JSON.parse(String(init && init.body ? init.body : '{}')) });
      return { ok: true, json: async () => ({ status: 'completed' }) };
    }
    return { ok: false, body: null };
  };
  const instance = api.create({
    selectionController: {},
    isCurrentMailQuery: () => false,
    logClientEvent: () => {},
    shortId: (value) => value,
  });

  const promiseProjects = await instance.listPromiseProjects();
  const promiseSummaries = await instance.listPromiseSummaries();
  const promiseSummary = await instance.getPromiseProjectSummary('P-1');
  const promiseDrafts = await instance.listPromiseDrafts();
  const financeProjects = await instance.listFinanceProjects();
  const financeBudget = await instance.getFinanceProjectBudget('F-1');
  const promiseSaved = await instance.submitPromiseDraft({ project_number: 'P-1' });
  const financeSaved = await instance.submitFinanceClaim({ project_number: 'F-1', amount: 100 });
  const hrSaved = await instance.submitHrRequest({ request_type: '휴가신청' });

  assert.equal(promiseProjects.length, 1);
  assert.equal(promiseSummaries.length, 1);
  assert.equal(promiseSummary.project_number, 'P-1');
  assert.equal(promiseDrafts.length, 1);
  assert.equal(financeProjects.length, 1);
  assert.equal(financeBudget.project_number, 'F-1');
  assert.equal(promiseSaved.status, 'completed');
  assert.equal(financeSaved.status, 'completed');
  assert.equal(hrSaved.status, 'completed');
  assert.equal(requestBodies.length, 3);
});
