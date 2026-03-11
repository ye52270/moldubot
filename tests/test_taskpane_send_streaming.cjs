const test = require('node:test');
const assert = require('node:assert/strict');

const sendModulePath = '../clients/outlook-addin/taskpane.send.js';

function loadSendModule() {
  global.window = {};
  delete require.cache[require.resolve(sendModulePath)];
  return require(sendModulePath);
}

test('taskpane send renders final assistant message without streaming preview dependency', async () => {
  const sendModule = loadSendModule();
  const calls = [];
  const toastCalls = [];
  const inputNode = {
    value: '현재메일 요약',
    focus() {},
  };

  const sender = sendModule.create({
    byId: (id) => (id === 'chatInput' ? inputNode : null),
    chatApi: {
      requestAssistantReply: async () => ({ answer: '최종 응답', metadata: { elapsed_ms: 120 } }),
    },
    messageUi: {
      addMessage: (role, text) => calls.push(['addMessage', role, text]),
      clearClarificationToast: () => toastCalls.push('clear'),
      showClarificationToast: () => toastCalls.push('show'),
      addElapsedDivider: () => calls.push(['addElapsedDivider']),
      setProgressStatus: () => {},
      clearProgressStatus: () => {},
      setSendingState: () => {},
      addMeetingRoomBuildingCard: () => {},
      addMeetingRoomScheduleCard: () => {},
      addCalendarEventCard: () => {},
      addPromiseBudgetCard: () => {},
      addFinanceSettlementCard: () => {},
      setFinanceBudgetText: () => {},
      addHrApplyCard: () => {},
      addReportConfirmCard: () => {},
      addWeeklyReportConfirmCard: () => {},
    },
    state: {
      isSendingRef: () => false,
      setProgressShownAtMs: () => {},
      pendingReportContext: null,
      pendingWeeklyReportContext: null,
      pendingMeetingRoomContext: null,
      pendingCalendarContext: null,
      pendingPromiseContext: null,
      pendingFinanceContext: null,
      pendingHrContext: null,
    },
    handleProgress: () => {},
    selectionController: {
      getSelectionContext: async () => ({ emailId: '', mailboxUser: '' }),
    },
    setSendingState: () => {},
    clearProgressWithMinimumVisibility: () => {},
    logClientEvent: () => {},
    isReportGenerationQuery: () => false,
    isWeeklyReportGenerationQuery: () => false,
    isMeetingRoomBookingQuery: () => false,
    isCurrentMailMeetingRoomSuggestionQuery: () => false,
    isCalendarEventQuery: () => false,
    isCurrentMailCalendarSuggestionQuery: () => false,
    isPromiseBudgetQuery: () => false,
    isFinanceSettlementQuery: () => false,
    isHrApplyQuery: () => false,
    buildMeetingRoomHilMessage: () => '{}',
  });

  await sender.sendMessage();

  assert.equal(calls.some((item) => item[0] === 'addMessage' && item[1] === 'assistant' && item[2] === '최종 응답'), true);
  assert.equal(calls.some((item) => item[0] === 'addElapsedDivider'), true);
  assert.deepEqual(toastCalls, ['clear', 'show']);
});

