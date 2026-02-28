/* ========================================
   MolduBot - Mail Open Utils
   ======================================== */

(function initTaskpaneMailOpenUtils(global) {
function isLikelyEmailNotFoundAnswer(content) {
  const raw = normalizeAssistantTextForParsing(content).trim();
  if (!raw) return false;
  return EMAIL_NOT_FOUND_PATTERNS.some((pattern) => pattern.test(raw));
}

function buildOpenMailItemListHtml(items = []) {
  return items
    .map(
      (item, index) => `
              <li class="mail-open-inline-item">
                <a href="#" class="mail-open-item-link" data-message-id="${escapeAttr(item.messageId)}" data-item-index="${index}">
                  ${escapeHtml(item.subject || '(제목 없음)')}
                </a>
              </li>`
    )
    .join('');
}

async function handleOpenMailItemClick(buttonEl) {
  const messageId = String(buttonEl?.getAttribute('data-message-id') || '').trim();
  if (!messageId || !buttonEl) return;
  const originalText = buttonEl.textContent || '';
  buttonEl.dataset.busy = 'true';
  buttonEl.textContent = 'Opening...';

  try {
    await openMessageNative(messageId);
  } catch (error) {
    logError('mail.open_native.failed', error, {
      message_id_prefix: messageId.slice(0, 24),
    });
    const detail = [error?.message, error?.code].filter(Boolean).join(' | ');
    addSystemMessage(
      `메일 열기에 실패했습니다. Outlook 항목을 다시 선택한 뒤 재시도해주세요.${
        detail ? ` (${detail})` : ''
      }`
    );
  } finally {
    buttonEl.dataset.busy = '';
    buttonEl.textContent = originalText || '메일 열기';
  }
}

function bindOpenMailItemActions(card) {
  if (!card) return;
  card.querySelectorAll('.mail-open-item-link').forEach((buttonEl) => {
    buttonEl.addEventListener('click', (event) => {
      event.preventDefault();
      void handleOpenMailItemClick(buttonEl);
    });
  });
}

function attachNativeOpenMailList(container, text, prebuiltItems = null) {
  const items = Array.isArray(prebuiltItems)
    ? prebuiltItems
    : extractOpenableMailItems(text);
  logEvent('mail.open_list.parsed', 'ok', { count: items.length });
  if (!items.length) return;

  const html = `
    <div class="mail-open-inline-results">
      <div>관련 메일 (${items.length})</div>
      <ul>
        ${buildOpenMailItemListHtml(items)}
      </ul>
    </div>
  `;

  container.insertAdjacentHTML('beforeend', html);
  const card = container.lastElementChild;
  if (!card) return;
  bindOpenMailItemActions(card);
}

function isValidOpenableMessageId(messageId) {
  const value = String(messageId || '').trim();
  if (!value) return false;
  if (/redacted|sensitive_data|\[.*redacted.*\]/i.test(value)) return false;
  return value.length >= 16;
}

function extractInlineOpenableMailItems(source) {
  const items = [];
  const inlinePattern =
    /제목:\s*(.*?)\s+발신자:\s*(.*?)\s+날짜:\s*(.*?)\s+메일\s*ID:\s*([A-Za-z0-9_\-=%+/]+)|제목:\s*(.*?)\s+발신자:\s*(.*?)\s+날짜:\s*(.*?)\s+메일ID:\s*([A-Za-z0-9_\-=%+/]+)/g;
  let matched = null;
  while ((matched = inlinePattern.exec(source)) !== null) {
    const messageId = String(matched[4] || matched[8] || '').trim();
    if (!isValidOpenableMessageId(messageId)) continue;
    items.push({
      subject: String(matched[1] || matched[5] || '').trim(),
      from: String(matched[2] || matched[6] || '').trim(),
      date: String(matched[3] || matched[7] || '').trim(),
      messageId,
    });
  }
  return items;
}

function buildCommittedOpenableMailItem(current) {
  if (!isValidOpenableMessageId(current?.messageId || '')) return null;
  return {
    subject: String(current.subject || '').trim(),
    from: String(current.from || '').trim(),
    date: String(current.date || '').trim(),
    messageId: String(current.messageId || '').trim(),
  };
}

function applyOpenableLineField(current, line) {
  if (!current) return false;
  if (line.startsWith('발신자:')) {
    current.from = line.slice(4).trim();
    return true;
  }
  if (line.startsWith('날짜:')) {
    current.date = line.slice(3).trim();
    return true;
  }
  if (line.startsWith('메일ID:')) {
    current.messageId = line.slice(5).trim();
    return true;
  }
  if (line.startsWith('메일 ID:')) {
    current.messageId = line.slice(6).trim();
    return true;
  }
  if (line.toLowerCase().startsWith('mail id:')) {
    current.messageId = line.slice(8).trim();
    return true;
  }
  return false;
}

function extractLineOpenableMailItems(source) {
  const items = [];
  const lines = source.split(/\r?\n/);
  let current = null;

  const commit = () => {
    const item = buildCommittedOpenableMailItem(current);
    if (item) items.push(item);
    current = null;
  };

  for (const raw of lines) {
    const line = normalizeResultLine(raw);
    if (!line) continue;
    if (line.startsWith('제목:')) {
      commit();
      current = { subject: line.slice(3).trim(), from: '', date: '', messageId: '' };
      continue;
    }
    if (applyOpenableLineField(current, line)) continue;
    if (line.startsWith('---')) {
      commit();
    }
  }

  commit();
  return items;
}

function extractOpenableMailItems(text) {
  const source = String(text || '');
  if (!source) return [];
  const inlineItems = extractInlineOpenableMailItems(source);
  if (inlineItems.length) return sanitizeOpenableMailItems(inlineItems);
  return sanitizeOpenableMailItems(extractLineOpenableMailItems(source));
}

function sanitizeOpenableMailItems(items) {
  if (!Array.isArray(items)) return [];

  const unique = new Map();
  for (const sourceItem of items) {
    if (!sourceItem || typeof sourceItem !== 'object') continue;
    const messageId = String(sourceItem.messageId || '').trim();
    if (!messageId) continue;
    if (
      /redacted|sensitive_data|\[.*redacted.*\]/i.test(messageId) ||
      messageId.length < 16
    ) {
      continue;
    }
    if (!unique.has(messageId)) {
      unique.set(messageId, {
        subject: String(sourceItem.subject || '').trim(),
        from: String(sourceItem.from || '').trim(),
        date: String(sourceItem.date || '').trim(),
        messageId,
      });
    }
  }
  return Array.from(unique.values()).slice(0, 8);
}

function isMailOpenableToolEntry(tool) {
  if (!tool || typeof tool !== 'object') return false;
  if (String(tool?.result_type || '').trim().toLowerCase() === 'mail_search_results') {
    return true;
  }
  const name = String(tool?.name || '').trim().toLowerCase();
  return name === 'search_emails' || name === 'task';
}

function extractOpenableMailItemsFromMetadata(metadata) {
  try {
    const direct = sanitizeOpenableMailItems(
      metadata?.openable_items || metadata?.openableItems || metadata?.mail_openable_items
    );
    if (direct.length) return direct;

    const workflow = metadata?.workflow;
    if (!Array.isArray(workflow)) return [];

    const merged = new Map();
    for (const step of workflow) {
      const tools = step?.tools;
      if (!Array.isArray(tools)) continue;

      for (const tool of tools) {
        if (!isMailOpenableToolEntry(tool)) continue;
        const prebuilt = sanitizeOpenableMailItems(tool?.openable_items);
        if (prebuilt.length) {
          for (const item of prebuilt) {
            const key = String(item?.messageId || '').trim();
            if (!key) continue;
            if (!merged.has(key)) merged.set(key, item);
          }
          continue;
        }
      }
    }

    return sanitizeOpenableMailItems(Array.from(merged.values()));
  } catch (error) {
    logError('metadata.mail_result.parse_failed', error);
    return [];
  }
}

function isReplyDraftRequest(userMessage) {
  const text = String(userMessage || '').toLowerCase().trim();
  if (!text) return false;
  const hasReplyIntent =
    /답변\s*(초안|작성|해줘|생성|부탁)/.test(text) ||
    /답장\s*(초안|작성|해줘|생성|부탁)/.test(text) ||
    /회신\s*(초안|작성|해줘|생성|부탁)/.test(text) ||
    text.includes('reply');
  if (!hasReplyIntent) return false;

  if (/답변은\s*반드시|번호\s*형식/.test(text)) return false;
  return true;
}

function attachReplyComposerAction(container, draftText) {
  const content = String(draftText || '').trim();
  if (!content) return;

  const actionId = `reply_action_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
  const actionHtml = `
    <div class="msg-action-row" id="${actionId}">
      <button class="msg-action-btn" type="button">
        ${ICONS.reply} 답장 창 열기
      </button>
    </div>
  `;
  container.insertAdjacentHTML('beforeend', actionHtml);
  const row = document.getElementById(actionId);
  const button = row?.querySelector('.msg-action-btn');
  if (!button) return;

  button.addEventListener('click', () => {
    const originalHtml = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `${ICONS.clock} 여는 중...`;

    try {
      openReplyComposerWithDraft(content);
      button.innerHTML = `${ICONS.check} 열림`;
      window.setTimeout(() => {
        button.disabled = false;
        button.innerHTML = originalHtml;
      }, 1500);
    } catch (error) {
      logError('mail.reply_compose.open_failed', error);
      button.disabled = false;
      button.innerHTML = originalHtml;
      addSystemMessage('답장 창을 열지 못했습니다. 메일 읽기 화면에서 다시 시도해주세요.');
    }
  });
}

function attachRestartSessionAction(container) {
  const actionId = `restart_action_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
  const actionHtml = `
    <div class="msg-action-row msg-action-row-restart" id="${actionId}">
      <button class="msg-action-link msg-action-link-retry" type="button">
        ${ICONS.refreshCw} 다시 시도
      </button>
    </div>
  `;
  container.insertAdjacentHTML('beforeend', actionHtml);
  const row = document.getElementById(actionId);
  const button = row?.querySelector('.msg-action-link');
  if (!button) return;
  button.addEventListener('click', () => {
    if (isProcessing) return;
    const retryMessage = getLatestUserMessageText();
    if (!retryMessage) {
      addSystemMessage('재시도할 요청을 찾지 못했습니다.');
      return;
    }
    const input = document.getElementById('chatInput');
    if (input) {
      input.value = retryMessage;
      autoResize(input);
    }
    logEvent('ui.chat.retry_from_assistant', 'ok', {
      source: 'assistant_retry_action',
      message_len: retryMessage.length,
    });
    if (typeof sendMessage === 'function') {
      sendMessage();
      return;
    }
    if (typeof dispatchAssistantWorkflowMessage === 'function') {
      addUserMessage(retryMessage);
      void dispatchAssistantWorkflowMessage(retryMessage);
      return;
    }
    addSystemMessage('재시도 기능을 사용할 수 없습니다.');
  });
}

function openReplyComposerWithDraft(draftText) {
  const mailbox = Office?.context?.mailbox;
  const item = mailbox?.item;
  if (!mailbox || !item) {
    throw new Error('mailbox item unavailable');
  }

  const htmlBody = buildReplyHtmlBody(sanitizeReplyDraftForSend(draftText));

  // Priority 1: native reply for currently selected message (keeps thread context).
  if (typeof item.displayReplyForm === 'function') {
    item.displayReplyForm(htmlBody);
    return;
  }

  // Fallback: reply all if only this API is available.
  if (typeof item.displayReplyAllForm === 'function') {
    item.displayReplyAllForm(htmlBody);
    return;
  }

  // Last fallback: new compose (thread context won't be preserved).
  if (typeof mailbox.displayNewMessageForm === 'function') {
    mailbox.displayNewMessageForm({ htmlBody });
    return;
  }

  throw new Error('reply compose API unavailable');
}

function buildReplyHtmlBody(text) {
  const normalized = String(text || '').trim();
  const rendered = renderMarkdown(normalized || '답변 초안');
  return `
    <div style="font-family:'Segoe UI',Arial,sans-serif;font-size:14px;line-height:1.6;color:#1f2937;">
      ${rendered}
    </div>
    <br/>
  `;
}

function stripReplyMarkdownFences(text) {
  return String(text || '').replace(/^```[a-zA-Z]*\n?/g, '').replace(/\n?```$/g, '').trim();
}

function unwrapReplyDraftSections(text) {
  const parts = String(text || '')
    .split(/\n-{3,}\n/g)
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length >= 2) return parts[1] || parts[0];
  return String(text || '').trim();
}

function stripReplyDraftMetaLines(text) {
  return String(text || '')
    .replace(/^\s*(다음은|아래는).*(답변|회신|초안).*(입니다\.?)\s*\n+/i, '')
    .replace(/^\s*(요청하신|요청하신 내용의).*(초안).*(입니다\.?)\s*\n+/i, '')
    .replace(/\n*\s*이 초안을 바탕으로.*$/is, '')
    .replace(/\n*\s*추가(적인)?\s*(수정|보완|문의).*(말씀|연락).*(주세요|바랍니다).*$/is, '')
    .trim();
}

function filterReplyDraftBodyLines(text) {
  const lines = String(text || '')
    .split('\n')
    .map((line) => String(line || '').trimEnd());
  const filtered = [];
  for (const rawLine of lines) {
    const line = String(rawLine || '').trim();
    if (!line) {
      filtered.push('');
      continue;
    }
    if (/^(?:\d+[\.\)]\s*)?(?:제목|subject)\s*[:：]/i.test(line)) continue;
    if (/^(?:\d+[\.\)]\s*)?(?:답변\s*초안|회신\s*초안|본문)\s*(?:\([^)]*\))?\s*[:：]?$/i.test(line)) continue;
    if (/^(?:다음은|아래는).*(?:답변|회신|초안).*(?:입니다\.?)?$/i.test(line)) continue;
    filtered.push(rawLine);
  }
  return filtered.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}

