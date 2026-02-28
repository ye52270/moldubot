/* ========================================
   MolduBot – Workflow Module
   ======================================== */

function workflowLogEvent(event, status = 'ok', meta = {}) {
  try {
    if (typeof globalThis.molduLogEvent === 'function') {
      globalThis.molduLogEvent(event, status, meta);
      return;
    }
  } catch {
    // ignore
  }
}

// Outlook 런타임 환경별 전역 바인딩 편차를 방지하기 위해 명시적으로 노출한다.
globalThis.showScheduleDraftCard = showScheduleDraftCard;
globalThis.startRoomSelection = startRoomSelection;
globalThis.showMyHRDraftCard = showMyHRDraftCard;
globalThis.showPromiseProjectsCard = showPromiseProjectsCard;
globalThis.showPromiseMenuCard = showPromiseMenuCard;
globalThis.showFinanceProjectsCard = showFinanceProjectsCard;
globalThis.showFinanceMenuCard = showFinanceMenuCard;
globalThis.showFinanceDraftCard = showFinanceDraftCard;
globalThis.sendMessage = sendMessage;

function workflowLogError(event, error, meta = {}) {
  try {
    if (typeof globalThis.molduLogError === 'function') {
      globalThis.molduLogError(event, error, meta);
      return;
    }
  } catch {
    // ignore
  }
}

function getScheduleTitlePrefill() {
  const raw = String(emailContext?.subject || '').trim();
  if (!raw) return '';
  return raw.replace(/^(re|fw|fwd)\s*:\s*/i, '').trim();
}

function stripForwardHeaderFragments(value) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) return '';
  const cleaned = text.replace(
    /(?:(?:^|\s)(?:from|sent|to|cc|subject|보낸\s*사람|받는\s*사람|참조|제목)\s*[:：]\s*[^:\n]{1,300})(?=(?:\s(?:from|sent|to|cc|subject|보낸\s*사람|받는\s*사람|참조|제목)\s*[:：])|$)/gi,
    ' '
  ).replace(/\s+/g, ' ').trim();
  if (/^(?:from|sent|to|cc|subject|보낸\s*사람|받는\s*사람|참조|제목)\s*[:：]/i.test(cleaned)) {
    return '';
  }
  return cleaned;
}

function getScheduleDescriptionPrefill() {
  const rawBody = String(emailContext?.body || '').trim();
  if (!rawBody) return '';

  const cleanedLines = rawBody
    .replace(/\r/g, '\n')
    .split('\n')
    .map((line) => stripForwardHeaderFragments(String(line || '').trim()))
    .filter(Boolean)
    .filter((line) => !/^[-=_]{3,}$/.test(line))
    .filter((line) => !/^(?:from|sent|to|subject|cc)\s*:/i.test(line))
    .filter((line) => !/^(?:보낸\s*사람|받는\s*사람|제목|참조)\s*:/i.test(line))
    .filter((line) => !/^on\s+.+wrote\s*:/i.test(line))
    .filter((line) => !/^>+/.test(line));

  if (!cleanedLines.length) return '';

  const compactText = cleanedLines.join(' ');
  const sentenceCandidates = compactText
    .split(/[.!?。！？]\s+|\s{2,}/)
    .map((item) => String(item || '').replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .filter((line) => line.length >= 8)
    .filter((line) => !/https?:\/\/\S+/i.test(line))
    .filter((line) => !/(unsubscribe|confidential|무단|광고|수신거부)/i.test(line));

  const picked = [];
  const seen = new Set();
  for (const sentence of sentenceCandidates) {
    const normalized = sentence.toLowerCase();
    if (seen.has(normalized)) continue;
    seen.add(normalized);
    picked.push(sentence);
    if (picked.length >= 3) break;
  }

  if (!picked.length) return '';

  const concise = picked.map((line) => `- ${line}`).join('\n').slice(0, 320).trim();
  return concise;
}

function shouldUseLlmScheduleSummaryPrefill(prefill = {}) {
  const llmFlag = prefill?.llm_summary_prefill;
  if (llmFlag === true || llmFlag === 'true' || llmFlag === 1 || llmFlag === '1') return true;
  const requirement = String(prefill?.additional_requirement || '').trim();
  if (!requirement) return false;
  return /(요약|핵심|주요내용|포인트|정리)/i.test(requirement);
}

function extractScheduleSummaryPrefillFromAnswer(answer) {
  const raw = String(answer || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/\r/g, '\n')
    .trim();
  if (!raw) return '';

  const lines = raw
    .split('\n')
    .map((line) => String(line || '').trim())
    .filter(Boolean)
    .filter((line) => !/^\s*#{1,6}\s*/.test(line))
    .filter((line) => !/^(?:핵심\s*요약|요약|분석|권장\s*조치|참고)\s*[:：]?$/i.test(line))
    .map((line) => line.replace(/^\s*\d+[.)]\s*/, '').replace(/^\s*[-*•]\s*/, '').trim())
    .filter((line) => line.length >= 6);

  const picked = [];
  const seen = new Set();
  for (const line of lines) {
    const normalized = line.toLowerCase();
    if (seen.has(normalized)) continue;
    seen.add(normalized);
    picked.push(line);
    if (picked.length >= 3) break;
  }

  if (!picked.length) return '';
  return picked.map((line) => `- ${line}`).join('\n').slice(0, 420).trim();
}

async function hydrateScheduleDescriptionWithLlm(cardId, prefill = {}, setInlineMessage = () => {}, fallbackDesc = '') {
  try {
    if (!shouldUseLlmScheduleSummaryPrefill(prefill)) return;
    if (currentMode !== 'email' || !emailContext) return;
    if (typeof requestChat !== 'function') return;

    const noteEl = document.getElementById(`${cardId}_note`);
    if (!noteEl) return;
    const initialValue = String(noteEl.value || '').trim();

    setInlineMessage('메일 핵심 요약 생성 중...');
    workflowLogEvent('workflow.schedule.llm_prefill.start', 'ok', {
      has_requirement: Boolean(String(prefill?.additional_requirement || '').trim()),
      initial_chars: initialValue.length,
    });

    const requestEmailId = typeof resolveEmailContextId === 'function'
      ? String((await resolveEmailContextId()) || '').trim()
      : '';
    const runtimePayload = typeof getRuntimeOptionsPayload === 'function'
      ? getRuntimeOptionsPayload()
      : {};
    runtimePayload.current_mail_only = true;
    if (requestEmailId) runtimePayload.email_message_id = requestEmailId;
    runtimePayload.structured_input = {
      chips: ['current_mail'],
      verbs: ['summary'],
      combo_key: 'current_mail|summary',
      extra_context: String(prefill?.additional_requirement || '').trim(),
    };

    const requirement = String(prefill?.additional_requirement || '').trim();
    const summaryPromptBase = '이 메일 내용을 일정 등록용으로 요약해줘. 반드시 핵심 3개만 불릿(-) 형식으로 출력해줘.';
    const summaryPrompt = requirement
      ? `${summaryPromptBase}\n추가 조건: ${requirement}`
      : summaryPromptBase;

    let fullMessage = summaryPrompt;
    const subject = String(emailContext?.subject || '').trim();
    const sender = String(emailContext?.from || '').trim();
    const scheduleMailContextPayload = {
      subject: subject || 'N/A',
      from: sender || 'N/A',
    };
    if (requestEmailId) {
      fullMessage += `\nMessage ID: ${requestEmailId}`;
      scheduleMailContextPayload.message_id = requestEmailId;
    }
    if (emailContext?.body) {
      scheduleMailContextPayload.body_preview = String(emailContext.body || '').slice(0, 1600);
    }
    if (subject || sender || requestEmailId || scheduleMailContextPayload.body_preview) {
      fullMessage += `\n\n[메일 컨텍스트]\n${JSON.stringify(scheduleMailContextPayload)}`;
    }

    const response = await requestChat({
      message: fullMessage,
      thread_id: chatThreadId,
      runtime_options: runtimePayload,
      email_id: requestEmailId || undefined,
    });

    const answer = String(response?.answer || '').trim();
    const llmSummary = extractScheduleSummaryPrefillFromAnswer(answer);
    if (!llmSummary) {
      setInlineMessage('메일 요약 생성 결과가 비어 기존 내용을 유지합니다.');
      return;
    }

    // 사용자가 이미 수동 편집했다면 LLM 결과로 덮어쓰지 않는다.
    if (String(noteEl.value || '').trim() !== initialValue) {
      setInlineMessage('사용자 수정을 감지해 기존 입력을 유지합니다.');
      return;
    }
    noteEl.value = llmSummary;
    setInlineMessage('메일 핵심 요약을 반영했습니다.', true);
    workflowLogEvent('workflow.schedule.llm_prefill.done', 'ok', {
      summary_chars: llmSummary.length,
      fallback_chars: String(fallbackDesc || '').trim().length,
    });
  } catch (error) {
    workflowLogError('workflow.schedule.llm_prefill.failed', error);
    setInlineMessage('메일 요약 생성에 실패해 기존 내용을 유지합니다.');
  }
}

function showScheduleDraftCard(prefill = {}) {
  removeWelcomeStateIfExists();
  removeWorkflowCards();

  const chatArea = document.getElementById('chatArea');
  if (!chatArea) return;

  const today = new Date().toISOString().slice(0, 10);
  const defaultTitle = String(prefill.title || '').trim() || getScheduleTitlePrefill();
  const defaultDesc = String(prefill.description || '').trim() || getScheduleDescriptionPrefill();
  const cardId = `schedule_draft_${Date.now()}`;

  const html = `
    <div class="message assistant workflow-card-message" id="${cardId}">
      <div class="msg-avatar">${ICONS.sparkles}</div>
      <div class="msg-body" style="padding:0; overflow:hidden;">
        <div class="approval-card">
          <div class="approval-header">${ICONS.calendarPlus} 일정 등록</div>
          <div class="approval-body">
            <div class="wf-form-grid">
              <label class="wf-field">
                <span class="wf-label">일자</span>
                <input id="${cardId}_date" class="wf-input" type="date" value="${escapeAttr(today)}" />
              </label>
              <label class="wf-field">
                <span class="wf-label">제목</span>
                <input id="${cardId}_title" class="wf-input" type="text" placeholder="예: 팀 미팅" value="${escapeAttr(defaultTitle)}" />
              </label>
            </div>

            <div class="wf-form-grid" style="margin-top:10px;">
              <label class="wf-field">
                <span class="wf-label">시작 시간</span>
                <input id="${cardId}_start" class="wf-input" type="time" value="09:00" />
              </label>
              <label class="wf-field">
                <span class="wf-label">종료 시간</span>
                <input id="${cardId}_end" class="wf-input" type="time" value="10:00" />
              </label>
            </div>

            <label class="wf-field" style="margin-top:10px;">
              <span class="wf-label">내용 (선택)</span>
              <textarea id="${cardId}_note" class="wf-input wf-textarea" placeholder="설명을 입력하세요.">${escapeHtml(defaultDesc)}</textarea>
            </label>
            <div id="${cardId}_msg" class="wf-inline-msg"></div>
          </div>
          <div class="approval-actions" style="display:flex; gap:8px;">
            <button type="button" class="approval-btn reject" id="${cardId}_cancel">취소</button>
            <button type="button" class="approval-btn approve" id="${cardId}_submit">등록해줘</button>
          </div>
        </div>
      </div>
    </div>
  `;
  chatArea.insertAdjacentHTML('beforeend', html);
  scrollToBottom();
  recordHistory('assistant', '일정 등록 입력 카드 표시');
  persistTaskpaneState();

  const msgEl = document.getElementById(`${cardId}_msg`);
  const setInlineMessage = (message, ok = false) => {
    if (!msgEl) return;
    msgEl.textContent = message || '';
    msgEl.className = ok ? 'wf-inline-msg ok' : 'wf-inline-msg error';
  };

  // 현재메일 + 일정 요약 조합이면 카드는 즉시 띄우고,
  // 본문 초안은 비동기 LLM 요약으로 고품질로 덮어쓴다.
  void hydrateScheduleDescriptionWithLlm(cardId, prefill, setInlineMessage, defaultDesc);

  document.getElementById(`${cardId}_cancel`)?.addEventListener('click', () => {
    document.getElementById(cardId)?.remove();
    addAssistantMessage('일정 등록을 취소했습니다.');
  });

  document.getElementById(`${cardId}_submit`)?.addEventListener('click', async () => {
    const date = String(document.getElementById(`${cardId}_date`)?.value || '').trim();
    const title = String(document.getElementById(`${cardId}_title`)?.value || '').trim();
    const start = String(document.getElementById(`${cardId}_start`)?.value || '').trim();
    const end = String(document.getElementById(`${cardId}_end`)?.value || '').trim();
    const note = String(document.getElementById(`${cardId}_note`)?.value || '').trim();

    if (!date) return setInlineMessage('일자를 입력해주세요.');
    if (!title) return setInlineMessage('제목을 입력해주세요.');
    if (!start || !end) return setInlineMessage('시작/종료 시간을 입력해주세요.');
    if (start >= end) return setInlineMessage('종료 시간은 시작 시간보다 늦어야 합니다.');

    const contextNote =
      currentMode === 'email' && emailContext?.subject
        ? ` (메일 기반: ${emailContext.subject})`
        : '';
    const composedMessage = `${date} ${start}부터 ${end}까지 "${title}" 일정 등록해줘${
      note ? `. 설명: ${note}` : ''
    }${contextNote}`;

    document.getElementById(cardId)?.remove();
    addUserMessage('일정 등록해줘');
    await dispatchAssistantWorkflowMessage(composedMessage);
  });
}

function formatRoomOptionLabel(step, item) {
  if (step === 'building') {
    return String(item?.name || '').trim();
  }
  if (step === 'floor') {
    const floor = Number(item?.floor || 0);
    const roomCount = Number(item?.room_count || 0);
    if (Number.isFinite(floor) && floor > 0) {
      return roomCount > 0 ? `${floor}층 (${roomCount}실)` : `${floor}층`;
    }
    return '';
  }
  if (step === 'room') {
    return String(item?.room_name || '').trim();
  }
  return '';
}

function normalizeRoomPrefill(prefill = {}) {
  if (!prefill || typeof prefill !== 'object') return {};
  return {
    title: String(prefill.title || '').trim(),
    note: String(prefill.note || '').trim(),
    attendees: String(prefill.attendees || '').trim(),
  };
}

function showRoomSelectionCard(step, items = [], context = {}) {
  removeWorkflowCards();
  removeWelcomeStateIfExists();

  const chatArea = document.getElementById('chatArea');
  if (!chatArea) return;

  const stepConfig = {
    building: { title: '건물을 선택하세요', subtitle: '' },
    floor: {
      title: '층을 선택하세요',
      subtitle: context.building ? `${context.building}` : '',
    },
    room: {
      title: '회의실을 선택하세요',
      subtitle:
        context.building && context.floor
          ? `${context.building} · ${context.floor}층`
          : '',
    },
  };
  const conf = stepConfig[step] || stepConfig.building;
  const cardId = `room_select_${Date.now()}`;

  const optionsHtml =
    items
      .map((item, idx) => {
        const label = formatRoomOptionLabel(step, item);
        if (!label) return '';
        return `<button type="button" class="wf-choice-btn" data-idx="${idx}">${escapeHtml(
          label
        )}</button>`;
      })
      .join('') || '<div class="wf-inline-msg">선택 가능한 항목이 없습니다.</div>';

  const html = `
    <div class="message assistant workflow-card-message" id="${cardId}">
      <div class="msg-avatar">${ICONS.sparkles}</div>
      <div class="msg-body" style="padding:0; overflow:hidden;">
        <div class="approval-card">
          <div class="approval-header">${ICONS.buildingPlus} 회의실 예약</div>
          <div class="approval-body">
            <div class="wf-step-title">${escapeHtml(conf.title)}</div>
            ${conf.subtitle ? `<div class="wf-step-subtitle">${escapeHtml(conf.subtitle)}</div>` : ''}
            <div class="wf-choice-grid">${optionsHtml}</div>
          </div>
          <div class="approval-actions" style="display:flex; gap:8px;">
            <button type="button" class="approval-btn reject" id="${cardId}_cancel">취소</button>
          </div>
        </div>
      </div>
    </div>
  `;
  chatArea.insertAdjacentHTML('beforeend', html);
  scrollToBottom();
  recordHistory('assistant', `회의실 선택 카드 표시 (${step})`);
  persistTaskpaneState();

  const cardEl = document.getElementById(cardId);
  cardEl?.querySelectorAll('.wf-choice-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const idx = Number(btn.getAttribute('data-idx'));
      const selected = items[idx];
      if (!selected) return;
      if (step === 'building') {
        await handleRoomBuildingSelect(
          String(selected?.name || '').trim(),
          context?.prefill || {}
        );
        return;
      }
      if (step === 'floor') {
        await handleRoomFloorSelect(
          String(context.building || '').trim(),
          Number(selected?.floor || 0),
          context?.prefill || {}
        );
        return;
      }
      if (step === 'room') {
        showRoomBookingFormCard({
          building: String(context.building || '').trim(),
          floor: Number(context.floor || 0),
          room: String(selected?.room_name || '').trim(),
          prefill: context?.prefill || {},
        });
      }
    });
  });

  document.getElementById(`${cardId}_cancel`)?.addEventListener('click', () => {
    pendingRoomSelection = null;
    cardEl?.remove();
    addAssistantMessage('회의실 예약을 취소했습니다.');
  });
}