test('taskpane send applies state next-action filter before rendering assistant metadata', async () => {
  const sendModule = loadSendModule();
  const calls = { assistantMetadata: null };
  const inputNode = {
    value: '현재메일 요약',
    focus() {},
  };

  const sender = sendModule.create({
    byId: (id) => (id === 'chatInput' ? inputNode : null),
    chatApi: {
      requestAssistantReply: async () => ({
        answer: '최종 응답',
        metadata: {
          next_actions: [
            { action_id: 'draft_reply', title: '회신 초안 작성', query: 'q1' },
            { action_id: 'create_todo', title: '할 일(ToDo) 등록', query: 'q2' },
          ],
        },
      }),
    },
    messageUi: {
      addMessage: (role, _text, metadata) => {
        if (role === 'assistant') calls.assistantMetadata = metadata;
      },
      addElapsedDivider: () => {},
      setProgressStatus: () => {},
      clearProgressStatus: () => {},
      setSendingState: () => {},
      addMeetingRoomBuildingCard: () => {},
      addMeetingRoomScheduleCard: () => {},
      addCalendarEventCard: () => {},
      addPromiseBudgetCard: () => {},
      addFinanceSettlementCard: () => {},
      setFinanceBudgetText: () => {},
      addHrApplyCard: () => {},
      addReportConfirmCard: () => {},
      addWeeklyReportConfirmCard: () => {},
    },
    state: {
      isSendingRef: () => false,
      setProgressShownAtMs: () => {},
      filterNextActionsMetadata: (metadata) => {
        const next = Object.assign({}, metadata || {});
        next.next_actions = (Array.isArray(next.next_actions) ? next.next_actions : [])
          .filter((item) => String(item.action_id || '') !== 'draft_reply');
        return next;
      },
      pendingReportContext: null,
      pendingWeeklyReportContext: null,
      pendingMeetingRoomContext: null,
      pendingCalendarContext: null,
      pendingPromiseContext: null,
      pendingFinanceContext: null,
      pendingHrContext: null,
    },
    handleProgress: () => {},
    selectionController: {
      getSelectionContext: async () => ({ emailId: '', mailboxUser: '' }),
    },
    setSendingState: () => {},
    clearProgressWithMinimumVisibility: () => {},
    logClientEvent: () => {},
    isReportGenerationQuery: () => false,
    isWeeklyReportGenerationQuery: () => false,
    isMeetingRoomBookingQuery: () => false,
    isCurrentMailMeetingRoomSuggestionQuery: () => false,
    isCalendarEventQuery: () => false,
    isCurrentMailCalendarSuggestionQuery: () => false,
    isPromiseBudgetQuery: () => false,
    isFinanceSettlementQuery: () => false,
    isHrApplyQuery: () => false,
    buildMeetingRoomHilMessage: () => '{}',
  });

  await sender.sendMessage();

  assert.equal(Array.isArray(calls.assistantMetadata.next_actions), true);
  assert.equal(calls.assistantMetadata.next_actions.length, 1);
  assert.equal(calls.assistantMetadata.next_actions[0].action_id, 'create_todo');
});

test('taskpane send updates streaming assistant preview and finalizes message', async () => {
  const sendModule = loadSendModule();
  const calls = [];
  const inputNode = {
    value: '수신실패 주소 알려줘',
    focus() {},
  };

  const sender = sendModule.create({
    byId: (id) => (id === 'chatInput' ? inputNode : null),
    chatApi: {
      requestAssistantReply: async (_message, _onProgress, _runtimeOptions, onToken) => {
        if (typeof onToken === 'function') {
          onToken({ text: '수신실패 ' });
          onToken({ text: '주소는 A@B.COM' });
        }
        return { answer: '수신실패 주소는 A@B.COM 입니다.', metadata: { elapsed_ms: 88 } };
      },
    },
    messageUi: {
      addMessage: (role, text) => calls.push(['addMessage', role, text]),
      beginStreamingAssistantMessage: (text) => calls.push(['begin', text]),
      updateStreamingAssistantMessage: (text) => calls.push(['update', text]),
      finalizeStreamingAssistantMessage: (text) => calls.push(['finalize', text]),
      cancelStreamingAssistantMessage: () => calls.push(['cancel']),
      clearClarificationToast: () => {},
      showClarificationToast: () => {},
      addElapsedDivider: () => calls.push(['elapsed']),
      setProgressStatus: () => {},
      clearProgressStatus: () => {},
      setSendingState: () => {},
      addMeetingRoomBuildingCard: () => {},
      addMeetingRoomScheduleCard: () => {},
      addCalendarEventCard: () => {},
      addPromiseBudgetCard: () => {},
      addFinanceSettlementCard: () => {},
      setFinanceBudgetText: () => {},
      addHrApplyCard: () => {},
      addReportConfirmCard: () => {},
      addWeeklyReportConfirmCard: () => {},
    },
    state: {
      isSendingRef: () => false,
      setProgressShownAtMs: () => {},
      pendingReportContext: null,
      pendingWeeklyReportContext: null,
      pendingMeetingRoomContext: null,
      pendingCalendarContext: null,
      pendingPromiseContext: null,
      pendingFinanceContext: null,
      pendingHrContext: null,
    },
    handleProgress: () => {},
    selectionController: {
      getSelectionContext: async () => ({ emailId: '', mailboxUser: '' }),
    },
    setSendingState: () => {},
    clearProgressWithMinimumVisibility: () => {},
    logClientEvent: () => {},
    isReportGenerationQuery: () => false,
    isWeeklyReportGenerationQuery: () => false,
    isMeetingRoomBookingQuery: () => false,
    isCurrentMailMeetingRoomSuggestionQuery: () => false,
    isCalendarEventQuery: () => false,
    isCurrentMailCalendarSuggestionQuery: () => false,
    isPromiseBudgetQuery: () => false,
    isFinanceSettlementQuery: () => false,
    isHrApplyQuery: () => false,
    buildMeetingRoomHilMessage: () => '{}',
  });

  await sender.sendMessage();

  assert.equal(calls.some((item) => item[0] === 'begin'), true);
  assert.equal(calls.some((item) => item[0] === 'update' && item[1] === '수신실패 주소는 A@B.COM'), true);
  assert.equal(calls.some((item) => item[0] === 'finalize' && item[1] === '수신실패 주소는 A@B.COM 입니다.'), true);
  assert.equal(calls.some((item) => item[0] === 'addMessage' && item[1] === 'assistant'), false);
});