function finalizeReplyDraftText(text) {
  return String(text || '')
    .replace(/^\s*-{3,}\s*$/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function sanitizeReplyDraftForSend(text) {
  let draft = String(text || '').replace(/\r\n/g, '\n').trim();
  if (!draft) return '';

  draft = stripReplyMarkdownFences(draft);
  draft = unwrapReplyDraftSections(draft);
  draft = stripReplyDraftMetaLines(draft);
  draft = filterReplyDraftBodyLines(draft);
  return finalizeReplyDraftText(draft);
}

function normalizeResultLine(line) {
  const trimmed = String(line || '').trim();
  if (!trimmed) return '';
  return trimmed
    .replace(/^[-*]\s+/, '')
    .replace(/^\d+\.\s+/, '')
    .trim();
}

function safeDecodeUriComponent(value) {
  try {
    return decodeURIComponent(value);
  } catch (error) {
    void error;
    return value;
  }
}

function safeEncodeUriComponent(value) {
  try {
    return encodeURIComponent(value);
  } catch (error) {
    void error;
    return value;
  }
}

function addOpenIdVariant(variants, value) {
  const normalized = String(value || '').trim();
  if (!normalized) return;
  variants.add(normalized);
}

function addBase64StyleOpenIdVariants(variants, value) {
  const text = String(value || '').trim();
  if (!text) return;

  const withPadding = (source) => {
    const normalized = String(source || '').replace(/=+$/g, '');
    const mod = normalized.length % 4;
    if (mod === 0) return normalized;
    return normalized + '='.repeat(4 - mod);
  };

  addOpenIdVariant(variants, text);
  const standard = text.replace(/-/g, '+').replace(/_/g, '/');
  const urlSafe = text.replace(/\+/g, '-').replace(/\//g, '_');
  addOpenIdVariant(variants, standard);
  addOpenIdVariant(variants, urlSafe);
  addOpenIdVariant(variants, standard.replace(/=+$/g, ''));
  addOpenIdVariant(variants, urlSafe.replace(/=+$/g, ''));
  addOpenIdVariant(variants, withPadding(standard));
  addOpenIdVariant(variants, withPadding(urlSafe));
}

function buildOpenIdVariants(value) {
  const raw = String(value || '').trim();
  if (!raw) return [];

  const variants = new Set();
  addOpenIdVariant(variants, raw);
  const decoded = safeDecodeUriComponent(raw);
  addOpenIdVariant(variants, decoded);
  addOpenIdVariant(variants, safeEncodeUriComponent(raw));
  addOpenIdVariant(variants, safeEncodeUriComponent(decoded));
  addBase64StyleOpenIdVariants(variants, raw);
  addBase64StyleOpenIdVariants(variants, decoded);

  return Array.from(variants);
}

function appendConvertedOpenMessageCandidates(mailbox, targetVariants, ewsVariants, pushCandidate) {
  try {
    const restV1 = Office?.MailboxEnums?.RestVersion?.v1_0;
    const restV2 = Office?.MailboxEnums?.RestVersion?.v2_0;
    if (restV1 && typeof mailbox.convertToEwsId === 'function') {
      for (const variant of targetVariants) {
        pushCandidate(mailbox.convertToEwsId(variant, restV1));
      }
    }
    if (restV2 && typeof mailbox.convertToEwsId === 'function') {
      for (const variant of targetVariants) {
        pushCandidate(mailbox.convertToEwsId(variant, restV2));
      }
    }
    if (restV1 && typeof mailbox.convertToRestId === 'function') {
      for (const variant of [...targetVariants, ...ewsVariants]) {
        pushCandidate(mailbox.convertToRestId(variant, restV1));
      }
    }
    if (restV2 && typeof mailbox.convertToRestId === 'function') {
      for (const variant of [...targetVariants, ...ewsVariants]) {
        pushCandidate(mailbox.convertToRestId(variant, restV2));
      }
    }
  } catch (error) {
    logError('mail.open_id_variants.convert_failed', error);
  }
}

function buildOpenMessageCandidates(mailbox, { targetId = '', ewsId = '', internetMessageId = '' } = {}) {
  const candidates = [];
  const pushCandidate = (value) => {
    const id = String(value || '').trim();
    if (!id) return;
    if (!candidates.includes(id)) candidates.push(id);
  };
  const targetVariants = buildOpenIdVariants(targetId);
  const ewsVariants = buildOpenIdVariants(ewsId);
  const internetVariants = buildOpenIdVariants(internetMessageId);
  ewsVariants.forEach(pushCandidate);
  targetVariants.forEach(pushCandidate);
  internetVariants.forEach(pushCandidate);
  appendConvertedOpenMessageCandidates(mailbox, targetVariants, ewsVariants, pushCandidate);
  return candidates;
}

async function tryOpenMessageCandidates(candidates = []) {
  let lastError = null;
  for (const candidate of candidates) {
    try {
      await displayMessageForm(candidate);
      logEvent('mail.open_native.success', 'ok', {
        candidate_prefix: String(candidate || '').slice(0, 40),
      });
      return null;
    } catch (error) {
      logError('mail.open_native.candidate_failed', error, {
        candidate: String(candidate || '').slice(0, 40),
        code: error?.code,
        name: error?.name,
        message: error?.message,
      });
      lastError = error;
    }
  }
  return lastError;
}

async function openMessageNative(messageId) {
  const resolved = await resolveOpenMessageTarget(messageId);
  const targetId = resolved?.messageId || messageId;
  const webLink = resolved?.webLink || '';
  const ewsId = resolved?.ewsId || '';
  const internetMessageId = resolved?.internetMessageId || '';

  const mailbox = Office?.context?.mailbox;
  if (!mailbox) {
    if (ENABLE_WEB_OPEN_FALLBACK && webLink) {
      window.open(webLink, '_blank', 'noopener,noreferrer');
      return;
    }
    throw new Error('Mailbox API unavailable');
  }

  const candidates = buildOpenMessageCandidates(mailbox, {
    targetId,
    ewsId,
    internetMessageId,
  });

  logEvent('mail.open_native.candidates', 'ok', {
    count: candidates.length,
    sample: candidates.slice(0, 5).map((c) => `${String(c).slice(0, 28)}...`),
  });
  const lastError = await tryOpenMessageCandidates(candidates);
  if (!lastError) return;

  if (ENABLE_WEB_OPEN_FALLBACK && webLink) {
    try {
      window.open(webLink, '_blank', 'noopener,noreferrer');
      return;
    } catch (error) {
      logError('mail.open_native.web_fallback_failed', error, {
        link_prefix: String(webLink || '').slice(0, 64),
      });
    }
  }

  throw lastError || new Error('open failed');
}

async function resolveOpenMessageTarget(messageId) {
  const raw = String(messageId || '').trim();
  if (!raw) return { messageId: '', webLink: '', ewsId: '', internetMessageId: '' };
  try {
    const response = await apiFetch('/search/id', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: raw }),
    });
    if (!response.ok) {
      return { messageId: raw, webLink: '', ewsId: '', internetMessageId: '' };
    }
    const data = await response.json().catch(() => ({}));
    if (!data?.found) {
      return { messageId: raw, webLink: '', ewsId: '', internetMessageId: '' };
    }
    return {
      messageId: String(data.open_message_id || data.message_id || raw).trim(),
      webLink: String(data.web_link || data?.summary?.web_link || '').trim(),
      ewsId: String(data.ews_id || '').trim(),
      internetMessageId: String(data.internet_message_id || '').trim(),
    };
  } catch (error) {
    logError('mail.open_target.resolve_failed', error);
    return { messageId: raw, webLink: '', ewsId: '', internetMessageId: '' };
  }
}

