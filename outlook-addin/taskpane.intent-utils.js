/* ========================================
   MolduBot - Intent Utils
   ======================================== */

(function initIntentUtils(global) {
function containsAnyToken(text, tokens) {
  const normalized = String(text || '').toLowerCase();
  const compact = normalized.replace(/\s+/g, '');
  return tokens.some((token) => {
    const rawToken = String(token || '').toLowerCase();
    if (!rawToken) return false;
    if (normalized.includes(rawToken)) return true;
    const compactToken = rawToken.replace(/\s+/g, '');
    return compact.includes(compactToken);
  });
}

function normalizeAssistantPrompt(message) {
  const raw = String(message || '').trim();
  if (!raw) return raw;
  const compact = raw.replace(/\s+/g, '').toLowerCase();
  for (const alias of ASSISTANT_PROMPT_ALIASES) {
    const patterns = Array.isArray(alias.patterns) ? alias.patterns : [];
    if (patterns.some((pattern) => compact.includes(String(pattern).toLowerCase()))) {
      return alias.canonical;
    }
  }
  return raw;
}

function hasRecentFollowupContext(runtimePayload = {}) {
  const payload = runtimePayload && typeof runtimePayload === 'object' ? runtimePayload : {};
  if (toBool(payload.has_recent_followup_context)) return true;
  if (toBool(payload.current_mail_only)) return true;
  if (String(payload.email_message_id || '').trim()) return true;
  const stickySnapshot = resolveStickyCurrentMailSnapshot({
    threadId: String(chatThreadId || '').trim(),
  });
  return Boolean(stickySnapshot && String(stickySnapshot.emailMessageId || '').trim());
}

function isExplicitSmalltalkPrompt(message) {
  const raw = String(message || '').trim();
  if (!raw) return false;
  const compact = String(message || '')
    .toLowerCase()
    .replace(/[\s\.,!?~"'`()\[\]{}\-_:;]+/g, '')
    .trim();
  if (!compact) return false;
  if (SMALLTALK_PROMPT_SET.has(compact)) return true;
  if (compact.length > 24) return false;
  if (TASK_SIGNAL_RE.test(raw)) return false;
  if (EXPLICIT_SMALLTALK_SIGNAL_RE.test(raw)) return true;
  if (compact.length <= 8 && /^(안녕|고마워|감사|반가워|hi|hello|hey|thanks?)$/i.test(compact)) return true;
  return false;
}

function isFollowupRefinePrompt(message, options = {}) {
  const raw = String(message || '').trim();
  if (!raw) return false;
  const hasRecentContext = Boolean(options?.hasRecentContext);
  if (!hasRecentContext) return false;
  if (FOLLOWUP_CONTEXT_SHORT_QUERY_RE.test(raw)) return true;
  if (FOLLOWUP_REFINE_SIGNAL_RE.test(raw)) return true;
  const compact = raw.replace(/\s+/g, '');
  if (compact.length <= 20 && /(다시|간단|요약|정리|자세히|왜|근거)/i.test(compact)) return true;
  return false;
}

function classifyTurnKind(message, runtimePayload = {}) {
  const raw = String(message || '').trim();
  if (!raw) return TURN_KIND.TASK;
  const hasRecentContext = hasRecentFollowupContext(runtimePayload);
  if (isFollowupRefinePrompt(raw, { hasRecentContext })) {
    return TURN_KIND.FOLLOWUP_REFINE;
  }
  if (isExplicitSmalltalkPrompt(raw)) {
    return TURN_KIND.EXPLICIT_SMALLTALK;
  }
  return TURN_KIND.TASK;
}

function isLikelyMailSearchRequest(message, options = {}) {
  const searchUtils =
    (typeof window !== 'undefined' && window.__searchQueryUtils) || null;
  if (searchUtils && typeof searchUtils.looksLikeMailSearchIntent === 'function') {
    const detectedBySearchUtils = Boolean(searchUtils.looksLikeMailSearchIntent(message, options));
    if (detectedBySearchUtils) return true;
  }

  const legacyMailUtils =
    (typeof window !== 'undefined' && window.__mailIntentUtils) || null;
  if (legacyMailUtils && typeof legacyMailUtils.looksLikeMailSearchIntent === 'function') {
    const detectedByLegacyMailUtils = Boolean(legacyMailUtils.looksLikeMailSearchIntent(message, options));
    if (detectedByLegacyMailUtils) return true;
  }

  const text = String(message || '').trim();
  if (!text) return false;
  const lower = text.toLowerCase();
  if (/(?:이|현재|해당|본|지금)\s*(?:메일|이메일|mail|email)|(?:this|current)\s*(?:mail|email)/i.test(lower)) {
    return false;
  }

  const compact = lower.replace(/\s+/g, '');
  if (compact.includes('메일조회') || compact.includes('메일검색')) return true;
  const hasInsightToken = /(?:insight|인사이트|분석|보고서|리포트|추출|요약|정리|브리핑)/i.test(text);
  const hasMailToken = /(?:메일|이메일|mail|email)/i.test(text);
  if (hasMailToken && hasInsightToken) {
    return true;
  }
  const allowRelatedInsightWithoutMail = Boolean(options && options.allowRelatedInsightWithoutMail);
  if (allowRelatedInsightWithoutMail && hasInsightToken && /(?:관련|related|relation)/i.test(text)) {
    return true;
  }

  return (
    /메일.*(?:조회|검색|찾아|찾기|보여줘|보여주|찾아줘)/i.test(text) ||
    /(?:보낸|받은|관련)\s*메일.*(?:조회|검색|찾아|찾기)/i.test(text) ||
    /메일.*(?:요약|정리|브리핑)/i.test(text)
  );
}

function shouldShowThinkingProgress(message, runtimePayload = {}, turnKind = '') {
  const text = String(message || '').trim();
  const resolvedTurnKind =
    String(turnKind || runtimePayload?.turn_kind || '').trim().toLowerCase() || classifyTurnKind(text, runtimePayload);
  if (resolvedTurnKind === TURN_KIND.EXPLICIT_SMALLTALK) {
    return false;
  }
  void runtimePayload;
  if (isRoomLookupFastPath(text, runtimePayload)) {
    return false;
  }
  if (isHrLookupFastPath(text, runtimePayload)) {
    return false;
  }
  if (isScheduleLookupFastPath(text, runtimePayload)) {
    return false;
  }
  if (isTodoLookupFastPath(text, runtimePayload)) {
    return false;
  }
  return Boolean(text);
}

function isRoomLookupFastPath(message, runtimePayload = {}) {
  const text = String(message || '').trim();
  if (!text) return false;
  const parsed = parseScopeFromMessagePrefix(text);
  const coreMessage = String(parsed?.message || text).trim();
  const domain = String(parsed?.domain || '').trim().toLowerCase();
  const scope = normalizeScope(runtimePayload?.scope);
  const scopeLooksRoom = scope === 'systems' && /회의실|미팅룸/i.test(String(currentScopeLabelOverride || ''));
  const hasRoomSignal = domain === 'room' || /회의실|미팅룸/i.test(text) || scopeLooksRoom;
  if (!hasRoomSignal) return false;

  const hasLookupSignal = /(조회|확인|목록|예약한)/i.test(coreMessage);
  const hasBookingSignal = /(예약(?!한)|생성|잡아|book)/i.test(coreMessage);
  return hasLookupSignal && !hasBookingSignal;
}

function isHrLookupFastPath(message, runtimePayload = {}) {
  const text = String(message || '').trim();
  if (!text) return false;
  const parsed = parseScopeFromMessagePrefix(text);
  const coreMessage = String(parsed?.message || text).trim();
  const domain = String(parsed?.domain || '').trim().toLowerCase();
  const scope = normalizeScope(runtimePayload?.scope);
  const scopeLooksHr = scope === 'systems' && /근태|휴가|연차|hr/i.test(String(currentScopeLabelOverride || ''));
  const hasHrSignal = domain === 'hr' || /근태|휴가|연차|hr/i.test(text) || scopeLooksHr;
  if (!hasHrSignal) return false;

  const hasLookupSignal = /(조회|내역|현황|기록|목록|리스트|확인|보여|요약)/i.test(coreMessage);
  const hasApplyKeyword = /(신청|승인|결재|기안|생성|작성|draft)/i.test(coreMessage);
  const hasApplyWriteSignal =
    /(신청\s*(해|해주세요|진행|요청|등록)|승인\s*(해|해주세요|처리)|결재\s*(해|해주세요|처리)|기안\s*(해|해주세요|작성)|생성\s*(해|해주세요)|작성\s*(해|해주세요)|draft)/i.test(
      coreMessage
    );
  const hasApplySignal = hasLookupSignal ? hasApplyWriteSignal : hasApplyKeyword;
  return hasLookupSignal && !hasApplySignal;
}

function isScheduleLookupFastPath(message, runtimePayload = {}) {
  const text = String(message || '').trim();
  if (!text) return false;
  const parsed = parseScopeFromMessagePrefix(text);
  const coreMessage = String(parsed?.message || text).trim();
  const domain = normalizeShortcutDomain(parsed?.domain || runtimePayload?.shortcut_domain);
  const scope = normalizeScope(runtimePayload?.scope);
  const scopeLooksSchedule =
    scope === 'systems' && /일정|캘린더|스케줄/i.test(String(currentScopeLabelOverride || ''));
  const hasScheduleSignal =
    domain === 'schedule' || /일정|캘린더|스케줄|calendar/i.test(text) || scopeLooksSchedule;
  if (!hasScheduleSignal) return false;

  const hasLookupSignal = /(조회|확인|목록|보여|이번주|다음주|오늘|내일)/i.test(coreMessage);
  const hasCreateSignal = /(등록|추가|생성|만들|잡아|예약)/i.test(coreMessage);
  return hasLookupSignal && !hasCreateSignal;
}

function isTodoLookupFastPath(message, runtimePayload = {}) {
  const text = String(message || '').trim();
  if (!text) return false;
  const parsed = parseScopeFromMessagePrefix(text);
  const coreMessage = String(parsed?.message || text).trim();
  const domain = normalizeShortcutDomain(parsed?.domain || runtimePayload?.shortcut_domain);
  const scope = normalizeScope(runtimePayload?.scope);
  const scopeLooksTodo = scope === 'systems' && /할\s*일|todo/i.test(String(currentScopeLabelOverride || ''));
  const hasTodoSignal = domain === 'todo' || /할\s*일|todo|to\s*do/i.test(text) || scopeLooksTodo;
  if (!hasTodoSignal) return false;

  const hasLookupSignal = /(조회|확인|목록|리스트|보여)/i.test(coreMessage);
  const hasCreateSignal = /(생성|추가|등록|만들|작성)/i.test(coreMessage);
  return hasLookupSignal && !hasCreateSignal;
}

function hasPromiseTimeSliceToken(text) {
  return /(?:^|\D)([1-9]|1[0-2])월/.test(text) || /(?:^|\D)([1-4])\s*분기/.test(text) || /\bq[1-4]\b/i.test(text);
}

function hasPromiseAnalysisKeyword(text) {
  const compact = text.toLowerCase().replace(/\s+/g, '');
  return (
    containsAnyToken(text, PROMISE_ANALYSIS_KEYWORDS) ||
    compact.includes('현황') ||
    compact.includes('증감') ||
    compact.includes('변화')
  );
}

function hasPromiseDomainKeyword(text) {
  return containsAnyToken(text, [
    '실행예산',
    '실행 예산',
    'promise',
    '프로젝트',
    'project',
    '프로젝트번호',
    '예산',
    '인건비',
    '외주비',
    '재료비',
    '경비',
    'cost',
  ]);
}

function hasPromiseMailSignal(text) {
  return containsAnyToken(text, [
    '메일',
    '이메일',
    '수신자',
    'to/cc',
    '회신',
    '답변',
    '본문',
  ]);
}

function hasPromiseBudgetSignal(text) {
  return containsAnyToken(text, [
    '예산',
    '인건비',
    '외주비',
    '재료비',
    '경비',
    '비용',
    '총액',
    '합계',
  ]);
}

function isPromiseAnalysisFollowUpContext({
  hasTimeSliceToken,
  hasBudgetSignal,
  hasAnalysisKeyword,
  hasMailSignal,
}) {
  if (pendingPromiseContext?.projectNumber && (hasTimeSliceToken || hasBudgetSignal)) {
    return true;
  }
  return (
    resolveActiveAssistantShortcutDomain('') === 'promise' &&
    (hasTimeSliceToken || hasBudgetSignal || hasAnalysisKeyword) &&
    !hasMailSignal
  );
}

function isPromiseAnalysisQuery(message, intentResult = null) {
  if (String(intentResult?.intent || '').trim() === 'promise_analysis') return true;

  const text = String(message || '').trim();
  if (!text) return false;

  const hasTimeSliceToken = hasPromiseTimeSliceToken(text);
  const hasAnalysisKeyword = hasPromiseAnalysisKeyword(text);
  const hasDomainKeyword = hasPromiseDomainKeyword(text);
  const hasMailSignal = hasPromiseMailSignal(text);
  const hasBudgetSignal = hasPromiseBudgetSignal(text);

  if (!hasAnalysisKeyword && !hasTimeSliceToken) return false;
  if (hasMailSignal && !hasDomainKeyword) return false;
  if (hasDomainKeyword) return true;

  return isPromiseAnalysisFollowUpContext({
    hasTimeSliceToken,
    hasBudgetSignal,
    hasAnalysisKeyword,
    hasMailSignal,
  });
}

function enrichPromiseAnalysisMessage(message, intentResult = null) {
  const raw = String(message || '').trim();
  if (!raw) return raw;
  if (currentMode !== 'assistant') return raw;
  if (!pendingPromiseContext?.projectNumber) return raw;
  if (!isPromiseAnalysisQuery(raw, intentResult)) return raw;

  if (/project_number\s*:|project_number\s*=|프로젝트번호\s*:|프로젝트번호\s*=/i.test(raw)) {
    return raw;
  }

  return `[실행예산 분석 컨텍스트]
project_number: ${pendingPromiseContext.projectNumber}
[실행 규칙]
- 반드시 analyze_promise_budget 도구를 호출해서 답변한다.
- 추정/요약으로 직접 답하지 않는다.
- 도구 출력의 숫자, 월, 증감률, 섹션 구조를 유지한다.
question: ${raw}`;
}

function openMockupWindow(path, name, extraParams = {}) {
  const base = API_BASE.replace(/\/+$/, '');
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const params = new URLSearchParams();
  params.set('thread_id', chatThreadId);
  for (const [key, value] of Object.entries(extraParams || {})) {
    if (value === undefined || value === null || String(value).trim() === '') continue;
    params.set(key, String(value));
  }
  const url = `${base}${normalizedPath}?${params.toString()}`;
  return window.open(
    url,
    name,
    'width=1180,height=900,menubar=no,toolbar=no,location=no,status=no,resizable=yes,scrollbars=yes'
  );
}

function resolveRequestTimeoutMeta(runtimePayload = {}, requestedIntent = '', messageText = '') {
  const resolvedTurnKind =
    String(runtimePayload?.turn_kind || '').trim().toLowerCase() || classifyTurnKind(messageText, runtimePayload);
  const isMailSearchByText =
    typeof window.__searchQueryUtils?.looksLikeMailSearchIntent === 'function'
      ? Boolean(window.__searchQueryUtils.looksLikeMailSearchIntent(messageText))
      : /(메일|이메일|mail|email).*(조회|검색|찾아|찾기|보여)/i.test(messageText);
  const isLikelyMailSearchChat = requestedIntent === 'mail_search' || isMailSearchByText;

  void runtimePayload;
  const quickActionId = String(runtimePayload.quick_action_id || '').trim().toLowerCase();
  const isCodeReviewQuickAction = ['code_analysis', 'code-analysis', 'codeanalysis'].includes(quickActionId);

  let requestTimeoutMs =
    resolvedTurnKind === TURN_KIND.EXPLICIT_SMALLTALK
      ? API_TIMEOUT_MS
      : API_TIMEOUT_DEEP_MS;

  if (isLikelyMailSearchChat) {
    requestTimeoutMs = Math.max(requestTimeoutMs, API_TIMEOUT_DEEP_MS);
  }

  if (isCodeReviewQuickAction) {
    requestTimeoutMs = Math.max(requestTimeoutMs, API_TIMEOUT_CODE_REVIEW_MS);
  }

  return {
    requestTimeoutMs,
    isLikelyMailSearchChat,
    quickActionId,
    isCodeReviewQuickAction,
    turnKind: resolvedTurnKind || TURN_KIND.TASK,
  };
}

function buildChatRequestContext(payload) {
  const safePayload = payload || {};
  const runtimePayload = safePayload.runtime_options || {};
  const messageText = String(safePayload.message || '').trim();
  const requestedIntent = String(safePayload.intent_name || '').trim().toLowerCase();
  const timeoutMeta = resolveRequestTimeoutMeta(runtimePayload, requestedIntent, messageText);
  return {
    safePayload,
    requestedIntent,
    timeoutMeta,
    requestTimeoutMs: timeoutMeta.requestTimeoutMs,
  };
}

function logChatRequestStart(requestContext) {
  const { safePayload, requestedIntent, timeoutMeta, requestTimeoutMs } = requestContext;
  logEvent('model.chat.request.start', 'ok', {
    mode: currentMode,
    has_email_id: Boolean(safePayload.email_id),
    thread_id: String(safePayload.thread_id || '').slice(0, 42),
    message_len: String(safePayload.message || '').length,
    quick_action_id: timeoutMeta.quickActionId || '',
    code_review_timeout: timeoutMeta.isCodeReviewQuickAction,
    intent_name: requestedIntent || 'unknown',
    turn_kind: timeoutMeta.turnKind || TURN_KIND.TASK,
    mail_search_timeout: timeoutMeta.isLikelyMailSearchChat,
    timeout_ms: requestTimeoutMs,
  });
}

function logChatRequestOutcome(response, data, elapsedMs) {
  if (!response.ok) {
    logEvent('model.chat.request.http_error', 'warn', {
      status_code: response.status,
      elapsed_ms: elapsedMs,
    });
    return;
  }
  logEvent('model.chat.request.success', 'ok', {
    status: data?.status || 'completed',
    confirm_required: data?.status === 'confirm_required',
    elapsed_ms: elapsedMs,
  });
}

function logChatRequestFailure(error, elapsedMs, requestTimeoutMs) {
  if (error?.name === 'AbortError') {
    logEvent('model.chat.request.timeout', 'warn', {
      elapsed_ms: elapsedMs,
      timeout_ms: requestTimeoutMs,
    });
  }
  logError('model.chat.request.failed', error, {
    elapsed_ms: elapsedMs,
    timeout_ms: requestTimeoutMs,
  });
}

async function requestChat(payload) {
  const requestStartedAt = Date.now();
  const requestContext = buildChatRequestContext(payload);
  const { safePayload, requestTimeoutMs } = requestContext;
  logChatRequestStart(requestContext);
  try {
    const response = await apiFetch('/search/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(safePayload),
    }, requestTimeoutMs);
    const data = await response.json().catch(() => ({}));
    const elapsedMs = Date.now() - requestStartedAt;
    logChatRequestOutcome(response, data, elapsedMs);
    return data;
  } catch (error) {
    const elapsedMs = Date.now() - requestStartedAt;
    logChatRequestFailure(error, elapsedMs, requestTimeoutMs);
    throw error;
  }
}

function logChatStreamRequestStart(safePayload, timeoutMeta, requestTimeoutMs, requestStartedAt) {
  logEvent('model.chat.stream.start', 'ok', {
    mode: currentMode,
    has_email_id: Boolean(safePayload.email_id),
    thread_id: String(safePayload.thread_id || '').slice(0, 42),
    message_len: String(safePayload.message || '').length,
    quick_action_id: timeoutMeta.quickActionId || '',
    code_review_timeout: timeoutMeta.isCodeReviewQuickAction,
    intent_name: String(safePayload.intent_name || '').trim().toLowerCase() || 'unknown',
    turn_kind: timeoutMeta.turnKind || TURN_KIND.TASK,
    timeout_ms: requestTimeoutMs,
    started_at: requestStartedAt,
  });
}

function logChatStreamSuccess(finalData, requestStartedAt) {
  logEvent('model.chat.stream.success', 'ok', {
    status: finalData.status || 'completed',
    elapsed_ms: Date.now() - requestStartedAt,
  });
}

function logChatStreamFailure(error, requestStartedAt, requestTimeoutMs) {
  if (error?.name === 'AbortError') {
    logEvent('model.chat.stream.timeout', 'warn', {
      elapsed_ms: Date.now() - requestStartedAt,
      timeout_ms: requestTimeoutMs,
    });
  }
  logError('model.chat.stream.failed', error, {
    elapsed_ms: Date.now() - requestStartedAt,
    timeout_ms: requestTimeoutMs,
  });
}

async function requestChatStream(payload, { onEvent } = {}) {
  const requestStartedAt = Date.now();
  const safePayload = payload || {};
  const runtimePayload = safePayload.runtime_options || {};
  const messageText = String(safePayload.message || '').trim();
  const requestedIntent = String(safePayload.intent_name || '').trim().toLowerCase();
  const timeoutMeta = resolveRequestTimeoutMeta(runtimePayload, requestedIntent, messageText);
  const requestTimeoutMs = timeoutMeta.requestTimeoutMs;

  logChatStreamRequestStart(safePayload, timeoutMeta, requestTimeoutMs, requestStartedAt);

  try {
    if (typeof onEvent === 'function') {
      onEvent({ type: 'start', message: '분석 시작...' });
    }
    const finalData = await requestChat(safePayload);
    if (typeof onEvent === 'function') {
      onEvent({
        type: finalData?.status === 'confirm_required' ? 'confirm_required' : 'complete',
        ...finalData,
      });
    }
    logChatStreamSuccess(finalData, requestStartedAt);
    return finalData;
  } catch (error) {
    logChatStreamFailure(error, requestStartedAt, requestTimeoutMs);
    throw error;
  }
}

function buildAssistantActionButtonsHtml(actions = []) {
  return actions
    .map(
      (action, idx) => `
        <button
          type="button"
          class="approval-btn approve"
          data-action-index="${idx}"
          style="min-width:0; flex:1;"
        >
          ${escapeHtml(action.label || '실행')}
        </button>
      `
    )
    .join('');
}

function buildAssistantActionCardHtml(cardId, config, actionsHtml) {
  return `
    <div class="message assistant workflow-card-message" id="${cardId}">
      <div class="msg-body" style="padding:0; overflow:hidden;">
        <div class="approval-card">
          <div class="approval-header">
            ${ICONS.fileText}
            ${escapeHtml(config.title || '업무 선택')}
          </div>
          <div class="approval-body">
            <div style="font-size:13px; line-height:1.6; color:var(--color-text-secondary);">
              ${renderMarkdown(config.description || '')}
            </div>
          </div>
          <div class="approval-actions" style="display:flex; gap:8px; flex-wrap:wrap;">
            ${actionsHtml}
          </div>
        </div>
      </div>
    </div>
  `;
}

function bindAssistantActionCardEvents(cardEl, config, actions = []) {
  if (!cardEl) return;
  cardEl.querySelectorAll('button[data-action-index]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const idx = Number(btn.getAttribute('data-action-index'));
      const action = actions[idx];
      if (!action) return;
      logEvent('ui.assistant_action.click', 'ok', {
        title: String(config.title || ''),
        action_label: String(action.label || ''),
      });
      Promise.resolve()
        .then(() => action.onClick?.())
        .catch((error) => {
        logError('ui.assistant_action.click.failed', error, {
          title: String(config.title || ''),
          action_label: String(action.label || ''),
        });
        addSystemMessage('작업 실행 중 오류가 발생했습니다.');
        });
    });
  });
}

