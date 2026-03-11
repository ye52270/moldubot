/* ========================================
   MolduBot – Taskpane Runtime Helpers
   ======================================== */

(function initTaskpaneRuntimeHelpers(global) {
  function create(options) {
    const byId = options.byId;
    const shortId = options.shortId;
    const logClientEvent = options.logClientEvent;
    const windowRef = options.windowRef;

    function mapProgressMessage(progressEvent) {
      const source = progressEvent && typeof progressEvent === 'object' ? progressEvent : {};
      const phase = String(source.phase || '').trim();
      const step = Number(source.step || 0);
      const total = Number(source.total_steps || 0);
      const serverMessage = String(source.message || '').trim();
      const serverDetail = String(source.detail || '').trim();
      const normalizedStep = Number.isFinite(step) && step > 0 ? step : 0;
      const normalizedTotal = Number.isFinite(total) && total > 0 ? total : 0;
      const resolvedTotal = normalizedTotal;
      const resolvedStep = normalizedStep;
      if (serverMessage) {
        return {
          phase: phase || 'processing',
          text: serverMessage,
          detail: serverDetail,
          step: resolvedStep,
          total: resolvedTotal,
        };
      }
      if (phase === 'received') {
        return { phase: phase, text: '요청을 확인하고 있습니다.', detail: '입력을 검증 중이에요.', step: resolvedStep, total: resolvedTotal };
      }
      if (phase === 'retrieving_context') {
        return { phase: phase, text: '메일 컨텍스트를 불러오는 중입니다.', detail: '현재 선택 메일 정보를 동기화하고 있어요.', step: resolvedStep, total: resolvedTotal };
      }
      if (phase === 'processing' || phase === 'analyzing_context' || phase === 'analyzing' || !phase) {
        return { phase: phase || 'processing', text: '요청을 처리 중입니다.', detail: '답변을 준비하고 있어요.', step: resolvedStep, total: resolvedTotal };
      }
      if (phase === 'critic_review') {
        return { phase: phase, text: '품질 점검(critic) 중입니다.', detail: '과장 표현, 언어 오판, 근거 부족 여부를 검사하고 있어요.', step: resolvedStep, total: resolvedTotal };
      }
      if (phase === 'revising') {
        return { phase: phase, text: '리뷰 결과를 보정 중입니다.', detail: '주석·리스크·개선 항목의 정확도를 높이고 있어요.', step: resolvedStep, total: resolvedTotal };
      }
      if (phase === 'finalizing') {
        return { phase: phase, text: '최종 결과를 정리하고 있습니다.', detail: '표현을 정돈하고 응답 포맷을 마무리해요.', step: resolvedStep, total: resolvedTotal };
      }
      if (phase === 'error' || phase === 'completed') return { phase: phase, text: '', detail: '', step: 0, total: 0 };
      return { phase: phase, text: '', detail: '', step: 0, total: 0 };
    }

    function openEvidenceMail(messageId) {
      return new Promise(function (resolve, reject) {
        const mailbox = windowRef.Office && windowRef.Office.context && windowRef.Office.context.mailbox;
        const id = String(messageId || '').trim();
        if (!id) {
          reject(new Error('evidence-mail-open-missing-message-id'));
          return;
        }
        if (mailbox && typeof mailbox.displayMessageForm === 'function') {
          try {
            mailbox.displayMessageForm(id);
            logClientEvent('info', 'evidence_mail_opened_native', { message_id: shortId(id) });
            resolve();
            return;
          } catch (nativeError) {
            logClientEvent('warning', 'evidence_mail_open_native_failed', {
              message_id: shortId(id),
              error: String(nativeError && nativeError.message ? nativeError.message : nativeError),
            });
          }
        }
        reject(new Error('evidence-mail-open-failed'));
      });
    }

    function openReplyCompose(draftBody) {
      return new Promise(function (resolve, reject) {
        const mailbox = windowRef.Office && windowRef.Office.context && windowRef.Office.context.mailbox;
        const item = mailbox && mailbox.item ? mailbox.item : null;
        const body = String(draftBody || '').trim();
        if (!item || typeof item.displayReplyForm !== 'function') {
          reject(new Error('reply-form-unavailable'));
          return;
        }
        if (!body) {
          reject(new Error('reply-body-empty'));
          return;
        }
        try {
          item.displayReplyForm(body);
          logClientEvent('info', 'reply_draft_opened', { body_length: body.length });
          resolve();
        } catch (error) {
          logClientEvent('warning', 'reply_draft_open_failed', {
            error: String(error && error.message ? error.message : error),
          });
          reject(error);
        }
      });
    }

    function buildMeetingRoomHilMessage(form) {
      const date = String(form && form.date ? form.date : '').trim();
      const startTime = String(form && form.start_time ? form.start_time : '').trim();
      const endTime = String(form && form.end_time ? form.end_time : '').trim();
      const attendeeCount = Math.max(1, Number(form && form.attendee_count ? form.attendee_count : 1));
      const building = String(form && form.building ? form.building : '').trim();
      const floor = Number(form && form.floor ? form.floor : 0);
      const roomName = String(form && form.room_name ? form.room_name : '').trim();
      const subject = String(form && form.subject ? form.subject : '').trim() || (
        '[회의실] ' + building + ' ' + String(floor || 0) + '층 ' + roomName
      );
      return [
        '[회의실 예약 HIL 실행]',
        'task=book_meeting_room',
        'require_human_approval=true',
        'timezone=Asia/Seoul',
        'date=' + date,
        'start_time=' + startTime,
        'end_time=' + endTime,
        'attendee_count=' + String(attendeeCount),
        'building=' + building,
        'floor=' + String(floor),
        'room_name=' + roomName,
        'subject=' + subject,
        'instruction=추가 질문 없이 book_meeting_room 도구를 호출하고 Human-In-The-Loop 승인을 요청하세요.',
      ].join('\n');
    }

    function buildCalendarEventHilMessage(form) {
      const subject = String(form && form.subject ? form.subject : '').trim();
      const date = String(form && form.date ? form.date : '').trim();
      const startTime = String(form && form.start_time ? form.start_time : '').trim();
      const endTime = String(form && form.end_time ? form.end_time : '').trim();
      const attendeesRaw = Array.isArray(form && form.attendees) ? form.attendees : [];
      const attendees = attendeesRaw
        .map(function (item) { return String(item || '').trim(); })
        .filter(function (item) { return Boolean(item); });
      const body = String(form && form.body ? form.body : '').trim();
      return [
        '[일정 등록 HIL 실행]',
        'task=create_outlook_calendar_event',
        'require_human_approval=true',
        'timezone=Asia/Seoul',
        'subject=' + subject,
        'date=' + date,
        'start_time=' + startTime,
        'end_time=' + endTime,
        'attendees=' + attendees.join(', '),
        'body=' + body,
        'instruction=추가 질문 없이 create_outlook_calendar_event 도구를 호출하고 Human-In-The-Loop 승인을 요청하세요.',
      ].join('\n');
    }

    function sanitizeMeetingHilMetadata(metadata) {
      const source = metadata && typeof metadata === 'object' ? metadata : {};
      const normalized = Object.assign({}, source);
      normalized.evidence_mails = [];
      normalized.aggregated_summary = [];
      return normalized;
    }

    function setMeetingRoomBookingButtonLabel(labelText) {
      const chatArea = byId('chatArea');
      if (!chatArea || typeof chatArea.querySelector !== 'function') return;
      const button = chatArea.querySelector('[data-action="meeting-room-book-confirm"]');
      if (!button) return;
      button.textContent = String(labelText || '').trim() || '예약';
    }

    return {
      mapProgressMessage: mapProgressMessage,
      openEvidenceMail: openEvidenceMail,
      openReplyCompose: openReplyCompose,
      buildMeetingRoomHilMessage: buildMeetingRoomHilMessage,
      buildCalendarEventHilMessage: buildCalendarEventHilMessage,
      sanitizeMeetingHilMetadata: sanitizeMeetingHilMetadata,
      setMeetingRoomBookingButtonLabel: setMeetingRoomBookingButtonLabel,
    };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  global.TaskpaneRuntimeHelpers = api;
})(typeof window !== 'undefined' ? window : globalThis);