function displayMessageForm(itemId) {
  const mailbox = Office?.context?.mailbox;
  if (!mailbox) {
    return Promise.reject(new Error('Mailbox API unavailable'));
  }

  return new Promise((resolve, reject) => {
    // Sync API 우선: 일부 클라이언트에서 Async 경로만 7000으로 실패하는 사례 회피
    if (typeof mailbox.displayMessageForm === 'function') {
      try {
        mailbox.displayMessageForm(itemId);
        resolve();
        return;
      } catch (error) {
        logError('mail.display_form.sync_failed', error, {
          message: error?.message,
          code: error?.code,
        });
      }
    }

    if (typeof mailbox.displayMessageFormAsync === 'function') {
      mailbox.displayMessageFormAsync(itemId, (result) => {
        if (result?.status === Office.AsyncResultStatus.Succeeded) {
          resolve();
          return;
        }
        const error = result?.error || {};
        const detail = new Error(
          `displayMessageFormAsync failed: ${error.message || 'unknown'} (code=${error.code || 'n/a'})`
        );
        detail.code = error.code;
        detail.diagnostics = result?.diagnostics;
        reject(detail);
      });
      return;
    }

    reject(new Error('displayMessageForm API unavailable'));
  });
}

function maskSensitiveLongTokens(text) {
  const source = String(text || '');
  if (!source) return '';
  return source
    .replace(
      /((?:메일\s*ID|message[\s_-]*id|internet[\s_-]*message[\s_-]*id|id)\s*[:：]\s*)([A-Za-z0-9+/_=-]{16,})/gi,
      '$1[REDACTED]'
    )
    .replace(/([A-Za-z0-9+/_=-]{64,})/g, '[REDACTED]');
}