test('taskpane send hides leading shortcut tokens in user bubble but keeps raw request payload', async () => {
  const sendModule = loadSendModule();
  const calls = [];
  let requestedMessage = '';
  const inputNode = {
    value: '/메일요약 @회의실 현재 메일 요약해줘',
    focus() {},
  };

  const sender = sendModule.create({
    byId: (id) => (id === 'chatInput' ? inputNode : null),
    chatApi: {
      requestAssistantReply: async (message) => {
        requestedMessage = String(message || '');
        return { answer: '요약 완료', metadata: { elapsed_ms: 30 } };
      },
    },
    messageUi: {
      addMessage: (role, text) => calls.push([role, text]),
      clearClarificationToast: () => {},
      showClarificationToast: () => {},
      addElapsedDivider: () => {},
      setProgressStatus: () => {},
      clearProgressStatus: () => {},
      setSendingState: () => {},
      addMeetingRoomBuildingCard: () => {},
      addMeetingRoomScheduleCard: () => {},
      addCalendarEventCard: () => {},
      addPromiseBudgetCard: () => {},
      addFinanceSettlementCard: () => {},
      setFinanceBudgetText: () => {},
      addHrApplyCard: () => {},
      addReportConfirmCard: () => {},
      addWeeklyReportConfirmCard: () => {},
    },
    state: {
      isSendingRef: () => false,
      setProgressShownAtMs: () => {},
      pendingReportContext: null,
      pendingWeeklyReportContext: null,
      pendingMeetingRoomContext: null,
      pendingCalendarContext: null,
      pendingPromiseContext: null,
      pendingFinanceContext: null,
      pendingHrContext: null,
    },
    handleProgress: () => {},
    selectionController: {
      getSelectionContext: async () => ({ emailId: '', mailboxUser: '' }),
    },
    setSendingState: () => {},
    clearProgressWithMinimumVisibility: () => {},
    logClientEvent: () => {},
    isReportGenerationQuery: () => false,
    isWeeklyReportGenerationQuery: () => false,
    isMeetingRoomBookingQuery: () => false,
    isCurrentMailMeetingRoomSuggestionQuery: () => false,
    isCalendarEventQuery: () => false,
    isCurrentMailCalendarSuggestionQuery: () => false,
    isPromiseBudgetQuery: () => false,
    isFinanceSettlementQuery: () => false,
    isHrApplyQuery: () => false,
    buildMeetingRoomHilMessage: () => '{}',
  });

  await sender.sendMessage();

  assert.equal(calls.some((item) => item[0] === 'user' && item[1] === '현재 메일 요약해줘'), true);
  assert.equal(requestedMessage, '/메일요약 @회의실 현재 메일 요약해줘');
});
