/* ========================================
   MolduBot - Renderer Utils
   ======================================== */

(function initTaskpaneRendererUtils(global) {

/* =========================================
   Chat – Message Rendering
   ========================================= */

function formatTurnElapsedLabel(elapsedMs) {
  const safeMs = Number(elapsedMs);
  if (!Number.isFinite(safeMs) || safeMs <= 0) return '';
  const totalSeconds = Math.max(1, Math.round(safeMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s 동안 작업`;
  if (minutes > 0) return `${minutes}m ${seconds}s 동안 작업`;
  return `${seconds}s 동안 작업`;
}

function resolveLastTurnElapsedMsFromHistory() {
  if (!Array.isArray(chatHistory) || !chatHistory.length) return Number.NaN;
  let lastUserTs = Number.NaN;
  let lastAssistantTs = Number.NaN;
  for (let i = chatHistory.length - 1; i >= 0; i -= 1) {
    const entry = chatHistory[i];
    if (!entry || typeof entry !== 'object') continue;
    const role = String(entry.role || '').trim().toLowerCase();
    const ts = Number(entry.ts);
    if (!Number.isFinite(ts) || ts <= 0) continue;
    if (!Number.isFinite(lastAssistantTs) && role === 'assistant') {
      lastAssistantTs = ts;
      continue;
    }
    if (!Number.isFinite(lastUserTs) && role === 'user') {
      lastUserTs = ts;
      if (Number.isFinite(lastAssistantTs)) break;
    }
  }
  if (!Number.isFinite(lastAssistantTs) || !Number.isFinite(lastUserTs)) return Number.NaN;
  if (lastAssistantTs < lastUserTs) return Number.NaN;
  return Math.max(0, lastAssistantTs - lastUserTs);
}

function resolveLastTurnElapsedMs(nowMs = Date.now()) {
  if (Number.isFinite(lastCompletedTurnElapsedMs) && lastCompletedTurnElapsedMs > 0) {
    return lastCompletedTurnElapsedMs;
  }
  if (Number.isFinite(lastTurnStartedAtMs) && lastTurnStartedAtMs > 0 && nowMs > lastTurnStartedAtMs) {
    return nowMs - lastTurnStartedAtMs;
  }
  const fromHistory = resolveLastTurnElapsedMsFromHistory();
  if (Number.isFinite(fromHistory) && fromHistory > 0) {
    return fromHistory;
  }
  return Number.NaN;
}

function insertTurnSeparatorIfNeeded(chatArea, options = {}) {
  if (!chatArea) return;
  const hasMessage = Boolean(chatArea.querySelector('.message'));
  if (!hasMessage) return;
  const last = chatArea.lastElementChild;
  if (last && last.classList && last.classList.contains('turn-separator')) return;
  const elapsedLabel = formatTurnElapsedLabel(options?.elapsedMs);
  const labelHtml = elapsedLabel
    ? `<span class="turn-separator-label">${escapeHtml(elapsedLabel)}</span>`
    : '';
  chatArea.insertAdjacentHTML('beforeend', `<div class="turn-separator" aria-hidden="true">${labelHtml}</div>`);
}

function bindInlineCopyButton(buttonEl, text, meta = {}) {
  if (!buttonEl) return;
  const payload = String(text || '');
  buttonEl.addEventListener('click', async (event) => {
    event.preventDefault();
    event.stopPropagation();
    const copied = await copyTextToClipboard(payload);
    flashIconActionFeedback(buttonEl, {
      okLabel: '복사됨',
      failLabel: '복사 실패',
      success: copied,
    });
    if (copied) {
      showInlineCopyToast(buttonEl, 'copied');
    }
    logEvent('ui.message.copy', copied ? 'ok' : 'warn', {
      source: String(meta.source || 'unknown'),
      message_len: payload.length,
    });
  });
}

function showInlineCopyToast(anchorEl, label = 'copied') {
  if (!anchorEl) return;
  const host =
    anchorEl.closest('.msg-user-shell, .assistant-feedback-row') ||
    anchorEl.parentElement;
  if (!host) return;
  const text = String(label || '').trim() || 'copied';
  const existing = host.querySelector('.inline-copy-toast');
  if (existing) existing.remove();
  const toastEl = document.createElement('span');
  toastEl.className = 'inline-copy-toast';
  toastEl.textContent = text;
  host.appendChild(toastEl);
  window.requestAnimationFrame(() => {
    toastEl.classList.add('is-visible');
  });
  window.setTimeout(() => {
    toastEl.classList.remove('is-visible');
    window.setTimeout(() => toastEl.remove(), 180);
  }, 900);
}

function addUserMessage(text, options = {}) {
  const { save = true, separatorElapsedMs = Number.NaN } = options;
  const chatArea = document.getElementById('chatArea');
  removeWelcomeStateIfExists();
  const shouldInsertSeparator = save || Number.isFinite(Number(separatorElapsedMs));
  if (shouldInsertSeparator) {
    const nowMs = Date.now();
    const explicitElapsedMs = Number(separatorElapsedMs);
    const elapsedMs = Number.isFinite(explicitElapsedMs)
      ? explicitElapsedMs
      : resolveLastTurnElapsedMs(nowMs);
    insertTurnSeparatorIfNeeded(chatArea, { elapsedMs });
    if (save) {
      lastTurnStartedAtMs = nowMs;
      lastCompletedTurnElapsedMs = Number.NaN;
    }
  }
  const html = `
    <div class="message user">
      <div class="msg-user-shell">
        <button class="msg-inline-copy-btn" type="button" aria-label="메시지 복사" title="메시지 복사">
          ${ICONS.copy}
        </button>
        <div class="msg-body">${escapeHtml(text)}</div>
      </div>
    </div>`;
  chatArea.insertAdjacentHTML('beforeend', html);
  const lastMessage = chatArea.lastElementChild;
  const copyBtn = lastMessage?.querySelector('.msg-inline-copy-btn');
  bindInlineCopyButton(copyBtn, text, { source: 'user' });
  if (save) {
    recordHistory('user', text);
    persistTaskpaneState();
  }
  scrollToBottom();
}

function resolveAssistantPrimaryCards(text, metadata) {
  const promiseAnalysis = formatPromiseAnalysisMessage(text);
  if (promiseAnalysis) {
    return {
      promiseAnalysis,
      hrLeaveEvent: null,
      calendarEvent: null,
      todoTask: null,
      meetingRoomEvent: null,
    };
  }
  return {
    promiseAnalysis: null,
    hrLeaveEvent: formatHrLeaveMessage(text, metadata),
    calendarEvent: formatCalendarEventMessage(text, metadata),
    todoTask: formatTodoTaskMessage(text, metadata),
    meetingRoomEvent: formatMeetingRoomMessage(text, metadata),
  };
}

function hasAssistantPrimaryCard(state) {
  return Boolean(
    state.promiseAnalysis ||
      state.hrLeaveEvent ||
      state.calendarEvent ||
      state.todoTask ||
      state.meetingRoomEvent
  );
}

function resolveAssistantMailUiState(metadata = null) {
  const uiContractIntent = String(metadata?.ui_contract?.intent || '')
    .trim()
    .toLowerCase();
  const cardContractIntent = String(metadata?.card_contract?.intent || '')
    .trim()
    .toLowerCase();
  const intentDecisionIntent = String(
    metadata?.intent_decision?.intent || metadata?.intent_decision?.primary_intent || ''
  )
    .trim()
    .toLowerCase();
  const hasMailUiContract =
    uiContractIntent === 'mail_search' ||
    intentDecisionIntent === 'mail_search' ||
    cardContractIntent === 'mail_search';
  return {
    hasMailUiContract,
  };
}

function shouldAttachRestartSessionAction(text, metadata = null) {
  const meta = metadata && typeof metadata === 'object' ? metadata : {};
  const clarification = meta.clarification && typeof meta.clarification === 'object' ? meta.clarification : {};
  const clarificationMode = String(clarification.mode || '').trim().toLowerCase();
  if (clarificationMode === 'prompt') {
    return false;
  }
  const intentDecision =
    meta.intent_decision && typeof meta.intent_decision === 'object' ? meta.intent_decision : {};
  const contextContract =
    meta.context_contract && typeof meta.context_contract === 'object' ? meta.context_contract : {};

  const intent = String(intentDecision.intent || intentDecision.primary_intent || '').trim().toLowerCase();
  const clarificationTier = String(
    intentDecision.clarification_tier || contextContract.clarification_tier || ''
  )
    .trim()
    .toLowerCase();
  const clarificationReason = String(
    intentDecision.clarification_reason || contextContract.clarification_reason || ''
  )
    .trim()
    .toLowerCase();
  const needsClarification =
    toBool(intentDecision.needs_clarification) || toBool(contextContract.needs_clarification);

  if (
    intent === 'unknown' ||
    clarificationTier === 'clarify' ||
    clarificationReason === 'unknown_intent' ||
    clarificationReason === 'missing_slots' ||
    (needsClarification && clarificationTier !== 'confirm')
  ) {
    return true;
  }

  const normalizedText = normalizeAssistantTextForParsing(text).trim();
  if (!normalizedText) return false;
  if (ASSISTANT_ERROR_HINT_RE.test(normalizedText)) return true;
  return ASSISTANT_RESTART_HINT_RE.test(normalizedText);
}

function shouldAttachAssistantOpenMailList({
  hasMailUiContract,
  metadataMailItems,
  persistedOpenableItems,
  promiseAnalysis,
}) {
  if (promiseAnalysis) return false;
  return Boolean(
    hasMailUiContract ||
      metadataMailItems.length ||
      persistedOpenableItems.length
  );
}

function canAttachAssistantOpenableItems({
  shouldAttachOpenMailList,
  hrLeaveEvent,
  calendarEvent,
  todoTask,
  meetingRoomEvent,
}) {
  return (
    shouldAttachOpenMailList &&
    !hrLeaveEvent &&
    !calendarEvent &&
    !todoTask &&
    !meetingRoomEvent
  );
}

function resolveAssistantOpenableMailState(params = {}) {
  const state = params && typeof params === 'object' ? params : {};
  const uiOutputV2OpenableItems = sanitizeOpenableMailItems(
    state.uiOutputV2?.openable_items || state.uiOutputV2?.openableItems || []
  );
  const persistedOpenableItems = sanitizeOpenableMailItems(
    uiOutputV2OpenableItems.length ? uiOutputV2OpenableItems : state.persistedOpenableItems
  );
  const metadataMailItems = state.promiseAnalysis
    ? []
    : uiOutputV2OpenableItems.length
      ? uiOutputV2OpenableItems
      : extractOpenableMailItemsFromMetadata(state.metadata);
  const shouldAttachOpenMailList = shouldAttachAssistantOpenMailList({
    hasMailUiContract: state.hasMailUiContract,
    metadataMailItems,
    persistedOpenableItems,
    promiseAnalysis: state.promiseAnalysis,
  });
  const safePersistedOpenableItems = shouldAttachOpenMailList
    ? persistedOpenableItems
    : [];
  const metadataItems = shouldAttachOpenMailList ? metadataMailItems : [];
  const canAttachOpenableItems = canAttachAssistantOpenableItems({
    shouldAttachOpenMailList,
    hrLeaveEvent: state.hrLeaveEvent,
    calendarEvent: state.calendarEvent,
    todoTask: state.todoTask,
    meetingRoomEvent: state.meetingRoomEvent,
  });
  let openableItems = [];
  if (canAttachOpenableItems) {
    if (safePersistedOpenableItems.length) openableItems = safePersistedOpenableItems;
    else if (metadataItems.length) openableItems = metadataItems;
    else openableItems = [];
  }
  return {
    shouldAttachOpenMailList,
    metadataItems,
    openableItems,
  };
}

function computeAssistantRenderState({
  text,
  metadata,
  replyDraft,
  forceRestartAction,
  persistedOpenableItems,
  uiOutputV2,
}) {
  const normalizedAssistantText = normalizeAssistantTextForParsing(text).trim();
  const primaryCards = resolveAssistantPrimaryCards(text, metadata);
  const hasPrimaryCard = hasAssistantPrimaryCard(primaryCards);
  const mailUiState = resolveAssistantMailUiState(metadata);
  const openableMailState = resolveAssistantOpenableMailState({
    text,
    metadata,
    persistedOpenableItems,
    uiOutputV2,
    hasMailUiContract: mailUiState.hasMailUiContract,
    ...primaryCards,
  });
  return {
    normalizedAssistantText,
    metadata,
    uiOutputV2,
    ...primaryCards,
    ...mailUiState,
    shouldAttachReplyAction: Boolean(replyDraft && !hasPrimaryCard),
    shouldAttachRestartAction:
      Boolean(forceRestartAction) || shouldAttachRestartSessionAction(text, metadata),
    ...openableMailState,
  };
}

function truncateInlineText(value, max = 120) {
  const normalized = String(value || '').replace(/\s+/g, ' ').trim();
  if (!normalized) return '';
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, Math.max(1, max - 3))}...`;
}

function appendSummaryLine(lines, value) {
  const normalized = String(value || '').trim();
  if (!normalized) return;
  lines.push(normalized);
}

function buildPromiseAnalysisSummaryMarkdown(data) {
  if (!data || typeof data !== 'object') return '';
  const lines = [];
  const title = String(data.projectName || '').trim();
  const projectNumber = String(data.projectNumber || '').trim();
  appendSummaryLine(lines, title ? `실행예산 분석: ${title}` : '실행예산 분석 결과');
  appendSummaryLine(lines, projectNumber ? `프로젝트번호: ${projectNumber}` : '');
  appendSummaryLine(lines, data.executionTotal ? `총 실행비용: ${data.executionTotal}` : '');
  appendSummaryLine(lines, data.finalCost ? `최종 Cost총액: ${data.finalCost}` : '');
  appendSummaryLine(lines, data.avgGrowth ? `월평균 증감률: ${data.avgGrowth}` : '');
  if (Array.isArray(data.directLines)) {
    data.directLines.slice(0, 3).forEach((item) => {
      appendSummaryLine(lines, `- ${truncateInlineText(item, 160)}`);
    });
  }
  if (Array.isArray(data.reasonLines) && data.reasonLines.length) {
    appendSummaryLine(lines, '증감 근거:');
    data.reasonLines.slice(0, 3).forEach((item) => {
      appendSummaryLine(lines, `- ${truncateInlineText(item, 160)}`);
    });
  }
  return lines.join('\n').trim();
}

function buildCalendarSummaryMarkdown(event) {
  if (!event || typeof event !== 'object') return '';
  const lines = [];
  if (Array.isArray(event.items)) {
    appendSummaryLine(lines, `일정 조회 결과 (${event.items.length}건)`);
    event.items.slice(0, 8).forEach((item) => {
      const when = truncateInlineText(item?.when || '-', 60);
      const subject = truncateInlineText(item?.subject || '-', 80);
      const location = truncateInlineText(item?.location || '-', 40);
      appendSummaryLine(lines, `- ${when} | ${subject} | ${location}`);
    });
    return lines.join('\n').trim();
  }
  appendSummaryLine(lines, '일정 등록 완료');
  appendSummaryLine(lines, event.subject ? `- 제목: ${event.subject}` : '');
  appendSummaryLine(lines, event.startTime ? `- 시작: ${event.startTime}` : '');
  appendSummaryLine(lines, event.endTime ? `- 종료: ${event.endTime}` : '');
  return lines.join('\n').trim();
}

function buildHrLeaveSummaryMarkdown(payload) {
  if (!payload || typeof payload !== 'object') return '';
  const list = Array.isArray(payload.items) ? payload.items : [];
  const lines = [];
  appendSummaryLine(lines, `근태 조회 결과 (${list.length}건)`);
  if (!list.length) {
    appendSummaryLine(lines, '- 조회된 근태 신청 내역이 없습니다.');
    return lines.join('\n').trim();
  }
  list.slice(0, 8).forEach((item) => {
    const when = truncateInlineText(item?.when || '-', 60);
    const subject = truncateInlineText(item?.subject || '-', 80);
    const note = truncateInlineText(item?.note || '-', 60);
    appendSummaryLine(lines, `- ${when} | ${subject} | ${note}`);
  });
  return lines.join('\n').trim();
}

function buildTodoSummaryMarkdown(todo) {
  if (!todo || typeof todo !== 'object') return '';
  const lines = [];
  if (Array.isArray(todo.items)) {
    appendSummaryLine(lines, `To Do 목록 (${todo.items.length}건)`);
    if (!todo.items.length) {
      appendSummaryLine(lines, '- 등록된 To Do가 없습니다.');
      return lines.join('\n').trim();
    }
    todo.items.slice(0, 10).forEach((item) => {
      const title = truncateInlineText(item?.title || '-', 80);
      const due = truncateInlineText(item?.dueDate || '-', 40);
      const status = truncateInlineText(item?.status || '-', 20);
      appendSummaryLine(lines, `- ${title} | 마감: ${due} | 상태: ${status}`);
    });
    return lines.join('\n').trim();
  }
  appendSummaryLine(lines, 'To Do 등록 결과');
  appendSummaryLine(lines, todo.title ? `- 작업: ${todo.title}` : '');
  appendSummaryLine(lines, todo.dueDate ? `- 마감: ${todo.dueDate}` : '');
  appendSummaryLine(lines, todo.importance ? `- 우선순위: ${todo.importance}` : '');
  return lines.join('\n').trim();
}

function buildMeetingRoomSummaryMarkdown(payload) {
  if (!payload || typeof payload !== 'object') return '';
  const list = Array.isArray(payload.items) ? payload.items : [];
  const lines = [];
  appendSummaryLine(lines, `회의실 조회 결과 (${list.length}건)`);
  if (!list.length) {
    appendSummaryLine(lines, '- 예약된 회의실이 없습니다.');
    return lines.join('\n').trim();
  }
  list.slice(0, 8).forEach((item) => {
    const room = truncateInlineText(item?.room || '회의실 미기재', 40);
    const subject = truncateInlineText(item?.subject || '-', 80);
    const when = truncateInlineText(item?.when || '-', 60);
    appendSummaryLine(lines, `- ${room} | ${subject} | ${when}`);
  });
  return lines.join('\n').trim();
}

function buildAssistantPrimarySummaryMarkdown(renderState) {
  if (!renderState || typeof renderState !== 'object') return '';
  if (renderState.promiseAnalysis) return buildPromiseAnalysisSummaryMarkdown(renderState.promiseAnalysis);
  if (renderState.hrLeaveEvent) return buildHrLeaveSummaryMarkdown(renderState.hrLeaveEvent);
  if (renderState.calendarEvent) return buildCalendarSummaryMarkdown(renderState.calendarEvent);
  if (renderState.todoTask) return buildTodoSummaryMarkdown(renderState.todoTask);
  if (renderState.meetingRoomEvent) return buildMeetingRoomSummaryMarkdown(renderState.meetingRoomEvent);
  return '';
}

function buildStructuredUiOutputMarkdown(uiOutput) {
  const normalized = normalizeUiOutputPayload(uiOutput);
  if (!normalized || normalized.type === 'free_chat') return '';
  const body = String(normalized.body || '').trim();
  if (!body) return '';
  // 본문 중심 렌더링: title 강제 삽입은 중복 섹션을 만들기 쉬워 제외한다.
  return body;
}

function normalizeAssistantMergeBlock(text) {
  return String(text || '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n+/g, '\n')
    .trim()
    .toLowerCase();
}

function mergeAssistantBodyTextSegments(segments = []) {
  const merged = [];
  const seenBlocks = new Set();
  for (const segment of segments) {
    const normalizedSegment = String(segment || '').trim();
    if (!normalizedSegment) continue;

    const blocks = normalizedSegment
      .split(/\n{2,}/)
      .map((block) => block.trim())
      .filter(Boolean);
    if (!blocks.length) continue;

    const keptBlocks = [];
    for (const block of blocks) {
      const normalizedBlock = normalizeAssistantMergeBlock(block);
      if (!normalizedBlock) continue;
      if (seenBlocks.has(normalizedBlock)) continue;
      seenBlocks.add(normalizedBlock);
      keptBlocks.push(block);
    }

    if (keptBlocks.length) {
      merged.push(keptBlocks.join('\n\n'));
    }
  }
  return merged.join('\n\n').trim();
}

const ASSISTANT_DISPLAY_NOISE_LINE_PATTERNS = [
  /^\s*워크플로우를\s*시작했습니다\.?\s*$/i,
  /^\s*도구\s*실행을\s*준비\s*중입니다\.?\s*$/i,
  /^\s*단계\s*진행\s*:\s*[a-z0-9_-]+\s*$/i,
  /^\s*단계\s*완료\s*:\s*[a-z0-9_-]+\s*$/i,
  /^\s*사용자\s*확인이\s*필요합니다\.?\s*$/i,
  /^\s*[a-z_][a-z0-9_]*\s*도구가\s*성공적으로\s*실행되었습니다\.?\s*$/i,
  /^\s*get_current_datetime\s*도구가\s*성공적으로\s*실행되었습니다\.?\s*$/i,
  /^\s*현재\s*날짜\s*\/?\s*시간\s*[:：]\s*$/i,
  /^\s*iso\s*형식\s*[:：].*$/i,
];

const ASSISTANT_SENSITIVE_LINE_PATTERNS = [
  /^(?:[-•*]\s*)?(?:메일\s*id|mail\s*id|message\s*id)\s*[:：].*$/i,
  /^<\[REDACTED_SENSITIVE_DATA\]>$/i,
  /^\[REDACTED_SENSITIVE_DATA\]$/i,
];

function stripLeadingDecorativeEmoji(text) {
  const line = String(text || '');
  return line.replace(/^\s*[\p{Extended_Pictographic}\u2600-\u26ff\u2700-\u27bf]+\s*/u, '');
}

function isLikelyOpaqueMessageIdToken(text) {
  const token = String(text || '').trim();
  if (!token) return false;
  if (!/^[A-Za-z0-9+/_=-]{24,}$/.test(token)) return false;
  if (/^https?:\/\//i.test(token)) return false;
  if (/@/.test(token)) return false;
  return /^AQMk/i.test(token) || token.length >= 64;
}

function sanitizeAssistantDisplayText(text) {
  const raw = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim();
  if (!raw) return '';

  const lines = raw.split('\n');
  const cleaned = [];
  let droppingToolMetaBlock = false;
  let droppingMessageIdValueLine = false;

  for (const sourceLine of lines) {
    const withoutEmoji = stripLeadingDecorativeEmoji(sourceLine);
    const normalized = withoutEmoji.replace(/\s+/g, ' ').trim();
    if (!normalized) {
      droppingToolMetaBlock = false;
      droppingMessageIdValueLine = false;
      cleaned.push('');
      continue;
    }

    if (droppingMessageIdValueLine) {
      const maybeValue = normalized.replace(/^[-•*]\s*/, '').trim();
      if (isLikelyOpaqueMessageIdToken(maybeValue)) {
        droppingMessageIdValueLine = false;
        continue;
      }
      droppingMessageIdValueLine = false;
    }

    const normalizedNoListMarker = normalized.replace(/^[-•*]\s*/, '').trim();
    const isSensitiveLine = ASSISTANT_SENSITIVE_LINE_PATTERNS.some((pattern) =>
      pattern.test(normalizedNoListMarker)
    );
    if (isSensitiveLine) {
      if (/(?:메일\s*id|mail\s*id|message\s*id)\s*[:：]\s*$/i.test(normalizedNoListMarker)) {
        droppingMessageIdValueLine = true;
      }
      continue;
    }
    if (isLikelyOpaqueMessageIdToken(normalizedNoListMarker)) {
      continue;
    }

    const isNoise = ASSISTANT_DISPLAY_NOISE_LINE_PATTERNS.some((pattern) => pattern.test(normalized));
    if (isNoise) {
      droppingToolMetaBlock = true;
      continue;
    }

    if (droppingToolMetaBlock) {
      const looksLikeToolMeta =
        /^(?:[-•*]\s*)?(?:날짜|시간|현재\s*날짜|현재\s*시간|iso\s*형식)\s*[:：]/i.test(normalized) ||
        /^(?:[-•*]\s*)?\d{4}-\d{2}-\d{2}t/i.test(normalized);
      if (looksLikeToolMeta) continue;
      droppingToolMetaBlock = false;
    }

    cleaned.push(withoutEmoji);
  }

  const deduped = [];
  let previousNormalized = '';
  for (const line of cleaned) {
    const normalized = line.replace(/\s+/g, ' ').trim();
    if (!normalized) {
      if (deduped.length && deduped[deduped.length - 1] !== '') deduped.push('');
      previousNormalized = '';
      continue;
    }
    if (normalized === previousNormalized) continue;
    deduped.push(line.trimEnd());
    previousNormalized = normalized;
  }

  return deduped.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}

function shouldAppendCalendarPrimarySummary(text, calendarEvent) {
  if (!calendarEvent || typeof calendarEvent !== 'object' || Array.isArray(calendarEvent.items)) {
    return true;
  }
  const raw = String(text || '').trim();
  if (!raw) return true;

  // 본문에 일정 생성 완료 + 요약(제목/시작/종료)이 이미 있으면 중복 요약을 붙이지 않는다.
  const hasCompletionSignal =
    /(일정\s*(등록|생성).*(완료|성공)|등록된\s*일정\s*요약|일정\s*등록\s*완료)/i.test(raw);
  const hasFieldSignal =
    /(제목\s*[:：]|시작\s*[:：]|종료\s*[:：])/.test(raw) ||
    /-\s*제목\s*[:：].*\n.*-\s*시작\s*[:：].*\n.*-\s*종료\s*[:：]/s.test(raw);

  return !(hasCompletionSignal && hasFieldSignal);
}

function shouldAppendPrimarySummary(text, uiOutput, renderState) {
  const summary = buildAssistantPrimarySummaryMarkdown(renderState);
  if (!summary) return false;

  if (renderState?.calendarEvent && !shouldAppendCalendarPrimarySummary(text, renderState.calendarEvent)) {
    return false;
  }

  // ui_output가 구조화 본문을 제공하는 경우, 일반적으로 중복을 피하기 위해 primary summary를 생략한다.
  if (normalizeUiOutputPayload(uiOutput)) {
    return false;
  }

  return true;
}

function buildAssistantMessageBodyHtml(text, renderState, uiOutput = null, uiOutputV2 = null, options = {}) {
  const replyDraft = Boolean(options.replyDraft);
  const normalizedUiOutputV2 = normalizeUiOutputV2Payload(uiOutputV2);
  if (!replyDraft && normalizedUiOutputV2) {
    const structuredPayload =
      normalizedUiOutputV2?.body?.payload && typeof normalizedUiOutputV2.body.payload === 'object'
        ? normalizedUiOutputV2.body.payload
        : null;
    if (structuredPayload) {
      const kind = String(structuredPayload.kind || '').trim().toLowerCase();
      if (kind === 'mail_list_v1') {
        return {
          bodyHtml: buildMailListPayloadHtml(structuredPayload),
          isCardMessage: false,
        };
      }
      if (kind === 'mail_summary_v1') {
        const summaryHtml = buildMailSummaryPayloadHtml(structuredPayload);
        if (summaryHtml) {
          return {
            bodyHtml: summaryHtml,
            isCardMessage: false,
          };
        }
      }
    }
    const bodyText = sanitizeAssistantDisplayText(
      String(normalizedUiOutputV2?.body?.text || '').trim()
    );
    if (bodyText) {
      if (normalizedUiOutputV2.type === 'weekly_report') {
        const cardBodyHtml = buildWeeklyReportCardHtml(
          bodyText,
          normalizedUiOutputV2?.weekly_report?.data || null,
          normalizedUiOutputV2?.weekly_report?.ranges || null
        );
        return {
          bodyHtml: `<div class="weekly-report-card">${cardBodyHtml}</div>`,
          isCardMessage: true,
        };
      }
      const bodyHtml = normalizedUiOutputV2.body.format === 'plain'
        ? `<p>${escapeHtml(bodyText).replace(/\n/g, '<br/>')}</p>`
        : renderMarkdown(bodyText);
      return {
        bodyHtml,
        isCardMessage: false,
      };
    }
  }

  const primarySummary = shouldAppendPrimarySummary(text, uiOutput, renderState)
    ? buildAssistantPrimarySummaryMarkdown(renderState)
    : '';
  const bodySegments = [sanitizeAssistantDisplayText(String(text || '').trim())];
  if (!replyDraft) {
    bodySegments.push(sanitizeAssistantDisplayText(buildStructuredUiOutputMarkdown(uiOutput)));
  }
  bodySegments.push(sanitizeAssistantDisplayText(primarySummary));
  const mergedBodyText = mergeAssistantBodyTextSegments(bodySegments);
  const fallbackText = sanitizeAssistantDisplayText(String(text || '').trim());
  const bodyHtml = renderMarkdown(mergedBodyText || fallbackText);
  return {
    bodyHtml,
    isCardMessage: false,
  };
}

function attachAssistantFeedbackActionRow(container, text) {
  if (!container) return;
  const payload = String(text || '').trim();
  if (!payload) return;
  if (container.querySelector('.assistant-feedback-row')) return;

  const rowId = `assistant_feedback_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
  const rowHtml = `
    <div class="assistant-feedback-row" id="${rowId}">
      <button class="assistant-feedback-btn" type="button" data-action="copy" aria-label="답변 복사" title="답변 복사">
        ${ICONS.copy}
      </button>
      <button class="assistant-feedback-btn" type="button" data-action="up" aria-label="좋아요" title="좋아요">
        ${ICONS.thumbsUp}
      </button>
      <button class="assistant-feedback-btn" type="button" data-action="down" aria-label="별로예요" title="별로예요">
        ${ICONS.thumbsDown}
      </button>
    </div>
  `;
  container.insertAdjacentHTML('beforeend', rowHtml);
  const rowEl = document.getElementById(rowId);
  if (!rowEl) return;

  const copyBtn = rowEl.querySelector('.assistant-feedback-btn[data-action="copy"]');
  bindInlineCopyButton(copyBtn, payload, { source: 'assistant' });

  const upBtn = rowEl.querySelector('.assistant-feedback-btn[data-action="up"]');
  const downBtn = rowEl.querySelector('.assistant-feedback-btn[data-action="down"]');
  const applyReactionState = (direction = '') => {
    const normalizedDirection = String(direction || '').trim().toLowerCase();
    const isUp = normalizedDirection === 'up';
    const isDown = normalizedDirection === 'down';
    if (upBtn) {
      upBtn.classList.toggle('is-active', isUp);
      upBtn.setAttribute('aria-pressed', isUp ? 'true' : 'false');
    }
    if (downBtn) {
      downBtn.classList.toggle('is-active', isDown);
      downBtn.setAttribute('aria-pressed', isDown ? 'true' : 'false');
    }
  };
  if (upBtn) {
    upBtn.addEventListener('click', () => {
      const next = upBtn.classList.contains('is-active') ? '' : 'up';
      applyReactionState(next);
      logEvent('ui.assistant_feedback.click', 'ok', {
        reaction: next || 'clear',
      });
    });
  }
  if (downBtn) {
    downBtn.addEventListener('click', () => {
      const next = downBtn.classList.contains('is-active') ? '' : 'down';
      applyReactionState(next);
      logEvent('ui.assistant_feedback.click', 'ok', {
        reaction: next || 'clear',
      });
    });
  }
}

function extractWeeklyReportBullets(lines = [], startIdx = 0) {
  const bullets = [];
  for (let idx = startIdx; idx < lines.length; idx += 1) {
    const line = String(lines[idx] || '').trim();
    if (!line) {
      if (bullets.length) break;
      continue;
    }
    const matched = line.match(/^[-*]\s+(.+)$/);
    if (matched) {
      bullets.push(matched[1].trim());
      if (bullets.length >= 4) break;
      continue;
    }
    if (bullets.length) break;
    if (/^(?:이번주\s*주요\s*내용|핵심\s*인사이트|리스크|요청사항|이번주\s*실적|다음주\s*계획)/.test(line)) {
      break;
    }
  }
  return bullets;
}

function parseWeeklyPlanTable(lines = []) {
  let headerIndex = -1;
  for (let i = 0; i < lines.length; i += 1) {
    const line = String(lines[i] || '').trim();
    if (!line.includes('|')) continue;
    if (/실적/.test(line) && /계획/.test(line)) {
      headerIndex = i;
      break;
    }
  }
  if (headerIndex < 0 || headerIndex + 1 >= lines.length) return [];
  const rows = [];
  for (let i = headerIndex + 2; i < lines.length; i += 1) {
    const line = String(lines[i] || '').trim();
    if (!line || !line.includes('|')) break;
    const cells = line
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map((cell) => cell.trim());
    if (cells.length < 2) continue;
    const toBullets = (raw) => raw
      .split('<br>')
      .map((item) => item.replace(/^[-*]\s*/, '').trim())
      .filter(Boolean)
      .slice(0, 4);
    let date = '';
    let actualRaw = '';
    let planRaw = '';
    if (cells.length >= 3) {
      date = String(cells[0] || '').trim();
      actualRaw = String(cells[1] || '').trim();
      planRaw = String(cells[2] || '').trim();
    } else {
      date = '';
      actualRaw = String(cells[0] || '').trim();
      planRaw = String(cells[1] || '').trim();
    }
    const actualBullets = toBullets(actualRaw);
    const planBullets = toBullets(planRaw);
    if (!actualBullets.length && !planBullets.length) continue;
    rows.push({
      date: date || '미지정',
      actual_bullets: actualBullets,
      plan_bullets: planBullets,
    });
    if (rows.length >= 4) break;
  }
  return rows;
}

function normalizeWeeklyReportStructuredData(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const sections = raw.sections && typeof raw.sections === 'object' ? raw.sections : {};
  const ranges = raw.ranges && typeof raw.ranges === 'object' ? raw.ranges : {};
  const scrubWeeklyBulletText = (value) => {
    let text = String(value || '').trim();
    if (!text) return '';
    text = text.replace(/\(\s*참조\s*메일\s*[:：][^)]+\)\s*$/i, '');
    text = text.replace(/\(\s*mail[_\s-]?id\s*[:：][^)]+\)\s*$/i, '');
    text = text.replace(/\(\s*message[_\s-]?id\s*[:：][^)]+\)\s*$/i, '');
    text = text.replace(/\bAQMk[A-Za-z0-9+/_=-]{20,}\b/g, '');
    text = text.replace(/(?:참조\s*메일|mail[_\s-]?id|message[_\s-]?id)\s*[:：]\s*[A-Za-z0-9+/_=-]{20,}/gi, '');
    text = text.replace(/\s{2,}/g, ' ').trim();
    return text;
  };
  const normalizeBullets = (items, max = 6) => {
    if (!Array.isArray(items)) return [];
    const output = [];
    const seen = new Set();
    for (const item of items) {
      const text = scrubWeeklyBulletText(item);
      if (!text) continue;
      const token = text.replace(/\s+/g, ' ').toLowerCase();
      if (seen.has(token)) continue;
      seen.add(token);
      output.push(text);
      if (output.length >= max) break;
    }
    return output;
  };
  const normalizeSection = (name, max = 6) => {
    const section = sections[name] && typeof sections[name] === 'object' ? sections[name] : {};
    return {
      actual: normalizeBullets(section.actual, max),
      plan: normalizeBullets(section.plan, max),
    };
  };
  const normalized = {
    title: String(raw.title || '').trim(),
    meta: raw.meta && typeof raw.meta === 'object' ? raw.meta : {},
    ranges: {
      actual_range: String(ranges.actual_range || '').trim(),
      plan_range: String(ranges.plan_range || '').trim(),
    },
    sections: {
      main_progress: normalizeSection('main_progress', 6),
      issues: normalizeSection('issues', 4),
      etc: normalizeSection('etc', 3),
    },
  };
  const hasAnyBullets =
    normalized.sections.main_progress.actual.length ||
    normalized.sections.main_progress.plan.length ||
    normalized.sections.issues.actual.length ||
    normalized.sections.issues.plan.length ||
    normalized.sections.etc.actual.length ||
    normalized.sections.etc.plan.length;
  return hasAnyBullets ? normalized : null;
}

function normalizeWeeklyReportRanges(raw) {
  if (!raw || typeof raw !== 'object') return { actual_range: '', plan_range: '' };
  return {
    actual_range: String(raw.actual_range || '').trim(),
    plan_range: String(raw.plan_range || '').trim(),
  };
}

function parseWeeklyReportContent(rawText, structuredData = null, fallbackRanges = null) {
  const lines = String(rawText || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  const normalizedStructuredData = normalizeWeeklyReportStructuredData(structuredData);
  const result = {
    progress: '',
    highlights: [],
    insights: [],
    risks: [],
    plan_rows: parseWeeklyPlanTable(lines),
    structured_data: normalizedStructuredData,
    ranges: normalizeWeeklyReportRanges(fallbackRanges),
  };
  for (let i = 0; i < lines.length; i += 1) {
    const line = String(lines[i] || '').trim();
    if (!line) continue;
    if (!result.progress) {
      const progressMatch = line.match(/^진행\s*현황\s*[:：]\s*(.+)$/);
      if (progressMatch) {
        result.progress = progressMatch[1].trim();
        continue;
      }
    }
    if (/^이번주\s*주요\s*내용/.test(line)) {
      result.highlights = extractWeeklyReportBullets(lines, i + 1);
      continue;
    }
    if (/^핵심\s*인사이트/.test(line)) {
      result.insights = extractWeeklyReportBullets(lines, i + 1);
      continue;
    }
    if (/^(리스크|요청사항|리스크\/요청사항)/.test(line)) {
      result.risks = extractWeeklyReportBullets(lines, i + 1);
    }
  }
  return result;
}

function stripWeeklyBulletPrefix(value, rowType = 'main') {
  let text = String(value || '').trim();
  if (!text) return '';
  text = text.replace(/\(\s*참조\s*메일\s*[:：][^)]+\)\s*$/i, '');
  text = text.replace(/\(\s*mail[_\s-]?id\s*[:：][^)]+\)\s*$/i, '');
  text = text.replace(/\(\s*message[_\s-]?id\s*[:：][^)]+\)\s*$/i, '');
  text = text.replace(/\bAQMk[A-Za-z0-9+/_=-]{20,}\b/g, '');
  text = text.replace(/(?:참조\s*메일|mail[_\s-]?id|message[_\s-]?id)\s*[:：]\s*[A-Za-z0-9+/_=-]{20,}/gi, '');
  if (rowType === 'main') {
    text = text.replace(/^(?:주요\s*진행사항)\s*[-:]\s*/i, '');
    text = text.replace(/^(?:주요)\s*[-:]\s*/i, '');
  }
  if (rowType === 'issue') {
    text = text.replace(/^(?:이슈|핵심\s*이슈|리스크\/요청사항)\s*[-:]\s*/i, '');
  }
  if (rowType === 'main') {
    // 주요 진행사항 셀에서는 개별 메일 날짜 꼬리 표기를 제거한다.
    text = text.replace(/\(\s*날짜\s*[:：]?\s*\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\s*\)\s*$/i, '');
    text = text.replace(/\(\s*\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\s*\)\s*$/i, '');
    text = text.replace(/\(\s*\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\s*\)\s*$/i, '');
  }
  text = text.replace(/\s{2,}/g, ' ').trim();
  return text;
}

function renderWeeklyBullets(items = [], fallbackText = '') {
  const list = Array.isArray(items)
    ? items
      .map((item) => String(item || '').trim())
      .filter((item) => item && !/^(?:-|n\/?a|na|없음|none|null)$/i.test(item))
      .slice(0, 4)
    : [];
  if (!list.length) {
    const fallback = String(fallbackText || '').trim();
    return `<div class="weekly-report-empty">${fallback ? escapeHtml(fallback) : ''}</div>`;
  }
  const isFallbackDetail = (value) => /^(?:담당\s*\/?\s*기한\s*확인\s*필요)$/i.test(String(value || '').trim());
  const splitBulletParts = (value) => {
    const text = String(value || '').trim();
    if (!text) return { head: '', tail: '' };
    const hyphenMatch = /^(.+?)\s+-\s+(.+)$/.exec(text);
    if (hyphenMatch) {
      return {
        head: String(hyphenMatch[1] || '').trim(),
        tail: String(hyphenMatch[2] || '').trim(),
      };
    }
    // "핵심 1줄 + 상세 1줄" 포맷을 최대한 맞추기 위해, 구분자가 없으면 자동 분할한다.
    if (text.length > 30) {
      const sentenceSplit = text.split(/\s+(?=[가-힣A-Za-z0-9]{2,}\s*(?:및|후|으로|관련|대응|확정|정리|반영|검토|공유))/);
      if (sentenceSplit.length >= 2) {
        const head = String(sentenceSplit[0] || '').trim();
        const tail = String(text.slice(head.length).trim()).replace(/^\s+/, '');
        return { head, tail };
      }
      const cut = Math.min(24, Math.max(12, text.indexOf(' ', 10)));
      if (cut > 0 && cut < text.length - 4) {
        return {
          head: text.slice(0, cut).trim(),
          tail: text.slice(cut).trim(),
        };
      }
    }
    return { head: text, tail: '' };
  };
  const renderItem = (raw) => {
    const parts = splitBulletParts(raw);
    const headText = String(parts.head || '').trim();
    const tailText = String(parts.tail || '').trim();
    if (!headText && !tailText) return '';
    const head = escapeHtml(headText || tailText);
    const shouldShowTail = Boolean(tailText) && !isFallbackDetail(tailText);
    if (!shouldShowTail) return `<span class="weekly-bullet-head">${head}</span>`;
    const tail = escapeHtml(tailText);
    return `<span class="weekly-bullet-head">${head}</span><br><span class="weekly-bullet-tail">- ${tail}</span>`;
  };
  const htmlItems = list
    .map((item) => renderItem(item))
    .filter(Boolean);
  if (!htmlItems.length) return `<div class="weekly-report-empty"></div>`;
  return `<ul>${htmlItems.map((itemHtml) => `<li>${itemHtml}</li>`).join('')}</ul>`;
}

function collectWeeklyOnePageRows(parsed = {}) {
  const structured = normalizeWeeklyReportStructuredData(parsed?.structured_data);
  if (structured) {
    const main = structured.sections.main_progress || { actual: [], plan: [] };
    const issues = structured.sections.issues || { actual: [], plan: [] };
    const mainActualRaw = (Array.isArray(main.actual) ? main.actual : []).map((item) =>
      stripWeeklyBulletPrefix(item, 'main')
    ).filter(Boolean);
    const mainPlanRaw = (Array.isArray(main.plan) ? main.plan : []).map((item) =>
      stripWeeklyBulletPrefix(item, 'main')
    ).filter(Boolean);
    const issueActual = (Array.isArray(issues.actual) ? issues.actual : []).map((item) =>
      stripWeeklyBulletPrefix(item, 'issue')
    ).filter(Boolean);
    const issuePlan = (Array.isArray(issues.plan) ? issues.plan : []).map((item) =>
      stripWeeklyBulletPrefix(item, 'issue')
    ).filter(Boolean);

    const mainActual = [];
    const mainPlan = [];
    const migratedIssueActual = [...issueActual];
    const migratedIssuePlan = [...issuePlan];
    mainActualRaw.forEach((item) => {
      if (/^(?:이슈|핵심\s*이슈|리스크)/i.test(item)) {
        migratedIssueActual.push(stripWeeklyBulletPrefix(item, 'issue'));
      } else {
        mainActual.push(item);
      }
    });
    mainPlanRaw.forEach((item) => {
      if (/^(?:이슈|핵심\s*이슈|리스크)/i.test(item)) {
        migratedIssuePlan.push(stripWeeklyBulletPrefix(item, 'issue'));
      } else {
        mainPlan.push(item);
      }
    });
    return {
      main_actual: mainActual.slice(0, 6),
      main_plan: mainPlan.slice(0, 6),
      issue_actual: migratedIssueActual.slice(0, 5),
      issue_plan: migratedIssuePlan.slice(0, 5),
      actual_range: String(structured.ranges?.actual_range || parsed?.ranges?.actual_range || '').trim(),
      plan_range: String(structured.ranges?.plan_range || parsed?.ranges?.plan_range || '').trim(),
    };
  }
  const rows = Array.isArray(parsed?.plan_rows) ? parsed.plan_rows : [];
  const actualMain = [];
  const planMain = [];
  rows.forEach((row) => {
    const date = String(row?.date || '').trim();
    const actual = Array.isArray(row?.actual_bullets) ? row.actual_bullets : [];
    const plan = Array.isArray(row?.plan_bullets) ? row.plan_bullets : [];
    actual.forEach((item) => {
      const text = String(item || '').trim();
      if (!text) return;
      actualMain.push(stripWeeklyBulletPrefix(date && date !== '미지정' ? `${date} - ${text}` : text, 'main'));
    });
    plan.forEach((item) => {
      const text = String(item || '').trim();
      if (!text) return;
      planMain.push(stripWeeklyBulletPrefix(date && date !== '미지정' ? `${date} - ${text}` : text, 'main'));
    });
  });
  const issueSource = Array.isArray(parsed?.risks) ? parsed.risks : [];
  const actualIssue = issueSource.length
    ? issueSource.map((item) => stripWeeklyBulletPrefix(item, 'issue')).filter(Boolean)
    : [];
  const planIssue = issueSource.length
    ? issueSource.map((item) => `조치 계획: ${stripWeeklyBulletPrefix(item, 'issue')}`).filter(Boolean)
    : [];
  return {
    main_actual: actualMain.slice(0, 6),
    main_plan: planMain.slice(0, 6),
    issue_actual: actualIssue.slice(0, 5),
    issue_plan: planIssue.slice(0, 5),
    actual_range: String(parsed?.ranges?.actual_range || '').trim(),
    plan_range: String(parsed?.ranges?.plan_range || '').trim(),
  };
}

function renderWeeklyPlanRows(planRows = []) {
  const rows = Array.isArray(planRows) ? planRows : [];
  if (!rows.length) {
    return (
      '<tr>' +
      '<td>미지정</td>' +
      '<td><div class="weekly-report-empty"></div></td>' +
      '<td><div class="weekly-report-empty"></div></td>' +
      '</tr>'
    );
  }
  return rows.map((row) => {
    const actualHtml = renderWeeklyBullets(row.actual_bullets || []);
    const planHtml = renderWeeklyBullets(row.plan_bullets || []);
    return `<tr><td>${escapeHtml(String(row.date || '미지정'))}</td><td>${actualHtml}</td><td>${planHtml}</td></tr>`;
  }).join('');
}

function buildWeeklyReportCardHtml(rawText, structuredData = null, fallbackRanges = null) {
  const parsed = parseWeeklyReportContent(rawText, structuredData, fallbackRanges);
  const onePage = collectWeeklyOnePageRows(parsed);
  const actualHeader = onePage.actual_range ? `실적(${escapeHtml(onePage.actual_range)})` : '실적';
  const planHeader = onePage.plan_range ? `계획(${escapeHtml(onePage.plan_range)})` : '계획';
  const previewPlan = (
    '<tr>' +
    '<td>주요 진행사항</td>' +
    `<td>${renderWeeklyBullets(onePage.main_actual)}</td>` +
    `<td>${renderWeeklyBullets(onePage.main_plan)}</td>` +
    '</tr>' +
    '<tr>' +
    '<td>이슈</td>' +
    `<td>${renderWeeklyBullets(onePage.issue_actual)}</td>` +
    `<td>${renderWeeklyBullets(onePage.issue_plan)}</td>` +
    '</tr>'
  );

  return (
    '<div class="weekly-report-shell">' +
    '<div class="weekly-report-head">' +
    `<span class="weekly-report-head-icon">${ICONS.calendar}</span>` +
    '<span class="weekly-report-head-title">주간보고</span>' +
    '</div>' +
    '<div class="weekly-report-progress">1페이지 요약 문서를 준비했습니다.</div>' +
    '<div class="weekly-report-sections">' +
    '<div class="weekly-report-right-pane">' +
    '<div class="weekly-report-pane-title">미리보기</div>' +
    '<div class="weekly-report-preview-stage">' +
    '<div class="weekly-report-preview-doc weekly-report-preview-sheet">' +
    '<div class="weekly-report-preview-doc-topline"></div>' +
    '<div class="weekly-report-preview-doc-title">주간보고 (미리보기)</div>' +
    '<div class="weekly-report-preview-mini-table-wrap">' +
    '<table class="weekly-report-preview-mini-table">' +
    `<thead><tr><th>구분</th><th>${actualHeader}</th><th>${planHeader}</th></tr></thead>` +
    `<tbody>${previewPlan}</tbody>` +
    '</table>' +
    '</div>' +
    '</div>' +
    '</div>' +
    '<div class="weekly-report-preview-row">' +
    '<button class="weekly-report-preview-btn" type="button">미리보기</button>' +
    '</div>' +
    '</div>' +
    '</div>' +
    '</div>'
  );
}

function toSafeDownloadFileName(value, fallback = 'weekly-report') {
  const normalized = String(value || fallback).trim() || fallback;
  const safe = normalized
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
  return safe || fallback;
}

function triggerBlobDownload(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function downloadWeeklyReportDocx(markdownText, reportFileName = 'weekly-report', structuredData = null, fallbackRanges = null) {
  const result = await buildWeeklyReportDocxBlob(markdownText, reportFileName, { showToast: true, structuredData, fallbackRanges });
  const safeName = toSafeDownloadFileName(reportFileName, 'weekly-report');
  triggerBlobDownload(result.blob, `${safeName}.docx`);
  return result;
}

async function downloadWeeklyReportDocxFromServer(markdownText, reportFileName = 'weekly-report') {
  const response = await fetch('/addin/export/weekly-report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      format: 'docx',
      markdown: String(markdownText || ''),
      file_name: String(reportFileName || 'weekly-report'),
    }),
  });
  if (!response.ok) {
    let errorMessage = 'DOCX 내보내기에 실패했습니다.';
    try {
      const payload = await response.json();
      if (payload && payload.detail) errorMessage = String(payload.detail);
    } catch (_) {
      // noop
    }
    return { error: new Error(errorMessage), blob: null };
  }
  const blob = await response.blob();
  return { error: null, blob };
}

const weeklyDocxBlobCache = new Map();
const weeklyDocxInFlight = new Map();

function getWeeklyDocxCacheKey(markdownText, reportFileName, structuredData = null) {
  const safeName = toSafeDownloadFileName(reportFileName, 'weekly-report');
  const structuredKey = structuredData && typeof structuredData === 'object'
    ? JSON.stringify(structuredData).length
    : 0;
  return `${safeName}:${String(markdownText || '').length}:${structuredKey}`;
}

async function buildWeeklyReportDocxBlob(markdownText, reportFileName = 'weekly-report', options = {}) {
  const showToast = options?.showToast !== false;
  const structuredData = options?.structuredData || null;
  const fallbackRanges = options?.fallbackRanges || null;
  const key = getWeeklyDocxCacheKey(markdownText, reportFileName, structuredData);
  if (weeklyDocxBlobCache.has(key)) {
    return { blob: weeklyDocxBlobCache.get(key), source: 'cache' };
  }
  if (weeklyDocxInFlight.has(key)) {
    return weeklyDocxInFlight.get(key);
  }
  const work = (async () => {
    if (showToast) startWeeklyDocxBuildToast();
    setWeeklyDocxBuildStatus('본문 파싱');
    appendWeeklyDocxBuildLine('const parsed = parseWeeklyReport(markdown);');
    const parsed = parseWeeklyReportContent(String(markdownText || ''), structuredData, fallbackRanges);
    const title = toSafeDownloadFileName(reportFileName, 'weekly-report');
    try {
      setWeeklyDocxBuildStatus('HTML 템플릿 조립');
      appendWeeklyDocxBuildLine("const template = ['<!doctype html>', '<body>'];");
      const htmlTemplate = buildWeeklyReportHtmlTemplate(parsed, title);
      appendWeeklyDocxBuildLine('template.push(renderWeeklyTable(plan_rows));');
      appendWeeklyDocxBuildLine('const html = template.join("");');
      setWeeklyDocxBuildStatus('HTML→DOCX 변환');
      const htmlDocxApi = await ensureHtmlDocxBrowserLibrary();
      appendWeeklyDocxBuildLine('const htmlDocx = await ensureHtmlDocxBrowserLibrary();');
      const blob = htmlDocxApi.asBlob(htmlTemplate);
      appendWeeklyDocxBuildLine('const blob = htmlDocx.asBlob(html);');
      weeklyDocxBlobCache.set(key, blob);
      if (showToast) {
        appendWeeklyDocxBuildLine(`ready("${title}.docx");`);
        finishWeeklyDocxBuildToast(true, `${title}.docx 생성 완료 (html-template)`);
      }
      return { blob, source: 'html-template' };
    } catch (browserError) {
      appendWeeklyDocxBuildLine('// html-template failed, fallback to docx-js');
      setWeeklyDocxBuildStatus('DOCX JS fallback');
      try {
        const docxApi = await ensureDocxBrowserLibrary();
        appendWeeklyDocxBuildLine('const docx = await ensureDocxBrowserLibrary();');
        const documentNode = buildWeeklyReportDocxDocument(docxApi, parsed, title);
        appendWeeklyDocxBuildLine('const doc = buildWeeklyReportDocxDocument(docx, parsed);');
        const blob = await docxApi.Packer.toBlob(documentNode);
        appendWeeklyDocxBuildLine('const blob = await docx.Packer.toBlob(doc);');
        weeklyDocxBlobCache.set(key, blob);
        if (showToast) finishWeeklyDocxBuildToast(true, `${title}.docx 생성 완료 (docx-js fallback)`);
        return { blob, source: 'docx-js-fallback' };
      } catch (docxJsError) {
        appendWeeklyDocxBuildLine('// docx-js failed, fallback to server export');
      }
      setWeeklyDocxBuildStatus('서버 fallback');
      const { error: fallbackError, blob } = await downloadWeeklyReportDocxFromServer(markdownText, title);
      if (!fallbackError && blob) {
        weeklyDocxBlobCache.set(key, blob);
        if (showToast) finishWeeklyDocxBuildToast(true, `${title}.docx 생성 완료 (server-fallback)`);
        return { blob, source: 'server-fallback' };
      }
      if (showToast) {
        finishWeeklyDocxBuildToast(false, String(browserError?.message || fallbackError?.message || 'DOCX 생성 실패'));
      }
      throw (fallbackError || browserError);
    } finally {
      weeklyDocxInFlight.delete(key);
    }
  })();
  weeklyDocxInFlight.set(key, work);
  return work;
}

const weeklyResultToastShownKeys = new Set();

function showWeeklyReportResultToast({ markdownText, fileName, formats, structuredData = null, fallbackRanges = null }) {
  const safeName = toSafeDownloadFileName(fileName, 'weekly-report');
  const key = `${safeName}:${String(markdownText || '').length}`;
  if (weeklyResultToastShownKeys.has(key)) return;
  weeklyResultToastShownKeys.add(key);
  const toastId = 'weeklyReportResultToast';
  const existing = document.getElementById(toastId);
  if (existing) existing.remove();
  const enableMd = Array.isArray(formats) && formats.includes('md');
  const enableDocx = Array.isArray(formats) && formats.includes('docx');
  const hasReadyDocx = weeklyDocxBlobCache.has(getWeeklyDocxCacheKey(markdownText, safeName, structuredData));
  const html = `
    <div class="weekly-result-toast" id="${toastId}">
      <div class="weekly-result-toast-head">
        <span class="weekly-result-toast-title">주간보고 생성 완료${hasReadyDocx ? ' · DOCX 준비됨' : ''}</span>
        <button type="button" class="weekly-result-toast-close" aria-label="닫기">닫기</button>
      </div>
      <div class="weekly-result-toast-desc">미리보기 확인 후 바로 다운로드할 수 있습니다.</div>
      <div class="weekly-result-toast-actions">
        <button type="button" class="weekly-result-toast-btn" data-action="preview">미리보기</button>
        ${enableMd ? '<button type="button" class="weekly-result-toast-btn" data-action="md">Markdown</button>' : ''}
        ${enableDocx ? '<button type="button" class="weekly-result-toast-btn" data-action="docx">Word</button>' : ''}
      </div>
    </div>
  `;
  document.body.insertAdjacentHTML('beforeend', html);
  const toastEl = document.getElementById(toastId);
  if (!toastEl) return;
  const close = () => toastEl.remove();
  toastEl.querySelector('.weekly-result-toast-close')?.addEventListener('click', close);
  toastEl.querySelectorAll('.weekly-result-toast-btn').forEach((buttonEl) => {
    buttonEl.addEventListener('click', async () => {
      const action = String(buttonEl.getAttribute('data-action') || '').trim().toLowerCase();
      if (action === 'preview') {
        openWeeklyReportPreviewModal(markdownText, safeName, structuredData, fallbackRanges);
        return;
      }
      buttonEl.disabled = true;
      try {
        if (action === 'md') {
          const blob = new Blob([String(markdownText || '')], { type: 'text/markdown;charset=utf-8' });
          triggerBlobDownload(blob, `${safeName}.md`);
        } else if (action === 'docx') {
          const cacheKey = getWeeklyDocxCacheKey(markdownText, safeName, structuredData);
          if (weeklyDocxBlobCache.has(cacheKey)) {
            triggerBlobDownload(weeklyDocxBlobCache.get(cacheKey), `${safeName}.docx`);
          } else {
            await downloadWeeklyReportDocx(markdownText, safeName, structuredData, fallbackRanges);
          }
        }
      } finally {
        buttonEl.disabled = false;
      }
    });
  });
  window.setTimeout(() => {
    if (toastEl.isConnected) toastEl.remove();
  }, 12000);
}

function attachWeeklyReportDownloadActions(container, uiOutputV2, sourceText, options = {}) {
  if (!container || !uiOutputV2 || uiOutputV2.type !== 'weekly_report') return;
  if (container.querySelector('.weekly-report-download-row')) return;
  const autoBuildDocx = options?.autoBuildDocx !== false;
  const showResultToast = options?.showResultToast !== false;

  const weeklyReport = uiOutputV2.weekly_report || {};
  const weeklyData = weeklyReport.data && typeof weeklyReport.data === 'object'
    ? weeklyReport.data
    : null;
  const weeklyRanges = normalizeWeeklyReportRanges(weeklyReport.ranges);
  const formats = Array.isArray(weeklyReport.download_formats) && weeklyReport.download_formats.length
    ? weeklyReport.download_formats
    : ['md', 'docx'];
  const fileName = toSafeDownloadFileName(
    weeklyReport.report_file_name || 'weekly-report',
    'weekly-report'
  );
  const markdownText = String(uiOutputV2?.body?.text || sourceText || '').trim();
  if (!markdownText) return;

  const buttonHtml = [];
  if (formats.includes('md')) {
    buttonHtml.push('<button class="weekly-report-download-btn" type="button" data-format="md">Markdown</button>');
  }
  if (formats.includes('docx')) {
    buttonHtml.push('<button class="weekly-report-download-btn" type="button" data-format="docx">Word 생성중...</button>');
  }
  if (!buttonHtml.length) return;

  container.insertAdjacentHTML(
    'beforeend',
    '<div class="weekly-report-download-row">' +
    '<div class="weekly-report-file-card">' +
    `<div class="weekly-report-file-icon">${ICONS.fileText}</div>` +
    '<div class="weekly-report-file-meta">' +
    `<div class="weekly-report-file-name">${escapeHtml(fileName)}</div>` +
    '<div class="weekly-report-file-type">문서 · DOCX/MD</div>' +
    '</div>' +
    `<div class="weekly-report-file-actions">${buttonHtml.join('')}</div>` +
    '</div>' +
    '</div>'
  );
  const row = container.querySelector('.weekly-report-download-row:last-of-type');
  if (!row) return;
  const previewBtn = container.querySelector('.weekly-report-preview-btn');
  if (previewBtn) {
    previewBtn.addEventListener('click', () => {
      openWeeklyReportPreviewModal(markdownText, fileName, weeklyData, weeklyRanges);
    });
  }
  row.querySelectorAll('.weekly-report-download-btn').forEach((buttonEl) => {
    buttonEl.addEventListener('click', async () => {
      const format = String(buttonEl.getAttribute('data-format') || '').trim().toLowerCase();
      buttonEl.disabled = true;
      try {
        if (format === 'md') {
          const blob = new Blob([markdownText], { type: 'text/markdown;charset=utf-8' });
          triggerBlobDownload(blob, `${fileName}.md`);
        } else if (format === 'docx') {
          const cacheKey = getWeeklyDocxCacheKey(markdownText, fileName, weeklyData);
          if (weeklyDocxBlobCache.has(cacheKey)) {
            triggerBlobDownload(weeklyDocxBlobCache.get(cacheKey), `${fileName}.docx`);
          } else {
            await downloadWeeklyReportDocx(markdownText, fileName, weeklyData, weeklyRanges);
          }
        }
        flashIconActionFeedback(buttonEl, {
          okLabel: '다운로드 완료',
          failLabel: '다운로드 실패',
          success: true,
        });
      } catch (error) {
        if (format === 'docx') {
          finishWeeklyDocxBuildToast(false, String(error?.message || 'DOCX 생성 실패'));
        }
        flashIconActionFeedback(buttonEl, {
          okLabel: '다운로드 완료',
          failLabel: '다운로드 실패',
          success: false,
        });
        logError('weekly_report.download_failed', error);
      } finally {
        buttonEl.disabled = false;
      }
    });
  });
  const fileTypeEl = row.querySelector('.weekly-report-file-type');
  const docxButtonEl = row.querySelector('.weekly-report-download-btn[data-format="docx"]');
  if (docxButtonEl) {
    if (autoBuildDocx) {
      docxButtonEl.disabled = true;
      buildWeeklyReportDocxBlob(markdownText, fileName, { showToast: true, structuredData: weeklyData, fallbackRanges: weeklyRanges })
        .then(() => {
          docxButtonEl.textContent = 'Microsoft Word';
          docxButtonEl.disabled = false;
          if (fileTypeEl) fileTypeEl.textContent = '문서 · DOCX 준비 완료';
        })
        .catch((error) => {
          docxButtonEl.textContent = 'Word 재시도';
          docxButtonEl.disabled = false;
          if (fileTypeEl) fileTypeEl.textContent = '문서 · DOCX 생성 실패';
          logError('weekly_report.docx_auto_build_failed', error);
        })
        .finally(() => {
          if (showResultToast) {
            showWeeklyReportResultToast({
              markdownText,
              fileName,
              formats,
              structuredData: weeklyData,
              fallbackRanges: weeklyRanges,
            });
          }
        });
      return;
    }
    docxButtonEl.textContent = 'Microsoft Word';
  }
  if (showResultToast) {
    showWeeklyReportResultToast({
      markdownText,
      fileName,
      formats,
      structuredData: weeklyData,
      fallbackRanges: weeklyRanges,
    });
  }
}

function openWeeklyReportPreviewModal(markdownText, title = 'weekly-report', structuredData = null, fallbackRanges = null) {
  const parsed = parseWeeklyReportContent(markdownText, structuredData, fallbackRanges);
  const wordPreviewHtml = buildWeeklyReportWordPreviewHtml(parsed, title);
  const existing = document.getElementById('weeklyReportPreviewModal');
  if (existing) existing.remove();
  const modalId = 'weeklyReportPreviewModal';
  const html = `
    <div class="weekly-report-modal-backdrop" id="${modalId}">
      <div class="weekly-report-modal">
        <div class="weekly-report-modal-head">
          <div class="weekly-report-modal-title">${escapeHtml(title)}</div>
          <button type="button" class="weekly-report-modal-close" aria-label="닫기">닫기</button>
        </div>
        <div class="weekly-report-modal-body">${wordPreviewHtml}</div>
      </div>
    </div>
  `;
  document.body.insertAdjacentHTML('beforeend', html);
  const modal = document.getElementById(modalId);
  if (!modal) return;
  const close = () => modal.remove();
  modal.querySelector('.weekly-report-modal-close')?.addEventListener('click', close);
  modal.addEventListener('click', (event) => {
    if (event.target === modal) close();
  });
}

function buildWeeklyReportWordPreviewHtml(parsed, title = 'weekly-report') {
  const onePage = collectWeeklyOnePageRows(parsed);
  const actualHeader = onePage.actual_range ? `실적(${escapeHtml(onePage.actual_range)})` : '실적';
  const planHeader = onePage.plan_range ? `계획(${escapeHtml(onePage.plan_range)})` : '계획';
  const tableRowsHtml =
    '<tr>' +
    '<td>주요 진행사항</td>' +
    `<td>${renderWeeklyBullets(onePage.main_actual)}</td>` +
    `<td>${renderWeeklyBullets(onePage.main_plan)}</td>` +
    '</tr>' +
    '<tr>' +
    '<td>이슈</td>' +
    `<td>${renderWeeklyBullets(onePage.issue_actual)}</td>` +
    `<td>${renderWeeklyBullets(onePage.issue_plan)}</td>` +
    '</tr>';
  return (
    '<div class="weekly-word-preview">' +
    '<div class="weekly-word-preview-topline"></div>' +
    `<div class="weekly-word-preview-title">${escapeHtml(title)}</div>` +
    '<div class="weekly-word-preview-table-wrap">' +
    '<table class="weekly-word-preview-table">' +
    `<thead><tr><th>구분</th><th>${actualHeader}</th><th>${planHeader}</th></tr></thead>` +
    `<tbody>${tableRowsHtml}</tbody>` +
    '</table>' +
    '</div>' +
    '</div>'
  );
}

function attachAssistantMessageActions(bodyEl, text, renderState, uiOutputV2 = null, options = {}) {
  if (!bodyEl || renderState.promiseAnalysis) return;
  const normalizedUiOutputV2 = normalizeUiOutputV2Payload(uiOutputV2);
  if (normalizedUiOutputV2?.type === 'weekly_report') {
    const feedbackText = String(normalizedUiOutputV2?.body?.text || text || '').trim();
    const isHistoryRestore = Boolean(options?.isHistoryRestore);
    attachWeeklyReportDownloadActions(bodyEl, normalizedUiOutputV2, feedbackText, {
      autoBuildDocx: !isHistoryRestore,
      showResultToast: !isHistoryRestore,
    });
    return;
  }
  const feedbackEnabled = normalizedUiOutputV2 ? normalizedUiOutputV2.feedback !== false : true;
  const feedbackText = String(normalizedUiOutputV2?.body?.text || text || '').trim();
  logEvent('mail.open_candidates.parsed', 'ok', {
    enabled: renderState.shouldAttachOpenMailList,
    fromMetadata: renderState.metadataItems.length,
    attached: renderState.openableItems.length,
  });
  if (renderState.openableItems.length) {
    attachNativeOpenMailList(bodyEl, '', renderState.openableItems);
  }
  if (renderState.shouldAttachReplyAction) {
    attachReplyComposerAction(bodyEl, text);
  }
  if (renderState.shouldAttachRestartAction && !renderState.openableItems.length) {
    attachRestartSessionAction(bodyEl);
  }
  if (feedbackEnabled) {
    attachAssistantFeedbackActionRow(bodyEl, feedbackText);
  }
}

function addAssistantMessage(text, options = {}) {
  const {
    save = true,
    metadata = null,
    replyDraft = false,
    uiOutput = null,
    uiOutputV2 = null,
    forceRestartAction = false,
    openableItems: persistedOpenableItems = null,
    suppressAssistantActions = false,
    restore = false,
  } = options;
  const chatArea = document.getElementById('chatArea');
  removeWelcomeStateIfExists();
  const normalizedUiOutputV2 = normalizeUiOutputV2Payload(
    uiOutputV2
      || metadata?.ui_output_v2
      || metadata?.uiOutputV2
      || null
  );
  const renderState = computeAssistantRenderState({
    text,
    metadata,
    replyDraft,
    forceRestartAction,
    persistedOpenableItems,
    uiOutputV2: normalizedUiOutputV2,
  });
  const { bodyHtml, isCardMessage } = buildAssistantMessageBodyHtml(
    text,
    renderState,
    uiOutput,
    normalizedUiOutputV2,
    {
      replyDraft,
    }
  );
  const html = `
    <div class="message assistant${isCardMessage ? ' assistant-card-message' : ''}">
      <div class="msg-body${isCardMessage ? ' msg-body-card' : ''}">${bodyHtml}</div>
    </div>`;
  chatArea.insertAdjacentHTML('beforeend', html);
  const lastMessage = chatArea.lastElementChild;
  const bodyEl = lastMessage?.querySelector('.msg-body');
  if (!suppressAssistantActions) {
    attachAssistantMessageActions(bodyEl, text, renderState, normalizedUiOutputV2, {
      isHistoryRestore: Boolean(restore),
    });
  }
  if (save) {
    recordHistory('assistant', text, {
      uiOutput,
      uiOutputV2: normalizedUiOutputV2,
      replyDraft: Boolean(replyDraft),
      openableItems: renderState.openableItems,
    });
    persistTaskpaneState();
  }
  scrollToBottom();
}

function showStreamingAssistantMessage(initialText = '') {
  const chatArea = document.getElementById('chatArea');
  removeWelcomeStateIfExists();
  const id = 'assistant_stream_' + Date.now();
  const html = `
    <div class="message assistant streaming-message" id="${id}">
      <div class="msg-body">${renderMarkdown(initialText || '작성 중...')}</div>
    </div>`;
  chatArea.insertAdjacentHTML('beforeend', html);
  scrollToBottom();
  return {
    id,
    text: String(initialText || ''),
    rafId: 0,
    dirty: false,
  };
}

function scheduleStreamingAssistantRender(handle) {
  if (!handle || handle.rafId) return;
  handle.rafId = window.requestAnimationFrame(() => {
    handle.rafId = 0;
    if (!handle.dirty) return;
    const root = document.getElementById(handle.id);
    const bodyEl = root?.querySelector('.msg-body');
    if (!bodyEl) return;
    const text = sanitizeAssistantDisplayText(String(handle.text || '').trim());
    bodyEl.innerHTML = renderMarkdown(text || '작성 중...');
    handle.dirty = false;
    scrollToBottom();
  });
}

function updateStreamingAssistantMessage(handle, text, options = {}) {
  if (!handle) return;
  const append = options?.append !== false;
  const incoming = String(text || '');
  if (!incoming && append) return;
  handle.text = append ? `${String(handle.text || '')}${incoming}` : incoming;
  handle.dirty = true;
  scheduleStreamingAssistantRender(handle);
}

function resetStreamingAssistantMessage(handle) {
  if (!handle) return;
  handle.text = '';
  handle.dirty = true;
  scheduleStreamingAssistantRender(handle);
}

function removeStreamingAssistantMessage(handle) {
  if (!handle) return;
  if (handle.rafId) {
    window.cancelAnimationFrame(handle.rafId);
    handle.rafId = 0;
  }
  const root = document.getElementById(handle.id);
  if (root) root.remove();
}

function addSystemMessage(text, options = {}) {
  const { save = true } = options;
  const chatArea = document.getElementById('chatArea');
  removeWelcomeStateIfExists();
  const html = `<div class="system-msg">${escapeHtml(text)}</div>`;
  chatArea.insertAdjacentHTML('beforeend', html);
  if (save) {
    recordHistory('system', text);
    persistTaskpaneState();
  }
  scrollToBottom();
}

function showTyping() {
  const chatArea = document.getElementById('chatArea');
  const id = 'typing_' + Date.now();
  const html = `
    <div class="message assistant" id="${id}">
      <div class="msg-body typing-indicator">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    </div>`;
  chatArea.insertAdjacentHTML('beforeend', html);
  scrollToBottom();
  return id;
}

function removeTyping(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

let weeklyDocxBuildState = {
  el: null,
  linesEl: null,
  statusEl: null,
  lineSeq: 0,
};

let docxBrowserLibraryPromise = null;
const DOCX_BROWSER_SOURCE_URLS = [
  'https://unpkg.com/docx@9.5.1/dist/index.umd.cjs',
  'https://unpkg.com/docx@9.5.1/build/index.umd.js',
];
let htmlDocxBrowserLibraryPromise = null;
const HTML_DOCX_SOURCE_URLS = [
  'https://unpkg.com/html-docx-js/dist/html-docx.js',
];

function ensureWeeklyDocxBuildToast() {
  if (weeklyDocxBuildState.el && weeklyDocxBuildState.el.isConnected) return weeklyDocxBuildState.el;
  const existing = document.getElementById('weeklyDocxBuildToast');
  if (existing) {
    weeklyDocxBuildState.el = existing;
    weeklyDocxBuildState.linesEl = existing.querySelector('.weekly-docx-build-lines');
    weeklyDocxBuildState.statusEl = existing.querySelector('.weekly-docx-build-status');
    return existing;
  }
  const html = `
    <div class="weekly-docx-build-toast hidden" id="weeklyDocxBuildToast">
      <div class="weekly-docx-build-head">
        <span class="weekly-docx-build-title">DOCX 생성 스크립트</span>
        <span class="weekly-docx-build-status">대기</span>
      </div>
      <pre class="weekly-docx-build-code"><code class="weekly-docx-build-lines"></code></pre>
    </div>
  `;
  document.body.insertAdjacentHTML('beforeend', html);
  const el = document.getElementById('weeklyDocxBuildToast');
  weeklyDocxBuildState.el = el;
  weeklyDocxBuildState.linesEl = el?.querySelector('.weekly-docx-build-lines') || null;
  weeklyDocxBuildState.statusEl = el?.querySelector('.weekly-docx-build-status') || null;
  return el;
}

function startWeeklyDocxBuildToast() {
  const el = ensureWeeklyDocxBuildToast();
  if (!el) return;
  el.classList.remove('hidden', 'is-error', 'is-done');
  weeklyDocxBuildState.lineSeq = 0;
  if (weeklyDocxBuildState.linesEl) weeklyDocxBuildState.linesEl.textContent = '';
  if (weeklyDocxBuildState.statusEl) weeklyDocxBuildState.statusEl.textContent = '초기화';
}

function appendWeeklyDocxBuildLine(line) {
  if (!weeklyDocxBuildState.linesEl) return;
  const script = String(line || '').trim();
  if (!script) return;
  weeklyDocxBuildState.lineSeq += 1;
  const numbered = `${String(weeklyDocxBuildState.lineSeq).padStart(2, '0')}. ${script}`;
  const current = String(weeklyDocxBuildState.linesEl.textContent || '').trim();
  const merged = current ? `${current}\n${numbered}` : numbered;
  weeklyDocxBuildState.linesEl.textContent = merged.split('\n').slice(-10).join('\n');
}

function setWeeklyDocxBuildStatus(label) {
  if (!weeklyDocxBuildState.statusEl) return;
  weeklyDocxBuildState.statusEl.textContent = String(label || '진행 중').trim();
}

function finishWeeklyDocxBuildToast(ok = true, message = '') {
  const el = ensureWeeklyDocxBuildToast();
  if (!el) return;
  el.classList.remove('is-error', 'is-done');
  el.classList.add(ok ? 'is-done' : 'is-error');
  if (weeklyDocxBuildState.statusEl) {
    weeklyDocxBuildState.statusEl.textContent = ok ? '완료' : '실패';
  }
  if (weeklyDocxBuildState.linesEl && message) {
    const current = String(weeklyDocxBuildState.linesEl.textContent || '').trim();
    weeklyDocxBuildState.linesEl.textContent = current
      ? `${current}\n// ${message}`
      : `// ${message}`;
  }
  window.setTimeout(() => {
    el.classList.add('hidden');
  }, ok ? 1200 : 1800);
}

function resolveDocxBrowserApi() {
  if (window.docx && typeof window.docx === 'object') {
    if (window.docx.Packer) return window.docx;
    if (window.docx.default && window.docx.default.Packer) return window.docx.default;
  }
  return null;
}

function resolveHtmlDocxBrowserApi() {
  if (window.htmlDocx && typeof window.htmlDocx.asBlob === 'function') {
    return window.htmlDocx;
  }
  return null;
}

function loadExternalScript(url) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-external-lib="${url}"]`);
    if (existing && existing.dataset.loaded === 'true') {
      resolve();
      return;
    }
    const scriptEl = existing || document.createElement('script');
    scriptEl.src = url;
    scriptEl.async = true;
    scriptEl.dataset.externalLib = url;
    scriptEl.onload = () => {
      scriptEl.dataset.loaded = 'true';
      resolve();
    };
    scriptEl.onerror = () => {
      reject(new Error(`외부 스크립트를 불러오지 못했습니다: ${url}`));
    };
    if (!existing) document.head.appendChild(scriptEl);
  });
}

async function ensureDocxBrowserLibrary() {
  const cachedApi = resolveDocxBrowserApi();
  if (cachedApi) return cachedApi;
  if (docxBrowserLibraryPromise) return docxBrowserLibraryPromise;
  docxBrowserLibraryPromise = (async () => {
    for (const url of DOCX_BROWSER_SOURCE_URLS) {
      try {
        appendWeeklyDocxBuildLine(`await importDocx("${url}");`);
        await loadExternalScript(url);
        const api = resolveDocxBrowserApi();
        if (api) return api;
      } catch (_) {
        // try next source
      }
    }
    throw new Error('브라우저 DOCX 라이브러리 로드 실패');
  })();
  try {
    return await docxBrowserLibraryPromise;
  } catch (error) {
    docxBrowserLibraryPromise = null;
    throw error;
  }
}

async function ensureHtmlDocxBrowserLibrary() {
  const cachedApi = resolveHtmlDocxBrowserApi();
  if (cachedApi) return cachedApi;
  if (htmlDocxBrowserLibraryPromise) return htmlDocxBrowserLibraryPromise;
  htmlDocxBrowserLibraryPromise = (async () => {
    for (const url of HTML_DOCX_SOURCE_URLS) {
      try {
        appendWeeklyDocxBuildLine(`await importHtmlDocx("${url}");`);
        await loadExternalScript(url);
        const api = resolveHtmlDocxBrowserApi();
        if (api) return api;
      } catch (_) {
        // try next source
      }
    }
    throw new Error('브라우저 HTML→DOCX 라이브러리 로드 실패');
  })();
  try {
    return await htmlDocxBrowserLibraryPromise;
  } catch (error) {
    htmlDocxBrowserLibraryPromise = null;
    throw error;
  }
}

function buildWeeklyBulletHtml(items = [], fallback = '확인 필요') {
  const list = Array.isArray(items) && items.length ? items : [fallback];
  return `<ul>${list.map((item) => `<li>- ${escapeHtml(String(item || '').trim())}</li>`).join('')}</ul>`;
}

function buildWeeklyReportHtmlTemplate(parsed, titleText = 'weekly-report') {
  const title = escapeHtml(String(titleText || 'weekly-report'));
  const onePage = collectWeeklyOnePageRows(parsed);
  const actualHeader = onePage.actual_range ? `실적(${escapeHtml(onePage.actual_range)})` : '실적';
  const planHeader = onePage.plan_range ? `계획(${escapeHtml(onePage.plan_range)})` : '계획';
  const rowsHtml =
    '<tr>' +
    '<td>주요 진행사항</td>' +
    `<td>${buildWeeklyBulletHtml(onePage.main_actual, '확인 필요')}</td>` +
    `<td>${buildWeeklyBulletHtml(onePage.main_plan, '담당/기한 확인 필요')}</td>` +
    '</tr>' +
    '<tr>' +
    '<td>이슈</td>' +
    `<td>${buildWeeklyBulletHtml(onePage.issue_actual, '핵심 이슈 확인 필요')}</td>` +
    `<td>${buildWeeklyBulletHtml(onePage.issue_plan, '조치 계획 확인 필요')}</td>` +
    '</tr>';
  return (
    '<!DOCTYPE html><html><head><meta charset="utf-8" />' +
    '<style>' +
    'body{font-family:"Malgun Gothic","Apple SD Gothic Neo",sans-serif;color:#111;line-height:1.45;font-size:12pt;padding:24px;}' +
    'h1{font-size:24pt;margin:0 0 8px;} h2{font-size:14pt;margin:18px 0 8px;color:#1f3d63;}' +
    'ul{margin:0;padding-left:16px;} li{margin:0 0 4px;}' +
    'table{width:100%;border-collapse:collapse;table-layout:fixed;}' +
    'th,td{border:1px solid #cfd8e3;vertical-align:top;padding:8px;text-align:left;}' +
    'th{background:#eef4fb;}' +
    '</style></head><body>' +
    `<h1>${title}</h1>` +
    '<h2>주간 요약 (1 Page)</h2>' +
    `<table><thead><tr><th style="width:18%;">구분</th><th style="width:41%;">${actualHeader}</th><th style="width:41%;">${planHeader}</th></tr></thead>` +
    `<tbody>${rowsHtml}</tbody></table>` +
    '</body></html>'
  );
}

function buildWeeklyReportDocxDocument(docxApi, parsed, titleText) {
  const {
    Document,
    Packer,
    Paragraph,
    TextRun,
    HeadingLevel,
    AlignmentType,
    Table,
    TableRow,
    TableCell,
    WidthType,
  } = docxApi;
  if (!Document || !Packer || !Paragraph || !Table || !TableRow || !TableCell || !TextRun) {
    throw new Error('docx API가 충분하지 않습니다.');
  }
  const buildBulletRows = (items, fallback) => {
    const target = Array.isArray(items) && items.length ? items : [fallback];
    return target.slice(0, 6).map((item) => new Paragraph({
      text: `- ${String(item || '').trim()}`,
      spacing: { after: 120 },
    }));
  };
  const onePage = collectWeeklyOnePageRows(parsed);
  const actualHeader = onePage.actual_range ? `실적(${String(onePage.actual_range)})` : '실적';
  const planHeader = onePage.plan_range ? `계획(${String(onePage.plan_range)})` : '계획';
  const rowMain = new TableRow({
    children: [
      new TableCell({ children: [new Paragraph('주요 진행사항')] }),
      new TableCell({ children: buildBulletRows(onePage.main_actual, '확인 필요') }),
      new TableCell({ children: buildBulletRows(onePage.main_plan, '담당/기한 확인 필요') }),
    ],
  });
  const rowIssue = new TableRow({
    children: [
      new TableCell({ children: [new Paragraph('이슈')] }),
      new TableCell({ children: buildBulletRows(onePage.issue_actual, '핵심 이슈 확인 필요') }),
      new TableCell({ children: buildBulletRows(onePage.issue_plan, '조치 계획 확인 필요') }),
    ],
  });
  return new Document({
    sections: [
      {
        properties: {},
        children: [
          new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ text: String(titleText || 'weekly-report'), bold: true, size: 34 })],
            spacing: { after: 260 },
          }),
          new Paragraph({
            heading: HeadingLevel.HEADING_2,
            text: '주간 요약 (1 Page)',
            spacing: { before: 220, after: 120 },
          }),
          new Table({
            width: { size: 100, type: WidthType.PERCENTAGE },
            rows: [
              new TableRow({
                children: [
                  new TableCell({ children: [new Paragraph({ text: '구분', bold: true })] }),
                  new TableCell({ children: [new Paragraph({ text: actualHeader, bold: true })] }),
                  new TableCell({ children: [new Paragraph({ text: planHeader, bold: true })] }),
                ],
              }),
              rowMain,
              rowIssue,
            ],
          }),
        ],
      },
    ],
  });
}

let weeklyReportToastState = {
  el: null,
  phraseEl: null,
  statusEl: null,
  scriptEl: null,
  phraseIdx: 0,
  scriptSeq: 0,
};

const WEEKLY_REPORT_TOAST_PHRASES = [
  '메일 흐름을 스캔하고 있습니다',
  '핵심 이슈를 정리하고 있습니다',
  '실적/차주 계획을 구조화하고 있습니다',
  '보고서 미리보기를 준비하고 있습니다',
];

const WEEKLY_REPORT_SCRIPT_LINES = [
  "const weekly = collectMailSignals(range7d);",
  "const issues = extractTopIssues(weekly);",
  "const actions = mapActions(issues);",
  "const rows = buildPlanRows(actions);",
  "docx.addHeading('주간보고');",
  "docx.addTable(rows, ['실적', '계획']);",
  "docx.addSection('리스크/요청사항');",
  "exportFile('weekly-report.docx');",
];

function ensureWeeklyReportBuildToast() {
  if (weeklyReportToastState.el && weeklyReportToastState.el.isConnected) {
    return weeklyReportToastState.el;
  }
  const existing = document.getElementById('weeklyReportBuildToast');
  if (existing) {
    weeklyReportToastState.el = existing;
    weeklyReportToastState.phraseEl = existing.querySelector('.weekly-build-toast-phrase');
    weeklyReportToastState.statusEl = existing.querySelector('.weekly-build-toast-status');
    weeklyReportToastState.scriptEl = existing.querySelector('.weekly-build-toast-script-lines');
    return existing;
  }
  const html = `
    <div class="weekly-build-toast hidden" id="weeklyReportBuildToast" aria-live="polite">
      <div class="weekly-build-toast-icon">${ICONS.sparkles}</div>
      <div class="weekly-build-toast-body">
        <div class="weekly-build-toast-title">주간보고 생성 중</div>
        <div class="weekly-build-toast-phrase">메일 흐름을 스캔하고 있습니다</div>
        <div class="weekly-build-toast-status">초기화</div>
        <pre class="weekly-build-toast-script"><code class="weekly-build-toast-script-lines"></code></pre>
      </div>
    </div>
  `;
  document.body.insertAdjacentHTML('beforeend', html);
  const el = document.getElementById('weeklyReportBuildToast');
  weeklyReportToastState.el = el;
  weeklyReportToastState.phraseEl = el?.querySelector('.weekly-build-toast-phrase') || null;
  weeklyReportToastState.statusEl = el?.querySelector('.weekly-build-toast-status') || null;
  weeklyReportToastState.scriptEl = el?.querySelector('.weekly-build-toast-script-lines') || null;
  return el;
}

function startWeeklyReportBuildToast() {
  const el = ensureWeeklyReportBuildToast();
  if (!el) return;
  el.classList.remove('hidden', 'is-done', 'is-error');
  weeklyReportToastState.phraseIdx = 0;
  weeklyReportToastState.scriptSeq = 0;
  if (weeklyReportToastState.phraseEl) {
    weeklyReportToastState.phraseEl.textContent = WEEKLY_REPORT_TOAST_PHRASES[0];
  }
  if (weeklyReportToastState.statusEl) {
    weeklyReportToastState.statusEl.textContent = '분석 시작';
  }
  if (weeklyReportToastState.scriptEl) {
    weeklyReportToastState.scriptEl.textContent = '';
  }
  const firstLine = WEEKLY_REPORT_SCRIPT_LINES[0];
  if (firstLine && weeklyReportToastState.scriptEl) {
    weeklyReportToastState.scriptEl.textContent = `01. ${firstLine}`;
    weeklyReportToastState.scriptSeq = 1;
  }
}

function normalizeWeeklyEventToolName(eventData = {}) {
  const toolValue =
    eventData?.tool
    || eventData?.tool_name
    || eventData?.name
    || eventData?.toolName
    || '';
  const resolved =
    resolveDeepProgressEntityName(toolValue, 80)
    || normalizeDeepProgressTaskName(toolValue, 80);
  return String(resolved || '').trim();
}

function normalizeWeeklyEventArgsSnippet(eventData = {}) {
  const args = eventData?.args;
  if (!args) return '';
  if (typeof args === 'string') {
    const compact = args.replace(/\s+/g, ' ').trim();
    return compact.length > 90 ? `${compact.slice(0, 90)}...` : compact;
  }
  if (typeof args === 'object') {
    try {
      const serialized = JSON.stringify(args);
      if (!serialized) return '';
      return serialized.length > 120 ? `${serialized.slice(0, 120)}...` : serialized;
    } catch (_) {
      return '';
    }
  }
  return '';
}

function buildWeeklyRawEventLine(eventData = {}) {
  const payload = eventData && typeof eventData === 'object' ? eventData : {};
  const keys = [
    'type',
    'phase',
    'status',
    'tool_name',
    'name',
    'subagent_name',
    'message',
    'detail',
  ];
  const compact = {};
  for (const key of keys) {
    const value = payload[key];
    if (value === null || value === undefined) continue;
    const normalized = String(value).trim();
    if (!normalized) continue;
    compact[key] = normalized.length > 80 ? `${normalized.slice(0, 80)}...` : normalized;
  }
  const tool = normalizeWeeklyEventToolName(payload);
  if (tool) compact.tool = tool;
  const args = normalizeWeeklyEventArgsSnippet(payload);
  if (args) compact.args = args;
  let serialized = '';
  try {
    serialized = JSON.stringify(compact);
  } catch (_) {
    serialized = '';
  }
  if (!serialized || serialized === '{}') return '';
  return `event ${serialized}`;
}

function updateWeeklyReportBuildToast(eventData = {}) {
  const el = ensureWeeklyReportBuildToast();
  if (!el || el.classList.contains('hidden')) return;
  const type = String(eventData?.type || '').trim().toLowerCase();
  const status = String(eventData?.status || '').trim().toLowerCase();
  const phase = normalizeDeepProgressTaskName(eventData?.phase || '', 40).toLowerCase();
  const toolName = normalizeWeeklyEventToolName(eventData);
  const argsSnippet = normalizeWeeklyEventArgsSnippet(eventData);
  let label = '생성 중';
  if (type === 'tool_start') label = `도구 실행: ${toolName || 'unknown'}`;
  else if (type === 'tool_end') label = `도구 완료: ${toolName || 'unknown'}`;
  else if (type === 'progress' && status === 'done') label = '단계 완료';
  else if (type === 'progress' && phase) label = `단계 진행: ${phase}`;
  else if (type === 'partial_answer') label = '보고서 정리';
  else if (type === 'complete') label = '완료';
  else if (type === 'error' || type === 'tool_error') label = '오류';
  if (weeklyReportToastState.statusEl) {
    weeklyReportToastState.statusEl.textContent = label;
  }
  let scriptLine = '';
  if (type === 'start') scriptLine = 'const events = streamRuntimeEvents();';
  else if (type === 'worker_start') scriptLine = 'const worker = await connectWorkerAgent();';
  else if (type === 'tool_start') {
    scriptLine = argsSnippet
      ? `const ${toolName || 'tool'}Result = await ${toolName || 'tool'}(${argsSnippet});`
      : `const ${toolName || 'tool'}Result = await ${toolName || 'tool'}(...);`;
  } else if (type === 'tool_end') {
    scriptLine = `mergeToolResult("${toolName || 'tool'}");`;
  } else if (type === 'progress') {
    scriptLine = phase
      ? `await advancePhase("${phase}", "${status || 'running'}");`
      : `await advancePhase("unknown", "${status || 'running'}");`;
  } else if (type === 'partial_answer') {
    scriptLine = 'const weeklyReport = compileWeeklyMarkdown();';
  } else if (type === 'complete') {
    scriptLine = 'return weeklyReportCard;';
  } else if (type === 'tool_error') {
    scriptLine = `throw new Error("tool_error:${toolName || 'unknown'}");`;
  } else if (type === 'error') {
    scriptLine = 'throw new Error("weekly_report_failed");';
  }
  const rawEventLine = buildWeeklyRawEventLine(eventData);
  if (scriptLine && weeklyReportToastState.scriptEl) {
    weeklyReportToastState.scriptSeq += 1;
    const seq = String(weeklyReportToastState.scriptSeq).padStart(2, '0');
    const current = String(weeklyReportToastState.scriptEl.textContent || '').trim();
    const merged = current ? `${current}\n${seq}. ${scriptLine}` : `${seq}. ${scriptLine}`;
    weeklyReportToastState.scriptEl.textContent = merged.split('\n').slice(-8).join('\n');
  }
  if (rawEventLine && weeklyReportToastState.scriptEl) {
    weeklyReportToastState.scriptSeq += 1;
    const seq = String(weeklyReportToastState.scriptSeq).padStart(2, '0');
    const current = String(weeklyReportToastState.scriptEl.textContent || '').trim();
    const merged = current ? `${current}\n${seq}. // ${rawEventLine}` : `${seq}. // ${rawEventLine}`;
    weeklyReportToastState.scriptEl.textContent = merged.split('\n').slice(-10).join('\n');
  }
}

function finishWeeklyReportBuildToast(finalState = 'done') {
  const el = ensureWeeklyReportBuildToast();
  if (!el) return;
  const state = String(finalState || 'done').trim().toLowerCase();
  el.classList.remove('is-done', 'is-error');
  if (state === 'error') {
    el.classList.add('is-error');
    if (weeklyReportToastState.statusEl) weeklyReportToastState.statusEl.textContent = '생성 실패';
  } else {
    el.classList.add('is-done');
    if (weeklyReportToastState.statusEl) weeklyReportToastState.statusEl.textContent = '생성 완료';
  }
  window.setTimeout(() => {
    el.classList.add('hidden');
  }, state === 'error' ? 1800 : 1200);
}

function coerceStatusLineValue(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => coerceStatusLineValue(item))
      .filter(Boolean)
      .join(' ');
  }
  if (typeof value === 'object') {
    const candidateKeys = [
      'label',
      'name',
      'tool_name',
      'subagent',
      'phase',
      'status',
      'message',
      'detail',
      'text',
      'value',
    ];
    for (const key of candidateKeys) {
      const candidate = value?.[key];
      if (typeof candidate === 'string' || typeof candidate === 'number' || typeof candidate === 'boolean') {
        const normalized = String(candidate).trim();
        if (normalized) return normalized;
      }
    }
    return '';
  }
  return '';
}