function compactDisplayText(value, maxChars = 160) {
  const normalized = String(value || '')
    .replace(/\\[nrt]/g, ' ')
    .replace(/\[메일\s*컨텍스트\]/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!normalized) return '';
  if (normalized.length <= maxChars) return normalized;
  return `${normalized.slice(0, maxChars)}...`;
}

function formatArgValue(key, value) {
  const normalizedKey = String(key || '').toLowerCase();
  if ((normalizedKey.includes('time') || normalizedKey.includes('date')) && typeof value === 'string') {
    try {
      const d = new Date(value);
      if (!isNaN(d.getTime())) {
        return d.toLocaleString('ko-KR', {
          year: 'numeric',
          month: 'long',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
        });
      }
    } catch (error) {
      void error;
      // fall through
    }
  }
  if (typeof value === 'object') {
    try {
      return compactDisplayText(JSON.stringify(value), 180);
    } catch (error) {
      void error;
      return compactDisplayText(String(value), 180);
    }
  }
  let text = String(value ?? '');
  if (normalizedKey === 'body' || normalizedKey === 'description' || normalizedKey === 'note') {
    text = text.replace(/\\[nrt]/g, ' ').replace(/\[메일\s*컨텍스트\]/gi, ' ');
    text = maskSensitiveLongTokens(text);
    return compactDisplayText(text, 120);
  }
  if (normalizedKey.includes('id')) {
    text = maskSensitiveLongTokens(text);
    return compactDisplayText(text, 32);
  }
  return compactDisplayText(text, 110);
}

