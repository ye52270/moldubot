const test = require('node:test');
const assert = require('node:assert/strict');

const modulePath = '../clients/outlook-addin/taskpane.chat_actions.js';

function loadModule() {
  delete require.cache[require.resolve(modulePath)];
  return require(modulePath);
}

test('hitl confirm click shows pending status immediately', async () => {
  let clickHandler = null;
  const pendingLabels = [];
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const moduleRef = loadModule();
  const actions = moduleRef.create({
    windowRef: {},
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    chatApi: {
      requestChatConfirm: async function () {
        return { answer: '승인 처리됨', metadata: {} };
      },
    },
    messageUi: {
      showHitlConfirmPendingStatus(label) {
        pendingLabels.push(label);
      },
      disableHitlConfirmControls() {},
      addMessage() {},
    },
    state: {},
    setSendingState() {},
    handleProgress() {},
    runReportGeneration: async function () {},
    runWeeklyReportGeneration: async function () {},
    sanitizeMeetingHilMetadata(value) { return value; },
    setMeetingRoomBookingButtonLabel() {},
    buildMeetingRoomHilMessage() { return '{}'; },
  });

  actions.bindChatAreaActions();
  clickHandler({
    target: {
      closest() {
        return {
          dataset: {
            action: 'hitl-confirm-approve',
            threadId: 'thread-1',
            confirmToken: 'token-1',
            hitlActionName: 'create_outlook_todo',
          },
        };
      },
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(pendingLabels.length, 1);
  assert.equal(pendingLabels[0], '승인 처리 중입니다...');
});

test('hitl confirm ignores duplicate clicks while same token is in-flight', async () => {
  let clickHandler = null;
  let confirmCallCount = 0;
  const pendingLabels = [];
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const moduleRef = loadModule();
  const actions = moduleRef.create({
    windowRef: {},
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    chatApi: {
      requestChatConfirm: async function () {
        confirmCallCount += 1;
        await new Promise((resolve) => setTimeout(resolve, 5));
        return { answer: '승인 처리됨', metadata: {} };
      },
    },
    messageUi: {
      showHitlConfirmPendingStatus(label) {
        pendingLabels.push(label);
      },
      disableHitlConfirmControls() {},
      addMessage() {},
    },
    state: {},
    setSendingState() {},
    handleProgress() {},
    runReportGeneration: async function () {},
    runWeeklyReportGeneration: async function () {},
    sanitizeMeetingHilMetadata(value) { return value; },
    setMeetingRoomBookingButtonLabel() {},
    buildMeetingRoomHilMessage() { return '{}'; },
    buildCalendarEventHilMessage() { return '{}'; },
    openReplyCompose: async function () {},
  });

  actions.bindChatAreaActions();
  const eventPayload = {
    target: {
      closest() {
        return {
          dataset: {
            action: 'hitl-confirm-approve',
            threadId: 'thread-dup',
            confirmToken: 'token-dup',
            hitlActionName: 'create_outlook_calendar_event',
          },
        };
      },
    },
  };
  clickHandler(eventPayload);
  clickHandler(eventPayload);
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(confirmCallCount, 1);
  assert.equal(pendingLabels.length, 1);
});

test('hitl confirm todo approved shows fallback message when task id/link is missing', async () => {
  let clickHandler = null;
  const calls = {
    todoReadyCount: 0,
    assistantMessages: [],
  };
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const moduleRef = loadModule();
  const actions = moduleRef.create({
    windowRef: {},
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    chatApi: {
      requestChatConfirm: async function () {
        return {
          answer: '할 일 등록이 완료되었습니다.',
          metadata: {
            todo_task: {},
            next_actions: [{ action_id: 'search_related_mails', title: '관련 메일 추가 조회', query: 'q1' }],
          },
        };
      },
    },
    messageUi: {
      showHitlConfirmPendingStatus() {},
      disableHitlConfirmControls() {},
      addTodoReadyCard() { calls.todoReadyCount += 1; },
      addMessage(role, text) {
        if (role === 'assistant') calls.assistantMessages.push(String(text || ''));
      },
    },
    state: {},
    setSendingState() {},
    handleProgress() {},
    runReportGeneration: async function () {},
    runWeeklyReportGeneration: async function () {},
    sanitizeMeetingHilMetadata(value) { return value; },
    setMeetingRoomBookingButtonLabel() {},
    buildMeetingRoomHilMessage() { return '{}'; },
    openReplyCompose: async function () {},
  });

  actions.bindChatAreaActions();
  clickHandler({
    target: {
      closest() {
        return {
          dataset: {
            action: 'hitl-confirm-approve',
            threadId: 'thread-1',
            confirmToken: 'token-1',
            hitlActionName: 'create_outlook_todo',
          },
        };
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(calls.todoReadyCount, 0);
  assert.equal(calls.assistantMessages.length >= 1, true);
});

test('hitl confirm todo approved keeps follow-up next actions after todo ready card', async () => {
  let clickHandler = null;
  const calls = {
    todoReadyCount: 0,
    assistantMetadata: [],
  };
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const moduleRef = loadModule();
  const actions = moduleRef.create({
    windowRef: {},
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    chatApi: {
      requestChatConfirm: async function () {
        return {
          answer: '할 일 등록이 완료되었습니다.',
          metadata: {
            todo_task: { id: 'task-1', web_link: 'https://outlook.live.com/tasks/1', title: '검토', due_date: '2026-03-08' },
            next_actions: [{ action_id: 'search_related_mails', title: '관련 메일 추가 조회', query: 'q1' }],
          },
        };
      },
    },
    messageUi: {
      showHitlConfirmPendingStatus() {},
      disableHitlConfirmControls() {},
      addTodoReadyCard() { calls.todoReadyCount += 1; },
      addMessage(_role, _text, metadata) {
        calls.assistantMetadata.push(metadata || {});
      },
    },
    state: {},
    setSendingState() {},
    handleProgress() {},
    runReportGeneration: async function () {},
    runWeeklyReportGeneration: async function () {},
    sanitizeMeetingHilMetadata(value) { return value; },
    setMeetingRoomBookingButtonLabel() {},
    buildMeetingRoomHilMessage() { return '{}'; },
    openReplyCompose: async function () {},
  });

  actions.bindChatAreaActions();
  clickHandler({
    target: {
      closest() {
        return {
          dataset: {
            action: 'hitl-confirm-approve',
            threadId: 'thread-1',
            confirmToken: 'token-1',
            hitlActionName: 'create_outlook_todo',
          },
        };
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(calls.todoReadyCount, 1);
  assert.equal(calls.assistantMetadata.length >= 1, true);
  const nextActionsMeta = calls.assistantMetadata.find((item) => Array.isArray(item.next_actions));
  assert.equal(Boolean(nextActionsMeta), true);
  assert.equal(nextActionsMeta.next_actions.length, 1);
  assert.equal(nextActionsMeta.next_actions[0].action_id, 'search_related_mails');
});

test('calendar submit routes through assistant HIL path instead of direct calendar API', async () => {
  let clickHandler = null;
  const calls = {
    requestMessage: '',
    runtimeOptions: null,
    metadata: null,
  };
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const moduleRef = loadModule();
  const actions = moduleRef.create({
    windowRef: {},
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    chatApi: {
      requestAssistantReply: async function (message, _onProgress, runtimeOptions) {
        calls.requestMessage = String(message || '');
        calls.runtimeOptions = runtimeOptions || null;
        return {
          answer: '회의실/일정/ToDo 실행 전 승인 확인이 필요합니다.',
          metadata: {
            confirm: { required: true, thread_id: 'thread-1', confirm_token: 'token-1' },
          },
        };
      },
      createCalendarEvent: async function () {
        throw new Error('createCalendarEvent should not be called');
      },
    },
    messageUi: {
      getCalendarEventFormValues() {
        return {
          subject: '[일정] Tenant Restriction 방안',
          date: '2026-03-10',
          start_time: '10:00',
          end_time: '11:00',
          attendees: ['kim@example.com'],
          body: '회의 본문',
        };
      },
      disableCalendarEventControls() {},
      addMessage(_role, _text, metadata) {
        calls.metadata = metadata || {};
      },
    },
    state: { pendingCalendarContext: { sourceQuery: '현재메일 일정 등록' } },
    setSendingState() {},
    handleProgress() {},
    runReportGeneration: async function () {},
    runWeeklyReportGeneration: async function () {},
    sanitizeMeetingHilMetadata(value) { return value; },
    setMeetingRoomBookingButtonLabel() {},
    buildMeetingRoomHilMessage() { return '{}'; },
    buildCalendarEventHilMessage() { return 'task=create_outlook_calendar_event'; },
    openReplyCompose: async function () {},
  });

  actions.bindChatAreaActions();
  clickHandler({
    target: {
      closest() {
        return { dataset: { action: 'calendar-event-submit' } };
      },
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(calls.requestMessage.includes('create_outlook_calendar_event'), true);
  assert.deepEqual(calls.runtimeOptions, { calendar_event_hil: true });
  assert.equal(Boolean(calls.metadata.confirm && calls.metadata.confirm.required), true);
});

test('promise detail back action restores list step', async () => {
  let clickHandler = null;
  const calls = {
    step: [],
    summary: [],
    cleared: 0,
  };
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const moduleRef = loadModule();
  const actions = moduleRef.create({
    windowRef: {},
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    chatApi: {},
    messageUi: {
      setPromiseViewStep(step) {
        calls.step.push(step);
      },
      setPromiseSummaryText(text) {
        calls.summary.push(text);
      },
      clearPromiseMonthlyBreakdown() {
        calls.cleared += 1;
      },
      addMessage() {},
    },
    state: {},
    setSendingState() {},
    handleProgress() {},
    runReportGeneration: async function () {},
    runWeeklyReportGeneration: async function () {},
    sanitizeMeetingHilMetadata(value) { return value; },
    setMeetingRoomBookingButtonLabel() {},
    buildMeetingRoomHilMessage() { return '{}'; },
  });

  actions.bindChatAreaActions();
  clickHandler({
    target: {
      closest() {
        return {
          dataset: {
            action: 'promise-detail-back',
          },
        };
      },
    },
  });

  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(calls.step, ['list']);
  assert.equal(calls.summary[0], '목록에서 실행예산 항목을 선택해 주세요.');
  assert.equal(calls.cleared, 1);
});

test('meeting room candidate/time selection updates schedule form values', async () => {
  let changeHandler = null;
  const dateInput = { value: '2026-03-04' };
  const startInput = { value: '10:00' };
  const endInput = { value: '11:00' };
  const buildingInput = { value: 'sku-tower' };
  const floorInput = { value: '17' };
  const roomInput = { value: '1702-A' };
  const roomDisplayInput = { value: 'sku-tower 17층 1702-A' };
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'change') changeHandler = handler;
    },
    querySelector(selector) {
      if (selector === '[data-role="meeting-date-input"]') return dateInput;
      if (selector === '[data-role="meeting-start-input"]') return startInput;
      if (selector === '[data-role="meeting-end-input"]') return endInput;
      if (selector === '[data-role="meeting-building-select"]') return buildingInput;
      if (selector === '[data-role="meeting-floor-select"]') return floorInput;
      if (selector === '[data-role="meeting-room-select"]') return roomInput;
      if (selector === '[data-role="meeting-room-display"]') return roomDisplayInput;
      return null;
    },
  };
  const state = {
    pendingMeetingRoomContext: {
      selectedBuilding: 'sku-tower',
      selectedFloor: 17,
      selectedRoom: '1702-A',
    },
  };
  const moduleRef = loadModule();
  const actions = moduleRef.create({
    windowRef: {},
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    chatApi: {},
    messageUi: {
      addMessage() {},
    },
    state: state,
    setSendingState() {},
    handleProgress() {},
    runReportGeneration: async function () {},
    runWeeklyReportGeneration: async function () {},
    sanitizeMeetingHilMetadata(value) { return value; },
    setMeetingRoomBookingButtonLabel() {},
    buildMeetingRoomHilMessage() { return '{}'; },
  });

  actions.bindChatAreaActions();
  changeHandler({
    target: {
      dataset: { action: 'meeting-room-time-candidate-change' },
      value: '2026-03-04|14:00|15:00',
    },
  });
  assert.equal(dateInput.value, '2026-03-04');
  assert.equal(startInput.value, '14:00');
  assert.equal(endInput.value, '15:00');

  changeHandler({
    target: {
      dataset: { action: 'meeting-room-candidate-change' },
      value: 'sku-tower|17|1705',
    },
  });
  assert.equal(buildingInput.value, 'sku-tower');
  assert.equal(floorInput.value, '17');
  assert.equal(roomInput.value, '1705');
  assert.equal(roomDisplayInput.value, 'sku-tower 17층 1705');
  assert.equal(state.pendingMeetingRoomContext.selectedRoom, '1705');
});

test('next action run sends follow-up query and renders assistant reply', async () => {
  let clickHandler = null;
  const calls = {
    userMessages: [],
    assistantMessages: [],
    requestedQuery: '',
    runtimeOptions: null,
  };
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const state = {
    isSendingRef() { return false; },
  };
  const moduleRef = loadModule();
  const actions = moduleRef.create({
    windowRef: {},
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    chatApi: {
      requestAssistantReply: async function (query, _onProgress, runtimeOptions) {
        calls.requestedQuery = String(query || '');
        calls.runtimeOptions = runtimeOptions || null;
        return { answer: '후속 응답', metadata: { source: 'deep-agent' } };
      },
    },
    messageUi: {
      addMessage(role, text) {
        if (role === 'user') calls.userMessages.push(String(text || ''));
        if (role === 'assistant') calls.assistantMessages.push(String(text || ''));
      },
      showThinkingIndicator() {},
      clearThinkingIndicator() {},
      clearProgressStatus() {},
    },
    state: state,
    setSendingState() {},
    handleProgress() {},
    runReportGeneration: async function () {},
    runWeeklyReportGeneration: async function () {},
    sanitizeMeetingHilMetadata(value) { return value; },
    setMeetingRoomBookingButtonLabel() {},
    buildMeetingRoomHilMessage() { return '{}'; },
    openReplyCompose: async function () {},
  });

  actions.bindChatAreaActions();
  clickHandler({
    target: {
      closest() {
        return {
          dataset: {
            action: 'next-action-run',
            actionId: 'search_related_mails',
            query: '이 주제 관련 메일 최근순으로 5개 조회해줘',
          },
        };
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(calls.requestedQuery, '이 주제 관련 메일 최근순으로 5개 조회해줘');
  assert.equal(calls.runtimeOptions.next_action_id, 'search_related_mails');
  assert.deepEqual(calls.userMessages, ['이 주제 관련 메일 최근순으로 5개 조회해줘']);
  assert.deepEqual(calls.assistantMessages, ['후속 응답']);
});

test('next action run marks executed action and filters duplicated next action from metadata', async () => {
  let clickHandler = null;
  const calls = {
    marked: [],
    assistantMetadata: null,
  };
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const state = {
    executed: {},
    isSendingRef() { return false; },
    markNextActionExecuted(actionId) {
      const normalized = String(actionId || '').toLowerCase();
      this.executed[normalized] = true;
      calls.marked.push(normalized);
    },
    filterNextActionsMetadata(metadata) {
      const source = metadata && typeof metadata === 'object' ? metadata : {};
      const actions = Array.isArray(source.next_actions) ? source.next_actions : [];
      const filtered = actions.filter((item) => !this.executed[String(item.action_id || '').toLowerCase()]);
      const next = Object.assign({}, source);
      next.next_actions = filtered;
      return next;
    },
  };
  const moduleRef = loadModule();
  const actions = moduleRef.create({
    windowRef: {},
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    chatApi: {
      requestAssistantReply: async function () {
        return {
          answer: '후속 응답',
          metadata: {
            next_actions: [
              { action_id: 'search_related_mails', title: '관련 메일 추가 조회', query: 'q1' },
              { action_id: 'create_todo', title: '할 일(ToDo) 등록', query: 'q2' },
            ],
          },
        };
      },
    },
    messageUi: {
      addMessage(role, _text, metadata) {
        if (role === 'assistant') calls.assistantMetadata = metadata;
      },
      clearProgressStatus() {},
    },
    state: state,
    setSendingState() {},
    handleProgress() {},
    runReportGeneration: async function () {},
    runWeeklyReportGeneration: async function () {},
    sanitizeMeetingHilMetadata(value) { return value; },
    setMeetingRoomBookingButtonLabel() {},
    buildMeetingRoomHilMessage() { return '{}'; },
    openReplyCompose: async function () {},
  });

  actions.bindChatAreaActions();
  clickHandler({
    target: {
      closest() {
        return {
          dataset: {
            action: 'next-action-run',
            actionId: 'search_related_mails',
            query: '이 주제 관련 메일 최근순으로 5개 조회해줘',
          },
        };
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(calls.marked, ['search_related_mails']);
  assert.equal(Array.isArray(calls.assistantMetadata.next_actions), true);
  assert.equal(calls.assistantMetadata.next_actions.length, 1);
  assert.equal(calls.assistantMetadata.next_actions[0].action_id, 'create_todo');
});

test('todo next action always sends skip_intent_clarification runtime option', async () => {
  let clickHandler = null;
  const calls = {
    runtimeOptions: null,
  };
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const state = {
    isSendingRef() { return false; },
    markNextActionExecuted() {},
    filterNextActionsMetadata(metadata) { return metadata; },
  };
  const moduleRef = loadModule();
  const actions = moduleRef.create({
    windowRef: {},
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    chatApi: {
      requestAssistantReply: async function (_query, _onProgress, runtimeOptions) {
        calls.runtimeOptions = runtimeOptions || null;
        return { answer: '후속 응답', metadata: {} };
      },
    },
    messageUi: {
      addMessage() {},
      clearProgressStatus() {},
    },
    state: state,
    setSendingState() {},
    handleProgress() {},
    runReportGeneration: async function () {},
    runWeeklyReportGeneration: async function () {},
    sanitizeMeetingHilMetadata(value) { return value; },
    setMeetingRoomBookingButtonLabel() {},
    buildMeetingRoomHilMessage() { return '{}'; },
    openReplyCompose: async function () {},
  });

  actions.bindChatAreaActions();
  clickHandler({
    target: {
      closest() {
        return {
          dataset: {
            action: 'next-action-run',
            actionId: 'create_todo',
            title: '할 일(ToDo) 등록',
            query: '현재메일 기반으로 조치 필요 사항을 ToDo로 등록해줘',
          },
        };
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(Boolean(calls.runtimeOptions), true);
  assert.equal(calls.runtimeOptions.next_action_id, 'create_todo');
  assert.equal(calls.runtimeOptions.skip_intent_clarification, true);
});

test('reply draft next action attaches reply button metadata', async () => {
  let clickHandler = null;
  const calls = {
    assistantMetadata: null,
    runtimeOptions: null,
    requestedQuery: '',
  };
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const state = {
    isSendingRef() { return false; },
  };
  const moduleRef = loadModule();
  const actions = moduleRef.create({
    windowRef: {},
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    chatApi: {
      requestAssistantReply: async function (_query, _onProgress, runtimeOptions) {
        calls.requestedQuery = String(_query || '');
        calls.runtimeOptions = runtimeOptions || null;
        return { answer: '회신 초안 본문입니다.', metadata: { source: 'deep-agent' } };
      },
    },
    messageUi: {
      addMessage(role, _text, metadata) {
        if (role === 'assistant') calls.assistantMetadata = metadata;
      },
      showThinkingIndicator() {},
      clearThinkingIndicator() {},
      clearProgressStatus() {},
    },
    state: state,
    setSendingState() {},
    handleProgress() {},
    runReportGeneration: async function () {},
    runWeeklyReportGeneration: async function () {},
    sanitizeMeetingHilMetadata(value) { return value; },
    setMeetingRoomBookingButtonLabel() {},
    buildMeetingRoomHilMessage() { return '{}'; },
    openReplyCompose: async function () {},
  });

  actions.bindChatAreaActions();
  clickHandler({
    target: {
      closest() {
        return {
          dataset: {
            action: 'next-action-run',
            actionId: 'draft_reply',
            title: '회신 초안 작성',
            query: '현재메일 기준으로 회신 초안 작성해줘',
          },
        };
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(calls.requestedQuery, '');
  assert.equal(calls.runtimeOptions, null);
  assert.equal(Boolean(calls.assistantMetadata && calls.assistantMetadata.reply_tone_picker), true);
  assert.equal(calls.assistantMetadata.reply_tone_picker.enabled, true);
  assert.equal(calls.assistantMetadata.reply_tone_picker.base_query, '현재메일 기준으로 회신 초안 작성해줘');
});

test('reply draft next action does not attach button for clarifying question response', async () => {
  let clickHandler = null;
  const calls = {
    assistantMetadata: null,
    runtimeOptions: null,
  };
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const state = {
    isSendingRef() { return false; },
  };
  const moduleRef = loadModule();
  const actions = moduleRef.create({
    windowRef: {},
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    chatApi: {
      requestAssistantReply: async function (_query, _onProgress, runtimeOptions) {
        calls.runtimeOptions = runtimeOptions || null;
        return {
          answer: '회신의 주요 포인트나 강조하고 싶은 부분이 있으신가요?',
          metadata: { source: 'deep-agent' },
        };
      },
    },
    messageUi: {
      addMessage(role, _text, metadata) {
        if (role === 'assistant') calls.assistantMetadata = metadata;
      },
      showThinkingIndicator() {},
      clearThinkingIndicator() {},
      clearProgressStatus() {},
    },
    state: state,
    setSendingState() {},
    handleProgress() {},
    runReportGeneration: async function () {},
    runWeeklyReportGeneration: async function () {},
    sanitizeMeetingHilMetadata(value) { return value; },
    setMeetingRoomBookingButtonLabel() {},
    buildMeetingRoomHilMessage() { return '{}'; },
    openReplyCompose: async function () {},
  });

  actions.bindChatAreaActions();
  clickHandler({
    target: {
      closest() {
        return {
          dataset: {
            action: 'next-action-run',
            actionId: 'draft_reply',
            title: '회신 초안 작성',
            query: '현재메일 기준으로 회신 초안 작성해줘',
          },
        };
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(Boolean(calls.assistantMetadata && calls.assistantMetadata.reply_tone_picker), true);
  assert.equal(calls.runtimeOptions, null);
});

test('reply draft open button invokes outlook reply compose callback', async () => {
  let clickHandler = null;
  const calls = { openedBody: '' };
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const moduleRef = loadModule();
  const actions = moduleRef.create({
    windowRef: {},
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    chatApi: {},
    messageUi: {
      addMessage() {},
    },
    state: {},
    setSendingState() {},
    handleProgress() {},
    runReportGeneration: async function () {},
    runWeeklyReportGeneration: async function () {},
    sanitizeMeetingHilMetadata(value) { return value; },
    setMeetingRoomBookingButtonLabel() {},
    buildMeetingRoomHilMessage() { return '{}'; },
    openReplyCompose: async function (body) {
      calls.openedBody = String(body || '');
    },
  });

  actions.bindChatAreaActions();
  clickHandler({
    target: {
      closest() {
        return {
          dataset: {
            action: 'reply-draft-open',
            draftBody: '초안 본문',
          },
        };
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(calls.openedBody, '초안 본문');
});

test('reply tone generate sends tone-constrained query and attaches reply button metadata', async () => {
  let clickHandler = null;
  const calls = {
    requestedQuery: '',
    runtimeOptions: null,
    assistantMetadata: null,
  };
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const moduleRef = loadModule();
  const actions = moduleRef.create({
    windowRef: {},
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    chatApi: {
      requestAssistantReply: async function (query, _onProgress, runtimeOptions) {
        calls.requestedQuery = String(query || '');
        calls.runtimeOptions = runtimeOptions || null;
        return { answer: '회신 초안 본문입니다.', metadata: {} };
      },
    },
    messageUi: {
      addMessage(role, _text, metadata) {
        if (role === 'assistant') calls.assistantMetadata = metadata;
      },
      clearProgressStatus() {},
    },
    state: {},
    setSendingState() {},
    handleProgress() {},
    runReportGeneration: async function () {},
    runWeeklyReportGeneration: async function () {},
    sanitizeMeetingHilMetadata(value) { return value; },
    setMeetingRoomBookingButtonLabel() {},
    buildMeetingRoomHilMessage() { return '{}'; },
    openReplyCompose: async function () {},
  });

  actions.bindChatAreaActions();
  clickHandler({
    target: {
      closest() {
        return {
          dataset: {
            action: 'reply-tone-generate',
            tone: 'concise',
            baseQuery: '현재메일 기준으로 바로 보낼 수 있는 회신 메일 본문 초안을 작성해줘',
          },
        };
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(calls.requestedQuery.includes('간결하고 핵심만 전달하는 비즈니스 톤'), true);
  assert.equal(calls.runtimeOptions.skip_intent_clarification, true);
  assert.equal(Boolean(calls.assistantMetadata && calls.assistantMetadata.reply_draft), true);
});

test('reply tone generate retries once when first response is clarifying question', async () => {
  let clickHandler = null;
  const calls = {
    requestedQueries: [],
    assistantMetadata: null,
  };
  const chatArea = {
    addEventListener(eventName, handler) {
      if (eventName === 'click') clickHandler = handler;
    },
  };
  const moduleRef = loadModule();
  const actions = moduleRef.create({
    windowRef: {},
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    chatApi: {
      requestAssistantReply: async function (query) {
        calls.requestedQueries.push(String(query || ''));
        if (calls.requestedQueries.length === 1) {
          return { answer: '회신에 어떤 내용을 포함할까요?', metadata: {} };
        }
        return { answer: '안녕하세요. 요청하신 회신 본문입니다.', metadata: {} };
      },
    },
    messageUi: {
      addMessage(role, _text, metadata) {
        if (role === 'assistant') calls.assistantMetadata = metadata;
      },
      clearProgressStatus() {},
    },
    state: {},
    setSendingState() {},
    handleProgress() {},
    runReportGeneration: async function () {},
    runWeeklyReportGeneration: async function () {},
    sanitizeMeetingHilMetadata(value) { return value; },
    setMeetingRoomBookingButtonLabel() {},
    buildMeetingRoomHilMessage() { return '{}'; },
    openReplyCompose: async function () {},
  });

  actions.bindChatAreaActions();
  clickHandler({
    target: {
      closest() {
        return {
          dataset: {
            action: 'reply-tone-generate',
            tone: 'neutral',
            baseQuery: '현재메일 기준으로 바로 보낼 수 있는 회신 메일 본문 초안을 작성해줘',
          },
        };
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(calls.requestedQueries.length, 2);
  assert.equal(calls.requestedQueries[1].includes('절대 추가 질문하지 말고'), true);
  assert.equal(Boolean(calls.assistantMetadata && calls.assistantMetadata.reply_draft), true);
});