async function handleRoomBuildingSelect(building, prefill = {}) {
  if (!building) return;
  const normalizedPrefill = normalizeRoomPrefill(prefill);
  pendingRoomSelection = { step: 'floor', building, floor: null, room: '', prefill: normalizedPrefill };
  try {
    const response = await apiFetch(
      `/api/meeting-rooms?building=${encodeURIComponent(building)}`,
      { cache: 'no-store' }
    );
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data?.detail || '층 목록 조회 실패');
    const items = Array.isArray(data.items) ? data.items : [];
    showRoomSelectionCard('floor', items, { building, prefill: normalizedPrefill });
  } catch (error) {
    addAssistantMessage(`층 정보를 불러오지 못했습니다. (${error?.message || '오류'})`);
  }
}

async function handleRoomFloorSelect(building, floor, prefill = {}) {
  if (!building || !Number.isFinite(floor) || floor <= 0) return;
  const normalizedPrefill = normalizeRoomPrefill(prefill);
  pendingRoomSelection = { step: 'room', building, floor, room: '', prefill: normalizedPrefill };
  try {
    const response = await apiFetch(
      `/api/meeting-rooms?building=${encodeURIComponent(building)}&floor=${floor}`,
      { cache: 'no-store' }
    );
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data?.detail || '회의실 목록 조회 실패');
    const items = Array.isArray(data.items) ? data.items : [];
    showRoomSelectionCard('room', items, { building, floor, prefill: normalizedPrefill });
  } catch (error) {
    addAssistantMessage(`회의실 정보를 불러오지 못했습니다. (${error?.message || '오류'})`);
  }
}

function showRoomBookingFormCard(selection) {
  removeWorkflowCards();
  removeWelcomeStateIfExists();

  const building = String(selection?.building || '').trim();
  const floor = Number(selection?.floor || 0);
  const room = String(selection?.room || '').trim();
  const prefill = normalizeRoomPrefill(selection?.prefill || {});
  pendingRoomSelection = { step: 'form', building, floor, room, prefill };

  const chatArea = document.getElementById('chatArea');
  if (!chatArea) return;

  const today = new Date().toISOString().slice(0, 10);
  const cardId = `room_form_${Date.now()}`;
  const defaultTitle = prefill.title || '';
  const defaultNote = prefill.note || '';

  const html = `
    <div class="message assistant workflow-card-message" id="${cardId}">
      <div class="msg-avatar">${ICONS.sparkles}</div>
      <div class="msg-body" style="padding:0; overflow:hidden;">
        <div class="approval-card">
          <div class="approval-header">${ICONS.check} 회의실이 선택되었습니다</div>
          <div class="approval-body">
            <div class="wf-summary-line"><strong>건물</strong><span>${escapeHtml(building)}</span></div>
            <div class="wf-summary-line"><strong>층</strong><span>${escapeHtml(String(floor))}층</span></div>
            <div class="wf-summary-line"><strong>회의실</strong><span>${escapeHtml(room)}</span></div>

            <div class="wf-form-grid" style="margin-top:10px;">
              <label class="wf-field">
                <span class="wf-label">날짜</span>
                <input id="${cardId}_date" class="wf-input" type="date" value="${escapeAttr(today)}" />
              </label>
              <label class="wf-field">
                <span class="wf-label">회의 제목</span>
                <input id="${cardId}_title" class="wf-input" type="text" placeholder="예: 주간 팀 미팅" value="${escapeAttr(defaultTitle)}" />
              </label>
            </div>

            <div class="wf-form-grid" style="margin-top:10px;">
              <label class="wf-field">
                <span class="wf-label">시작 시간</span>
                <input id="${cardId}_start" class="wf-input" type="time" value="09:00" />
              </label>
              <label class="wf-field">
                <span class="wf-label">종료 시간</span>
                <input id="${cardId}_end" class="wf-input" type="time" value="10:00" />
              </label>
            </div>

            <label class="wf-field" style="margin-top:10px;">
              <span class="wf-label">메모 (선택)</span>
              <textarea id="${cardId}_note" class="wf-input wf-textarea" placeholder="추가 설명을 입력하세요.">${escapeHtml(defaultNote)}</textarea>
            </label>
            <div id="${cardId}_msg" class="wf-inline-msg"></div>
          </div>
          <div class="approval-actions" style="display:flex; gap:8px;">
            <button type="button" class="approval-btn reject" id="${cardId}_cancel">취소</button>
            <button type="button" class="approval-btn approve" id="${cardId}_submit">예약해줘</button>
          </div>
        </div>
      </div>
    </div>
  `;
  chatArea.insertAdjacentHTML('beforeend', html);
  scrollToBottom();
  recordHistory('assistant', '회의실 예약 입력 카드 표시');
  persistTaskpaneState();

  const msgEl = document.getElementById(`${cardId}_msg`);
  const setInlineMessage = (message, ok = false) => {
    if (!msgEl) return;
    msgEl.textContent = message || '';
    msgEl.className = ok ? 'wf-inline-msg ok' : 'wf-inline-msg error';
  };

  document.getElementById(`${cardId}_cancel`)?.addEventListener('click', () => {
    pendingRoomSelection = null;
    document.getElementById(cardId)?.remove();
    addAssistantMessage('회의실 예약 입력을 취소했습니다.');
  });

  document.getElementById(`${cardId}_submit`)?.addEventListener('click', async () => {
    const date = String(document.getElementById(`${cardId}_date`)?.value || '').trim();
    const title = String(document.getElementById(`${cardId}_title`)?.value || '').trim();
    const start = String(document.getElementById(`${cardId}_start`)?.value || '').trim();
    const end = String(document.getElementById(`${cardId}_end`)?.value || '').trim();
    const note = String(document.getElementById(`${cardId}_note`)?.value || '').trim();

    if (!date) return setInlineMessage('날짜를 입력해주세요.');
    if (!title) return setInlineMessage('회의 제목을 입력해주세요.');
    if (!start || !end) return setInlineMessage('시작/종료 시간을 입력해주세요.');
    if (start >= end) return setInlineMessage('종료 시간은 시작 시간보다 늦어야 합니다.');

    pendingRoomSelection = null;
    document.getElementById(cardId)?.remove();
    addUserMessage('회의실 예약해줘');
    const typingEl = typeof showTyping === 'function' ? showTyping() : null;
    try {
      const response = await apiFetch('/api/meeting-rooms/book', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          building,
          floor,
          room_name: room,
          subject: title,
          date,
          start_time: start,
          end_time: end,
          body: note,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data?.detail || '회의실 예약 실패');
      }
      if (typingEl && typeof removeTyping === 'function') {
        removeTyping(typingEl);
      }
      addAssistantMessage(String(data?.answer || '회의실 예약 요청을 처리했습니다.'));
    } catch (error) {
      if (typingEl && typeof removeTyping === 'function') {
        removeTyping(typingEl);
      }
      addAssistantMessage(`회의실 예약 처리에 실패했습니다. (${error?.message || '오류'})`);
    }
  });
}

async function startRoomSelection(prefill = {}) {
  pendingPromiseContext = null;
  removeWorkflowCards();
  removeWelcomeStateIfExists();
  const normalizedPrefill = normalizeRoomPrefill(prefill);
  pendingRoomSelection = {
    step: 'building',
    building: '',
    floor: null,
    room: '',
    prefill: normalizedPrefill,
  };
  try {
    const response = await apiFetch('/api/meeting-rooms', { cache: 'no-store' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data?.detail || '건물 목록 조회 실패');
    const items = Array.isArray(data.items) ? data.items : [];
    showRoomSelectionCard('building', items, { prefill: normalizedPrefill });
  } catch (error) {
    addAssistantMessage(`회의실 정보를 불러오지 못했습니다. (${error?.message || '오류'})`);
    pendingRoomSelection = null;
  }
}

function showMyHRDraftCard(prefill = {}) {
  removeWelcomeStateIfExists();
  removeWorkflowCards();

  const chatArea = document.getElementById('chatArea');
  if (!chatArea) return;

  const today = new Date().toISOString().slice(0, 10);
  pendingHrDraft = {
    leaveDate: prefill.leaveDate || today,
    leaveType: prefill.leaveType || '',
    reason: prefill.reason || '',
  };

  const cardId = `myhr_draft_${Date.now()}`;
  const html = `
    <div class="message assistant workflow-card-message" id="${cardId}">
      <div class="msg-avatar">${ICONS.sparkles}</div>
      <div class="msg-body" style="padding:0; overflow:hidden;">
        <div class="approval-card">
          <div class="approval-header">
            ${ICONS.badgeCheck}
            근태 승인서 작성
          </div>
          <div class="approval-body">
            <div class="wf-form-grid">
              <label class="wf-field">
                <span class="wf-label">근태 일자</span>
                <input id="${cardId}_date" class="wf-input" type="date" value="${escapeAttr(pendingHrDraft.leaveDate)}" />
              </label>
              <label class="wf-field">
                <span class="wf-label">근태 종류</span>
                <select id="${cardId}_type" class="wf-input">
                  <option value="">선택</option>
                  <option value="연차" ${pendingHrDraft.leaveType === '연차' ? 'selected' : ''}>연차</option>
                  <option value="family휴가" ${pendingHrDraft.leaveType === 'family휴가' ? 'selected' : ''}>family휴가</option>
                  <option value="refresh휴가" ${pendingHrDraft.leaveType === 'refresh휴가' ? 'selected' : ''}>refresh휴가</option>
                </select>
              </label>
            </div>
            <label class="wf-field" style="margin-top:10px;">
              <span class="wf-label">사유</span>
              <textarea id="${cardId}_reason" class="wf-input wf-textarea" placeholder="사유를 입력하세요.">${escapeHtml(pendingHrDraft.reason)}</textarea>
            </label>
            <div id="${cardId}_msg" class="wf-inline-msg"></div>
          </div>
          <div class="approval-actions" style="display:flex; gap:8px;">
            <button type="button" class="approval-btn reject" id="${cardId}_cancel">취소</button>
            <button type="button" class="approval-btn approve" id="${cardId}_draft">기안해줘</button>
          </div>
        </div>
      </div>
    </div>
  `;
  chatArea.insertAdjacentHTML('beforeend', html);
  scrollToBottom();
  recordHistory('assistant', '근태 승인서 입력 카드 표시');
  persistTaskpaneState();

  const cardEl = document.getElementById(cardId);
  const msgEl = document.getElementById(`${cardId}_msg`);
  const dateEl = document.getElementById(`${cardId}_date`);
  const typeEl = document.getElementById(`${cardId}_type`);
  const reasonEl = document.getElementById(`${cardId}_reason`);
  const cancelEl = document.getElementById(`${cardId}_cancel`);
  const draftEl = document.getElementById(`${cardId}_draft`);

  const setInlineMessage = (message, ok = false) => {
    if (!msgEl) return;
    msgEl.textContent = message || '';
    msgEl.className = ok ? 'wf-inline-msg ok' : 'wf-inline-msg error';
  };

  cancelEl?.addEventListener('click', () => {
    cardEl?.remove();
    pendingHrDraft = null;
    addAssistantMessage('근태 승인서 작성을 취소했습니다.');
  });

  draftEl?.addEventListener('click', () => {
    const leaveDate = String(dateEl?.value || '').trim();
    const leaveType = String(typeEl?.value || '').trim();
    const reason = String(reasonEl?.value || '').trim();

    if (!leaveDate) {
      setInlineMessage('근태 일자를 입력해주세요.');
      return;
    }
    if (!leaveType) {
      setInlineMessage('근태 종류를 선택해주세요.');
      return;
    }
    if (!reason) {
      setInlineMessage('사유를 입력해주세요.');
      return;
    }

    pendingHrDraft = { leaveDate, leaveType, reason };
    setInlineMessage('결재 화면을 여는 중입니다...', true);

    const popup = openMockupWindow('/myhr/', 'moldubot_myhr', {
      leave_date: leaveDate,
      leave_type: leaveType,
      reason,
    });

    if (!popup) {
      setInlineMessage('결재 화면을 열지 못했습니다. 팝업 차단을 해제해주세요.');
      return;
    }

    addAssistantMessage('결재 화면을 열었습니다. 화면에서 승인하면 챗봇에 완료 상태를 반영합니다.');
  });
}

async function showPromiseProjectsCard() {
  logEvent('ui.promise.projects.open', 'ok');
  if (typeof removeWorkflowCards === 'function') {
    removeWorkflowCards();
  }
  const chatArea = document.getElementById('chatArea');
  if (!chatArea) {
    logEvent('ui.promise.projects.open', 'warn', { reason: 'chat_area_missing' });
    return;
  }

  let projects = [];
  try {
    const response = await apiFetch('/api/promise/projects', { cache: 'no-store' });
    const data = await response.json().catch(() => ({}));
    const toProjectArray = (payload) => {
      if (Array.isArray(payload)) return payload;
      if (!payload || typeof payload !== 'object') return [];
      const candidates = [
        payload?.projects,
        payload?.items,
        payload?.data?.projects,
        payload?.data?.items,
        payload?.result?.projects,
      ];
      for (const candidate of candidates) {
        if (Array.isArray(candidate)) return candidate;
      }
      return [];
    };
    logEvent('ui.promise.projects.fetch', response.ok ? 'ok' : 'warn', {
      status_code: Number(response?.status || 0),
      has_projects_field: Array.isArray(data?.projects),
      count_field: Number(data?.count || 0),
      root_is_array: Array.isArray(data),
      root_keys: data && typeof data === 'object' ? Object.keys(data).slice(0, 8) : [],
    });
    if (!response.ok) throw new Error(data?.detail || '실행예산 프로젝트 조회 실패');
    projects = toProjectArray(data);
    if (!projects.length) {
      const fallbackCandidates = ['/myPromise/projects.json', '/promise/projects.json'];
      for (const path of fallbackCandidates) {
        logEvent('ui.promise.projects.fallback_static_try', 'ok', { source: path });
        try {
          // Outlook WebView 환경에서 API 라우트가 빈 목록을 반환하는 경우를 대비해 정적 mock 데이터로 보강한다.
          const fallbackResponse = await fetch(path, {
            method: 'GET',
            cache: 'no-store',
            credentials: 'same-origin',
          });
          const fallbackJson = await fallbackResponse.json().catch(() => []);
          if (fallbackResponse.ok && Array.isArray(fallbackJson) && fallbackJson.length) {
            projects = fallbackJson;
          logEvent('ui.promise.projects.fallback_static', 'ok', {
            project_count: projects.length,
            source: path,
            sample_project_number: String(projects?.[0]?.project_number || '').trim(),
          });
            break;
          } else {
            logEvent('ui.promise.projects.fallback_static_miss', 'warn', {
              source: path,
              status_code: Number(fallbackResponse?.status || 0),
              is_array: Array.isArray(fallbackJson),
              length: Array.isArray(fallbackJson) ? fallbackJson.length : -1,
            });
          }
        } catch (fallbackError) {
          logError('ui.promise.projects.fallback_static_failed', fallbackError, { source: path });
        }
      }
    }
    if (!projects.length) {
      try {
        const financeResponse = await apiFetch('/api/finance/projects', { cache: 'no-store' });
        const financeData = await financeResponse.json().catch(() => ({}));
        const financeProjects = Array.isArray(financeData?.projects) ? financeData.projects : [];
        if (financeResponse.ok && financeProjects.length) {
          projects = financeProjects.map((item) => ({
            project_number: item?.project_number,
            project_name: item?.project_name,
            project_type: item?.project_type,
            status: item?.status,
          }));
          logEvent('ui.promise.projects.fallback_finance', 'ok', {
            project_count: projects.length,
            status_code: Number(financeResponse?.status || 0),
            root_keys:
              financeData && typeof financeData === 'object'
                ? Object.keys(financeData).slice(0, 8)
                : [],
            sample_project_number: String(projects?.[0]?.project_number || '').trim(),
          });
        } else {
          logEvent('ui.promise.projects.fallback_finance', 'warn', {
            project_count: financeProjects.length,
            status_code: Number(financeResponse?.status || 0),
            root_keys:
              financeData && typeof financeData === 'object'
                ? Object.keys(financeData).slice(0, 8)
                : [],
          });
        }
      } catch (financeError) {
        logError('ui.promise.projects.fallback_finance_failed', financeError);
      }
    }
    logEvent('ui.promise.projects.render', 'ok', {
      project_count: projects.length,
    });
  } catch (error) {
    logError('ui.promise.projects.fetch_failed', error);
    addAssistantMessage(`실행예산 프로젝트 목록을 불러오지 못했습니다. (${error?.message || '오류'})`);
    return;
  }

  const cardId = `promise_list_${Date.now()}`;
  const rowsHtml = projects
    .map((project, idx) => {
      const number = String(project?.project_number || '').trim();
      const name = String(project?.project_name || number || '-').trim();
      const type = String(project?.project_type || '-');
      const status = String(project?.status || '-');
      return `
        <tr>
          <td>${escapeHtml(number || '-')}</td>
          <td>${escapeHtml(name)}</td>
          <td>${escapeHtml(type)}</td>
          <td>${escapeHtml(status)}</td>
          <td><button type="button" class="wf-table-btn" data-idx="${idx}">상세</button></td>
        </tr>
      `;
    })
    .join('');

  const html = `
    <div class="message assistant workflow-card-message" id="${cardId}">
      <div class="msg-avatar">${ICONS.sparkles}</div>
      <div class="msg-body" style="padding:0; overflow:hidden;">
        <div class="approval-card">
          <div class="approval-header">${ICONS.notebook} 실행예산 조회 (${projects.length}건)</div>
          <div class="approval-body">
            <div class="wf-table-wrap">
              <table class="wf-table">
                <thead>
                  <tr><th>프로젝트번호</th><th>프로젝트명</th><th>유형</th><th>상태</th><th></th></tr>
                </thead>
                <tbody>${rowsHtml || '<tr><td colspan="5">조회된 프로젝트가 없습니다.</td></tr>'}</tbody>
              </table>
            </div>
          </div>
          <div class="approval-actions" style="display:flex; gap:8px;">
            <button type="button" class="approval-btn reject" id="${cardId}_back">뒤로</button>
            <button type="button" class="approval-btn approve" id="${cardId}_write">실행예산 작성</button>
          </div>
        </div>
      </div>
    </div>
  `;
  chatArea.insertAdjacentHTML('beforeend', html);
  scrollToBottom();
  recordHistory('assistant', '실행예산 프로젝트 목록 카드 표시');
  persistTaskpaneState();

  const cardEl = document.getElementById(cardId);
  cardEl?.querySelectorAll('button.wf-table-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const idx = Number(btn.getAttribute('data-idx'));
      const item = projects[idx];
      const projectNumber = String(item?.project_number || '').trim();
      if (!projectNumber) return;
      await showPromiseSummaryCard(projectNumber, {
        project_name: item?.project_name || '',
        project_type: item?.project_type || '',
        status: item?.status || '',
      });
    });
  });

  document.getElementById(`${cardId}_back`)?.addEventListener('click', () => {
    cardEl?.remove();
    showPromiseMenuCard();
  });
  document.getElementById(`${cardId}_write`)?.addEventListener('click', () => {
    const popup = openMockupWindow('/promise/', 'moldubot_promise', { mode: 'create' });
    if (!popup) {
      addAssistantMessage('실행예산 작성 화면을 열지 못했습니다. 팝업 차단을 해제한 뒤 다시 시도해주세요.');
      return;
    }
    addAssistantMessage('실행예산 작성 화면을 열었습니다.');
  });
}