function toRestId(itemId) {
  if (!itemId) return '';
  try {
    const mailbox = Office?.context?.mailbox;
    const restVersion = Office?.MailboxEnums?.RestVersion?.v2_0;
    if (mailbox && restVersion && typeof mailbox.convertToRestId === 'function') {
      return mailbox.convertToRestId(itemId, restVersion) || itemId;
    }
  } catch (error) {
    logError('mail.id.convert_to_rest.failed', error);
  }
  return itemId;
}

function collectEmailContextIdCandidates(context) {
  if (!context || typeof context !== 'object') return [];
  const candidates = [];
  const pushCandidate = (v) => {
    const value = String(v || '').trim();
    if (!value || candidates.includes(value)) return;
    candidates.push(value);
  };
  pushCandidate(context.restItemId);
  pushCandidate(context.itemId);
  return candidates;
}

async function lookupEmailMessageIdByCandidate(id) {
  const response = await apiFetch('/search/id', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  });
  const data = response.ok ? await response.json().catch(() => ({})) : null;
  return {
    ok: response.ok,
    status: Number(response.status || 0),
    data: data && typeof data === 'object' ? data : {},
  };
}

function applyResolvedEmailContextFromLookup(data) {
  emailContext.resolvedMessageId = data.message_id;
  emailContext.resolvedBy = data.resolved_by || 'unknown';
  logEvent('mail.id.resolve.success', 'ok', {
    resolved_by: emailContext.resolvedBy,
    resolved_prefix: emailContext.resolvedMessageId.slice(0, 40),
  });
  return emailContext.resolvedMessageId;
}

