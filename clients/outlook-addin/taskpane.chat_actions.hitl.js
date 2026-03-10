(function initTaskpaneChatActionHitl(globalScope) {
  function create(options) {
    const windowRef = options.windowRef;
    const chatApi = options.chatApi;
    const messageUi = options.messageUi;
    const state = options.state;
    const setSendingState = options.setSendingState;
    const handleProgress = options.handleProgress;
    const sanitizeMeetingHilMetadata = options.sanitizeMeetingHilMetadata;
    const setMeetingRoomBookingButtonLabel = options.setMeetingRoomBookingButtonLabel;
    const buildMeetingRoomHilMessage = options.buildMeetingRoomHilMessage;
    const buildCalendarEventHilMessage = options.buildCalendarEventHilMessage;
    const focusInput = options.focusInput;
    const filterNextActionsMetadata = options.filterNextActionsMetadata;

    function openMeetingEvent(button) {
      const eventId = String(button.dataset.eventId || '').trim();
      const mailbox = windowRef.Office && windowRef.Office.context && windowRef.Office.context.mailbox;
      if (!eventId) {
        messageUi.addMessage('assistant', 'Outlook 일정 ID를 찾지 못했습니다.');
        return;
      }
      if (!mailbox || typeof mailbox.displayAppointmentForm !== 'function') {
        messageUi.addMessage('assistant', '현재 환경에서는 Outlook 일정 열기를 지원하지 않습니다.');
        return;
      }
      try {
        mailbox.displayAppointmentForm(eventId);
      } catch (_error) {
        messageUi.addMessage('assistant', 'Outlook에서 일정을 열지 못했습니다.');
      }
    }

    function handleHilConfirm(button, action) {
      const approved = action === 'hitl-confirm-approve';
      const threadId = String(button.dataset.threadId || '').trim();
      const confirmToken = String(button.dataset.confirmToken || '').trim();
      const promptVariant = String(button.dataset.promptVariant || '').trim();
      const hitlActionName = String(button.dataset.hitlActionName || '').trim();
      const lockKey = (threadId || '-') + '::' + (confirmToken || '-');
      if (!state.hiltConfirmLocks || typeof state.hiltConfirmLocks !== 'object') {
        state.hiltConfirmLocks = {};
      }
      if (state.hiltConfirmLocks[lockKey]) {
        return;
      }
      state.hiltConfirmLocks[lockKey] = true;
      if (typeof messageUi.showHitlConfirmPendingStatus === 'function') {
        messageUi.showHitlConfirmPendingStatus(approved ? '승인 처리 중입니다...' : '거절 처리 중입니다...');
      }
      if (typeof messageUi.disableHitlConfirmControls === 'function') {
        messageUi.disableHitlConfirmControls();
      }
      setSendingState(true);
      chatApi.requestChatConfirm({
        thread_id: threadId,
        approved: approved,
        confirm_token: confirmToken,
        prompt_variant: promptVariant || null,
      }).then(function (payload) {
        const answerText = String(payload && payload.answer ? payload.answer : '').trim() || '처리 결과를 확인하지 못했습니다.';
        const metadataRaw = payload && payload.metadata && typeof payload.metadata === 'object' ? payload.metadata : {};
        const bookingEvent = metadataRaw && metadataRaw.booking_event && typeof metadataRaw.booking_event === 'object'
          ? metadataRaw.booking_event
          : {};
        const todoTask = metadataRaw && metadataRaw.todo_task && typeof metadataRaw.todo_task === 'object'
          ? metadataRaw.todo_task
          : {};
        const filteredMetadata = filterNextActionsMetadata(metadataRaw);
        const filteredNextActions = filteredMetadata && Array.isArray(filteredMetadata.next_actions)
          ? filteredMetadata.next_actions
          : [];
        const hasFilteredNextActions = filteredNextActions.length > 0;
        const bookingEventId = String(bookingEvent.id || '').trim();
        const todoTaskLink = String(todoTask.web_link || '').trim();
        const todoTaskId = String(todoTask.id || '').trim();
        const todoTaskCreated = Boolean(todoTaskId || todoTaskLink);
        if (approved && bookingEventId && typeof messageUi.addMeetingBookingReadyCard === 'function') {
          if (typeof messageUi.clearMeetingBookingTransientMessages === 'function') {
            messageUi.clearMeetingBookingTransientMessages();
          }
          messageUi.addMeetingBookingReadyCard(answerText, bookingEventId);
          if (hasFilteredNextActions) {
            messageUi.addMessage('assistant', '다음 작업을 이어서 진행할 수 있습니다.', { next_actions: filteredNextActions });
          }
          return;
        }
        if (approved && hitlActionName === 'create_outlook_todo' && todoTaskCreated && typeof messageUi.addTodoReadyCard === 'function') {
          if (typeof messageUi.clearMeetingBookingTransientMessages === 'function') {
            messageUi.clearMeetingBookingTransientMessages();
          }
          messageUi.addTodoReadyCard(
            answerText,
            String(todoTask.title || '').trim() || '등록된 할 일',
            String(todoTask.due_date || '').trim(),
            todoTaskLink,
            todoTaskId
          );
          if (hasFilteredNextActions) {
            messageUi.addMessage('assistant', '다음 작업을 이어서 진행할 수 있습니다.', { next_actions: filteredNextActions });
          }
          return;
        }
        if (approved && hitlActionName === 'create_outlook_todo' && !todoTaskCreated && !answerText) {
          messageUi.addMessage('assistant', 'ToDo 등록에 실패했습니다. Graph 설정/로그인 상태를 확인해 주세요.');
          return;
        }
        const baseMetadata = (bookingEventId || todoTaskLink) ? sanitizeMeetingHilMetadata(metadataRaw) : metadataRaw;
        const metadata = filterNextActionsMetadata(baseMetadata);
        messageUi.addMessage('assistant', answerText, metadata);
      }).catch(function () {
        messageUi.addMessage('assistant', '승인 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
      }).finally(function () {
        delete state.hiltConfirmLocks[lockKey];
        setSendingState(false);
        focusInput();
      });
    }

    function handleMeetingRoomBookConfirm() {
      if (!state.pendingMeetingRoomContext) {
        messageUi.addMessage('assistant', '진행할 회의실 예약 요청을 찾지 못했습니다.');
        return;
      }
      const form = messageUi.getMeetingRoomBookingFormValues();
      if (!form || !form.building || !form.floor || !form.room_name || !form.date || !form.start_time || !form.end_time) {
        messageUi.addMessage('assistant', '건물/층/회의실/날짜/시간을 모두 입력해 주세요.');
        return;
      }
      setMeetingRoomBookingButtonLabel('예약 중');
      messageUi.disableMeetingRoomBookingControls();
      setSendingState(true);
      chatApi.requestAssistantReply(buildMeetingRoomHilMessage(form), handleProgress, { meeting_room_hil: true }).then(function (payload) {
        const answerText = String(payload && payload.answer ? payload.answer : '').trim() || '회의실 예약 요청을 처리하지 못했습니다.';
        const metadataRaw = payload && payload.metadata && typeof payload.metadata === 'object' ? payload.metadata : {};
        messageUi.addMessage('assistant', answerText, sanitizeMeetingHilMetadata(metadataRaw));
        const confirm = metadataRaw && metadataRaw.confirm && typeof metadataRaw.confirm === 'object' ? metadataRaw.confirm : null;
        if (!(confirm && confirm.required)) {
          messageUi.addMessage('assistant', 'HIL 승인 단계가 감지되지 않았습니다. 미들웨어 설정을 확인해 주세요.');
        }
        state.pendingMeetingRoomContext = null;
        setMeetingRoomBookingButtonLabel('예약');
      }).catch(function () {
        setMeetingRoomBookingButtonLabel('예약');
        messageUi.addMessage('assistant', '회의실 예약 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
      }).finally(function () {
        setSendingState(false);
        focusInput();
      });
    }

    function handleCalendarEventSubmit() {
      if (!state.pendingCalendarContext) {
        messageUi.addMessage('assistant', '진행할 일정 등록 요청을 찾지 못했습니다.');
        return;
      }
      const form = messageUi.getCalendarEventFormValues();
      if (!form || !form.subject || !form.date || !form.start_time || !form.end_time) {
        messageUi.addMessage('assistant', '제목/날짜/시작/종료 시간을 모두 입력해 주세요.');
        return;
      }
      messageUi.disableCalendarEventControls();
      setSendingState(true);
      chatApi.requestAssistantReply(buildCalendarEventHilMessage(form), handleProgress, { calendar_event_hil: true }).then(function (payload) {
        const answerText = String(payload && payload.answer ? payload.answer : '').trim() || '일정 등록 요청을 처리하지 못했습니다.';
        const metadataRaw = payload && payload.metadata && typeof payload.metadata === 'object' ? payload.metadata : {};
        messageUi.addMessage('assistant', answerText, sanitizeMeetingHilMetadata(metadataRaw));
        const confirm = metadataRaw && metadataRaw.confirm && typeof metadataRaw.confirm === 'object' ? metadataRaw.confirm : null;
        if (!(confirm && confirm.required)) {
          messageUi.addMessage('assistant', 'HIL 승인 단계가 감지되지 않았습니다. 미들웨어 설정을 확인해 주세요.');
        }
        state.pendingCalendarContext = null;
      }).catch(function () {
        messageUi.addMessage('assistant', '일정 등록 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
      }).finally(function () {
        setSendingState(false);
        focusInput();
      });
    }

    return {
      openMeetingEvent: openMeetingEvent,
      handleHilConfirm: handleHilConfirm,
      handleMeetingRoomBookConfirm: handleMeetingRoomBookConfirm,
      handleCalendarEventSubmit: handleCalendarEventSubmit,
    };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
    return;
  }
  globalScope.TaskpaneChatActionHitl = api;
})(typeof window !== 'undefined' ? window : globalThis);