async function showPromiseSummaryCard(projectNumber, meta = {}) {
  let summary = null;
  try {
    const toNumber = (value) => {
      const normalized = String(value ?? '')
        .replace(/[,\s원]/g, '')
        .replace(/[^\d.-]/g, '');
      const parsed = Number(normalized || 0);
      return Number.isFinite(parsed) ? parsed : 0;
    };
    const hasMeaningfulBudgetData = (payload) => {
      if (!payload || typeof payload !== 'object') return false;
      const topLevelTotals = [
        payload?.final_cost_total,
        payload?.execution_total,
        payload?.labor_cost,
        payload?.outsourcing_cost,
        payload?.material_cost,
        payload?.expense_cost,
        payload?.execution_breakdown?.labor_cost,
        payload?.execution_breakdown?.outsourcing_cost,
        payload?.execution_breakdown?.material_cost,
        payload?.execution_breakdown?.expense_cost,
      ];
      if (topLevelTotals.some((value) => toNumber(value) > 0)) return true;
      const monthly = Array.isArray(payload?.monthly_breakdown) ? payload.monthly_breakdown : [];
      return monthly.some((item) => {
        if (!item || typeof item !== 'object') return false;
        return (
          toNumber(item?.execution_total) > 0 ||
          toNumber(item?.labor_cost) > 0 ||
          toNumber(item?.outsourcing_cost) > 0 ||
          toNumber(item?.material_cost) > 0 ||
          toNumber(item?.expense_cost) > 0
        );
      });
    };
    const readSummaryFromStatic = async () => {
      const candidates = ['/myPromise/project_costs.json', '/promise/project_costs.json'];
      for (const path of candidates) {
        try {
          const fallbackResponse = await fetch(path, {
            method: 'GET',
            cache: 'no-store',
            credentials: 'same-origin',
          });
          const fallbackJson = await fallbackResponse.json().catch(() => []);
          const costItem =
            fallbackResponse.ok && Array.isArray(fallbackJson)
              ? fallbackJson.find(
                  (item) => String(item?.project_number || '').trim() === String(projectNumber || '').trim()
                )
              : null;
          if (costItem && hasMeaningfulBudgetData(costItem)) {
            return {
              ...costItem,
              project_number: String(costItem?.project_number || projectNumber || '').trim(),
              project_name: String(meta?.project_name || projectNumber || '').trim(),
              project_type: String(meta?.project_type || '-').trim(),
              status: String(meta?.status || '-').trim(),
              execution_breakdown: {
                labor_cost: costItem?.labor_cost,
                outsourcing_cost: costItem?.outsourcing_cost,
                material_cost: costItem?.material_cost,
                expense_cost: costItem?.expense_cost,
              },
            };
          }
        } catch (_ignored) {
          // 다음 후보 경로로 진행
        }
      }
      return null;
    };
    const readSummaryFromFinance = async () => {
      try {
        const financeResponse = await apiFetch(
          `/api/finance/projects/${encodeURIComponent(projectNumber)}/budget`,
          { cache: 'no-store' }
        );
        const financeData = await financeResponse.json().catch(() => null);
        if (!financeResponse.ok || !financeData || typeof financeData !== 'object') {
          return null;
        }
        const summaryFromFinance = {
          project_number: String(projectNumber || '').trim(),
          project_name: String(meta?.project_name || projectNumber || '').trim(),
          project_type: String(meta?.project_type || '-').trim(),
          status: String(meta?.status || '-').trim(),
          final_cost_total: financeData?.expense_budget_total || 0,
          execution_total: financeData?.used_amount || 0,
          execution_breakdown: {
            labor_cost: 0,
            outsourcing_cost: 0,
            material_cost: 0,
            expense_cost: financeData?.used_amount || 0,
          },
          monthly_breakdown: [],
          currency: 'KRW',
        };
        if (!hasMeaningfulBudgetData(summaryFromFinance)) return null;
        logEvent('ui.promise.summary.fallback_finance', 'ok', {
          project_number: String(projectNumber || ''),
          status_code: Number(financeResponse?.status || 0),
          final_cost_total: toNumber(summaryFromFinance?.final_cost_total),
          execution_total: toNumber(summaryFromFinance?.execution_total),
        });
        return summaryFromFinance;
      } catch (financeError) {
        logError('ui.promise.summary.fallback_finance_failed', financeError, {
          project_number: String(projectNumber || ''),
        });
        return null;
      }
    };

    const response = await apiFetch(
      `/api/promise/projects/${encodeURIComponent(projectNumber)}/summary`,
      { cache: 'no-store' }
    );
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error((data && data.detail) || '실행예산 상세 조회 실패');

    if (hasMeaningfulBudgetData(data)) {
      summary = {
        ...data,
        project_number: data?.project_number || projectNumber,
        project_name: data?.project_name || meta?.project_name || projectNumber,
        project_type: data?.project_type || meta?.project_type || '-',
        status: data?.status || meta?.status || '-',
      };
      logEvent('ui.promise.summary.payload', 'ok', {
        project_number: String(projectNumber || ''),
        source: 'api',
        final_cost_total: toNumber(summary?.final_cost_total),
        execution_total: toNumber(summary?.execution_total),
        monthly_len: Array.isArray(summary?.monthly_breakdown) ? summary.monthly_breakdown.length : 0,
      });
    } else {
      logEvent('ui.promise.summary.fallback_static', 'warn', {
        reason: 'api_summary_empty_or_all_zero',
        project_number: String(projectNumber || ''),
        status_code: Number(response?.status || 0),
      });
      summary = await readSummaryFromStatic();
      if (!summary) {
        summary = await readSummaryFromFinance();
      }
      if (!summary) throw new Error('실행예산 상세 데이터가 비어 있습니다.');
      logEvent('ui.promise.summary.payload', 'ok', {
        project_number: String(projectNumber || ''),
        source: 'static',
        final_cost_total: toNumber(summary?.final_cost_total),
        execution_total: toNumber(summary?.execution_total),
        monthly_len: Array.isArray(summary?.monthly_breakdown) ? summary.monthly_breakdown.length : 0,
      });
    }
  } catch (error) {
    addAssistantMessage(`실행예산 상세를 불러오지 못했습니다. (${error?.message || '오류'})`);
    return;
  }

  removeWorkflowCards();
  const chatArea = document.getElementById('chatArea');
  if (!chatArea) return;

  let monthly = Array.isArray(summary?.monthly_breakdown) ? summary.monthly_breakdown : [];
  const monthlyRows = monthly
    .map((item, idx) => {
      const month = Number(item?.month || idx + 1);
      return `
        <tr>
          <td>${escapeHtml(`${month}월`)}</td>
          <td>${escapeHtml(formatKrw(item?.execution_total))}</td>
          <td>${escapeHtml(formatKrw(item?.labor_cost))}</td>
          <td>${escapeHtml(formatKrw(item?.outsourcing_cost))}</td>
          <td>${escapeHtml(formatKrw(item?.material_cost))}</td>
          <td>${escapeHtml(formatKrw(item?.expense_cost))}</td>
        </tr>
      `;
    })
    .join('');

  const b = summary?.execution_breakdown || {};
  pendingPromiseContext = {
    projectNumber: String(summary?.project_number || projectNumber || '').trim(),
    projectName: String(summary?.project_name || '').trim(),
    projectType: String(summary?.project_type || '').trim(),
    status: String(summary?.status || '').trim(),
  };
  const cardId = `promise_summary_${Date.now()}`;
  const html = `
    <div class="message assistant workflow-card-message" id="${cardId}">
      <div class="msg-avatar">${ICONS.sparkles}</div>
      <div class="msg-body" style="padding:0; overflow:hidden;">
        <div class="approval-card">
          <div class="approval-header">${ICONS.notebook} ${escapeHtml(summary?.project_name || projectNumber)} 실행예산 상세</div>
          <div class="approval-body">
            <div class="wf-meta-line">
              프로젝트번호: ${escapeHtml(summary?.project_number || projectNumber)}
              <span class="wf-meta-sep">|</span>
              유형: ${escapeHtml(summary?.project_type || '-')}
              <span class="wf-meta-sep">|</span>
              상태: ${escapeHtml(summary?.status || '-')}
            </div>
            <div class="wf-kpi-grid">
              <div class="wf-kpi-item"><span>최종 Cost총액</span><strong>${escapeHtml(formatKrw(summary?.final_cost_total))}</strong></div>
              <div class="wf-kpi-item"><span>총 실행비용</span><strong>${escapeHtml(formatKrw(summary?.execution_total))}</strong></div>
              <div class="wf-kpi-item"><span>인건비</span><strong>${escapeHtml(formatKrw(b?.labor_cost))}</strong></div>
              <div class="wf-kpi-item"><span>외주비</span><strong>${escapeHtml(formatKrw(b?.outsourcing_cost))}</strong></div>
              <div class="wf-kpi-item"><span>재료비</span><strong>${escapeHtml(formatKrw(b?.material_cost))}</strong></div>
              <div class="wf-kpi-item"><span>경비</span><strong>${escapeHtml(formatKrw(b?.expense_cost))}</strong></div>
            </div>
            <div class="wf-table-wrap" style="margin-top:10px;">
              <table class="wf-table">
                <thead>
                  <tr><th>월</th><th>총 실행비용</th><th>인건비</th><th>외주비</th><th>재료비</th><th>경비</th></tr>
                </thead>
                <tbody>${monthlyRows || '<tr><td colspan="6">월별 데이터가 없습니다.</td></tr>'}</tbody>
              </table>
            </div>
          </div>
          <div class="approval-actions" style="display:flex; gap:8px;">
            <button type="button" class="approval-btn reject" id="${cardId}_list">목록으로</button>
            <button type="button" class="approval-btn approve" id="${cardId}_edit">현재 비용 수정</button>
          </div>
        </div>
      </div>
    </div>
  `;
  chatArea.insertAdjacentHTML('beforeend', html);
  scrollToBottom();
  recordHistory('assistant', '실행예산 상세 카드 표시');
  persistTaskpaneState();

  document.getElementById(`${cardId}_list`)?.addEventListener('click', () => {
    showPromiseProjectsCard();
  });
  document.getElementById(`${cardId}_edit`)?.addEventListener('click', () => {
    const popup = openMockupWindow('/promise/', 'moldubot_promise', {
      mode: 'edit',
      project_number: summary?.project_number || projectNumber,
      project_name: summary?.project_name || '',
      project_type: summary?.project_type || '',
      project_status: summary?.status || '',
    });
    if (!popup) {
      addAssistantMessage('실행예산 수정 화면을 열지 못했습니다. 팝업 차단을 해제한 뒤 다시 시도해주세요.');
      return;
    }
    addAssistantMessage('실행예산 수정 화면을 열었습니다.');
  });
}