function trimStatusLineText(value, maxLen = 140) {
  const raw = coerceStatusLineValue(value).replace(/\s+/g, ' ').trim();
  if (!raw) return '';
  if (raw.length <= maxLen) return raw;
  return `${raw.slice(0, Math.max(20, maxLen - 3))}...`;
}

function resolveStatusHeadlineByEvent(eventType = '', eventData = {}) {
  const type = String(eventType || eventData?.type || '').trim().toLowerCase();
  if (!type) return STATUS_LINE_HEADLINE.analyzing;
  if (type === 'confirm_required') return STATUS_LINE_HEADLINE.waiting;
  if (type === 'complete') return STATUS_LINE_HEADLINE.done;
  if (type === 'error' || type === 'tool_error') return STATUS_LINE_HEADLINE.error;
  return STATUS_LINE_HEADLINE.finalizing;
}

function resolveStatusLogByEvent(eventType = '', eventData = {}) {
  const type = String(eventType || '').trim().toLowerCase();
  if (type === 'partial_answer') return '';
  if (type === 'start') return '워크플로우를 시작했습니다.';
  if (type === 'worker_start') return '도구 실행을 준비 중입니다.';
  if (type === 'progress') {
    const phaseName = normalizeDeepProgressTaskName(eventData?.phase || '', 40).toLowerCase();
    if (!phaseName) return '';
    if (String(eventData?.status || '').trim().toLowerCase() === 'done') return `단계 완료: ${phaseName}`;
    return `단계 진행: ${phaseName}`;
  }

  const toolName =
    resolveDeepProgressEntityName(eventData?.tool) ||
    normalizeDeepProgressTaskName(eventData?.tool_name || eventData?.name || '', 64);
  if (toolName) {
    if (type === 'tool_start') return `도구 실행: ${toolName}`;
    if (type === 'tool_end') return `도구 완료: ${toolName}`;
    if (type === 'tool_error') return `도구 실패: ${toolName}`;
  }

  const subagentName =
    resolveDeepProgressEntityName(eventData?.subagent) ||
    normalizeDeepProgressTaskName(eventData?.subagent_name || '', 64);
  if (subagentName) {
    if (type === 'subagent_start') return `서브에이전트 실행: ${subagentName}`;
    if (type === 'subagent_end') return `서브에이전트 완료: ${subagentName}`;
  }

  if (type === 'complete') return '응답 작성을 완료했습니다.';
  if (type === 'confirm_required') return '사용자 확인이 필요합니다.';
  if (type === 'error') return '실행 중 오류가 발생했습니다.';

  const backendDetail = trimStatusLineText(eventData?.detail || '', 120);
  if (backendDetail) return backendDetail;
  const backendMessage = trimStatusLineText(eventData?.message || '', 120);
  if (backendMessage) return backendMessage;
  return '';
}