async function resolveEmailContextId() {
  if (!emailContext) return null;
  if (emailContext.resolvedMessageId) return emailContext.resolvedMessageId;
  if (pendingEmailIdResolve) return pendingEmailIdResolve;

  const candidates = collectEmailContextIdCandidates(emailContext);
  if (!candidates.length) return null;

  pendingEmailIdResolve = (async () => {
    for (const id of candidates) {
      try {
        const lookup = await lookupEmailMessageIdByCandidate(id);
        if (!lookup.ok) continue;
        if (lookup.data?.found && lookup.data?.message_id) {
          return applyResolvedEmailContextFromLookup(lookup.data);
        }
      } catch (error) {
        logError('mail.id.resolve.failed', error);
      }
    }
    return null;
  })();

  try {
    return await pendingEmailIdResolve;
  } finally {
    pendingEmailIdResolve = null;
  }
}

async function ensureResolvedEmailId() {
  if (!emailContext) return null;
  if (emailContext.resolvedMessageId) return emailContext.resolvedMessageId;
  const resolved = await resolveEmailContextId();
  if (resolved) return resolved;
  return emailContext.restItemId || emailContext.itemId || null;
}

async function forceRefreshResolvedEmailId() {
  if (!emailContext) return null;
  emailContext.resolvedMessageId = null;
  emailContext.resolvedBy = null;
  pendingEmailIdResolve = null;
  lastAutoBootstrapContextKey = '';
  await runAutoEmailBootstrap();
  return resolveEmailContextId();
}