function showPromiseMenuCard() {
  removeWorkflowCards();
  addAssistantActionCard({
    title: '실행예산',
    description: '원하는 작업을 선택하세요.',
    actions: [
      { label: '실행예산 조회', onClick: () => showPromiseProjectsCard() },
      {
        label: '실행예산 작성',
        onClick: () => {
          const popup = openMockupWindow('/promise/', 'moldubot_promise', { mode: 'create' });
          if (!popup) {
            addAssistantMessage('실행예산 작성 화면을 열지 못했습니다. 팝업 차단을 해제한 뒤 다시 시도해주세요.');
            return;
          }
          addAssistantMessage('실행예산 작성 화면을 열었습니다.');
        },
      },
    ],
    historyText: '실행예산 메뉴 카드 표시',
  });
}

function resolvePromiseLocalUiAction(rawMessage = '', normalizedMessage = '') {
  const raw = String(rawMessage || '').trim();
  const normalized = String(normalizedMessage || '').trim();
  const compactRaw = raw.replace(/\s+/g, '').toLowerCase();
  const compactNormalized = normalized.replace(/\s+/g, '').toLowerCase();
  const compact = compactNormalized || compactRaw;
  if (!compact) return '';
  if (compact === '@실행예산' || compact === '@promise') return 'promise_selector';
  if (compact === '실행예산조회' || compact === 'promise조회') return 'promise_projects';
  if (compact === '실행예산입력' || compact === '실행예산작성' || compact === 'promise입력') return 'promise_create';
  return '';
}

function openPromiseCreateWindowFromUi() {
  const popup = openMockupWindow('/promise/', 'moldubot_promise', { mode: 'create' });
  if (!popup) {
    addAssistantMessage('실행예산 작성 화면을 열지 못했습니다. 팝업 차단을 해제한 뒤 다시 시도해주세요.');
    return;
  }
  addAssistantMessage('실행예산 작성 화면을 열었습니다.');
}

function showPromiseSelectorToast() {
  if (typeof showClarificationPromptCard === 'function') {
    showClarificationPromptCard({
      question: '실행예산 작업을 선택해 주세요.',
      options: ['실행예산 조회', '실행예산 입력'],
      missingSlots: ['intent_target'],
      intent: 'promise_menu',
    });
    return;
  }
  showPromiseMenuCard();
}

function openMyHrWindowFromUi(mode = 'apply') {
  const popup = openMockupWindow('/myhr/', 'moldubot_myhr', { mode });
  if (!popup) {
    addAssistantMessage('근태 화면을 열지 못했습니다. 팝업 차단을 해제한 뒤 다시 시도해주세요.');
    return;
  }
  addAssistantMessage(mode === 'view' ? '근태 조회 화면을 열었습니다.' : '근태 신청 화면을 열었습니다.');
}

function showHrMenuCard() {
  removeWorkflowCards();
  addAssistantActionCard({
    title: '근태',
    description: '원하는 작업을 선택하세요.',
    actions: [
      { label: '근태 조회', onClick: () => openMyHrWindowFromUi('view') },
      { label: '근태 신청', onClick: () => showMyHRDraftCard() },
    ],
    historyText: '근태 메뉴 카드 표시',
  });
}

function showHrSelectorToast() {
  if (typeof showClarificationPromptCard === 'function') {
    showClarificationPromptCard({
      question: '근태 작업을 선택해 주세요.',
      options: ['근태 조회', '근태 신청'],
      missingSlots: ['intent_target'],
      intent: 'hr_apply',
    });
    return;
  }
  showHrMenuCard();
}

function openFinanceCreateWindowFromUi() {
  showFinanceDraftCard();
}

async function showFinanceProjectsCard() {
  removeWorkflowCards();
  const chatArea = document.getElementById('chatArea');
  if (!chatArea) return;

  let projects = [];
  try {
    const response = await apiFetch('/api/finance/projects', { cache: 'no-store' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data?.detail || '비용정산 프로젝트 조회 실패');
    projects = Array.isArray(data.projects) ? data.projects : [];
  } catch (error) {
    addAssistantMessage(`비용정산 프로젝트 목록을 불러오지 못했습니다. (${error?.message || '오류'})`);
    return;
  }

  const cardId = `finance_list_${Date.now()}`;
  const rowsHtml = projects
    .map((project, idx) => {
      const number = String(project?.project_number || '').trim();
      const name = String(project?.project_name || number || '-').trim();
      return `
        <tr>
          <td>${escapeHtml(number || '-')}</td>
          <td>${escapeHtml(name)}</td>
          <td>${escapeHtml(project?.project_type || '-')}</td>
          <td>${escapeHtml(project?.status || '-')}</td>
          <td>${escapeHtml(formatKrw(project?.remaining_amount))}</td>
          <td><button type="button" class="wf-table-btn" data-idx="${idx}">상세</button></td>
        </tr>
      `;
    })
    .join('');
  const html = `
    <div class="message assistant workflow-card-message" id="${cardId}">
      <div class="msg-avatar">${ICONS.sparkles}</div>
      <div class="msg-body" style="padding:0; overflow:hidden;">
        <div class="approval-card">
          <div class="approval-header">${ICONS.wallet} 비용정산 조회 (${projects.length}건)</div>
          <div class="approval-body">
            <div class="wf-table-wrap">
              <table class="wf-table">
                <thead>
                  <tr><th>프로젝트번호</th><th>프로젝트명</th><th>유형</th><th>상태</th><th>잔여 경비</th><th></th></tr>
                </thead>
                <tbody>${rowsHtml || '<tr><td colspan="6">조회된 프로젝트가 없습니다.</td></tr>'}</tbody>
              </table>
            </div>
          </div>
          <div class="approval-actions" style="display:flex; gap:8px;">
            <button type="button" class="approval-btn reject" id="${cardId}_back">뒤로</button>
            <button type="button" class="approval-btn approve" id="${cardId}_write">비용정산 작성</button>
          </div>
        </div>
      </div>
    </div>
  `;
  chatArea.insertAdjacentHTML('beforeend', html);
  scrollToBottom();
  recordHistory('assistant', '비용정산 프로젝트 목록 카드 표시');
  persistTaskpaneState();

  const cardEl = document.getElementById(cardId);
  cardEl?.querySelectorAll('button.wf-table-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const idx = Number(btn.getAttribute('data-idx'));
      const item = projects[idx];
      const projectNumber = String(item?.project_number || '').trim();
      if (!projectNumber) return;
      await showFinanceSummaryCard(projectNumber, item);
    });
  });
  document.getElementById(`${cardId}_back`)?.addEventListener('click', () => {
    cardEl?.remove();
    showFinanceMenuCard();
  });
  document.getElementById(`${cardId}_write`)?.addEventListener('click', () => {
    openFinanceCreateWindowFromUi();
  });
}

async function showFinanceSummaryCard(projectNumber, meta = {}) {
  let summary = null;
  try {
    const response = await apiFetch(
      `/api/finance/projects/${encodeURIComponent(projectNumber)}/budget`,
      { cache: 'no-store' }
    );
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data?.detail || '비용정산 상세 조회 실패');
    summary = {
      ...data,
      project_number: data?.project_number || projectNumber,
      project_name: data?.project_name || meta?.project_name || projectNumber,
      project_type: data?.project_type || meta?.project_type || '-',
      status: data?.status || meta?.status || '-',
    };
  } catch (error) {
    addAssistantMessage(`비용정산 상세를 불러오지 못했습니다. (${error?.message || '오류'})`);
    return;
  }

  removeWorkflowCards();
  const chatArea = document.getElementById('chatArea');
  if (!chatArea) return;
  const categories = Array.isArray(summary?.allowed_categories) ? summary.allowed_categories : [];
  const cardId = `finance_summary_${Date.now()}`;
  const html = `
    <div class="message assistant workflow-card-message" id="${cardId}">
      <div class="msg-avatar">${ICONS.sparkles}</div>
      <div class="msg-body" style="padding:0; overflow:hidden;">
        <div class="approval-card">
          <div class="approval-header">${ICONS.wallet} ${escapeHtml(summary?.project_name || projectNumber)} 비용정산 상세</div>
          <div class="approval-body">
            <div class="wf-meta-line">
              프로젝트번호: ${escapeHtml(summary?.project_number || projectNumber)}
              <span class="wf-meta-sep">|</span>
              유형: ${escapeHtml(summary?.project_type || '-')}
              <span class="wf-meta-sep">|</span>
              상태: ${escapeHtml(summary?.status || '-')}
            </div>
            <div class="wf-kpi-grid">
              <div class="wf-kpi-item"><span>경비 총 예산</span><strong>${escapeHtml(formatKrw(summary?.expense_budget_total))}</strong></div>
              <div class="wf-kpi-item"><span>사용 누계</span><strong>${escapeHtml(formatKrw(summary?.used_amount))}</strong></div>
              <div class="wf-kpi-item"><span>잔여 가능</span><strong>${escapeHtml(formatKrw(summary?.remaining_amount))}</strong></div>
            </div>
            <div class="wf-inline-msg ok" style="margin-top:10px;">
              사용 가능 항목: ${escapeHtml(categories.join(', ') || '-')}
            </div>
          </div>
          <div class="approval-actions" style="display:flex; gap:8px;">
            <button type="button" class="approval-btn reject" id="${cardId}_list">목록으로</button>
            <button type="button" class="approval-btn approve" id="${cardId}_write">비용정산 작성</button>
          </div>
        </div>
      </div>
    </div>
  `;
  chatArea.insertAdjacentHTML('beforeend', html);
  scrollToBottom();
  recordHistory('assistant', '비용정산 상세 카드 표시');
  persistTaskpaneState();
  document.getElementById(`${cardId}_list`)?.addEventListener('click', () => {
    showFinanceProjectsCard();
  });
  document.getElementById(`${cardId}_write`)?.addEventListener('click', () => {
    openFinanceCreateWindowFromUi();
  });
}

function showFinanceMenuCard() {
  removeWorkflowCards();
  addAssistantActionCard({
    title: '비용정산',
    description: '원하는 작업을 선택하세요.',
    actions: [
      { label: '비용정산 조회', onClick: () => showFinanceProjectsCard() },
      { label: '비용정산 작성', onClick: () => openFinanceCreateWindowFromUi() },
    ],
    historyText: '비용정산 메뉴 카드 표시',
  });
}

function showFinanceSelectorToast() {
  if (typeof showClarificationPromptCard === 'function') {
    showClarificationPromptCard({
      question: '비용정산 작업을 선택해 주세요.',
      options: ['비용정산 조회', '비용정산 작성'],
      missingSlots: ['intent_target'],
      intent: 'finance_workflow',
    });
    return;
  }
  showFinanceMenuCard();
}

function resolveSystemLocalUiAction(rawMessage = '', normalizedMessage = '') {
  const raw = String(rawMessage || '').trim();
  const normalized = String(normalizedMessage || '').trim();
  const compactRaw = raw.replace(/\s+/g, '').toLowerCase();
  const compactNormalized = normalized.replace(/\s+/g, '').toLowerCase();
  const compact = compactNormalized || compactRaw;
  if (!compact) return '';
  if (compact === '@실행예산' || compact === '@promise') return 'promise_selector';
  if (compact === '실행예산조회' || compact === 'promise조회') return 'promise_projects';
  if (compact === '실행예산입력' || compact === '실행예산작성' || compact === 'promise입력') return 'promise_create';
  if (compact === '@비용정산' || compact === '@finance') return 'finance_selector';
  if (compact === '비용정산조회' || compact === 'finance조회') return 'finance_projects';
  if (compact === '비용정산입력' || compact === '비용정산작성' || compact === 'finance입력') return 'finance_create';
  if (compact === '@근태신청' || compact === '@근태' || compact === '@hr') return 'hr_selector';
  if (compact === '근태조회' || compact === '휴가조회' || compact === 'hr조회') return 'hr_view';
  if (compact === '근태신청' || compact === '근태작성' || compact === 'hr신청') return 'hr_apply';
  return '';
}