function normalizeDeepProgressTaskName(value, maxLen = 64) {
  return trimStatusLineText(value || '', maxLen);
}

function resolveDeepProgressEntityName(value, maxLen = 64) {
  if (!value) return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return normalizeDeepProgressTaskName(value, maxLen);
  }
  if (typeof value === 'object') {
    const candidateKeys = ['tool_name', 'name', 'label', 'id', 'type'];
    for (const key of candidateKeys) {
      const candidate = value?.[key];
      if (typeof candidate === 'string' || typeof candidate === 'number' || typeof candidate === 'boolean') {
        const normalized = normalizeDeepProgressTaskName(candidate, maxLen);
        if (normalized) return normalized;
      }
    }
  }
  return '';
}

function appendStatusLog(tracker, line = '', options = {}) {
  if (!tracker || !line) return;
  const safeLine = trimStatusLineText(line, 140);
  if (!safeLine) return;
  const status = String(options?.status || 'neutral').trim().toLowerCase() || 'neutral';
  const taskKey = String(options?.taskKey || '').trim().toLowerCase();

  if (taskKey) {
    const targetIndex = tracker.logs.findIndex((entry) => entry && entry.taskKey === taskKey);
    if (targetIndex >= 0) {
      const current = tracker.logs[targetIndex] || {};
      if (current.text === safeLine && current.status === status) return;
      tracker.logSeq += 1;
      tracker.logs[targetIndex] = {
        ...current,
        key: `status_log_${tracker.logSeq}`,
        text: safeLine,
        status,
        taskKey,
      };
    } else {
      tracker.logSeq += 1;
      tracker.logs.push({
        key: `status_log_${tracker.logSeq}`,
        text: safeLine,
        status,
        taskKey,
      });
    }
  } else {
    const last = tracker.logs[tracker.logs.length - 1];
    if (last && last.text === safeLine && String(last.status || 'neutral') === status) return;
    tracker.logSeq += 1;
    tracker.logs.push({ key: `status_log_${tracker.logSeq}`, text: safeLine, status, taskKey: '' });
  }

  if (tracker.logs.length > STATUS_LINE_MAX_LOG_ITEMS) {
    tracker.logs.splice(0, tracker.logs.length - STATUS_LINE_MAX_LOG_ITEMS);
  }
}

