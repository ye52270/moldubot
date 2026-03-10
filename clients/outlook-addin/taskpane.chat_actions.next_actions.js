/* ========================================
   MolduBot – Taskpane Next Action Helpers
   ======================================== */

(function initTaskpaneChatActionNextActions(global) {
  function create(options) {
    const chatApi = options.chatApi;
    const messageUi = options.messageUi;
    const state = options.state;
    const setSendingState = options.setSendingState;
    const handleProgress = options.handleProgress;
    const openReplyCompose = options.openReplyCompose;
    const focusInput = options.focusInput;

    function hasDraftLikeMarkers(text) {
      const normalized = String(text || '').trim();
      if (!normalized) return false;
      return (
        normalized.indexOf('안녕하세요') >= 0 ||
        normalized.indexOf('안녕하십니까') >= 0 ||
        normalized.indexOf('드립니다') >= 0 ||
        normalized.indexOf('감사합니다') >= 0 ||
        normalized.indexOf('드림') >= 0
      );
    }

    function isClarifyingQuestion(text) {
      const normalized = String(text || '').trim();
      if (!normalized) return false;
      if (hasDraftLikeMarkers(normalized)) return false;
      return (
        /[?？]/.test(normalized) ||
        normalized.indexOf('원하시나요') >= 0 ||
        normalized.indexOf('있으신가요') >= 0 ||
        normalized.indexOf('필요하신가요') >= 0 ||
        normalized.indexOf('알려주시') >= 0 ||
        normalized.indexOf('확인해보고자 합니다') >= 0
      );
    }

    function normalizeReplyTone(rawTone) {
      const tone = String(rawTone || '').trim().toLowerCase();
      if (tone === 'formal' || tone === 'concise') return tone;
      return 'neutral';
    }

    function resolveToneDirective(tone) {
      const normalizedTone = normalizeReplyTone(tone);
      if (normalizedTone === 'formal') {
        return '톤은 공손하고 정중한 비즈니스 회신 톤으로 작성해줘.';
      }
      if (normalizedTone === 'concise') {
        return '톤은 간결하고 핵심만 전달하는 비즈니스 톤으로 작성해줘.';
      }
      return '톤은 기본 비즈니스 톤으로 작성해줘.';
    }

    function markActionExecuted(actionId) {
      if (!state || typeof state.markNextActionExecuted !== 'function') return;
      state.markNextActionExecuted(actionId);
    }

    function filterNextActionsMetadata(metadata) {
      if (!state || typeof state.filterNextActionsMetadata !== 'function') {
        return metadata && typeof metadata === 'object' ? metadata : {};
      }
      return state.filterNextActionsMetadata(metadata);
    }

    function handleNextActionRun(button) {
      const query = String(button && button.dataset && button.dataset.query ? button.dataset.query : '').trim();
      const title = String(button && button.dataset && button.dataset.title ? button.dataset.title : '').trim();
      const actionId = String(button && button.dataset && button.dataset.actionId ? button.dataset.actionId : '').trim();
      if (!query) return;
      if (state && typeof state.isSendingRef === 'function' && state.isSendingRef()) return;

      const isReplyDraftAction = title.indexOf('회신 초안') >= 0 || query.indexOf('회신 초안') >= 0;
      const compactQuery = query.replace(/\s+/g, '').toLowerCase();
      const isTodoRegistrationAction = (
        actionId === 'create_todo' ||
        ((compactQuery.indexOf('todo') >= 0 || compactQuery.indexOf('할일') >= 0) &&
          (compactQuery.indexOf('등록') >= 0 || compactQuery.indexOf('생성') >= 0 || compactQuery.indexOf('추가') >= 0))
      );

      if (actionId) markActionExecuted(actionId);
      if (isReplyDraftAction) {
        messageUi.addMessage(
          'assistant',
          '회신 톤을 선택하면 초안을 생성합니다.',
          { reply_tone_picker: { enabled: true, base_query: query } }
        );
        return;
      }

      messageUi.addMessage('user', query);
      setSendingState(true);
      const runtimeOptions = {};
      if (actionId) runtimeOptions.next_action_id = actionId;
      if (isTodoRegistrationAction) runtimeOptions.skip_intent_clarification = true;
      const requestRuntimeOptions = Object.keys(runtimeOptions).length ? runtimeOptions : null;

      chatApi.requestAssistantReply(query, handleProgress, requestRuntimeOptions).then(function (payload) {
        const answerText = String(payload && payload.answer ? payload.answer : '').trim() || '처리 결과를 확인하지 못했습니다.';
        const metadataRaw = payload && payload.metadata && typeof payload.metadata === 'object' ? payload.metadata : {};
        const metadata = filterNextActionsMetadata(Object.assign({}, metadataRaw));
        if (isReplyDraftAction && answerText && !isClarifyingQuestion(answerText)) {
          metadata.reply_draft = { enabled: true, body: answerText, button_label: '답변 메일 보내기' };
        }
        messageUi.addMessage('assistant', answerText, metadata);
      }).catch(function () {
        messageUi.addMessage('assistant', '후속 작업 실행 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
      }).finally(function () {
        if (typeof messageUi.clearProgressStatus === 'function') messageUi.clearProgressStatus();
        setSendingState(false);
        focusInput();
      });
    }

    function handleReplyToneGenerate(button) {
      const baseQuery = String(button && button.dataset && button.dataset.baseQuery ? button.dataset.baseQuery : '').trim();
      const selectedTone = normalizeReplyTone(button && button.dataset ? button.dataset.tone : '');
      if (!baseQuery) return;
      if (state && typeof state.isSendingRef === 'function' && state.isSendingRef()) return;

      const toneDirective = resolveToneDirective(selectedTone);
      const requestQuery = (baseQuery + ' ' + toneDirective).trim();
      const toneLabel = selectedTone === 'formal' ? '공손' : (selectedTone === 'concise' ? '간결' : '기본');
      markActionExecuted('draft_reply');
      messageUi.addMessage('user', '회신 톤 선택: ' + toneLabel);
      setSendingState(true);
      const runtimeOptions = { skip_intent_clarification: true };

      chatApi.requestAssistantReply(requestQuery, handleProgress, runtimeOptions).then(function (payload) {
        const firstAnswer = String(payload && payload.answer ? payload.answer : '').trim() || '처리 결과를 확인하지 못했습니다.';
        const firstMetadataRaw = payload && payload.metadata && typeof payload.metadata === 'object' ? payload.metadata : {};
        if (!isClarifyingQuestion(firstAnswer)) {
          const metadata = filterNextActionsMetadata(Object.assign({}, firstMetadataRaw, {
            reply_draft: { enabled: true, body: firstAnswer, button_label: '답변 메일 보내기' },
          }));
          messageUi.addMessage('assistant', firstAnswer, metadata);
          return;
        }
        const strictQuery = (requestQuery + ' 절대 추가 질문하지 말고 완성된 회신 메일 본문만 작성해줘.').trim();
        return chatApi.requestAssistantReply(strictQuery, handleProgress, runtimeOptions).then(function (retryPayload) {
          const retryAnswer = String(retryPayload && retryPayload.answer ? retryPayload.answer : '').trim() || firstAnswer;
          const retryMetadataRaw = retryPayload && retryPayload.metadata && typeof retryPayload.metadata === 'object' ? retryPayload.metadata : {};
          const retryMetadata = filterNextActionsMetadata(Object.assign({}, retryMetadataRaw));
          if (!isClarifyingQuestion(retryAnswer)) {
            retryMetadata.reply_draft = { enabled: true, body: retryAnswer, button_label: '답변 메일 보내기' };
          }
          messageUi.addMessage('assistant', retryAnswer, retryMetadata);
        });
      }).catch(function () {
        messageUi.addMessage('assistant', '회신 초안 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
      }).finally(function () {
        if (typeof messageUi.clearProgressStatus === 'function') messageUi.clearProgressStatus();
        setSendingState(false);
        focusInput();
      });
    }

    function handleReplyDraftOpen(button) {
      if (typeof openReplyCompose !== 'function') {
        messageUi.addMessage('assistant', '현재 환경에서는 답장 창 열기를 지원하지 않습니다.');
        return;
      }
      const draftBody = String(button && button.dataset && button.dataset.draftBody ? button.dataset.draftBody : '').trim();
      if (!draftBody) {
        messageUi.addMessage('assistant', '답장 본문 초안을 찾지 못했습니다.');
        return;
      }
      openReplyCompose(draftBody).catch(function () {
        messageUi.addMessage('assistant', 'Outlook 답장 창을 열지 못했습니다.');
      });
    }

    return {
      handleNextActionRun: handleNextActionRun,
      handleReplyToneGenerate: handleReplyToneGenerate,
      handleReplyDraftOpen: handleReplyDraftOpen,
      filterNextActionsMetadata: filterNextActionsMetadata,
    };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  global.TaskpaneChatActionNextActions = api;
})(typeof window !== 'undefined' ? window : globalThis);