function finalizeAssistantActionCard(config) {
  recordHistory('assistant', config.historyText || config.title || '업무 선택 카드 표시');
  persistTaskpaneState();
  scrollToBottom();
}

function addAssistantActionCard(config) {
  const chatArea = document.getElementById('chatArea');
  if (!chatArea || !config) return;
  removeWelcomeStateIfExists();

  const cardId = `assistant_action_card_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
  const actions = Array.isArray(config.actions) ? config.actions : [];
  const actionsHtml = buildAssistantActionButtonsHtml(actions);
  const html = buildAssistantActionCardHtml(cardId, config, actionsHtml);

  chatArea.insertAdjacentHTML('beforeend', html);
  const cardEl = document.getElementById(cardId);
  if (!cardEl) return;
  bindAssistantActionCardEvents(cardEl, config, actions);
  finalizeAssistantActionCard(config);
}

function formatKrw(value) {
  const normalized = String(value ?? '')
    .replace(/[,\s원]/g, '')
    .replace(/[^\d.-]/g, '');
  const amount = Number(normalized || 0);
  if (!Number.isFinite(amount)) return '0원';
  return `${amount.toLocaleString('ko-KR')}원`;
}

function removeWorkflowCards() {
  document.querySelectorAll('.workflow-card-message').forEach((el) => el.remove());
}

function resolveIntentRequestBase(message, options = {}) {
  const text = String(message || '').trim();
  const resolvedScope = normalizeScope(options?.scope || currentScope);
  const emailMessageId = String(
    options?.emailMessageId ||
      emailContext?.resolvedMessageId ||
      emailContext?.restItemId ||
      emailContext?.itemId ||
      ''
  ).trim();
  const currentMailOnly =
    resolvedScope === 'email' && Boolean(options?.currentMailOnly) && Boolean(emailMessageId);
  const resolveTimeoutRaw = Number.parseInt(String(options?.timeoutMs || '').trim(), 10);
  const resolveTimeoutMs =
    Number.isFinite(resolveTimeoutRaw) && resolveTimeoutRaw > 0
      ? resolveTimeoutRaw
      : API_TIMEOUT_INTENT_RESOLVE_MS;
  return {
    text,
    resolvedScope,
    emailMessageId,
    currentMailOnly,
    resolveTimeoutMs,
  };
}

function buildIntentResolveContext(runtimePayload, resolvedScope, emailMessageId, currentMailOnly) {
  const rawLimit = Number.parseInt(String(runtimePayload?.search_result_limit || '').trim(), 10);
  const normalizedLimit = rawLimit > 0 ? rawLimit : undefined;
  return {
    surface: 'outlook_addin',
    mode: String(currentMode || '').toLowerCase(),
    scope: resolvedScope,
    email_message_id: emailMessageId,
    current_mail_only: currentMailOnly,
    shortcut_domain: String(runtimePayload?.shortcut_domain || '').trim().toLowerCase(),
    shortcut_source: String(runtimePayload?.shortcut_source || '').trim().toLowerCase(),
    search_result_limit: normalizedLimit,
    search_sort_mode: normalizeSearchSortMode(runtimePayload?.search_sort_mode || '') || undefined,
    reply_tone: String(runtimePayload?.reply_tone || '').trim().toLowerCase(),
    reply_additional_context: String(runtimePayload?.reply_additional_context || '').trim(),
    force_intent_llm: Boolean(runtimePayload?.force_intent_llm),
    intent_probe: Boolean(runtimePayload?.intent_probe),
    intent_probe_parse_slots: Boolean(runtimePayload?.intent_probe_parse_slots),
    structured_input:
      runtimePayload?.structured_input && typeof runtimePayload.structured_input === 'object'
        ? runtimePayload.structured_input
        : undefined,
    pending_promise_project_number: String(
      runtimePayload?.pending_promise_project_number || ''
    ).trim() || undefined,
  };
}

async function resolveIntentPayloadForMessage(message, runtimePayload = {}, options = {}) {
  const {
    text,
    resolvedScope,
    emailMessageId,
    currentMailOnly,
    resolveTimeoutMs,
  } = resolveIntentRequestBase(message, options);
  if (!text) return null;
  const context = buildIntentResolveContext(
    runtimePayload,
    resolvedScope,
    emailMessageId,
    currentMailOnly
  );
  try {
    const response = await apiFetch('/intents/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        context,
      }),
    }, resolveTimeoutMs);
    if (!response.ok) return null;
    const payload = await response.json().catch(() => null);
    return payload && typeof payload === 'object' ? payload : null;
  } catch (error) {
    logError('intent.resolve.failed', error);
    return null;
  }
}

function buildPrefetchedRouteFromResolvedIntent(intentPayload) {
  if (!intentPayload || typeof intentPayload !== 'object') return null;
  const intentName = String(intentPayload.intent || intentPayload.primary_intent || '')
    .trim()
    .toLowerCase();
  if (!intentName || intentName === 'unknown') return null;

  const uiContract =
    intentPayload.ui_contract && typeof intentPayload.ui_contract === 'object'
      ? { ...intentPayload.ui_contract }
      : null;
  const searchSlots =
    intentPayload.search_slots && typeof intentPayload.search_slots === 'object'
      ? { ...intentPayload.search_slots }
      : null;
  const cardContract =
    intentPayload.card_contract && typeof intentPayload.card_contract === 'object'
      ? { ...intentPayload.card_contract }
      : null;

  const intentDecision = { ...intentPayload };
  delete intentDecision.ui_contract;
  delete intentDecision.search_slots;
  delete intentDecision.card_contract;
  delete intentDecision.router_version;

  const hasIntentPayload = Object.keys(intentDecision).length > 0;
  if (!hasIntentPayload && !uiContract && !searchSlots && !cardContract) {
    return null;
  }

  const prefetched = {};
  if (hasIntentPayload) prefetched.intent_payload = intentDecision;
  if (uiContract) prefetched.ui_contract = uiContract;
  if (searchSlots) prefetched.search_slots = searchSlots;
  if (cardContract) prefetched.card_contract = cardContract;
  return prefetched;
}

function buildStructuredChipSet(plan) {
  if (!plan || !Array.isArray(plan.chips)) return null;
  return new Set(plan.chips.map((item) => String(item || '').trim().toLowerCase()));
}

function resolveCurrentMailWorkflowIntentFromChipSet(chips) {
  if (!chips || !chips.has('current_mail')) return null;
  if (chips.has('schedule')) {
    return { intent: 'schedule_create', uiAction: 'open_schedule_draft' };
  }
  if (chips.has('room')) {
    return { intent: 'room_booking', uiAction: 'open_room_booking' };
  }
  if (chips.has('hr')) {
    return { intent: 'hr_apply', uiAction: 'open_myhr_draft' };
  }
  return null;
}

function buildLocalStructuredWorkflowIntentFromPlan(plan) {
  const chips = buildStructuredChipSet(plan);
  const workflowIntent = resolveCurrentMailWorkflowIntentFromChipSet(chips);
  if (!workflowIntent) return null;

  const rawExtraContext = String(plan?.extraContext || '').trim();
  const prefill = {};
  if (rawExtraContext) {
    prefill.additional_requirement = rawExtraContext;
  }
  const { intent, uiAction } = workflowIntent;

  return {
    intent,
    primary_intent: intent,
    confidence: 0.96,
    needs_clarification: false,
    clarification_tier: 'execute',
    clarification_reason: 'none',
    ui_action: uiAction,
    ui_contract: {
      intent,
      action: uiAction,
    },
    card_contract: {
      intent,
      prefill,
    },
    entities: {},
  };
}

function resolveStructuredWorkflowIntentFromPlan(plan) {
  return resolveCurrentMailWorkflowIntentFromChipSet(buildStructuredChipSet(plan));
}

function resolveIntentName(intentOrPayload) {
  if (typeof intentOrPayload === 'string') return String(intentOrPayload || '').trim().toLowerCase();
  if (!intentOrPayload || typeof intentOrPayload !== 'object') return '';
  return String(intentOrPayload.intent || intentOrPayload.primary_intent || '').trim().toLowerCase();
}

function shouldAutoExecuteStructuredWorkflow(plan, intentOrPayload, rawMessage = '') {
  const chips = buildStructuredChipSet(plan);
  if (!chips) return false;
  if (!chips.has('current_mail')) return false;

  const intent = resolveIntentName(intentOrPayload);
  const verbs = new Set(
    Array.isArray(plan.verbs)
      ? plan.verbs.map((item) => String(item || '').trim().toLowerCase()).filter(Boolean)
      : []
  );
  const extraContext = String(plan?.extraContext || '').trim();
  const text = `${String(rawMessage || '').trim()} ${extraContext}`.trim();
  if (!intent) return false;

  // 카드/폼 열기 의도, 방법 문의성 문장은 자동 실행을 피한다.
  if (/(카드|폼|초안|미리|보여줘|열어줘|입력|수정|가능|어떻게|방법|\?)/i.test(text)) {
    return false;
  }

  if (intent === 'schedule_create' && chips.has('schedule')) {
    if (verbs.has('summary') || verbs.has('register')) return true;
    return /(등록|추가|생성|만들|작성|잡아|예약|넣어|올려|기안)/i.test(text);
  }
  if (intent === 'room_booking' && chips.has('room')) {
    if (verbs.has('summary') || verbs.has('reserve')) return true;
    return /(예약|등록|배정|잡아|신청|만들|넣어|올려)/i.test(text);
  }
  if (intent === 'hr_apply' && chips.has('hr')) {
    if (verbs.has('summary') || verbs.has('write')) return true;
    return /(신청|등록|기안|작성|생성|제출|올려|넣어)/i.test(text);
  }
  return false;
}

function buildLocalMailSearchEntryIntentFromStructuredPlan(plan) {
  if (!plan || !Array.isArray(plan.verbs)) return null;
  const chips = buildStructuredChipSet(plan);
  if (!chips) return null;
  const verbs = new Set(plan.verbs.map((item) => String(item || '').trim().toLowerCase()));
  if (!chips.has('all_mailbox')) return null;
  const isAllMailboxSearchCombo =
    (chips.size === 1 &&
      (verbs.has('search') ||
        verbs.has('summary') ||
        verbs.has('analysis') ||
        verbs.has('todo_extract'))) ||
    (chips.size === 2 && chips.has('todo') && verbs.has('add') && (verbs.has('search') || verbs.has('summary')));
  if (!isAllMailboxSearchCombo) return null;

  const rawExtraContext = String(plan?.extraContext || '').trim();
  const queryPrefill = sanitizeMailSearchEntryQuery(rawExtraContext);
  const resultLimit = extractMailSearchResultLimit(rawExtraContext, { min: 1, max: 20 });
  const parsedSortMode = normalizeSearchSortMode(
    window.__searchQueryUtils?.extractSearchSortMode?.(rawExtraContext) || ''
  );
  const sortMode = parsedSortMode || 'relevance';
  let deliverable = 'list';
  if (verbs.has('analysis')) deliverable = 'analysis';
  else if (verbs.has('summary')) deliverable = 'summary';
  else if (verbs.has('todo_extract') || verbs.has('add')) deliverable = 'actions';
  const normalizedLimit = resultLimit > 0 ? resultLimit : 0;
  const normalizedLimitText = normalizedLimit > 0 ? String(normalizedLimit) : '';
  return {
    intent: 'mail_search',
    primary_intent: 'mail_search',
    confidence: 0.99,
    needs_clarification: false,
    entities: {
      mail_query_prefill: queryPrefill,
      mail_query_raw: rawExtraContext,
      mail_deliverable: deliverable,
      mail_current_mail_only: false,
      mail_result_limit: normalizedLimitText,
      mail_sort_mode: sortMode,
    },
    search_slots: {
      query: queryPrefill,
      sender: '',
      limit: normalizedLimit,
      sort_mode: sortMode,
      current_mail_only: false,
      deliverable,
    },
  };
}

function resolveIntentCardUiAction(intentPayload, quickActionMeta = null, rawMessage = '') {
  if (!intentPayload || typeof intentPayload !== 'object') return '';

  // 상세 카드 컨텍스트의 분석 후속 질의는 ui_action 우선 분기도 우회해야 한다.
  if (pendingPromiseContext?.projectNumber && isPromiseAnalysisQuery(rawMessage, intentPayload)) {
    return '';
  }

  const uiAction = String(intentPayload.ui_action || '').trim().toLowerCase();
  if (!uiAction) return '';
  if (uiAction === 'open_reply_tone_picker' && toBool(quickActionMeta?.skipReplyToneIntercept)) {
    return '';
  }
  if (uiAction === 'open_promise_menu' && isPromiseAnalysisQuery(rawMessage, intentPayload)) {
    return 'open_promise_projects';
  }
  return uiAction;
}

function normalizeSearchSortMode(value) {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'recent') return 'recent';
  if (normalized === 'oldest') return 'oldest';
  if (normalized === 'relevance') return 'relevance';
  return '';
}

function sanitizeMailSearchEntryQuery(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const sanitizer =
    typeof window.__searchQueryUtils?.sanitizeSearchPrefillQuery === 'function'
      ? window.__searchQueryUtils.sanitizeSearchPrefillQuery
      : null;
  if (!sanitizer) return raw;
  const sanitized = String(sanitizer(raw) || '').trim();
  return sanitized || raw;
}

function extractMailSearchResultLimit(value, { min = 1, max = 20 } = {}) {
  const raw = String(value || '').trim();
  if (!raw) return 0;

  const utilExtractor = window.__searchQueryUtils?.extractSearchResultLimit;
  if (typeof utilExtractor === 'function') {
    const parsed = Number(utilExtractor(raw, { min, max }) || 0);
    if (Number.isFinite(parsed) && parsed > 0) {
      return Math.max(min, Math.min(parsed, max));
    }
  }

  const match = raw.match(/(?:최대\s*)?(\d+)\s*(?:개|건)\s*(?:만)?/i);
  if (!match || !match[1]) return 0;
  const parsed = Number.parseInt(match[1], 10);
  if (!Number.isFinite(parsed) || parsed <= 0) return 0;
  return Math.max(min, Math.min(parsed, max));
}

  const api = {
    containsAnyToken,
    normalizeAssistantPrompt,
    hasRecentFollowupContext,
    isExplicitSmalltalkPrompt,
    isFollowupRefinePrompt,
    classifyTurnKind,
    isLikelyMailSearchRequest,
    shouldShowThinkingProgress,
    isRoomLookupFastPath,
    isHrLookupFastPath,
    isScheduleLookupFastPath,
    isTodoLookupFastPath,
    hasPromiseTimeSliceToken,
    hasPromiseAnalysisKeyword,
    hasPromiseDomainKeyword,
    hasPromiseMailSignal,
    hasPromiseBudgetSignal,
    isPromiseAnalysisFollowUpContext,
    isPromiseAnalysisQuery,
    enrichPromiseAnalysisMessage,
    openMockupWindow,
    resolveRequestTimeoutMeta,
    buildChatRequestContext,
    logChatRequestStart,
    logChatRequestOutcome,
    logChatRequestFailure,
    requestChat,
    logChatStreamRequestStart,
    logChatStreamSuccess,
    logChatStreamFailure,
    requestChatStream,
    buildAssistantActionButtonsHtml,
    buildAssistantActionCardHtml,
    bindAssistantActionCardEvents,
    finalizeAssistantActionCard,
    addAssistantActionCard,
    formatKrw,
    removeWorkflowCards,
    resolveIntentRequestBase,
    buildIntentResolveContext,
    resolveIntentPayloadForMessage,
    buildPrefetchedRouteFromResolvedIntent,
    buildStructuredChipSet,
    resolveCurrentMailWorkflowIntentFromChipSet,
    buildLocalStructuredWorkflowIntentFromPlan,
    resolveStructuredWorkflowIntentFromPlan,
    resolveIntentName,
    shouldAutoExecuteStructuredWorkflow,
    buildLocalMailSearchEntryIntentFromStructuredPlan,
    resolveIntentCardUiAction,
    normalizeSearchSortMode,
    sanitizeMailSearchEntryQuery,
    extractMailSearchResultLimit,
  };

  global.TaskpaneIntentUtils = {
    ...(global.TaskpaneIntentUtils || {}),
    ...api,
  };

  Object.assign(global, api);
})(window);