function removeStatusLogByTaskKey(tracker, taskKey = '') {
  if (!tracker || !Array.isArray(tracker.logs)) return;
  const normalizedTaskKey = String(taskKey || '').trim().toLowerCase();
  if (!normalizedTaskKey) return;
  const filtered = tracker.logs.filter(
    (entry) => String(entry?.taskKey || '').trim().toLowerCase() !== normalizedTaskKey
  );
  if (filtered.length === tracker.logs.length) return;
  tracker.logs = filtered;
}

function resolveStatusHeadlineByState(finalState = '') {
  const state = String(finalState || '').trim().toLowerCase();
  if (state === 'done') return STATUS_LINE_HEADLINE.done;
  if (state === 'confirm') return STATUS_LINE_HEADLINE.waiting;
  if (state === 'error') return STATUS_LINE_HEADLINE.error;
  return STATUS_LINE_HEADLINE.finalizing;
}

function renderDeepProgressCard(tracker, options = {}) {
  if (!tracker?.id) return;
  const headEl = document.getElementById(`${tracker.id}_head`);
  const progressEl = document.getElementById(`${tracker.id}_progress`);
  const statusEl = document.getElementById(`${tracker.id}_status`);
  const logEl = document.getElementById(`${tracker.id}_log`);
  if (!statusEl || !logEl) return;

  const force = Boolean(options.force);
  let shouldScroll = false;
  const nextHeadline = trimStatusLineText(
    options.statusText || tracker.statusText || STATUS_LINE_HEADLINE.analyzing,
    120
  );
  if (force || tracker.lastRenderedHeadline !== nextHeadline) {
    statusEl.textContent = nextHeadline;
    tracker.lastRenderedHeadline = nextHeadline;
    shouldScroll = true;
  }
  if (headEl) {
    const finalState = String(tracker.finalState || '').trim().toLowerCase();
    const isFinal = finalState === 'done' || finalState === 'confirm' || finalState === 'error';
    headEl.classList.toggle('is-running', !isFinal);
    headEl.classList.toggle('is-final', isFinal);
    if (progressEl) {
      progressEl.classList.toggle('is-running', !isFinal);
      progressEl.classList.toggle('is-final', isFinal);
    }
  }
  if (tracker.compactMode) {
    logEl.style.display = 'none';
    if (shouldScroll) scrollToBottom();
    return;
  }

  const nextLogDigest = tracker.logs
    .map((entry) => `${entry.key}:${entry.status || 'neutral'}:${entry.text || ''}`)
    .join('|');
  if (!force && tracker.lastRenderedLogDigest === nextLogDigest) {
    if (shouldScroll) scrollToBottom();
    return;
  }
  logEl.innerHTML = tracker.logs
    .map((entry) => {
      const stateClass = `is-${escapeAttr(String(entry?.status || 'neutral').toLowerCase())}`;
      return `<li class="status-line-log-item ${stateClass}">${escapeHtml(entry.text || '')}</li>`;
    })
    .join('');
  tracker.lastRenderedLogDigest = nextLogDigest;
  scrollToBottom();
}