async function runAutoEmailBootstrap() {
  if (!emailContext) return;

  const contextKey = emailContext.restItemId || emailContext.itemId || '';
  if (!contextKey) {
    logEvent('mail.bootstrap.skipped', 'warn', { reason: 'no_context_id' });
    return;
  }
  if (lastAutoBootstrapContextKey === contextKey) {
    return;
  }
  lastAutoBootstrapContextKey = contextKey;

  try {
    const lookupId = (await ensureResolvedEmailId()) || contextKey;
    const lookup = await lookupEmailMessageIdByCandidate(lookupId);
    if (!lookup.ok) {
      logEvent('mail.bootstrap.http_error', 'warn', { status_code: lookup.status });
      return;
    }
    const data = lookup.data;
    logEvent('mail.bootstrap.result', 'ok', {
      found: Boolean(data?.found),
      resolvedBy: data?.resolved_by || null,
      hasMessageId: Boolean(data?.message_id),
    });

    if (data?.found && data?.message_id) {
      emailContext.resolvedMessageId = data.message_id;
      emailContext.resolvedBy = data.resolved_by || emailContext.resolvedBy;
    }
  } catch (error) {
    logError('mail.bootstrap.failed', error);
  }
}

  const api = {
    isLikelyEmailNotFoundAnswer,
    buildOpenMailItemListHtml,
    handleOpenMailItemClick,
    bindOpenMailItemActions,
    attachNativeOpenMailList,
    isValidOpenableMessageId,
    extractInlineOpenableMailItems,
    buildCommittedOpenableMailItem,
    applyOpenableLineField,
    extractLineOpenableMailItems,
    extractOpenableMailItems,
    sanitizeOpenableMailItems,
    isMailOpenableToolEntry,
    extractOpenableMailItemsFromMetadata,
    isReplyDraftRequest,
    attachReplyComposerAction,
    attachRestartSessionAction,
    openReplyComposerWithDraft,
    buildReplyHtmlBody,
    stripReplyMarkdownFences,
    unwrapReplyDraftSections,
    stripReplyDraftMetaLines,
    filterReplyDraftBodyLines,
    finalizeReplyDraftText,
    sanitizeReplyDraftForSend,
    normalizeResultLine,
    safeDecodeUriComponent,
    safeEncodeUriComponent,
    addOpenIdVariant,
    addBase64StyleOpenIdVariants,
    buildOpenIdVariants,
    appendConvertedOpenMessageCandidates,
    buildOpenMessageCandidates,
    tryOpenMessageCandidates,
    openMessageNative,
    resolveOpenMessageTarget,
    displayMessageForm,
    maskSensitiveLongTokens,
    compactDisplayText,
    formatArgValue,
    toRestId,
    collectEmailContextIdCandidates,
    lookupEmailMessageIdByCandidate,
    applyResolvedEmailContextFromLookup,
    resolveEmailContextId,
    ensureResolvedEmailId,
    forceRefreshResolvedEmailId,
    runAutoEmailBootstrap,
  };

  global.TaskpaneMailOpenUtils = {
    ...(global.TaskpaneMailOpenUtils || {}),
    ...api,
  };

  Object.assign(global, api);
})(window);
