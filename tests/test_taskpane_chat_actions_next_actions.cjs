const test = require('node:test');
const assert = require('node:assert/strict');

const modulePath = '../clients/outlook-addin/taskpane.chat_actions.next_actions.js';

function loadModule() {
  delete require.cache[require.resolve(modulePath)];
  return require(modulePath);
}

test('next actions module: handleReplyDraftOpen reports unsupported environment', async () => {
  const moduleRef = loadModule();
  const assistantMessages = [];
  const api = moduleRef.create({
    chatApi: {},
    messageUi: {
      addMessage(role, text) {
        if (role === 'assistant') assistantMessages.push(String(text || ''));
      },
    },
    state: {},
    setSendingState() {},
    handleProgress() {},
    focusInput() {},
  });

  api.handleReplyDraftOpen({
    dataset: {
      action: 'reply-draft-open',
      draftBody: '본문',
    },
  });

  assert.equal(assistantMessages.length, 1);
  assert.equal(assistantMessages[0], '현재 환경에서는 답장 창 열기를 지원하지 않습니다.');
});

test('next actions module: reply tone generate appends formal directive', async () => {
  const moduleRef = loadModule();
  const capturedQueries = [];
  const assistantMessages = [];
  const api = moduleRef.create({
    chatApi: {
      requestAssistantReply: async function (query) {
        capturedQueries.push(String(query || ''));
        return { answer: '회신 초안 본문', metadata: {} };
      },
    },
    messageUi: {
      addMessage(role, text) {
        if (role === 'assistant') assistantMessages.push(String(text || ''));
      },
      clearProgressStatus() {},
    },
    state: {
      isSendingRef() { return false; },
      markNextActionExecuted() {},
      filterNextActionsMetadata(value) { return value; },
    },
    setSendingState() {},
    handleProgress() {},
    focusInput() {},
  });

  await api.handleReplyToneGenerate({
    dataset: {
      baseQuery: '현재메일 회신 초안 만들어줘',
      tone: 'formal',
    },
  });

  assert.equal(capturedQueries.length >= 1, true);
  assert.equal(capturedQueries[0].includes('공손하고 정중한 비즈니스 회신 톤'), true);
  assert.equal(assistantMessages.includes('회신 초안 본문'), true);
});

test('next actions module: todo next action sets skip_intent_clarification', async () => {
  const moduleRef = loadModule();
  const runtimeOptionsCalls = [];
  const api = moduleRef.create({
    chatApi: {
      requestAssistantReply: async function (_query, _progress, runtimeOptions) {
        runtimeOptionsCalls.push(runtimeOptions || null);
        return { answer: '처리 완료', metadata: {} };
      },
    },
    messageUi: {
      addMessage() {},
      clearProgressStatus() {},
    },
    state: {
      isSendingRef() { return false; },
      markNextActionExecuted() {},
      filterNextActionsMetadata(value) { return value; },
    },
    setSendingState() {},
    handleProgress() {},
    focusInput() {},
  });

  await api.handleNextActionRun({
    dataset: {
      actionId: 'create_todo',
      query: '현재메일 조치사항 todo 등록',
      title: 'Outlook 할 일 등록',
    },
  });

  assert.equal(runtimeOptionsCalls.length, 1);
  assert.equal(Boolean(runtimeOptionsCalls[0] && runtimeOptionsCalls[0].skip_intent_clarification), true);
});