function scheduleDeepProgressRender(tracker, delayMs = STATUS_LINE_RENDER_THROTTLE_MS) {
  if (!tracker?.id) return;
  if (Number.isFinite(tracker.renderTimerId)) return;
  const waitMs = Math.max(0, Number(delayMs) || 0);
  tracker.renderTimerId = window.setTimeout(() => {
    tracker.renderTimerId = null;
    renderDeepProgressCard(tracker);
  }, waitMs);
}

function applyDeepProgressEvent(tracker, eventData) {
  if (!tracker || !eventData || typeof eventData !== 'object') return;
  const eventType = String(eventData.type || '').trim().toLowerCase();
  if (!eventType) return;
  if (tracker.compactMode) {
    const resolveToolName = () => String(
      eventData?.tool?.name
      || eventData?.tool_name
      || eventData?.name
      || ''
    ).trim().toLowerCase();
    if (eventType === 'complete') {
      tracker.statusText = '주간보고 생성 완료';
      tracker.finalState = 'done';
      return;
    }
    if (eventType === 'confirm_required') {
      tracker.statusText = '사용자 확인이 필요합니다.';
      tracker.finalState = 'confirm';
      return;
    }
    if (eventType === 'error' || eventType === 'tool_error') {
      tracker.statusText = '주간보고 생성 실패';
      tracker.finalState = 'error';
      return;
    }
    if (eventType === 'progress') {
      const phase = normalizeDeepProgressTaskName(eventData?.phase || '', 30);
      tracker.statusText = phase ? `주간보고 단계: ${phase}` : '주간보고 단계: 처리 중';
      return;
    }
    if (eventType === 'tool_start') {
      const toolName = resolveToolName();
      if (toolName === 'search_emails') {
        tracker.statusText = '주간보고 단계: 메일 검색 중';
        return;
      }
      tracker.statusText = '주간보고 단계: 근거 수집 중';
      return;
    }
    if (eventType === 'tool_end') {
      const toolName = resolveToolName();
      if (toolName === 'search_emails') {
        tracker.statusText = '주간보고 단계: 근거 정리 중';
        return;
      }
      tracker.statusText = '주간보고 단계: 검토 중';
      return;
    }
    if (eventType === 'partial_answer') {
      tracker.statusText = '주간보고 단계: 보고서 작성 중';
      return;
    }
    tracker.statusText = '주간보고 생성 중...';
    return;
  }

  if (eventType === 'fallback_notice') {
    const fallbackStatus = String(eventData.status || '').trim().toLowerCase();
    const fallbackMessage = trimStatusLineText(eventData.message || eventData.detail || '', 140);
    if (
      !fallbackMessage
      || fallbackStatus === 'clear'
      || fallbackStatus === 'done'
      || fallbackStatus === 'resolved'
      || fallbackStatus === 'hidden'
    ) {
      removeStatusLogByTaskKey(tracker, STATUS_LINE_FALLBACK_NOTICE_TASK_KEY);
      return;
    }
    appendStatusLog(tracker, fallbackMessage, {
      status: 'running',
      taskKey: STATUS_LINE_FALLBACK_NOTICE_TASK_KEY,
    });
    return;
  }

  // partial_answer는 상태카드 헤드라인을 덮지 않고, 직전 실행 상태를 유지한다.
  if (eventType !== 'partial_answer') {
    tracker.statusText = resolveStatusHeadlineByEvent(eventType, eventData);
  }
  const backendLogLine = resolveStatusLogByEvent(eventType, eventData);
  if (backendLogLine) {
    appendStatusLog(tracker, backendLogLine);
  }

  if (eventType === 'confirm_required') {
    tracker.finalState = 'confirm';
  } else if (eventType === 'complete') {
    tracker.finalState = 'done';
  } else if (eventType === 'progress') {
    const phase = String(eventData.phase || '').trim().toLowerCase();
    const status = String(eventData.status || '').trim().toLowerCase();
    if (status === 'error') {
      tracker.finalState = 'error';
    } else if (phase === 'finalize' && status === 'done') {
      tracker.finalState = 'done';
    }
  } else if (eventType === 'error' || eventType === 'tool_error') {
    tracker.finalState = 'error';
  }
}