async function showFinanceDraftCard() {
  pendingPromiseContext = null;
  removeWorkflowCards();

  let projects = [];
  try {
    const response = await apiFetch('/api/finance/projects', { cache: 'no-store' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data?.detail || '비용정산 프로젝트 조회 실패');
    projects = Array.isArray(data.projects) ? data.projects : [];
  } catch (error) {
    addAssistantMessage(`비용정산 프로젝트 목록을 불러오지 못했습니다. (${error?.message || '오류'})`);
    return;
  }

  const chatArea = document.getElementById('chatArea');
  if (!chatArea) return;

  const cardId = `finance_draft_${Date.now()}`;
  const options = ['<option value="">프로젝트를 선택하세요</option>']
    .concat(
      projects.map((project) => {
        const number = String(project?.project_number || '').trim();
        const name = String(project?.project_name || number || '-').trim();
        return `<option value="${escapeAttr(number)}">${escapeHtml(name)}</option>`;
      })
    )
    .join('');

  const html = `
    <div class="message assistant workflow-card-message" id="${cardId}">
      <div class="msg-avatar">${ICONS.sparkles}</div>
      <div class="msg-body" style="padding:0; overflow:hidden;">
        <div class="approval-card">
          <div class="approval-header">${ICONS.wallet} 비용정산 작성</div>
          <div class="approval-body">
            <label class="wf-field">
              <span class="wf-label">프로젝트명</span>
              <select id="${cardId}_project" class="wf-input">${options}</select>
            </label>
            <div id="${cardId}_brief" class="wf-inline-msg"></div>
          </div>
          <div class="approval-actions" style="display:flex; gap:8px;">
            <button type="button" class="approval-btn reject" id="${cardId}_cancel">취소</button>
            <button type="button" class="approval-btn approve" id="${cardId}_open">비용정산 작성</button>
          </div>
        </div>
      </div>
    </div>
  `;
  chatArea.insertAdjacentHTML('beforeend', html);
  scrollToBottom();
  recordHistory('assistant', '비용정산 입력 카드 표시');
  persistTaskpaneState();

  const projectEl = document.getElementById(`${cardId}_project`);
  const briefEl = document.getElementById(`${cardId}_brief`);
  const renderBrief = () => {
    const selected = String(projectEl?.value || '').trim();
    const project = projects.find((item) => String(item?.project_number || '').trim() === selected);
    if (!briefEl) return;
    if (!project) {
      briefEl.textContent = '';
      briefEl.className = 'wf-inline-msg';
      return;
    }
    briefEl.textContent = `${project?.project_type || '-'} | ${project?.status || '-'} | 경비 잔여 ${formatKrw(project?.remaining_amount)}`;
    briefEl.className = 'wf-inline-msg ok';
  };

  projectEl?.addEventListener('change', renderBrief);
  renderBrief();

  document.getElementById(`${cardId}_cancel`)?.addEventListener('click', () => {
    document.getElementById(cardId)?.remove();
    addAssistantMessage('비용정산 작성을 취소했습니다.');
  });

  document.getElementById(`${cardId}_open`)?.addEventListener('click', () => {
    const selected = String(projectEl?.value || '').trim();
    if (!selected) {
      if (briefEl) {
        briefEl.textContent = '프로젝트를 선택해주세요.';
        briefEl.className = 'wf-inline-msg error';
      }
      return;
    }
    const popup = openMockupWindow('/finance/', 'moldubot_finance', {
      project_number: selected,
    });
    if (!popup) {
      addAssistantMessage('비용정산 작성 화면을 열지 못했습니다. 팝업 차단을 해제한 뒤 다시 시도해주세요.');
      return;
    }
    addAssistantMessage('비용정산 작성 화면을 열었습니다.');
  });
}


/* ========================================
   Send Message Helpers (moved from taskpane.js)
   ======================================== */

function resolveStructuredInputMetaForSend(structuredPlan, quickActionMeta) {
  if (structuredPlan) {
    return {
      chips: Array.isArray(structuredPlan.chips) ? structuredPlan.chips.slice(0, 2) : [],
      verbs: Array.isArray(structuredPlan.verbs) ? structuredPlan.verbs.slice(0, 2) : [],
      extra_context: String(structuredPlan.extraContext || '').trim(),
      combo_key: String(structuredPlan.combo?.combo_key || '').trim(),
    };
  }
  if (
    quickActionMeta &&
    quickActionMeta.structured_input &&
    typeof quickActionMeta.structured_input === 'object'
  ) {
    return {
      chips: Array.isArray(quickActionMeta.structured_input.chips)
        ? quickActionMeta.structured_input.chips.slice(0, 2)
        : [],
      verbs: Array.isArray(quickActionMeta.structured_input.verbs)
        ? quickActionMeta.structured_input.verbs.slice(0, 2)
        : [],
      extra_context: String(quickActionMeta.structured_input.extra_context || '').trim(),
      combo_key: String(quickActionMeta.structured_input.combo_key || '').trim(),
    };
  }
  return null;
}

function resolveWeeklyReportSkillRequest(rawMessage = '', normalizedMessage = '', quickActionMeta = null) {
  const raw = String(rawMessage || '').trim();
  const normalized = String(normalizedMessage || '').trim();
  const quickActionId = String(quickActionMeta?.quick_action_id || quickActionMeta?.id || '')
    .trim()
    .toLowerCase();
  const hasQuickActionSignal = ['weekly_report', 'weekly-report', 'weeklyreport'].includes(quickActionId);
  const hasTokenSignal = /(?:^|\s)\/주간보고(?=\s|$)/i.test(raw);
  if (!hasQuickActionSignal && !hasTokenSignal) {
    return {
      enabled: false,
      normalizedMessage: normalized,
      source: '',
    };
  }
  let cleaned = normalized;
  if (hasTokenSignal) {
    cleaned = raw.replace(/(?:^|\s)\/주간보고(?=\s|$)/ig, ' ').trim();
  }
  cleaned = cleaned.replace(/^(?:주간보고(?:\s*작성)?)(?:\s+|$)/i, '').trim();
  if (!cleaned) {
    cleaned = '이전 검색 조건은 무시하고, 발신자 조건 없이 최근 1주 메일 전체를 기준으로 주간보고를 작성해줘.';
  } else if (!/(이전\s*검색\s*조건\s*무시|재검색|다시\s*검색|다시\s*조회)/i.test(cleaned)) {
    cleaned = `이전 검색 조건은 무시하고 ${cleaned}`;
  }
  if (!/(최근\s*1\s*주|1\s*주일|지난\s*1\s*주|last\s*week|past\s*7\s*days|7\s*days)/i.test(cleaned)) {
    cleaned = `최근 1주 메일 전체를 기준으로 ${cleaned}`.trim();
  }
  return {
    enabled: true,
    normalizedMessage: cleaned,
    source: hasQuickActionSignal ? 'quick_action' : 'slash_skill',
  };
}

function applyQuickActionMetaToRuntimePayload(runtimePayload, quickActionMeta) {
  if (!quickActionMeta || typeof quickActionMeta !== 'object') return;
  const quickActionId = String(quickActionMeta.quick_action_id || '').trim().toLowerCase();
  const quickActionLabel = String(quickActionMeta.label || '').trim();
  const quickActionSource = String(quickActionMeta.source || 'ai_quick_action').trim().toLowerCase();
  const replyTone = String(quickActionMeta.reply_tone || '').trim().toLowerCase();
  const replyAdditionalContext = String(quickActionMeta.reply_additional_context || '').trim();
  const searchLimitRaw = Number.parseInt(String(quickActionMeta.search_limit || '').trim(), 10);
  const searchLimit = Number.isFinite(searchLimitRaw) && searchLimitRaw > 0
    ? Math.max(1, Math.min(searchLimitRaw, 20))
    : 0;
  const searchSortMode = normalizeSearchSortMode(quickActionMeta.search_sort_mode || '') || '';
  if (quickActionId) runtimePayload.quick_action_id = quickActionId;
  if (quickActionLabel) runtimePayload.quick_action_label = quickActionLabel;
  if (quickActionSource) runtimePayload.quick_action_source = quickActionSource;
  if (replyTone) runtimePayload.reply_tone = replyTone;
  if (replyAdditionalContext) runtimePayload.reply_additional_context = replyAdditionalContext;
  if (searchLimit > 0) runtimePayload.search_result_limit = searchLimit;
  if (searchSortMode) runtimePayload.search_sort_mode = searchSortMode;
}

function buildSendRuntimePayload({
  effectiveMessage,
  turnKind,
  structuredPlan,
  structuredInputMeta,
  weeklyReportRequest,
  naturalLanguageProbe,
  quickActionMeta,
  scopePrefix,
  domainShortcut,
  emailModeGlobalMailSearchRequest,
  scopedEmailMessageId,
}) {
  const runtimePayload = getRuntimeOptionsPayload();
  const normalizedTurnKind = String(turnKind || '').trim().toLowerCase() || 'task';
  runtimePayload.turn_kind = normalizedTurnKind;
  if (structuredInputMeta) {
    runtimePayload.structured_input = { ...structuredInputMeta };
    const structuredReplyExtra = String(structuredInputMeta.extra_context || '').trim();
    if (structuredReplyExtra) {
      runtimePayload.reply_additional_context = structuredReplyExtra;
    }
  }
  if (structuredPlan && !naturalLanguageProbe.enabled) {
    runtimePayload.execution_tier = 'light';
  }
  if (naturalLanguageProbe.enabled) {
    runtimePayload.force_intent_llm = true;
    runtimePayload.intent_probe = true;
    runtimePayload.intent_probe_parse_slots = true;
  }
  if (structuredPlan?.domain) {
    runtimePayload.shortcut_domain = String(structuredPlan.domain || '').trim().toLowerCase();
    runtimePayload.shortcut_source = 'structured_input';
  }
  const shortcutDomainFromPrefix = normalizeShortcutDomain(
    structuredPlan?.domain || scopePrefix.domain || domainShortcut.domain || ''
  );
  if (shortcutDomainFromPrefix) {
    runtimePayload.shortcut_domain = shortcutDomainFromPrefix;
    runtimePayload.shortcut_source = 'at_prefix';
  }
  if (weeklyReportRequest?.enabled) {
    runtimePayload.quick_action_id = runtimePayload.quick_action_id || 'weekly_report';
    runtimePayload.quick_action_label = runtimePayload.quick_action_label || '주간보고 작성';
    runtimePayload.quick_action_source = runtimePayload.quick_action_source || 'skill_shortcut';
    runtimePayload.execution_tier = 'deep';
    runtimePayload.workflow_contract = {
      id: 'weekly_report_v1',
      progress_style: 'stage_updates',
      output_format: 'markdown',
      download_formats: ['md', 'docx'],
      sections: ['이번주 주요 내용', '핵심 인사이트', '이번주 실적', '다음주 계획', '리스크/요청사항'],
    };
    runtimePayload.followup_policy_action = 'research';
    runtimePayload.followup_refine = false;
    runtimePayload.current_mail_only = false;
    delete runtimePayload.email_message_id;
    if (!String(runtimePayload.additional_requirement || '').trim()) {
      runtimePayload.additional_requirement = '기술 전문가 톤으로 핵심만 간결하게 작성';
    }
  }
  applyQuickActionMetaToRuntimePayload(runtimePayload, quickActionMeta);

  const asksCurrentMailOperation = isCurrentMailScopedOperationMessage(
    effectiveMessage,
    normalizedTurnKind
  );
  const asksExplicitCurrentMailDirective = isExplicitCurrentMailDirective(
    effectiveMessage,
    runtimePayload
  );
  const forceMailboxScope = Boolean(weeklyReportRequest?.enabled);
  const isCurrentMailScoped =
    currentMode === 'email' &&
    normalizeScope(currentScope) === 'email' &&
    !forceMailboxScope &&
    !emailModeGlobalMailSearchRequest &&
    asksCurrentMailOperation &&
    Boolean(scopedEmailMessageId);

  runtimePayload.current_mail_only = forceMailboxScope
    ? false
    : (isCurrentMailScoped || asksExplicitCurrentMailDirective);
  if (isCurrentMailScoped) {
    runtimePayload.email_message_id = scopedEmailMessageId;
  } else if (!forceMailboxScope && asksExplicitCurrentMailDirective) {
    const structuredInput = runtimePayload.structured_input && typeof runtimePayload.structured_input === 'object'
      ? { ...runtimePayload.structured_input }
      : {};
    const chips = Array.isArray(structuredInput.chips) ? [...structuredInput.chips] : [];
    if (!chips.some((chip) => String(chip || '').trim().toLowerCase() === 'current_mail')) {
      chips.push('current_mail');
    }
    structuredInput.chips = chips;
    runtimePayload.structured_input = structuredInput;
    delete runtimePayload.email_message_id;
  } else {
    delete runtimePayload.email_message_id;
  }

  const shouldEnableStickyCurrentMailContext =
    currentMode === 'email'
    && normalizeScope(currentScope) === 'email'
    && !forceMailboxScope
    && !emailModeGlobalMailSearchRequest;
  const stickySource =
    structuredPlan
      ? 'structured_input'
      : String(scopePrefix?.scope || '').trim().toLowerCase() === 'email'
        ? 'scope_prefix'
        : quickActionMeta
          ? 'quick_action'
          : 'runtime';

  if (typeof maybeSeedStickyCurrentMailContextFromRuntime === 'function') {
    maybeSeedStickyCurrentMailContextFromRuntime(runtimePayload, {
      source: stickySource,
      clearWhenDisabled: !shouldEnableStickyCurrentMailContext,
      clearReason: 'scope_or_query_changed',
    });
  }
  if (typeof applyStickyCurrentMailContextToRuntime === 'function') {
    applyStickyCurrentMailContextToRuntime(runtimePayload, {
      allow: shouldEnableStickyCurrentMailContext,
    });
  }

  return runtimePayload;
}

function isCurrentMailScopedOperationMessage(message = '', turnKind = '') {
  const rawMessage = String(message || '');
  const normalizedMessage = rawMessage.replace(/\s+/g, '');
  const hasExplicitCurrentMailDirective =
    /(?:@?현재\s*(?:선택한\s*)?메일|@?현제\s*(?:선택한\s*)?메일|@?혅재\s*(?:선택한\s*)?메일|@?이\s*메일)/i.test(rawMessage) ||
    /(?:@?현재메일|@?현제메일|@?혅재메일|currentmail|selectedmail|thismail|thisemail)/i.test(normalizedMessage);
  if (hasExplicitCurrentMailDirective) return true;

  const hasMailboxSearchPhrase =
    /(?:메일|이메일)\s*(?:조회|검색|찾(?:아|기))|사서함|inbox|recent\s*mail|recent\s*email/i.test(rawMessage);

  return (
    (
      /(?:메일|이메일|본문|요약|분석|번역|리스크|체크리스트|수신자|답변|translate|summary|report|insight)/i.test(
        rawMessage
      ) &&
      !hasMailboxSearchPhrase
    ) ||
    String(turnKind || '').trim().toLowerCase() === 'followup_refine'
  );
}

function hasCurrentMailStructuredChip(runtimePayload = {}) {
  const payload = runtimePayload && typeof runtimePayload === 'object' ? runtimePayload : {};
  const structuredInput = payload.structured_input;
  if (!structuredInput || typeof structuredInput !== 'object') return false;
  const chips = Array.isArray(structuredInput.chips) ? structuredInput.chips : [];
  return chips.some((chip) => String(chip || '').trim().toLowerCase() === 'current_mail');
}

function isExplicitCurrentMailDirective(message = '', runtimePayload = {}) {
  if (hasCurrentMailStructuredChip(runtimePayload)) return true;
  return /(?:현재\s*메일|현재메일|이\s*메일)/i.test(String(message || ''));
}

async function resolveIntentPayloadForSend({
  turnKind,
  naturalLanguageProbe,
  structuredPlan,
  structuredWorkflowIntent,
  structuredWorkflowAutoExecute,
  effectiveMessage,
  runtimePayload,
  scopedEmailMessageId,
  normalizedRawMessage,
}) {
  const skipIntentResolve = String(turnKind || '').trim().toLowerCase() === 'explicit_smalltalk';
  const useLocalStructuredWorkflowFastPath =
    !skipIntentResolve &&
    Boolean(structuredPlan) &&
    Boolean(structuredWorkflowIntent?.intent) &&
    structuredWorkflowAutoExecute;
  const localStructuredIntentCandidate =
    !skipIntentResolve && structuredPlan
      ? (
        buildLocalStructuredWorkflowIntentFromPlan(structuredPlan) ||
        buildLocalMailSearchEntryIntentFromStructuredPlan(structuredPlan)
      )
      : null;
  const preferLocalStructuredFastPath =
    !useLocalStructuredWorkflowFastPath &&
    Boolean(localStructuredIntentCandidate) &&
    Boolean(structuredPlan) &&
    !naturalLanguageProbe.enabled;
  const usedLocalStructuredFastPath = useLocalStructuredWorkflowFastPath || preferLocalStructuredFastPath;
  const intentResolveStartedAt = Date.now();
  const intentResolveTimeoutMs = naturalLanguageProbe.enabled ? 12000 : undefined;
  const backendResolvedIntentPayload = skipIntentResolve
    ? null
    : usedLocalStructuredFastPath
      ? localStructuredIntentCandidate
      : naturalLanguageProbe.enabled
        ? await resolveIntentPayloadForMessage(effectiveMessage, runtimePayload, { scope: currentScope, emailMessageId: scopedEmailMessageId, currentMailOnly: Boolean(scopedEmailMessageId), timeoutMs: intentResolveTimeoutMs })
        : null;
  const intentResolveElapsedMs = Date.now() - intentResolveStartedAt;
  if (useLocalStructuredWorkflowFastPath) {
    logEvent('intent.resolve.fastpath.local_structured_workflow', 'ok', {
      mode: currentMode,
      scope: normalizeScope(currentScope),
      intent: String(structuredWorkflowIntent?.intent || '').trim().toLowerCase(),
      message_len: normalizedRawMessage.length,
    });
  }
  if (preferLocalStructuredFastPath) {
    logEvent('intent.resolve.fastpath.local_structured', 'ok', {
      mode: currentMode,
      scope: normalizeScope(currentScope),
      message_len: normalizedRawMessage.length,
    });
  }
  const fallbackStructuredIntentPayload =
    !skipIntentResolve && !usedLocalStructuredFastPath && !backendResolvedIntentPayload
      ? (
        buildLocalStructuredWorkflowIntentFromPlan(structuredPlan) ||
        buildLocalMailSearchEntryIntentFromStructuredPlan(structuredPlan)
      )
      : null;
  if (fallbackStructuredIntentPayload) {
    logEvent('intent.resolve.fallback.local_structured', 'ok', {
      mode: currentMode,
      scope: normalizeScope(currentScope),
      message_len: normalizedRawMessage.length,
    });
  }
  return {
    resolvedIntentPayload: backendResolvedIntentPayload || fallbackStructuredIntentPayload,
    intentResolveElapsedMs,
  };
}

async function buildSendFullMessage({
  outboundMessage,
  emailModeGlobalMailSearchRequest,
  turnKind,
  shouldAutoComposeCurrentMailScheduleMessage,
  weeklyReportRequest,
}) {
  let fullMessage = outboundMessage;
  let requestEmailId = null;
  const getCurrentMailboxItemId = () => {
    try {
      return String(Office?.context?.mailbox?.item?.itemId || '').trim();
    } catch (error) {
      return '';
    }
  };
  const resolveRequestEmailId = async ({ preferLiveItem = false } = {}) => {
    void preferLiveItem;
    const liveItemId = getCurrentMailboxItemId();
    if (!liveItemId) return '';
    if (typeof toRestId === 'function') {
      const restId = String(toRestId(liveItemId) || '').trim();
      if (restId) return restId;
    }
    return liveItemId;
  };
  const asksCurrentMailOperation = isCurrentMailScopedOperationMessage(outboundMessage, turnKind);
  if (
    !weeklyReportRequest?.enabled &&
    currentMode === 'email' &&
    !emailModeGlobalMailSearchRequest &&
    asksCurrentMailOperation &&
    String(turnKind || '').trim().toLowerCase() !== 'explicit_smalltalk'
  ) {
    if (!emailContext && typeof loadEmailContext === 'function') {
      try {
        await Promise.race([
          loadEmailContext(),
          new Promise((resolve) => setTimeout(resolve, 3500)),
        ]);
      } catch (error) {
        workflowLogError('mail.context.prefill_load.failed', error);
      }
    }
    const liveItemId = getCurrentMailboxItemId();
    const contextItemId = String(emailContext?.itemId || '').trim();
    const hasLiveContextMismatch = Boolean(
      liveItemId && contextItemId && liveItemId !== contextItemId
    );
    requestEmailId = await resolveRequestEmailId({
      preferLiveItem: hasLiveContextMismatch,
    });
    if (!requestEmailId && typeof loadEmailContext === 'function') {
      try {
        await Promise.race([
          loadEmailContext(),
          new Promise((resolve) => setTimeout(resolve, 3000)),
        ]);
      } catch (error) {
        workflowLogError('mail.context.id_retry_load.failed', error);
      }
      requestEmailId = await resolveRequestEmailId();
    }

    if (hasLiveContextMismatch) {
      workflowLogEvent('mail.context.mismatch.at_send', 'warn', {
        live_item_prefix: liveItemId.slice(0, 24),
        context_item_prefix: contextItemId.slice(0, 24),
        has_request_email_id: Boolean(String(requestEmailId || '').trim()),
      });
    }

    const runtimeMailContextPayload = {
      subject: emailContext?.subject || 'N/A',
      from: emailContext?.from || 'N/A',
    };
    if (requestEmailId) {
      runtimeMailContextPayload.message_id = requestEmailId;
    }
    if (emailContext && !hasLiveContextMismatch) {
      fullMessage = `${outboundMessage}\n\n[메일 컨텍스트]\n${JSON.stringify(runtimeMailContextPayload)}`;
    }
    const summaryKeywords = ['요약', '내용', '본문', '자세히', '상세'];
    const shouldAttachBodyPreview =
      !shouldAutoComposeCurrentMailScheduleMessage &&
      summaryKeywords.some((kw) => outboundMessage.includes(kw));
    if (shouldAttachBodyPreview && emailContext?.body) {
      runtimeMailContextPayload.body_preview = String(emailContext.body || '');
      fullMessage = `${outboundMessage}\n\n[메일 컨텍스트]\n${JSON.stringify(runtimeMailContextPayload)}`;
    }
  }
  return { fullMessage, requestEmailId };
}

function maybeHandleIntentProbeOutput({
  naturalLanguageProbe,
  probeScopedMessage,
  resolvedIntentPayload,
  intentResolveElapsedMs,
  abortBeforeRequest,
}) {
  if (!naturalLanguageProbe?.enabled) return false;
  abortBeforeRequest();
  addAssistantMessage(
    buildIntentProbeResultText(
      probeScopedMessage,
      resolvedIntentPayload,
      intentResolveElapsedMs
    ),
    { save: false }
  );
  logEvent('intent.resolve.probe.complete', 'ok', {
    elapsed_ms: intentResolveElapsedMs,
    intent: String(
      resolvedIntentPayload?.intent || resolvedIntentPayload?.primary_intent || 'unknown'
    ).toLowerCase(),
    has_payload: Boolean(resolvedIntentPayload),
  });
  return true;
}

function maybeInterceptResolvedIntentActions({
  resolvedIntentUiAction,
  quickActionMeta,
  structuredInputMeta,
  resolvedIntentPayload,
  normalizedRawMessage,
  abortBeforeRequest,
}) {
  if (resolvedIntentUiAction === 'open_reply_tone_picker' && !toBool(quickActionMeta?.skipReplyToneIntercept)) {
    abortBeforeRequest();
    openReplyTonePickerCard(structuredInputMeta ? { structured_input: structuredInputMeta } : null);
    logEvent('chat.send.intercept.reply_tone', 'ok', {
      mode: currentMode,
      intent: String(
        resolvedIntentPayload?.intent || resolvedIntentPayload?.primary_intent || ''
      ).toLowerCase(),
      message_len: normalizedRawMessage.length,
    });
    return true;
  }

  return false;
}

function maybeApplyAutoComposedScheduleMessage({
  turnKind,
  structuredPlan,
  structuredWorkflowAutoExecute,
  structuredWorkflowIntent,
  resolvedIntentUiAction,
  outboundMessage,
  runtimePayload,
}) {
  const shouldAutoComposeCurrentMailScheduleMessage =
    currentMode === 'email' &&
    Boolean(emailContext) &&
    String(turnKind || '').trim().toLowerCase() !== 'explicit_smalltalk' &&
    Boolean(structuredPlan) &&
    structuredWorkflowAutoExecute &&
    String(structuredWorkflowIntent?.intent || '').trim().toLowerCase() === 'schedule_create' &&
    String(resolvedIntentUiAction || '').trim().toLowerCase() === 'open_schedule_draft';
  if (!shouldAutoComposeCurrentMailScheduleMessage) {
    return {
      outboundMessage,
      shouldAutoComposeCurrentMailScheduleMessage,
    };
  }

  const autoScheduleMessage = buildAutoScheduleRegistrationMessage({
    emailCtx: emailContext,
  });
  if (autoScheduleMessage) {
    outboundMessage = autoScheduleMessage;
    // 일정 자동 등록 경로에서는 요약/분석 신호를 제거해 deep 분석 lane으로 빠지지 않게 한다.
    runtimePayload.reply_additional_context = '';
    runtimePayload.additional_requirement = '';
    if (runtimePayload.structured_input && typeof runtimePayload.structured_input === 'object') {
      runtimePayload.structured_input = {
        chips: ['current_mail', 'schedule'],
        verbs: ['register'],
        extra_context: '',
        combo_key: 'current_mail+schedule|register',
      };
    }
    logEvent('chat.send.autofill.schedule_message', 'ok', {
      mode: currentMode,
      chars: autoScheduleMessage.length,
    });
  }

  return {
    outboundMessage,
    shouldAutoComposeCurrentMailScheduleMessage,
  };
}

/* =========================================
   Approval Flow (confirm_required)
   ========================================= */

function compactConfirmAnswerText(text) {
  const normalized = String(text || '')
    .replace(
      /((?:메일\s*ID|message[\s_-]*id|internet[\s_-]*message[\s_-]*id|id)\s*[:：]\s*)([A-Za-z0-9+/_=-]{16,})/gi,
      '$1[REDACTED]'
    )
    .replace(/([A-Za-z0-9+/_=-]{64,})/g, '[REDACTED]')
    .replace(/\\[nrt]/g, ' ')
    .replace(/\[메일\s*컨텍스트\]/gi, ' ')
    .replace(/사용자\s*확인이\s*필요합니다\.?\s*도구를\s*실행하기\s*전에\s*승인해주세요\.?/gi, '')
    .replace(/\s+/g, ' ')
    .trim();
  if (!normalized) return '실행 전에 승인 여부를 확인해주세요.';
  if (normalized.length <= 180) return normalized;
  return `${normalized.slice(0, 180)}...`;
}

function buildConfirmToolSummaryLines(toolCalls = []) {
  const lines = [];
  for (const tc of toolCalls || []) {
    if (!tc || typeof tc !== 'object') continue;
    const toolLabel = TOOL_LABELS[tc.name] || String(tc.name || '작업').trim() || '작업';
    const parts = [];
    if (tc.args && typeof tc.args === 'object') {
      for (const [key, value] of Object.entries(tc.args)) {
        if (value === null || value === undefined || value === '') continue;
        const label = ARG_LABELS[key] || key;
        const formatted = formatArgValue(key, value);
        const compact = String(formatted || '').replace(/\s+/g, ' ').trim();
        if (!compact) continue;
        const clipped = compact.length > 120 ? `${compact.slice(0, 117)}...` : compact;
        parts.push(`${label}: ${clipped}`);
      }
    }
    if (parts.length) lines.push(`- ${toolLabel} — ${parts.join(', ')}`);
    else lines.push(`- ${toolLabel}`);
  }
  return lines;
}

function handleConfirmRequired(data) {
  const threadId = data.thread_id || chatThreadId;
  const toolCalls = data.tool_calls || [];
  const answer = compactConfirmAnswerText(data.answer || '');
  const confirmToken =
    (typeof data?.confirm_token === 'string' && data.confirm_token) ||
    (typeof data?.metadata?.confirm?.token === 'string' && data.metadata.confirm.token) ||
    '';
  const confirmTokenEncoded = encodeURIComponent(confirmToken);
  const cardId = 'approval_' + Date.now();

  const chatArea = document.getElementById('chatArea');

  const summaryLines = buildConfirmToolSummaryLines(toolCalls);
  const summaryMarkdown = summaryLines.length ? `실행 예정 작업:\n${summaryLines.join('\n')}` : '';

  const messageHtml = `
    <div class="message assistant">
      <div class="msg-body">
        <p class="assistant-confirm-status" id="${cardId}_status">실행 전에 승인 여부를 확인해주세요.</p>
        ${answer ? `<div class="assistant-confirm-block">${renderMarkdown(answer)}</div>` : ''}
        ${summaryMarkdown ? `<div class="assistant-confirm-block">${renderMarkdown(summaryMarkdown)}</div>` : ''}
        <div class="assistant-confirm-inline" id="${cardId}">
          <div class="approval-actions" id="${cardId}_actions">
            <button class="approval-btn reject" onclick="rejectAction('${cardId}', '${threadId}', '${confirmTokenEncoded}')">
              ${ICONS.x} 거절
            </button>
            <button class="approval-btn approve" onclick="approveAction('${cardId}', '${threadId}', '${confirmTokenEncoded}')">
              ${ICONS.check} 승인
            </button>
          </div>
        </div>
      </div>
    </div>`;

  chatArea.insertAdjacentHTML('beforeend', messageHtml);
  scrollToBottom();
  recordHistory('assistant', answer || '실행 확인이 필요합니다.');
  persistTaskpaneState();
}

async function approveAction(cardId, threadId, confirmTokenEncoded = '') {
  setApprovalButtonsDisabled(cardId, true);
  replaceApprovalActions(cardId, '<div class="approval-done approved">승인 처리 중...</div>');

  try {
    const confirmToken = decodeURIComponent(String(confirmTokenEncoded || ''));
    const payload = { thread_id: threadId, approved: true };
    if (confirmToken) payload.confirm_token = confirmToken;
    const response = await apiFetch('/search/chat/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }, 60000);

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = String(data?.detail || `HTTP ${response.status}`);
      throw new Error(detail);
    }

    if (data?.status === 'confirm_required') {
      replaceApprovalActions(cardId, `<div class="approval-done approved">${ICONS.check} 1차 승인 완료</div>`);
      setApprovalCardResolved(cardId, 'approved', '추가 실행 확인 필요');
      handleConfirmRequired(data);
      persistTaskpaneState();
      return;
    }

    const noPending = Boolean(data?.metadata?.confirm?.no_pending_confirmation);
    if (noPending) {
      replaceApprovalActions(cardId, '<div class="approval-done rejected">승인 대기 작업이 없습니다.</div>');
      setApprovalCardResolved(cardId, 'rejected', '처리 대상 없음');
      resolveLatestConfirmWorkflow('승인 대기 작업이 없어 종료했습니다.');
    } else {
      replaceApprovalActions(cardId, `<div class="approval-done approved">${ICONS.check} 승인 완료</div>`);
      setApprovalCardResolved(cardId, 'approved', '실행 완료');
      resolveLatestConfirmWorkflow('승인된 작업을 실행 완료했습니다.');
    }
    const confirmMetadata =
      data?.metadata && typeof data.metadata === 'object' ? data.metadata : null;
    const confirmUiOutput = confirmMetadata?.ui_output || data?.ui_output || null;

    addAssistantMessage(data?.answer || '작업이 완료되었습니다.', {
      allowForward: true,
      metadata: confirmMetadata,
      uiOutput: confirmUiOutput,
    });
  } catch (error) {
    logError('approval.approve.failed', error, { thread_id: threadId });
    replaceApprovalActions(cardId, '<div class="approval-done rejected">처리 중 오류가 발생했습니다.</div>');
    setApprovalCardResolved(cardId, 'rejected', '처리 실패');
    failLatestConfirmWorkflow('승인 처리 실패');
  }
  persistTaskpaneState();
}

async function rejectAction(cardId, threadId, confirmTokenEncoded = '') {
  setApprovalButtonsDisabled(cardId, true);

  try {
    const confirmToken = decodeURIComponent(String(confirmTokenEncoded || ''));
    const payload = { thread_id: threadId, approved: false };
    if (confirmToken) payload.confirm_token = confirmToken;
    await apiFetch('/search/chat/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }, 30000);
  } catch (e) {
    logError('approval.reject.failed', e, { thread_id: threadId });
  }

  replaceApprovalActions(cardId, `<div class="approval-done rejected">${ICONS.x} 취소됨</div>`);
  setApprovalCardResolved(cardId, 'rejected', '요청 취소됨');
  resolveLatestConfirmWorkflow('요청이 취소되어 워크플로우를 종료했습니다.');
  persistTaskpaneState();
}

function setApprovalButtonsDisabled(cardId, disabled) {
  const actions = document.getElementById(cardId + '_actions');
  if (!actions) return;
  actions.querySelectorAll('button').forEach((btn) => (btn.disabled = disabled));
}

function replaceApprovalActions(cardId, html) {
  const actionsId = cardId + '_actions';
  const actions = document.getElementById(actionsId);
  if (actions) {
    actions.innerHTML = html;
    return;
  }
  const card = document.getElementById(cardId);
  const fallbackTarget =
    card?.querySelector('.approval-actions') || card?.querySelector('.approval-done');
  if (!fallbackTarget) return;
  fallbackTarget.outerHTML = `<div class="approval-actions" id="${actionsId}">${html}</div>`;
}

function setApprovalCardResolved(cardId, state = 'approved', title = '실행 완료') {
  const card = document.getElementById(cardId);
  const statusText = String(title || (state === 'rejected' ? '요청 취소됨' : '실행 완료')).trim();
  const statusEl = document.getElementById(`${cardId}_status`);
  if (statusEl) {
    statusEl.textContent = statusText;
    return;
  }
  if (!card) return;
  const header = card.querySelector('.approval-header');
  if (!header) return;
  if (state === 'rejected') {
    header.innerHTML = `${ICONS.x} ${escapeHtml(statusText || '요청 취소됨')}`;
    return;
  }
  header.innerHTML = `${ICONS.check} ${escapeHtml(statusText || '실행 완료')}`;
}

function findLatestDeepProgressTrackerByState(state = 'confirm') {
  const target = String(state || '').trim().toLowerCase();
  let selected = null;
  for (const [id, tracker] of deepProgressTrackerRegistry.entries()) {
    if (!tracker || typeof tracker !== 'object') {
      deepProgressTrackerRegistry.delete(id);
      continue;
    }
    if (!document.getElementById(String(tracker.id || id))) {
      deepProgressTrackerRegistry.delete(id);
      continue;
    }
    if (String(tracker.finalState || '').trim().toLowerCase() !== target) continue;
    if (!selected || Number(tracker.startedAt || 0) > Number(selected.startedAt || 0)) {
      selected = tracker;
    }
  }
  return selected;
}

function resolveLatestConfirmWorkflow(note = '승인 처리 완료') {
  const tracker = findLatestDeepProgressTrackerByState('confirm');
  if (!tracker) return;
  finishDeepProgressCard(tracker, {
    finalState: 'done',
    note: String(note || '').trim() || '승인 처리 완료',
  });
}

function failLatestConfirmWorkflow(note = '승인 처리 중 오류가 발생했습니다.') {
  const tracker = findLatestDeepProgressTrackerByState('confirm');
  if (!tracker) return;
  finishDeepProgressCard(tracker, {
    finalState: 'error',
    note: String(note || '').trim() || '승인 처리 중 오류가 발생했습니다.',
  });
}

globalThis.handleConfirmRequired = handleConfirmRequired;
globalThis.approveAction = approveAction;
globalThis.rejectAction = rejectAction;

function normalizeClarificationComparableText(value) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .replace(/[.!?]+$/g, '')
    .trim()
    .toLowerCase();
}

function shouldSuppressClarificationAssistantMessage(answerText, clarificationPayload = null) {
  const payload = clarificationPayload && typeof clarificationPayload === 'object'
    ? clarificationPayload
    : null;
  if (!payload) return false;

  const normalizedAnswer = normalizeClarificationComparableText(answerText);
  if (!normalizedAnswer) return true;

  const normalizedQuestion = normalizeClarificationComparableText(payload.question || '');
  if (!normalizedQuestion) return false;

  // clarification 카드 질문을 그대로 본문으로 반복하는 경우 본문은 생략한다.
  if (normalizedAnswer === normalizedQuestion) return true;
  if (normalizedAnswer.includes(normalizedQuestion) && normalizedAnswer.length <= normalizedQuestion.length + 24) {
    return true;
  }
  return false;
}

function handleSendSuccessResponse({
  data,
  effectiveMessage,
  weeklyReportRequest,
}) {
  if (data.status === 'confirm_required') {
    if (typeof hideClarificationPromptCard === 'function') {
      hideClarificationPromptCard();
    }
    logEvent('chat.send.confirm_required', 'ok', {
      tool_calls: Array.isArray(data.tool_calls) ? data.tool_calls.length : 0,
    });
    handleConfirmRequired(data);
    return;
  }

  const shouldOfferReply =
    currentMode === 'email' && isReplyDraftRequest(effectiveMessage);
  const responseMetadata = data?.metadata && typeof data.metadata === 'object' ? data.metadata : {};
  const responseUiOutput = responseMetadata?.ui_output || data?.ui_output || null;
  const clarificationPayload =
    typeof syncClarificationPromptFromResponse === 'function'
      ? syncClarificationPromptFromResponse(data)
      : null;
  const shouldSuppressAnswer =
    shouldSuppressClarificationAssistantMessage(data?.answer || '', clarificationPayload);
  const isWeeklyReportResponse =
    Boolean(weeklyReportRequest?.enabled) ||
    String(responseMetadata?.runtime_context?.quick_action_id || '').trim().toLowerCase() === 'weekly_report' ||
    String(responseMetadata?.runtime_context?.workflow_contract?.id || '').trim().toLowerCase() === 'weekly_report_v1';
  const forcedWeeklyCardText =
    String(responseMetadata?.ui_output_v2?.body?.text || responseMetadata?.uiOutputV2?.body?.text || '').trim()
    || String(data?.answer || '').trim()
    || '주간보고 생성이 완료되었습니다.';
  if (isWeeklyReportResponse || !shouldSuppressAnswer) {
    addAssistantMessage(isWeeklyReportResponse ? forcedWeeklyCardText : (data.answer || '응답을 받지 못했습니다.'), {
      metadata: data.metadata || null,
      replyDraft: shouldOfferReply,
      uiOutput: responseUiOutput,
      allowForward: true,
    });
  } else {
    logEvent('chat.send.clarification_answer_suppressed', 'ok', {
      answer_len: String(data?.answer || '').length,
      has_question: Boolean(String(clarificationPayload?.question || '').trim()),
    });
  }
  // 메일 검색 조건 카드는 요청 전 인터셉트 단계에서만 노출한다.
  // 응답 완료 후 metadata 기반 재표시는 답변 뒤늦은 카드 노출(순서 역전) 이슈를 만든다.
  logEvent('chat.send.completed', 'ok', {
    answer_len: String(data.answer || '').length,
    ui_output_type: String(responseUiOutput?.type || ''),
  });
}

function buildSendRequestPayload({
  fullMessage,
  runtimePayload,
  resolvedIntentPayload,
  requestEmailId,
  emailModeGlobalMailSearchRequest,
  useThinkingProgress,
}) {
  const normalizedRuntimePayload =
    runtimePayload && typeof runtimePayload === 'object' ? runtimePayload : {};
  if (typeof consumeStickyCurrentMailContextFromPayload === 'function') {
    consumeStickyCurrentMailContextFromPayload(normalizedRuntimePayload, {
      reason: 'chat_send',
    });
  } else if (Object.prototype.hasOwnProperty.call(normalizedRuntimePayload, '__sticky_current_mail_applied')) {
    delete normalizedRuntimePayload.__sticky_current_mail_applied;
  }

  const payload = {
    message: fullMessage,
    thread_id: chatThreadId,
    runtime_options: normalizedRuntimePayload,
    intent_name: undefined,
  };
  const prefetchedRoute = buildPrefetchedRouteFromResolvedIntent(resolvedIntentPayload);
  if (prefetchedRoute) {
    payload.prefetched_route = prefetchedRoute;
  }
  const runtimeEmailMessageId = String(
    (payload.runtime_options && payload.runtime_options.email_message_id) || ''
  ).trim();
  const resolvedRequestEmailId = String(requestEmailId || runtimeEmailMessageId || '').trim();
  const shouldBindCurrentMailContext = Boolean(resolvedRequestEmailId) && !emailModeGlobalMailSearchRequest;
  if (shouldBindCurrentMailContext) {
    payload.email_id = resolvedRequestEmailId;
    if (payload.runtime_options && typeof payload.runtime_options === 'object') {
      payload.runtime_options.email_message_id = resolvedRequestEmailId;
      payload.runtime_options.current_mail_only = true;
    }
  } else if (
    payload.runtime_options &&
    typeof payload.runtime_options === 'object' &&
    toBool(payload.runtime_options.current_mail_only)
  ) {
    const structuredInput =
      payload.runtime_options.structured_input && typeof payload.runtime_options.structured_input === 'object'
        ? { ...payload.runtime_options.structured_input }
        : {};
    const chips = Array.isArray(structuredInput.chips) ? [...structuredInput.chips] : [];
    if (!chips.some((chip) => String(chip || '').trim().toLowerCase() === 'current_mail')) {
      chips.push('current_mail');
    }
    structuredInput.chips = chips;
    payload.runtime_options.structured_input = structuredInput;
  } else if (emailModeGlobalMailSearchRequest && payload.runtime_options && typeof payload.runtime_options === 'object') {
    payload.runtime_options.current_mail_only = false;
    delete payload.runtime_options.email_message_id;
  }

  logEvent('chat.send.model_call', 'ok', {
    mode: currentMode,
    hasEmailContext: Boolean(emailContext),
    hasEmailId: Boolean(payload.email_id),
    email_mode_global_mail_search: emailModeGlobalMailSearchRequest,
    apiBase: API_BASE,
    thinking_ui: useThinkingProgress,
    prefetched_route: Boolean(payload.prefetched_route),
  });
  return payload;
}

async function requestChatDataWithRetry({
  payload,
  useThinkingProgress,
  deepProgressTracker,
  streamingAssistant,
  emailModeGlobalMailSearchRequest,
  weeklyReportRequest,
}) {
  const invokeChatRequest = async (requestPayload) =>
    useThinkingProgress
      ? requestChatStream(requestPayload, {
          onEvent: (eventData) => {
            if (weeklyReportRequest?.enabled && typeof updateWeeklyReportBuildToast === 'function') {
              updateWeeklyReportBuildToast(eventData);
            }
            if (deepProgressTracker) {
              applyDeepProgressEvent(deepProgressTracker, eventData);
              scheduleDeepProgressRender(deepProgressTracker);
            }
            if (ENABLE_PARTIAL_ANSWER_STREAM && streamingAssistant && eventData && typeof eventData === 'object') {
              const eventType = String(eventData.type || '').trim().toLowerCase();
              if (eventType === 'partial_answer') {
                const accumulated = typeof eventData.accumulated === 'string'
                  ? eventData.accumulated
                  : null;
                if (accumulated !== null) {
                  updateStreamingAssistantMessage(streamingAssistant, accumulated, { append: false });
                } else {
                  updateStreamingAssistantMessage(streamingAssistant, String(eventData.text || ''), { append: true });
                }
              }
            }
          },
        })
      : requestChat(requestPayload);

  let data = await invokeChatRequest(payload);
  const isNotFoundAnswer =
    data?.status !== 'confirm_required' && isLikelyEmailNotFoundAnswer(data?.answer || '');
  if (currentMode === 'email' && !emailModeGlobalMailSearchRequest && isNotFoundAnswer) {
    logEvent('chat.send.retry_mail_context', 'warn', {
      reason: 'mail_not_found_answer',
    });
    if (streamingAssistant) {
      resetStreamingAssistantMessage(streamingAssistant);
    }
    const refreshedId = await forceRefreshResolvedEmailId();
    if (refreshedId) {
      payload.email_id = refreshedId;
    }
    data = await invokeChatRequest(payload);
  }
  return data;
}

function resolveSendNormalizedInput({
  rawMessage,
  input,
  quickActionMeta,
}) {
  const naturalLanguageProbe = parseNaturalLanguageIntentProbe(rawMessage);
  const probeScopedMessage = String(naturalLanguageProbe.message || '').trim();
  const messageForRouting = naturalLanguageProbe.enabled ? probeScopedMessage : rawMessage;
  if (naturalLanguageProbe.enabled && !probeScopedMessage) {
    addSystemMessage('`@자연어` 뒤에 분석할 문장을 입력해 주세요.');
    return { aborted: true };
  }

  const structuredPlan = naturalLanguageProbe.enabled ? null : buildStructuredLegacyMessage(messageForRouting);
  const scopedRawMessage = structuredPlan ? structuredPlan.legacyMessage : messageForRouting;
  const domainShortcut = parseDomainShortcutFromPrefix(scopedRawMessage);
  const scopePrefix = parseScopeFromMessagePrefix(scopedRawMessage);
  const resolvedScope = structuredPlan?.scope || scopePrefix.scope;
  if (resolvedScope) {
    const scopeDomain = String(scopePrefix.domain || '').trim().toLowerCase();
    const structuredDomain = String(structuredPlan?.domain || '').trim().toLowerCase();
    const overrideDomain = structuredDomain || scopeDomain || domainShortcut.domain;
    switchScope(resolvedScope, {
      labelOverride: resolveSystemScopeLabelOverride(overrideDomain),
    });
  }

  let normalizedRawMessage = structuredPlan
    ? String(structuredPlan.legacyMessage || '').trim()
    : String(scopePrefix.message || '').trim();
  if (!structuredPlan && normalizedRawMessage.startsWith('/')) {
    normalizedRawMessage = normalizedRawMessage.replace(/^\/+/, '').trim();
  }
  const weeklyReportRequest = resolveWeeklyReportSkillRequest(
    rawMessage,
    normalizedRawMessage,
    quickActionMeta
  );
  if (weeklyReportRequest.enabled) {
    normalizedRawMessage = weeklyReportRequest.normalizedMessage;
  }
  const domainOnlyShortcut =
    !structuredPlan &&
    !normalizedRawMessage &&
    Boolean(scopePrefix.scope) &&
    Boolean(normalizeShortcutDomain(scopePrefix.domain || domainShortcut.domain));
  if (domainOnlyShortcut) {
    // "@실행예산" 같은 도메인 단독 입력은 가드에서 막지 않고 후속 의도 해석 단계로 넘긴다.
    normalizedRawMessage = String(messageForRouting || '').trim();
  }
  if (!normalizedRawMessage) {
    addSystemMessage(`범위를 "${scopeDisplayLabel(currentScope)}"(으)로 설정했습니다. 이어서 요청 내용을 입력해 주세요.`);
    input.value = '';
    autoResize(input);
    updateStructuredSelectionBadges();
    persistTaskpaneState();
    return { aborted: true };
  }

  const effectiveMessage =
    currentMode === 'assistant' ? normalizeAssistantPrompt(normalizedRawMessage) : normalizedRawMessage;

  return {
    aborted: false,
    naturalLanguageProbe,
    probeScopedMessage,
    structuredPlan,
    scopePrefix,
    domainShortcut,
    normalizedRawMessage,
    effectiveMessage,
    weeklyReportRequest,
  };
}

function initializeSendPreflightState({
  input,
  structuredPlan,
  rawMessage,
  normalizedRawMessage,
  displayUserMessage = '',
  turnKind,
}) {
  const welcome = document.getElementById('welcomeState');
  if (welcome) welcome.remove();

  const userMessageForDisplay = String(displayUserMessage || '').trim()
    || (structuredPlan ? rawMessage : normalizedRawMessage);
  addUserMessage(userMessageForDisplay);
  input.value = '';
  autoResize(input);
  updateStructuredSelectionBadges();
  persistTaskpaneState();
  isProcessing = true;
  setSendButtonState(false);

  let preflightTypingEl = null;
  const clearPreflightTyping = () => {
    if (preflightTypingEl) {
      removeTyping(preflightTypingEl);
      preflightTypingEl = null;
    }
  };
  const abortBeforeRequest = () => {
    clearPreflightTyping();
    isProcessing = false;
    setSendButtonState(true);
  };

  if (String(turnKind || '').trim().toLowerCase() !== 'explicit_smalltalk') {
    preflightTypingEl = showTyping();
  }

  return {
    preflightTypingEl,
    clearPreflightTyping,
    abortBeforeRequest,
  };
}

async function refreshEmailContextBeforeSendIfNeeded({
  turnKind,
  effectiveMessage = '',
}) {
  if (
    currentMode !== 'email' ||
    String(turnKind || '').trim().toLowerCase() === 'explicit_smalltalk'
  ) {
    return;
  }
  const getCurrentMailboxItemId = () => {
    try {
      return String(Office?.context?.mailbox?.item?.itemId || '').trim();
    } catch (error) {
      return '';
    }
  };
  try {
    const shouldResolveCurrentMailId =
      normalizeScope(currentScope) === 'email' &&
      isCurrentMailScopedOperationMessage(effectiveMessage, turnKind);
    const currentItemId = getCurrentMailboxItemId();
    const contextItemId = String(emailContext?.itemId || '').trim();
    const shouldForceReloadContext =
      !contextItemId || !currentItemId || contextItemId !== currentItemId;

    if (shouldForceReloadContext) {
      await Promise.race([
        loadEmailContext(),
        new Promise((resolve) => setTimeout(resolve, shouldResolveCurrentMailId ? 4000 : 1500)),
      ]);
    }

    if (shouldResolveCurrentMailId) {
      const liveItemId = getCurrentMailboxItemId();
      const refreshedContextItemId = String(emailContext?.itemId || '').trim();
      if (liveItemId && refreshedContextItemId && liveItemId !== refreshedContextItemId) {
        workflowLogEvent('mail.context.presend_mismatch', 'warn', {
          live_item_prefix: liveItemId.slice(0, 24),
          context_item_prefix: refreshedContextItemId.slice(0, 24),
        });
        // Outlook item 전환 타이밍 이슈를 고려해 한 번 더 재동기화 시도한다.
        await Promise.race([
          loadEmailContext(),
          new Promise((resolve) => setTimeout(resolve, 2000)),
        ]);
      }
    }

  } catch (error) {
    logError('mail.context.presend_refresh.failed', error);
  }
}

function resolveSendWorkflowContext({
  structuredPlan,
  quickActionMeta,
  effectiveMessage,
}) {
  const shouldForceReplyToneCard =
    currentMode === 'email' &&
    normalizeScope(currentScope) === 'email' &&
    Boolean(emailContext) &&
    isReplyDraftRequest(effectiveMessage) &&
    !toBool(quickActionMeta?.skipReplyToneIntercept);
  const structuredInputMeta = resolveStructuredInputMetaForSend(structuredPlan, quickActionMeta);
  const structuredWorkflowIntent = structuredPlan
    ? resolveStructuredWorkflowIntentFromPlan(structuredPlan)
    : null;
  const structuredWorkflowAutoExecute = shouldAutoExecuteStructuredWorkflow(
    structuredPlan,
    structuredWorkflowIntent?.intent,
    effectiveMessage
  );

  return {
    shouldForceReplyToneCard,
    structuredInputMeta,
    structuredWorkflowIntent,
    structuredWorkflowAutoExecute,
  };
}

function resolveAndHandleSendPreResolveInterceptions({
  structuredPlan,
  quickActionMeta,
  effectiveMessage,
  normalizedRawMessage,
  abortBeforeRequest,
}) {
  const workflowContext = resolveSendWorkflowContext({
    structuredPlan,
    quickActionMeta,
    effectiveMessage,
  });
  const {
    shouldForceReplyToneCard,
    structuredInputMeta,
    structuredWorkflowIntent,
    structuredWorkflowAutoExecute,
  } = workflowContext;

  if (shouldForceReplyToneCard) {
    abortBeforeRequest();
    openReplyTonePickerCard(structuredInputMeta ? { structured_input: structuredInputMeta } : null);
    logEvent('chat.send.intercept.reply_tone_fallback', 'ok', {
      mode: currentMode,
      scope: normalizeScope(currentScope),
      message_len: normalizedRawMessage.length,
    });
    return { intercepted: true };
  }

  return {
    intercepted: false,
    structuredInputMeta,
    structuredWorkflowIntent,
    structuredWorkflowAutoExecute,
  };
}

function buildScopedEmailMessageId({
  effectiveMessage,
  turnKind,
  emailModeGlobalMailSearchRequest,
  weeklyReportRequest,
}) {
  if (weeklyReportRequest?.enabled) {
    return '';
  }
  if (
    currentMode !== 'email' ||
    normalizeScope(currentScope) !== 'email' ||
    emailModeGlobalMailSearchRequest
  ) {
    return '';
  }
  const needsCurrentMailId = isCurrentMailScopedOperationMessage(effectiveMessage, turnKind);
  if (!needsCurrentMailId) return '';
  let liveItemId = '';
  try {
    liveItemId = String(Office?.context?.mailbox?.item?.itemId || '').trim();
  } catch (error) {
    liveItemId = '';
  }
  if (!liveItemId) return '';
  if (typeof toRestId === 'function') {
    const liveRestId = String(toRestId(liveItemId) || '').trim();
    if (liveRestId) return liveRestId;
  }
  return liveItemId;
}

async function resolveSendIntentAndRuntime({
  turnKind,
  naturalLanguageProbe,
  structuredPlan,
  structuredWorkflowIntent,
  structuredWorkflowAutoExecute,
  effectiveMessage,
  weeklyReportRequest,
  quickActionMeta,
  scopePrefix,
  domainShortcut,
  normalizedRawMessage,
  structuredInputMeta,
}) {
  const emailModeGlobalMailSearchRequest =
    currentMode === 'email' &&
    isLikelyMailSearchRequest(effectiveMessage, {
      mode: currentMode,
      surface: 'outlook_addin',
    });

  let outboundMessage = effectiveMessage;
  if (currentMode === 'assistant') {
    outboundMessage = enrichPromiseAnalysisMessage(outboundMessage, null);
  }
  const scopedEmailMessageId = buildScopedEmailMessageId({
    effectiveMessage,
    turnKind,
    emailModeGlobalMailSearchRequest,
    weeklyReportRequest,
  });
  const runtimePayload = buildSendRuntimePayload({
    effectiveMessage,
    turnKind,
    structuredPlan,
    structuredInputMeta,
    weeklyReportRequest,
    naturalLanguageProbe,
    quickActionMeta,
    scopePrefix,
    domainShortcut,
    emailModeGlobalMailSearchRequest,
    scopedEmailMessageId,
  });
  const { resolvedIntentPayload, intentResolveElapsedMs } = await resolveIntentPayloadForSend({
    turnKind,
    naturalLanguageProbe,
    structuredPlan,
    structuredWorkflowIntent,
    structuredWorkflowAutoExecute,
    effectiveMessage,
    runtimePayload,
    scopedEmailMessageId,
    normalizedRawMessage,
  });
  return {
    emailModeGlobalMailSearchRequest,
    outboundMessage,
    runtimePayload,
    resolvedIntentPayload,
    intentResolveElapsedMs,
  };
}

async function buildSendExecutionMessage({
  turnKind,
  structuredPlan,
  structuredWorkflowAutoExecute,
  structuredWorkflowIntent,
  resolvedIntentUiAction,
  outboundMessage,
  runtimePayload,
  emailModeGlobalMailSearchRequest,
  effectiveMessage,
  weeklyReportRequest,
}) {
  const {
    outboundMessage: resolvedOutboundMessage,
    shouldAutoComposeCurrentMailScheduleMessage,
  } = maybeApplyAutoComposedScheduleMessage({
    turnKind,
    structuredPlan,
    structuredWorkflowAutoExecute,
    structuredWorkflowIntent,
    resolvedIntentUiAction,
    outboundMessage,
    runtimePayload,
  });
  outboundMessage = resolvedOutboundMessage;

  const useThinkingProgress = shouldShowThinkingProgress(outboundMessage, runtimePayload, turnKind);
  const {
    fullMessage,
    requestEmailId,
  } = await buildSendFullMessage({
    outboundMessage,
    emailModeGlobalMailSearchRequest,
    turnKind,
    shouldAutoComposeCurrentMailScheduleMessage,
    weeklyReportRequest,
  });
  const effectiveRequestEmailId = emailModeGlobalMailSearchRequest
    ? ''
    : String(requestEmailId || runtimePayload?.email_message_id || '').trim();

  const missingCurrentMailId =
    !weeklyReportRequest?.enabled &&
    currentMode === 'email' &&
    normalizeScope(currentScope) === 'email' &&
    !emailModeGlobalMailSearchRequest &&
    isCurrentMailScopedOperationMessage(effectiveMessage, turnKind) &&
    isExplicitCurrentMailDirective(effectiveMessage, runtimePayload) &&
    !effectiveRequestEmailId;

  if (missingCurrentMailId) {
    runtimePayload.current_mail_only = false;
    delete runtimePayload.email_message_id;
    if (typeof clearStickyCurrentMailContext === 'function') {
      clearStickyCurrentMailContext('current_mail_id_missing');
    }
    workflowLogEvent('mail.current_mail_id.missing', 'warn', {
      mode: currentMode,
      scope: normalizeScope(currentScope),
      turn_kind: String(turnKind || '').trim().toLowerCase(),
    });
  }

  return {
    useThinkingProgress,
    fullMessage,
    requestEmailId: effectiveRequestEmailId,
    missingCurrentMailId,
  };
}

async function executeSendRequestLifecycle({
  preflightTypingEl,
  clearPreflightTyping,
  fullMessage,
  runtimePayload,
  resolvedIntentPayload,
  requestEmailId,
  emailModeGlobalMailSearchRequest,
  useThinkingProgress,
  effectiveMessage,
  quickActionMeta,
  weeklyReportRequest,
}) {
  let typingEl = preflightTypingEl;
  let deepProgressTracker = null;
  let streamingAssistant = null;

  try {
    if (useThinkingProgress) {
      if (typingEl) {
        removeTyping(typingEl);
        typingEl = null;
      }
      if (weeklyReportRequest?.enabled) {
        if (typeof startWeeklyReportBuildToast === 'function') {
          startWeeklyReportBuildToast();
        }
      } else {
        deepProgressTracker = startDeepProgressCard(currentMode);
      }
      if (ENABLE_PARTIAL_ANSWER_STREAM && !weeklyReportRequest?.enabled) {
        streamingAssistant = showStreamingAssistantMessage();
      }
    } else if (!typingEl) {
      typingEl = showTyping();
    }

    const payload = buildSendRequestPayload({
      fullMessage,
      runtimePayload,
      resolvedIntentPayload,
      requestEmailId,
      emailModeGlobalMailSearchRequest,
      useThinkingProgress,
    });
    const data = await requestChatDataWithRetry({
      payload,
      useThinkingProgress,
      deepProgressTracker,
      streamingAssistant,
      emailModeGlobalMailSearchRequest,
      weeklyReportRequest,
    });

    if (typingEl) removeTyping(typingEl);
    if (streamingAssistant) {
      removeStreamingAssistantMessage(streamingAssistant);
      streamingAssistant = null;
    }
    if (deepProgressTracker) {
      finishDeepProgressCard(deepProgressTracker, {
        finalState: data.status === 'confirm_required' ? 'confirm' : 'done',
        trace: data?.metadata?.thinking_trace || null,
        metadata: data?.metadata || null,
      });
    }
    if (weeklyReportRequest?.enabled && typeof finishWeeklyReportBuildToast === 'function') {
      finishWeeklyReportBuildToast(data.status === 'confirm_required' ? 'done' : 'done');
    }

    handleSendSuccessResponse({
      data,
      effectiveMessage,
      quickActionMeta,
      weeklyReportRequest,
    });
  } catch (error) {
    logError('chat.send.failed', error, { mode: currentMode });
    if (typingEl) removeTyping(typingEl);
    clearPreflightTyping();
    if (streamingAssistant) {
      removeStreamingAssistantMessage(streamingAssistant);
      streamingAssistant = null;
    }
    if (deepProgressTracker) {
      finishDeepProgressCard(deepProgressTracker, {
        finalState: 'error',
        note: '오류가 발생했습니다. 네트워크 또는 서버 상태를 확인해주세요.',
      });
    }
    if (weeklyReportRequest?.enabled && typeof finishWeeklyReportBuildToast === 'function') {
      finishWeeklyReportBuildToast('error');
    }
    addAssistantMessage(toUserFacingRequestErrorMessage(error));
  } finally {
    clearPreflightTyping();
    isProcessing = false;
    setSendButtonState(true);
  }
}


/* ========================================
   sendMessage Orchestrator (moved from taskpane.js)
   ======================================== */

async function sendMessage() {
  const input = document.getElementById('chatInput');
  if (!input) {
    addSystemMessage('입력창을 찾을 수 없습니다. 창을 새로고침한 뒤 다시 시도해주세요.');
    return;
  }
  hideScopeShortcutMenu();
  hideVerbShortcutMenu();
  const rawMessage = input.value.trim();
  if (!rawMessage) return;
  if (isProcessing) {
    workflowLogEvent('chat.send.stuck_processing_reset', 'warn', {
      reason: 'send_requested_while_processing',
    });
    isProcessing = false;
    setSendButtonState(true);
  }
  const quickActionMeta = pendingQuickAction ? { ...pendingQuickAction } : null;
  pendingQuickAction = null;
  const sendInput = resolveSendNormalizedInput({
    rawMessage,
    input,
    quickActionMeta,
  });
  if (sendInput.aborted) return;
  const {
    naturalLanguageProbe,
    probeScopedMessage,
    structuredPlan,
    scopePrefix,
    domainShortcut,
    normalizedRawMessage,
    effectiveMessage,
    weeklyReportRequest,
  } = sendInput;
  const userDisplayMessage = weeklyReportRequest?.enabled
    ? String(rawMessage || '').trim()
    : '';
  const systemLocalUiAction = resolveSystemLocalUiAction(rawMessage, normalizedRawMessage);
  if (systemLocalUiAction) {
    if (typeof hideClarificationPromptCard === 'function' && systemLocalUiAction !== 'promise_selector' && systemLocalUiAction !== 'finance_selector' && systemLocalUiAction !== 'hr_selector') {
      hideClarificationPromptCard();
    }
    if (input) {
      input.value = '';
      autoResize(input);
      updateStructuredSelectionBadges();
    }
    if (systemLocalUiAction === 'promise_selector') {
      showPromiseSelectorToast();
      return;
    }
    if (systemLocalUiAction === 'promise_projects') {
      await showPromiseProjectsCard();
      return;
    }
    if (systemLocalUiAction === 'promise_create') {
      openPromiseCreateWindowFromUi();
      return;
    }
    if (systemLocalUiAction === 'finance_selector') {
      showFinanceSelectorToast();
      return;
    }
    if (systemLocalUiAction === 'finance_projects') {
      await showFinanceProjectsCard();
      return;
    }
    if (systemLocalUiAction === 'finance_create') {
      openFinanceCreateWindowFromUi();
      return;
    }
    if (systemLocalUiAction === 'hr_selector') {
      showHrSelectorToast();
      return;
    }
    if (systemLocalUiAction === 'hr_view') {
      openMyHrWindowFromUi('view');
      return;
    }
    if (systemLocalUiAction === 'hr_apply') {
      showMyHRDraftCard();
      return;
    }
  }
  if (typeof hideClarificationPromptCard === 'function') {
    hideClarificationPromptCard();
  }
  const turnKind = classifyTurnKind(effectiveMessage);
  const isExplicitSmalltalk = turnKind === 'explicit_smalltalk';
  logEvent('chat.send.start', 'ok', {
    mode: currentMode,
    raw_len: normalizedRawMessage.length,
    effective_len: effectiveMessage.length,
    turn_kind: turnKind,
    explicit_smalltalk: isExplicitSmalltalk,
    structured_input: Boolean(structuredPlan),
  });

  const {
    preflightTypingEl: initialPreflightTypingEl,
    clearPreflightTyping,
    abortBeforeRequest,
  } = initializeSendPreflightState({
    input,
    structuredPlan,
    rawMessage,
    normalizedRawMessage,
    displayUserMessage: userDisplayMessage,
    turnKind,
  });
  let preflightTypingEl = initialPreflightTypingEl;

  // ItemChanged 이벤트가 지연/누락되는 환경이 있어,
  // 이메일 모드에서는 전송 직전에 항상 현재 아이템 컨텍스트를 재동기화한다.
  await refreshEmailContextBeforeSendIfNeeded({
    turnKind,
    effectiveMessage,
  });

  const {
    intercepted: preResolveIntercepted,
    structuredInputMeta,
    structuredWorkflowIntent,
    structuredWorkflowAutoExecute,
  } = resolveAndHandleSendPreResolveInterceptions({
    structuredPlan,
    quickActionMeta,
    effectiveMessage,
    normalizedRawMessage,
    abortBeforeRequest,
  });
  if (preResolveIntercepted) {
    return;
  }

  const {
    emailModeGlobalMailSearchRequest,
    outboundMessage: initialOutboundMessage,
    runtimePayload,
    resolvedIntentPayload,
    intentResolveElapsedMs,
  } = await resolveSendIntentAndRuntime({
    turnKind,
    naturalLanguageProbe,
    structuredPlan,
    structuredWorkflowIntent,
    structuredWorkflowAutoExecute,
    effectiveMessage,
    weeklyReportRequest,
    quickActionMeta,
    scopePrefix,
    domainShortcut,
    normalizedRawMessage,
    structuredInputMeta,
  });
  if (
    maybeHandleIntentProbeOutput({
      naturalLanguageProbe,
      probeScopedMessage,
      resolvedIntentPayload,
      intentResolveElapsedMs,
      abortBeforeRequest,
    })
  ) {
    return;
  }
  let outboundMessage = initialOutboundMessage;
  const resolvedIntentUiAction = resolveIntentCardUiAction(
    resolvedIntentPayload,
    quickActionMeta,
    effectiveMessage
  );
  if (
    maybeInterceptResolvedIntentActions({
      resolvedIntentUiAction,
      quickActionMeta,
      structuredInputMeta,
      resolvedIntentPayload,
      normalizedRawMessage,
      abortBeforeRequest,
    })
  ) {
    return;
  }

  const {
    useThinkingProgress,
    fullMessage,
    requestEmailId,
    missingCurrentMailId,
  } = await buildSendExecutionMessage({
    turnKind,
    structuredPlan,
    structuredWorkflowAutoExecute,
    structuredWorkflowIntent,
    resolvedIntentUiAction,
    outboundMessage,
    runtimePayload,
    emailModeGlobalMailSearchRequest,
    effectiveMessage,
    weeklyReportRequest,
  });

  if (missingCurrentMailId) {
    abortBeforeRequest();
    addSystemMessage('현재 선택한 메일 컨텍스트를 확인하지 못했습니다. 메일을 다시 선택한 뒤 "현재메일 요약해줘"처럼 다시 요청해 주세요.');
    return;
  }

  const requestPreflightTypingEl = preflightTypingEl;
  preflightTypingEl = null;
  await executeSendRequestLifecycle({
    preflightTypingEl: requestPreflightTypingEl,
    clearPreflightTyping,
    fullMessage,
    runtimePayload,
    resolvedIntentPayload,
    requestEmailId,
    emailModeGlobalMailSearchRequest,
    useThinkingProgress,
    effectiveMessage,
    quickActionMeta,
    weeklyReportRequest,
  });
}