function startDeepProgressCard(source = 'chat') {
  const chatArea = document.getElementById('chatArea');
  if (!chatArea) return null;
  removeWelcomeStateIfExists();

  const id = `deep_progress_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
  const compactMode = String(source || '').trim().toLowerCase() === 'weekly_report';
  const initialStatus = compactMode ? '주간보고 생성 중...' : STATUS_LINE_HEADLINE.analyzing;
  const html = `
    <div class="message assistant assistant-status-message" id="${id}">
      <div class="msg-body status-line-body">
        <div class="status-line-head is-running" id="${id}_head">
          <span class="status-line-blink" aria-hidden="true"></span>
          <span class="status-line-text" id="${id}_status">${escapeHtml(initialStatus)}</span>
        </div>
        <div class="status-line-progress is-running" id="${id}_progress" aria-hidden="true">
          <span class="status-line-progress-fill"></span>
        </div>
        <ul class="status-line-log" id="${id}_log"></ul>
      </div>
    </div>
  `;
  chatArea.insertAdjacentHTML('beforeend', html);

  const tracker = {
    id,
    source,
    compactMode,
    startedAt: Date.now(),
    finalState: null,
    statusText: initialStatus,
    logs: [],
    logSeq: 0,
    renderTimerId: null,
    removeTimerId: null,
    lastRenderedHeadline: '',
    lastRenderedLogDigest: '',
  };
  deepProgressTrackerRegistry.set(id, tracker);
  renderDeepProgressCard(tracker, { force: true });
  logEvent('deep_progress.start', 'ok', { source, style: 'minimal_status_line' });
  scrollToBottom();
  return tracker;
}

function cleanupFinishedDeepProgressTracker(tracker, keepMs) {
  if (!tracker?.id) return;
  if (Number.isFinite(tracker.removeTimerId)) {
    window.clearTimeout(tracker.removeTimerId);
    tracker.removeTimerId = null;
  }
  if (!Number.isFinite(keepMs) || Number(keepMs) < 0) return;
  if (Number(keepMs) === 0) {
    const el = document.getElementById(tracker.id);
    if (el) el.remove();
    deepProgressTrackerRegistry.delete(tracker.id);
    return;
  }
  tracker.removeTimerId = window.setTimeout(() => {
    const el = document.getElementById(tracker.id);
    if (el) el.remove();
    deepProgressTrackerRegistry.delete(tracker.id);
    tracker.removeTimerId = null;
  }, Number(keepMs));
}

function finishDeepProgressCard(tracker, options = {}) {
  if (!tracker) return;
  const { finalState = 'done', note = '', keepMs = null } = options;
  tracker.finalState = String(finalState || 'done').trim().toLowerCase();
  if (Number.isFinite(tracker.renderTimerId)) {
    window.clearTimeout(tracker.renderTimerId);
    tracker.renderTimerId = null;
  }

  const finalHeadline = resolveStatusHeadlineByState(tracker.finalState);
  tracker.statusText = finalHeadline;
  if (note) appendStatusLog(tracker, note);
  renderDeepProgressCard(tracker, { force: true, statusText: finalHeadline });

  const elapsedMs = Math.max(0, Date.now() - tracker.startedAt);
  if (
    tracker.source === 'assistant_workflow'
    && (tracker.finalState === 'done' || tracker.finalState === 'error')
  ) {
    lastCompletedTurnElapsedMs = elapsedMs;
  }

  logEvent('deep_progress.finish', 'ok', {
    source: tracker.source,
    final_state: tracker.finalState,
    elapsed_ms: elapsedMs,
  });

  let resolvedKeepMs = keepMs;
  if (!Number.isFinite(resolvedKeepMs)) {
    resolvedKeepMs =
      tracker.finalState === 'confirm'
        ? NaN
        : STATUS_LINE_AUTO_DISMISS_MS;
  }
  cleanupFinishedDeepProgressTracker(tracker, resolvedKeepMs);
}

function scrollToBottom() {
  const chatArea = document.getElementById('chatArea');
  requestAnimationFrame(() => {
    chatArea.scrollTop = chatArea.scrollHeight;
  });
}

// markdown/escape helpers are extracted to `taskpane.markdown-utils.js`.

const UI_OUTPUT_SUPPORTED_TYPES = new Set([
  'free_chat',
  'mail_list',
  'mail_summary',
  'mail_analysis',
  'mail_report',
  'mail_actions',
]);
const UI_OUTPUT_V2_SUPPORTED_TYPES = new Set(['assistant_message', 'weekly_report']);

function normalizeUiOutputPayload(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const type = String(payload.type || '').trim().toLowerCase();
  if (!UI_OUTPUT_SUPPORTED_TYPES.has(type)) return null;

  const formatRaw = String(payload.format || '').trim().toLowerCase();
  const format = formatRaw === 'plain' ? 'plain' : 'markdown';
  const title = String(payload.title || '').trim();
  const body = String(payload.body || payload.text || payload.markdown || '').trim();
  if (!body) return null;

  return {
    version: String(payload.version || 'v1').trim() || 'v1',
    type,
    format,
    title,
    body,
  };
}

function normalizeUiOutputV2Payload(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const type = String(payload.type || '').trim().toLowerCase();
  if (!UI_OUTPUT_V2_SUPPORTED_TYPES.has(type)) return null;

  const body = payload.body && typeof payload.body === 'object' ? payload.body : {};
  const formatRaw = String(body.format || payload.format || '').trim().toLowerCase();
  const format = formatRaw === 'plain' ? 'plain' : 'markdown';
  const text = String(body.text || payload.text || '').trim();
  const structuredPayload =
    body.payload && typeof body.payload === 'object'
      ? body.payload
      : payload.payload && typeof payload.payload === 'object'
        ? payload.payload
        : null;
  if (!text && !structuredPayload) return null;

  const openableItems = sanitizeOpenableMailItems(
    payload.openable_items || payload.openableItems || []
  );
  const weeklyReport = payload.weekly_report && typeof payload.weekly_report === 'object'
    ? payload.weekly_report
    : {};
  const weeklyData = normalizeWeeklyReportStructuredData(weeklyReport.data);
  const weeklyRanges = normalizeWeeklyReportRanges(weeklyReport.ranges);
  const downloadFormatsRaw = Array.isArray(weeklyReport.download_formats)
    ? weeklyReport.download_formats
    : [];
  const downloadFormats = [];
  for (const item of downloadFormatsRaw) {
    const value = String(item || '').trim().toLowerCase();
    if (!value) continue;
    if ((value === 'md' || value === 'markdown') && !downloadFormats.includes('md')) {
      downloadFormats.push('md');
      continue;
    }
    if ((value === 'docx' || value === 'word') && !downloadFormats.includes('docx')) {
      downloadFormats.push('docx');
    }
  }

  return {
    version: String(payload.version || 'v2').trim() || 'v2',
    type,
    body: {
      format,
      text,
      payload: structuredPayload,
    },
    openable_items: openableItems,
    feedback: payload.feedback !== false,
    allow_reply_compose: Boolean(payload.allow_reply_compose),
    allow_restart: Boolean(payload.allow_restart),
    weekly_report: type === 'weekly_report'
      ? {
          download_formats: downloadFormats.length ? downloadFormats : ['md', 'docx'],
          report_file_name: String(weeklyReport.report_file_name || 'weekly-report').trim() || 'weekly-report',
          data: weeklyData,
          ranges: weeklyRanges,
        }
      : null,
  };
}

function buildMailListPayloadHtml(payload) {
  if (!payload || typeof payload !== 'object') return '';
  const items = Array.isArray(payload.items) ? payload.items : [];
  if (!items.length) return '<p>검색 결과가 없습니다.</p>';

  const rows = [];
  for (let i = 0; i < items.length; i += 1) {
    const item = items[i] && typeof items[i] === 'object' ? items[i] : {};
    const date = String(item.date || '-').trim() || '-';
    const subject = String(item.subject || '제목 없음').trim() || '제목 없음';
    const from = String(item.from || '-').trim() || '-';
    const summary = String(item.summary || '').trim();
    rows.push(
      `<p>${i + 1}) ${escapeHtml(date)}<br/>- 제목: ${escapeHtml(subject)}<br/>- 발신자: ${escapeHtml(from)}${summary ? `<br/>- 요약: ${escapeHtml(summary)}` : ''}</p>`
    );
  }
  return rows.join('');
}

function buildMailSummaryPayloadHtml(payload) {
  if (!payload || typeof payload !== 'object') return '';
  const lines = Array.isArray(payload.lines) ? payload.lines : [];
  const listItems = lines
    .map((line) => String(line || '').trim())
    .filter((line) => line)
    .map((line) => `<li>${escapeHtml(line)}</li>`)
    .join('');
  if (!listItems) return '';
  return `<ul>${listItems}</ul>`;
}

function normalizeAssistantTextForParsing(content) {
  const raw = String(content || '');
  if (!raw) return '';
  if (raw.includes('<')) {
    // Avoid assigning untrusted text to innerHTML here.
    // Some mail/code snippets contain literal HTML tags (e.g. <img src="...">),
    // which can trigger unintended network requests even in detached nodes.
    return raw
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<\/(p|div|li|tr|h[1-6])\s*>/gi, '\n')
      .replace(/<li\b[^>]*>/gi, '- ')
      .replace(/<[^>]+>/g, '')
      .replace(/&nbsp;/gi, ' ')
      .replace(/&amp;/gi, '&')
      .replace(/&lt;/gi, '<')
      .replace(/&gt;/gi, '>')
      .replace(/&quot;/gi, '"')
      .replace(/&#39;/gi, "'")
      .replace(/\u00a0/g, ' ')
      .replace(/\r/g, '');
  }
  return raw;
}

function extractPromiseDirectLines(normalized) {
  const directSectionStart = normalized.indexOf('질문 직접 답변');
  const directMarkers = ['월별 증가세', '비용 상위 월 Top 3', '증감 근거']
    .map((marker) => normalized.indexOf(marker))
    .filter((idx) => idx > directSectionStart);
  const directSectionEnd = directMarkers.length > 0 ? Math.min(...directMarkers) : -1;
  const directScope =
    directSectionStart >= 0
      ? normalized.slice(
          directSectionStart,
          directSectionEnd > directSectionStart ? directSectionEnd : undefined
        )
      : '';
  return directScope
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.startsWith('- ') || line.startsWith('·'))
    .map((line) => line.replace(/^- /, '').trim());
}

function extractPromiseTop3(normalized) {
  const top3SectionStart = normalized.indexOf('비용 상위 월 Top 3');
  const reasonSectionStart = normalized.indexOf('증감 근거');
  const top3Scope =
    top3SectionStart >= 0
      ? normalized.slice(
          top3SectionStart,
          reasonSectionStart > top3SectionStart ? reasonSectionStart : undefined
        )
      : '';
  const top3Matches = [
    ...top3Scope.matchAll(
      /-\s*([0-9]{1,2})월:\s*총\s*([0-9,]+원)\s*\(인건비\s*([0-9,]+원),\s*외주비\s*([0-9,]+원)\)/g
    ),
  ];
  return top3Matches.map((m) => ({
    month: m[1],
    total: m[2],
    labor: m[3],
    outsourcing: m[4],
  }));
}

function extractPromiseReasonLines(normalized) {
  const reasonSectionStart = normalized.indexOf('증감 근거');
  const reasonLines = [];
  if (reasonSectionStart >= 0) {
    const reasonScope = normalized.slice(reasonSectionStart);
    const lines = reasonScope.split('\n').map((line) => line.trim()).filter(Boolean);
    for (const line of lines) {
      if (line.startsWith('- ')) {
        reasonLines.push(line.slice(2).trim());
      }
    }
    return reasonLines;
  }

  const lines = normalized.split('\n').map((line) => line.trim()).filter(Boolean);
  for (const line of lines) {
    if (/전월\s*대비|주요\s*변화\s*항목/i.test(line)) {
      reasonLines.push(line.replace(/^- /, '').trim());
    }
  }
  return reasonLines;
}

function applyPromiseFallbackSummaryLines(normalized, canFallbackAsPromise, directLines, reasonLines) {
  if (!canFallbackAsPromise || directLines.length > 0) return;
  const compact = normalized.replace(/\s+/g, ' ');
  const sentences = compact
    .split(/(?<=\.)\s+|(?<=다\.)\s+|(?<=[!?])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
  for (const sentence of sentences.slice(0, 3)) {
    directLines.push(sentence);
  }
  if (reasonLines.length > 0) return;
  for (const sentence of sentences) {
    if (/대비|증가|감소|변화|항목|근거/.test(sentence)) {
      reasonLines.push(sentence);
    }
  }
}

function canRenderPromiseAnalysisCard(normalized) {
  const hasAnalysisToken = /실행예산\s*분석/i.test(normalized);
  const hasProjectToken = /프로젝트번호\s*:/i.test(normalized);
  const inPromiseSummary = Boolean(pendingPromiseContext?.projectNumber);
  const hasMoneyToken = /[0-9][0-9,]*원/.test(normalized);
  const hasBudgetToken = /인건비|외주비|재료비|경비|실행비용|증가|감소|전월|월/.test(normalized);
  const canFallbackAsPromise = inPromiseSummary && hasMoneyToken && hasBudgetToken;
  return {
    canRender: hasAnalysisToken || hasProjectToken || canFallbackAsPromise,
    canFallbackAsPromise,
  };
}

function extractPromiseAnalysisMatches(normalized) {
  return {
    projectNameMatch: normalized.match(/(?:📘\s*)?실행예산\s*분석\s*:\s*(.+)/i),
    projectInfoMatch: normalized.match(
      /프로젝트번호\s*:\s*([^\s|]+)\s*(?:\|\s*유형\s*:\s*([^\s|]+))?\s*(?:\|\s*상태\s*:\s*([^\n]+))?/i
    ),
    finalCostMatch: normalized.match(/최종\s*Cost총액\s*:\s*([0-9,]+원)/i),
    executionTotalMatch: normalized.match(/총\s*실행비용\s*:\s*([0-9,]+원)/i),
    avgGrowthMatch: normalized.match(/월평균\s*증감률\s*:\s*([+\-]?[0-9.]+%)/i),
    maxIncreaseMatch: normalized.match(/최대\s*증가\s*:\s*([0-9]{1,2}월)\s*\(([+\-]?[0-9.]+%)\)/i),
    maxDecreaseMatch: normalized.match(/최대\s*감소\s*:\s*([0-9]{1,2}월)\s*\(([+\-]?[0-9.]+%)\)/i),
  };
}

function hasPromiseAnalysisCardData(matches, directLines = [], canFallbackAsPromise = false) {
  return Boolean(
    matches.projectNameMatch ||
      matches.projectInfoMatch ||
      matches.finalCostMatch ||
      matches.executionTotalMatch ||
      matches.avgGrowthMatch ||
      directLines.length > 0 ||
      canFallbackAsPromise
  );
}

function buildPromiseAnalysisPayload(matches, directLines, top3, reasonLines) {
  return {
    projectName: (
      matches.projectNameMatch?.[1] ||
      pendingPromiseContext?.projectName ||
      '실행예산 분석'
    ).trim(),
    projectNumber: (
      matches.projectInfoMatch?.[1] ||
      pendingPromiseContext?.projectNumber ||
      ''
    ).trim(),
    projectType: (
      matches.projectInfoMatch?.[2] ||
      pendingPromiseContext?.projectType ||
      ''
    ).trim(),
    status: (
      matches.projectInfoMatch?.[3] ||
      pendingPromiseContext?.status ||
      ''
    ).trim(),
    directLines,
    finalCost: matches.finalCostMatch?.[1] || '',
    executionTotal: matches.executionTotalMatch?.[1] || '',
    avgGrowth: matches.avgGrowthMatch?.[1] || '',
    maxIncreaseMonth: matches.maxIncreaseMatch?.[1] || '',
    maxIncreaseRate: matches.maxIncreaseMatch?.[2] || '',
    maxDecreaseMonth: matches.maxDecreaseMatch?.[1] || '',
    maxDecreaseRate: matches.maxDecreaseMatch?.[2] || '',
    top3,
    reasonLines,
  };
}

function formatPromiseAnalysisMessage(content) {
  const text = normalizeAssistantTextForParsing(content);
  const normalized = text.replace(/\u00a0/g, ' ').trim();
  const promiseState = canRenderPromiseAnalysisCard(normalized);
  if (!promiseState.canRender) return null;

  const directLines = extractPromiseDirectLines(normalized);
  const top3 = extractPromiseTop3(normalized);
  const reasonLines = extractPromiseReasonLines(normalized);
  applyPromiseFallbackSummaryLines(
    normalized,
    promiseState.canFallbackAsPromise,
    directLines,
    reasonLines
  );
  const matches = extractPromiseAnalysisMatches(normalized);
  if (!hasPromiseAnalysisCardData(matches, directLines, promiseState.canFallbackAsPromise)) {
    return null;
  }
  return buildPromiseAnalysisPayload(matches, directLines, top3, reasonLines);
}

function firstRegexMatch(text, patterns) {
  const raw = String(text || '');
  for (const pattern of patterns) {
    const matched = raw.match(pattern);
    if (matched && matched[1]) {
      return String(matched[1]).trim();
    }
  }
  return '';
}

function formatDateTimeLabel(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const korean = raw.match(/(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*(\d{1,2}):(\d{2})/);
  if (korean) {
    const [, , month, day, hour, minute] = korean;
    return `${Number(month)}월 ${Number(day)}일 ${hour}:${minute}`;
  }
  const iso = raw.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (iso) {
    const [, , month, day, hour, minute] = iso;
    return `${Number(month)}월 ${Number(day)}일 ${hour}:${minute}`;
  }
  return raw;
}

function extractWorkflowToolResults(metadata, toolNames = []) {
  const names = new Set((toolNames || []).map((name) => String(name || '').trim()).filter(Boolean));
  if (!names.size) return [];
  try {
    const workflow = metadata?.workflow;
    if (!Array.isArray(workflow)) return [];
    const results = [];
    for (const step of workflow) {
      const tools = step?.tools;
      if (!Array.isArray(tools)) continue;
      for (const tool of tools) {
        const name = String(tool?.name || '').trim();
        if (!names.has(name)) continue;
        const result = String(tool?.result || '').trim();
        if (result) results.push(result);
      }
    }
    return results;
  } catch (error) {
    logError('metadata.workflow_tool.parse_failed', error);
    return [];
  }
}

function normalizeParsingText(content) {
  return normalizeAssistantTextForParsing(content).replace(/\u00a0/g, ' ').trim();
}

function buildToolResultCandidates(content, metadata = null, toolNames = []) {
  return [content, ...extractWorkflowToolResults(metadata, toolNames)];
}

function parseFirstMatchedCandidate(candidates = [], parsers = []) {
  for (const candidate of candidates) {
    for (const parser of parsers) {
      const parsed = parser(candidate);
      if (parsed) return parsed;
    }
  }
  return null;
}

function parseTodoImportance(value) {
  const raw = String(value || '').trim().toLowerCase();
  if (!raw) return { key: 'normal', label: '보통' };
  if (raw === 'high' || raw.includes('높음')) return { key: 'high', label: '높음' };
  if (raw === 'low' || raw.includes('낮음')) return { key: 'low', label: '낮음' };
  return { key: 'normal', label: '보통' };
}

function parseTodoStatus(value) {
  const raw = String(value || '').trim().toLowerCase();
  if (!raw) return { key: 'progress', label: '진행중' };
  if (raw === 'completed' || raw.includes('완료')) return { key: 'done', label: '완료' };
  return { key: 'progress', label: '진행중' };
}

function appendCalendarListItem(items, current) {
  if (!current?.subject) return null;
  items.push({
    subject: String(current.subject || '').trim(),
    when: String(current.when || '').trim(),
    location: String(current.location || '').trim(),
    eventId: String(current.eventId || '').trim(),
  });
  return null;
}

function parseCalendarListItems(lines = []) {
  const items = [];
  let current = null;
  for (const line of lines) {
    const text = String(line || '').trim();
    if (!text) continue;

    const titleMatch = text.match(/^(\d+)\.\s*(.+)$/);
    if (titleMatch) {
      current = appendCalendarListItem(items, current);
      current = { subject: titleMatch[2].trim(), when: '', location: '', eventId: '' };
      continue;
    }
    if (!current) continue;

    const timeMatch = text.match(/^⏰\s*(.+)$/);
    if (timeMatch) {
      const timeRaw = String(timeMatch[1] || '').trim();
      const segments = timeRaw.split(/\s+@\s+/);
      current.when = String(segments[0] || '').trim();
      current.location = String(segments[1] || '').trim();
      continue;
    }

    const idMatch = text.match(/^🔑\s*(.+)$/);
    if (idMatch) current.eventId = String(idMatch[1] || '').trim();
  }
  appendCalendarListItem(items, current);
  return items;
}

function parseCalendarListFromText(content) {
  const raw = normalizeParsingText(content);
  if (!raw) return null;
  const emptyMatch = raw.match(/오늘\s*포함\s*향후\s*(\d+)일\s*(?:동안)?\s*예정된\s*일정이\s*없/i);
  if (emptyMatch) {
    return {
      kind: 'list',
      days: Number(emptyMatch[1] || 0) || null,
      total: 0,
      items: [],
    };
  }

  if (!/오늘\s*포함\s*향후\s*\d+일\s*일정|list_calendar_events|일정\s*\(총\s*\d+건\)/i.test(raw)) {
    return null;
  }

  const headerMatch = raw.match(/오늘\s*포함\s*향후\s*(\d+)일\s*일정\s*\(총\s*(\d+)건\)/i);
  const items = parseCalendarListItems(raw.split('\n'));

  if (!items.length) return null;
  return {
    kind: 'list',
    days: Number(headerMatch?.[1] || 0) || null,
    total: Number(headerMatch?.[2] || 0) || items.length,
    items,
  };
}

function parseCalendarResultFromText(content) {
  const raw = normalizeParsingText(content);
  if (!raw) return null;

  const hasCalendarToken = /캘린더\s*이벤트|일정\s*(등록|수정)|create_calendar_event|update_calendar_event/i.test(raw);
  const subject = firstRegexMatch(raw, [
    /📅\s*\*\*([^*]+)\*\*/i,
    /(?:^|\n)\s*(?:📌\s*)?(?:제목|일정명)\s*[:：]\s*(.+?)(?:\n|$)/i,
  ]);
  const start = firstRegexMatch(raw, [
    /🕐\s*\*\*시작\*\*[:：]?\s*(.+?)(?:\n|$)/i,
    /(?:^|\n)\s*시작\s*[:：]\s*(.+?)(?:\n|$)/i,
  ]);
  const end = firstRegexMatch(raw, [
    /🕐\s*\*\*종료\*\*[:：]?\s*(.+?)(?:\n|$)/i,
    /(?:^|\n)\s*종료\s*[:：]\s*(.+?)(?:\n|$)/i,
  ]);

  // Avoid false-positive conversion of mail search results (which also contain "제목:")
  // into calendar cards. Require explicit calendar signal or time fields.
  if (!hasCalendarToken && !start && !end) return null;
  if (!subject && !start && !end) return null;

  return {
    kind: 'single',
    subject: subject || '등록된 일정',
    startTime: formatDateTimeLabel(start),
    endTime: formatDateTimeLabel(end),
  };
}

function formatCalendarEventMessage(content, metadata = null) {
  const candidates = buildToolResultCandidates(content, metadata, [
    'list_calendar_events',
    'create_calendar_event',
    'update_calendar_event',
  ]);
  return parseFirstMatchedCandidate(candidates, [
    parseCalendarListFromText,
    parseCalendarResultFromText,
  ]);
}

function appendHrLeaveListItem(items, current) {
  if (!current?.subject) return null;
  items.push({
    subject: String(current.subject || '').trim(),
    when: String(current.when || '').trim(),
    note: String(current.note || '').trim(),
    eventId: String(current.eventId || '').trim(),
  });
  return null;
}

function parseHrLeaveListItems(lines = []) {
  const items = [];
  let current = null;
  for (const line of lines) {
    const text = String(line || '').trim();
    if (!text) continue;

    const titleMatch = text.match(/^(\d+)\.\s*(.+)$/);
    if (titleMatch) {
      current = appendHrLeaveListItem(items, current);
      current = { subject: titleMatch[2].trim(), when: '', note: '', eventId: '' };
      continue;
    }
    if (!current) continue;

    const whenMatch = text.match(/^📅\s*(.+)$/);
    if (whenMatch) {
      current.when = String(whenMatch[1] || '').trim();
      continue;
    }
    const noteMatch = text.match(/^📝\s*(.+)$/);
    if (noteMatch) {
      current.note = String(noteMatch[1] || '').trim();
      continue;
    }
    const idMatch = text.match(/^🔑\s*(.+)$/);
    if (idMatch) current.eventId = String(idMatch[1] || '').trim();
  }
  appendHrLeaveListItem(items, current);
  return items;
}

function parseHrLeaveListFromText(content) {
  const raw = normalizeParsingText(content);
  if (!raw) return null;
  const emptyMatch = raw.match(/최근\s*(\d+)일\s*근태\s*신청\s*내역이\s*없/i);
  if (emptyMatch) {
    return {
      kind: 'list',
      days: Number(emptyMatch[1] || 0) || 0,
      total: 0,
      items: [],
    };
  }

  if (!/근태\s*신청\s*내역|list_hr_leave_events/i.test(raw)) {
    return null;
  }

  const headerMatch = raw.match(/최근\s*(\d+)일\s*근태\s*신청\s*내역\s*\(총\s*(\d+)건\)/i);
  const items = parseHrLeaveListItems(raw.split('\n'));

  if (!items.length && !headerMatch) return null;
  return {
    kind: 'list',
    days: Number(headerMatch?.[1] || 0) || null,
    total: Number(headerMatch?.[2] || 0) || items.length,
    items,
  };
}

function formatHrLeaveMessage(content, metadata = null) {
  const candidates = buildToolResultCandidates(content, metadata, ['list_hr_leave_events']);
  return parseFirstMatchedCandidate(candidates, [parseHrLeaveListFromText]);
}

function parseTodoResultFromText(content) {
  const raw = normalizeParsingText(content);
  if (!raw) return null;

  const hasTodoToken = /to[\s-]?do|todo|할\s*일|할일|create_todo_task|update_todo_task/i.test(raw);
  const hasTodoFieldToken = /(?:^|\n)\s*(?:작업(?:명)?|마감(?:일)?|우선순위)\s*[:：]/i.test(raw);
  const title = firstRegexMatch(raw, [
    /📋\s*\*\*([^*]+)\*\*/i,
    /(?:^|\n)\s*(?:📋\s*)?(?:제목|작업(?:명)?)\s*[:：]\s*(.+?)(?:\n|$)/i,
  ]);
  const dueDate = firstRegexMatch(raw, [
    /📅\s*\*\*마감일\*\*[:：]?\s*(.+?)(?:\n|$)/i,
    /(?:^|\n)\s*마감(?:일)?\s*[:：]\s*(.+?)(?:\n|$)/i,
  ]);
  const importance = firstRegexMatch(raw, [
    /⭐\s*\*\*우선순위\*\*[:：]?\s*(.+?)(?:\n|$)/i,
    /(?:^|\n)\s*우선순위\s*[:：]\s*(.+?)(?:\n|$)/i,
  ]);

  // Avoid false-positive conversion of mail list/search results that include "제목:"
  // but do not carry todo intent/signals.
  if (!hasTodoToken && !hasTodoFieldToken && !dueDate && !importance) return null;
  if (!title && !dueDate && !importance) return null;

  const parsedImportance = parseTodoImportance(importance);
  return {
    kind: 'single',
    title: title || 'To Do 작업',
    dueDate: formatDateTimeLabel(dueDate),
    importance: parsedImportance.label,
    importanceKey: parsedImportance.key,
    status: '진행중',
    statusKey: 'progress',
  };
}

function parseTodoListFromText(content) {
  const raw = normalizeParsingText(content);
  if (!raw) return null;
  if (!/to[\s-]?do\s*작업\s*목록|list_todo_tasks|등록된\s*to[\s-]?do\s*작업이\s*없/i.test(raw)) {
    return null;
  }
  if (/등록된\s*to[\s-]?do\s*작업이\s*없/i.test(raw)) {
    return { kind: 'list', items: [] };
  }

  const items = parseTodoListItems(raw.split('\n'));
  if (!items.length) return null;
  return { kind: 'list', items };
}

function appendTodoListItem(items, current) {
  if (!current?.title) return null;
  items.push({
    title: String(current.title || '').trim(),
    dueDate: String(current.dueDate || '').trim(),
    importance: current.importanceLabel || '보통',
    importanceKey: current.importanceKey || 'normal',
    status: current.statusLabel || '진행중',
    statusKey: current.statusKey || 'progress',
    taskId: String(current.taskId || '').trim(),
  });
  return null;
}

function parseTodoListItems(lines = []) {
  const items = [];
  let current = null;

  for (const line of lines) {
    const text = String(line || '').trim();
    if (!text) continue;

    const taskMatch = text.match(/^- (.+)$/);
    if (taskMatch) {
      current = appendTodoListItem(items, current);
      const rawTask = String(taskMatch[1] || '').trim();
      const dueMatch = rawTask.match(/\(마감:\s*([^)]+)\)/i);
      const badgeMatches = [...rawTask.matchAll(/\[([^\]]+)\]/g)].map((m) =>
        String(m[1] || '').trim()
      );
      const importance = parseTodoImportance(badgeMatches[0] || '');
      const status = parseTodoStatus(badgeMatches[1] || '');
      const cleanedTitle = rawTask
        .replace(/\(마감:[^)]+\)/i, '')
        .replace(/\[[^\]]+\]/g, '')
        .trim();

      current = {
        title: cleanedTitle,
        dueDate: formatDateTimeLabel(dueMatch?.[1] || ''),
        importanceLabel: importance.label,
        importanceKey: importance.key,
        statusLabel: status.label,
        statusKey: status.key,
        taskId: '',
      };
      continue;
    }

    if (current) {
      const idMatch = text.match(/^id\s*:\s*(.+)$/i);
      if (idMatch) {
        current.taskId = String(idMatch[1] || '').trim();
      }
    }
  }
  appendTodoListItem(items, current);
  return items;
}

function formatTodoTaskMessage(content, metadata = null) {
  const candidates = buildToolResultCandidates(content, metadata, [
    'list_todo_tasks',
    'create_todo_task',
    'update_todo_task',
    'complete_todo_task',
  ]);
  return parseFirstMatchedCandidate(candidates, [
    parseTodoListFromText,
    parseTodoResultFromText,
  ]);
}

function parseMeetingRoomScheduleDetail(rawDetail) {
  const cleaned = String(rawDetail || '').replace(/^📅\s*/, '').trim();
  if (!cleaned) {
    return { subject: '', when: '' };
  }
  const parts = cleaned.split('|');
  if (parts.length >= 2) {
    return {
      subject: String(parts.slice(0, -1).join('|') || '').trim(),
      when: String(parts[parts.length - 1] || '').trim(),
    };
  }
  return { subject: cleaned, when: '' };
}

function parseMeetingRoomListFromText(content) {
  const raw = normalizeParsingText(content);
  if (!raw) return null;
  if (!/예약된\s*회의실|list_booked_meeting_rooms|회의실\s*예약\s*조회/i.test(raw)) {
    return null;
  }

  const noneMatch = raw.match(/오늘\s*포함\s*향후\s*(\d+)\s*일\s*동안\s*예약된\s*회의실이\s*없/i);
  if (noneMatch) {
    return {
      kind: 'list',
      days: Number(noneMatch[1] || 0) || 0,
      total: 0,
      items: [],
    };
  }

  const headerMatch = raw.match(/예약된\s*회의실\s*\((\d+)\s*건\)/i);
  const items = parseMeetingRoomListItems(raw.split('\n'));

  if (!items.length) return null;
  return {
    kind: 'list',
    total: Number(headerMatch?.[1] || 0) || items.length,
    items,
  };
}

function buildMeetingRoomListItem(room, detailRaw) {
  const detail = parseMeetingRoomScheduleDetail(detailRaw);
  return {
    room: String(room || '').trim() || '회의실 미기재',
    subject: detail.subject || '제목 없음',
    when: detail.when || '-',
    note: '-',
  };
}

function parseMeetingRoomListItems(lines = []) {
  const normalizedLines = lines.map((line) => String(line || '').trim());
  const items = [];
  for (let idx = 0; idx < normalizedLines.length; idx += 1) {
    const line = normalizedLines[idx];
    if (!line) continue;

    const roomLineMatch = line.match(/^\d+\.\s*📍\s*(.+)$/);
    if (roomLineMatch) {
      const room = String(roomLineMatch[1] || '').trim();
      let detailLine = '';
      for (let j = idx + 1; j < normalizedLines.length; j += 1) {
        const candidate = String(normalizedLines[j] || '').trim();
        if (!candidate) continue;
        detailLine = candidate;
        idx = j;
        break;
      }
      items.push(buildMeetingRoomListItem(room, detailLine));
      continue;
    }

    const detailOnlyMatch = line.match(/^\d+\.\s*📅\s*(.+)$/);
    if (detailOnlyMatch) {
      items.push(buildMeetingRoomListItem('회의실 미기재', detailOnlyMatch[1]));
    }
  }
  return items;
}

function formatMeetingRoomMessage(content, metadata = null) {
  const candidates = buildToolResultCandidates(content, metadata, [
    'list_booked_meeting_rooms',
    'book_meeting_room',
  ]);
  return parseFirstMatchedCandidate(candidates, [parseMeetingRoomListFromText]);
}

  const api = {
    formatTurnElapsedLabel,
    resolveLastTurnElapsedMsFromHistory,
    resolveLastTurnElapsedMs,
    insertTurnSeparatorIfNeeded,
    bindInlineCopyButton,
    addUserMessage,
    resolveAssistantPrimaryCards,
    hasAssistantPrimaryCard,
    resolveAssistantMailUiState,
    shouldAttachRestartSessionAction,
    shouldAttachAssistantOpenMailList,
    canAttachAssistantOpenableItems,
    resolveAssistantOpenableMailState,
    computeAssistantRenderState,
    truncateInlineText,
    appendSummaryLine,
    buildPromiseAnalysisSummaryMarkdown,
    buildCalendarSummaryMarkdown,
    buildHrLeaveSummaryMarkdown,
    buildTodoSummaryMarkdown,
    buildMeetingRoomSummaryMarkdown,
    buildAssistantPrimarySummaryMarkdown,
    buildStructuredUiOutputMarkdown,
    normalizeAssistantMergeBlock,
    mergeAssistantBodyTextSegments,
    stripLeadingDecorativeEmoji,
    isLikelyOpaqueMessageIdToken,
    sanitizeAssistantDisplayText,
    shouldAppendCalendarPrimarySummary,
    shouldAppendPrimarySummary,
    buildAssistantMessageBodyHtml,
    attachWeeklyReportDownloadActions,
    attachAssistantFeedbackActionRow,
    attachAssistantMessageActions,
    addAssistantMessage,
    showStreamingAssistantMessage,
    scheduleStreamingAssistantRender,
    updateStreamingAssistantMessage,
    resetStreamingAssistantMessage,
    removeStreamingAssistantMessage,
    addSystemMessage,
    showTyping,
    removeTyping,
    startWeeklyReportBuildToast,
    updateWeeklyReportBuildToast,
    finishWeeklyReportBuildToast,
    coerceStatusLineValue,
    trimStatusLineText,
    resolveStatusHeadlineByEvent,
    resolveStatusLogByEvent,
    normalizeDeepProgressTaskName,
    resolveDeepProgressEntityName,
    appendStatusLog,
    removeStatusLogByTaskKey,
    resolveStatusHeadlineByState,
    renderDeepProgressCard,
    scheduleDeepProgressRender,
    applyDeepProgressEvent,
    startDeepProgressCard,
    cleanupFinishedDeepProgressTracker,
    finishDeepProgressCard,
    scrollToBottom,
    normalizeUiOutputPayload,
    normalizeUiOutputV2Payload,
    normalizeAssistantTextForParsing,
    extractPromiseDirectLines,
    extractPromiseTop3,
    extractPromiseReasonLines,
    applyPromiseFallbackSummaryLines,
    canRenderPromiseAnalysisCard,
    extractPromiseAnalysisMatches,
    hasPromiseAnalysisCardData,
    buildPromiseAnalysisPayload,
    formatPromiseAnalysisMessage,
    firstRegexMatch,
    formatDateTimeLabel,
    extractWorkflowToolResults,
    normalizeParsingText,
    buildToolResultCandidates,
    parseFirstMatchedCandidate,
    parseTodoImportance,
    parseTodoStatus,
    appendCalendarListItem,
    parseCalendarListItems,
    parseCalendarListFromText,
    parseCalendarResultFromText,
    formatCalendarEventMessage,
    appendHrLeaveListItem,
    parseHrLeaveListItems,
    parseHrLeaveListFromText,
    formatHrLeaveMessage,
    parseTodoResultFromText,
    parseTodoListFromText,
    appendTodoListItem,
    parseTodoListItems,
    formatTodoTaskMessage,
    parseMeetingRoomScheduleDetail,
    parseMeetingRoomListFromText,
    buildMeetingRoomListItem,
    parseMeetingRoomListItems,
    formatMeetingRoomMessage,
  };

  global.TaskpaneRendererUtils = {
    ...(global.TaskpaneRendererUtils || {}),
    ...api,
  };

  Object.assign(global, api);
})(window);
