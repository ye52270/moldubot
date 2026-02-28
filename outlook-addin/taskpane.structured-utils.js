(function attachTaskpaneStructuredUtils(globalThis) {
  const SCOPE_VALUES = new Set(['email', 'all', 'systems']);
  const SCOPE_SHORTCUTS = [
    {
      scope: 'email',
      token: '@현재메일',
      label: '이 메일',
      aliases: ['현재 메일', '현재메일', '이 메일', 'email'],
      hint: '현재 메일 기준',
    },
    {
      scope: 'all',
      token: '@전체사서함',
      label: '전체 사서함',
      aliases: ['전체사서함', '전체 사서함', 'all'],
      hint: '전체 사서함 검색',
    },
    {
      scope: 'systems',
      token: '@회의실',
      label: '회의실',
      aliases: ['회의실', '미팅룸'],
      hint: '업무 시스템 액션',
    },
    {
      scope: 'systems',
      token: '@캘린더',
      label: '일정',
      aliases: ['캘린더', '일정', '스케줄'],
      hint: '업무 시스템 액션',
    },
    {
      scope: 'systems',
      token: '@일정',
      label: '일정',
      aliases: ['일정', '캘린더', '스케줄'],
      hint: '업무 시스템 액션',
    },
    {
      scope: 'systems',
      token: '@할일',
      label: '할 일',
      aliases: ['할일', '할 일', 'todo'],
      hint: '업무 시스템 액션',
    },
    {
      scope: 'all',
      token: '@자연어',
      label: '자연어',
      aliases: ['자연어', 'nl', 'intent'],
      hint: '의도 분류 테스트',
    },
    {
      scope: 'systems',
      token: '@근태',
      label: '근태',
      aliases: ['근태', '휴가', '승인'],
      hint: '업무 시스템 액션',
    },
    {
      scope: 'systems',
      token: '@실행예산',
      label: '실행예산',
      aliases: ['실행예산', '예산', 'promise'],
      hint: '업무 시스템 액션',
    },
    {
      scope: 'systems',
      token: '@비용정산',
      label: '비용정산',
      aliases: ['비용정산', '경비정산', 'finance'],
      hint: '업무 시스템 액션',
    },
  ];
  const STRUCTURED_CHIP_DEFS = [
    { id: 'current_mail', token: '@현재메일', aliases: ['@현재메일', '@현재 메일', '@이메일', '@현재'] },
    { id: 'all_mailbox', token: '@전체사서함', aliases: ['@전체사서함', '@전체 사서함', '@all'] },
    { id: 'room', token: '@회의실', aliases: ['@회의실', '@미팅룸'] },
    { id: 'schedule', token: '@일정', aliases: ['@일정', '@캘린더', '@스케줄'] },
    { id: 'todo', token: '@할일', aliases: ['@할일', '@할 일', '@todo'] },
    { id: 'hr', token: '@근태', aliases: ['@근태', '@휴가', '@연차'] },
    { id: 'promise', token: '@실행예산', aliases: ['@실행예산', '@예산', '@promise'] },
    { id: 'finance', token: '@비용정산', aliases: ['@비용정산', '@경비정산', '@finance'] },
  ];
  const STRUCTURED_VERB_DEFS = [
    { id: 'summary', token: '/요약', aliases: ['요약', '요약해줘', 'summary'] },
    { id: 'analysis', token: '/분석', aliases: ['분석', '분석해줘', 'analysis'] },
    { id: 'reply', token: '/답장', aliases: ['답장', '답장해줘', '답변', 'reply'] },
    { id: 'translate', token: '/번역', aliases: ['번역', '번역해줘', 'translate'] },
    { id: 'todo_extract', token: '/할일추출', aliases: ['할일추출', '할 일 추출', 'todo추출', '액션추출', '액션 추출'] },
    { id: 'add', token: '/추가', aliases: ['추가', '생성', 'add'] },
    { id: 'register', token: '/등록', aliases: ['등록', '생성', 'create'] },
    { id: 'reserve', token: '/예약', aliases: ['예약', '예약해줘', 'book'] },
    { id: 'write', token: '/작성', aliases: ['작성', '작성해줘', '신청'] },
    { id: 'search', token: '/검색', aliases: ['검색', '검색해줘', '조회', '조회해줘', 'search'] },
  ];
  const STRUCTURED_COMBO_MAP = [
    { chips: ['current_mail'], verbs: ['summary'], legacy_message: '이 메일을 요약해줘.' },
    { chips: ['current_mail'], verbs: ['analysis'], legacy_message: '@현재메일 분석해줘' },
    { chips: ['current_mail'], verbs: ['reply'], legacy_message: '이 메일에 대한 전문적이고 간결한 답변 초안을 작성해줘.' },
    { chips: ['current_mail'], verbs: ['translate'], legacy_message: '이 메일 내용을 자연스러운 한국어로 번역해줘.' },
    { chips: ['current_mail'], verbs: ['todo_extract'], legacy_message: '이 메일에서 액션 아이템만 추출해줘.' },
    { chips: ['current_mail'], verbs: ['search'], legacy_message: '@현재메일 기준으로 관련 메일을 조회해줘' },
    { chips: ['current_mail', 'todo'], verbs: ['summary', 'add'], legacy_message: '이 메일에서 액션 아이템을 추출해서 To Do로 만들어줘' },
    { chips: ['current_mail', 'schedule'], verbs: ['summary', 'register'], legacy_message: '이 메일 내용으로 일정 등록해줘' },
    { chips: ['current_mail', 'schedule'], verbs: ['summary'], legacy_message: '이 메일 내용을 요약해서 일정 등록해줘' },
    { chips: ['current_mail', 'room'], verbs: ['summary', 'reserve'], legacy_message: '이 메일 내용을 요약해서 회의실 예약해줘' },
    { chips: ['current_mail', 'room'], verbs: ['summary'], legacy_message: '이 메일 내용을 요약해서 회의실 예약해줘' },
    { chips: ['current_mail', 'hr'], verbs: ['summary', 'write'], legacy_message: '이 메일 내용을 요약해서 근태신청서를 작성해줘' },
    { chips: ['current_mail', 'hr'], verbs: ['summary'], legacy_message: '이 메일 내용을 요약해서 근태신청서를 작성해줘' },
    { chips: ['all_mailbox', 'todo'], verbs: ['search', 'add'], legacy_message: '전체 사서함에서 관련 메일을 검색해 액션 아이템을 추출해서 To Do로 만들어줘' },
    { chips: ['all_mailbox'], verbs: ['search'], legacy_message: '전체 사서함에서 관련 메일을 검색해줘' },
    { chips: ['all_mailbox'], verbs: ['summary'], legacy_message: '전체 사서함에서 관련 메일을 검색해 핵심만 요약해줘' },
    { chips: ['all_mailbox'], verbs: ['analysis'], legacy_message: '전체 사서함에서 관련 메일을 검색해 분석해줘' },
    { chips: ['all_mailbox'], verbs: ['todo_extract'], legacy_message: '전체 사서함에서 관련 메일을 검색해 액션 아이템만 추출해줘' },
    { chips: ['all_mailbox', 'todo'], verbs: ['summary', 'add'], legacy_message: '전체 사서함에서 관련 메일을 요약하고 액션 아이템을 To Do로 만들어줘' },
  ];
  const STRUCTURED_INPUT_MAX_CHIPS = 2;
  const STRUCTURED_INPUT_MAX_VERBS = 2;
  const STRUCTURED_FORBIDDEN_CHIP_PAIRS = [['current_mail', 'all_mailbox']];

  const STRUCTURED_CHIP_ALIAS_TO_ID = new Map();
  const STRUCTURED_CHIP_TOKEN_BY_ID = new Map();
  const STRUCTURED_VERB_ALIAS_TO_ID = new Map();
  const STRUCTURED_VERB_TOKEN_BY_ID = new Map();
  const STRUCTURED_COMBO_BY_KEY = new Map();
  const STRUCTURED_COMBOS_BY_CHIPS_KEY = new Map();

  const SYSTEM_SCOPE_LABEL_BY_DOMAIN = {
    room: '회의실',
    schedule: '일정',
    todo: '할 일',
    hr: '근태',
    promise: '실행예산',
    finance: '비용정산',
  };

  function toBool(value) {
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') return value !== 0;
    if (typeof value === 'string') {
      const lowered = value.trim().toLowerCase();
      if (['1', 'true', 'yes', 'on'].includes(lowered)) return true;
      if (['0', 'false', 'no', 'off'].includes(lowered)) return false;
    }
    return false;
  }

  function normalizeScope(value) {
    const normalized = String(value || '').trim().toLowerCase();
    return SCOPE_VALUES.has(normalized) ? normalized : 'email';
  }

  function normalizeShortcutDomain(value) {
    const normalized = String(value || '').trim().toLowerCase();
    return ['room', 'hr', 'schedule', 'todo', 'finance', 'promise'].includes(normalized)
      ? normalized
      : '';
  }

  function modeFromScope(scope) {
    return normalizeScope(scope) === 'email' ? 'email' : 'assistant';
  }

  function scopeFromMode(mode) {
    const normalized = String(mode || '').trim().toLowerCase();
    return normalized === 'email' ? 'email' : 'all';
  }

  function parseScopeFromMessagePrefix(rawMessage) {
    const text = String(rawMessage || '').trim();
    if (!text.startsWith('@')) {
      return { scope: null, message: text, domain: '' };
    }

    const patterns = [
      { scope: 'email', regex: /^@\s*(?:현재\s*메일|현재메일|이\s*메일)(?=\s|[:：]|$)\s*[:：]?\s*/i },
      { scope: 'all', regex: /^@\s*(?:전체\s*사서함|전체사서함|all)(?=\s|[:：]|$)\s*[:：]?\s*/i },
      { scope: 'systems', domain: 'room', regex: /^@\s*(?:회의실|미팅룸)(?=\s|[:：]|$)\s*[:：]?\s*/i },
      { scope: 'systems', domain: 'schedule', regex: /^@\s*(?:캘린더|일정|스케줄)(?=\s|[:：]|$)\s*[:：]?\s*/i },
      { scope: 'systems', domain: 'hr', regex: /^@\s*(?:근태|휴가|연차)(?=\s|[:：]|$)\s*[:：]?\s*/i },
      { scope: 'systems', domain: 'promise', regex: /^@\s*(?:실행\s*예산|실행예산|promise)(?=\s|[:：]|$)\s*[:：]?\s*/i },
      { scope: 'systems', domain: 'finance', regex: /^@\s*(?:비용\s*정산|비용정산|경비\s*정산|경비정산|finance)(?=\s|[:：]|$)\s*[:：]?\s*/i },
      { scope: 'systems', domain: 'todo', regex: /^@\s*(?:todo|할\s*일|할일)(?=\s|[:：]|$)\s*[:：]?\s*/i },
    ];

    for (const pattern of patterns) {
      if (pattern.regex.test(text)) {
        const message = text.replace(pattern.regex, '').trim();
        return { scope: pattern.scope, message, domain: String(pattern.domain || '').trim().toLowerCase() };
      }
    }
    return { scope: null, message: text, domain: '' };
  }

  function parseNaturalLanguageIntentProbe(rawMessage) {
    const text = String(rawMessage || '').trim();
    if (!text.startsWith('@')) return { enabled: false, message: text };
    const probeRe = /^@\s*(?:자연어|nl|intent)(?=\s|[:：]|$)\s*[:：]?\s*/i;
    if (!probeRe.test(text)) return { enabled: false, message: text };
    const message = text.replace(probeRe, '').trim();
    return { enabled: true, message };
  }

  function parseDomainShortcutFromPrefix(rawMessage) {
    const text = String(rawMessage || '').trim();
    if (!text.startsWith('@')) {
      return { domain: '', message: text };
    }

    const domainPatterns = [
      { domain: 'room', regex: /^@\s*(?:회의실|미팅룸)(?=\s|[:：]|$)\s*[:：]?\s*/i },
      { domain: 'schedule', regex: /^@\s*(?:일정|캘린더|스케줄)(?=\s|[:：]|$)\s*[:：]?\s*/i },
      { domain: 'todo', regex: /^@\s*(?:todo|할\s*일|할일)(?=\s|[:：]|$)\s*[:：]?\s*/i },
      { domain: 'hr', regex: /^@\s*(?:근태|휴가|연차)(?=\s|[:：]|$)\s*[:：]?\s*/i },
      { domain: 'promise', regex: /^@\s*(?:실행\s*예산|실행예산|promise)(?=\s|[:：]|$)\s*[:：]?\s*/i },
      { domain: 'finance', regex: /^@\s*(?:비용\s*정산|비용정산|경비\s*정산|경비정산|finance)(?=\s|[:：]|$)\s*[:：]?\s*/i },
    ];

    for (const pattern of domainPatterns) {
      if (pattern.regex.test(text)) {
        return {
          domain: pattern.domain,
          message: text.replace(pattern.regex, '').trim(),
        };
      }
    }
    return { domain: '', message: text };
  }

  function resolveSystemScopeLabelOverride(domain = '') {
    const key = String(domain || '').trim().toLowerCase();
    return SYSTEM_SCOPE_LABEL_BY_DOMAIN[key] || '';
  }

  function normalizeCompactToken(value) {
    return String(value || '').toLowerCase().replace(/\s+/g, '').trim();
  }

  function registerStructuredAliasIndex(defs = [], tokenMap, aliasMap, prefixPattern) {
    for (const item of defs) {
      if (!item || !item.id || !item.token) continue;
      tokenMap.set(item.id, item.token);
      const aliases = [item.token, ...(Array.isArray(item.aliases) ? item.aliases : [])];
      aliases.forEach((alias) => {
        const normalized = normalizeCompactToken(String(alias || '').replace(prefixPattern, ''));
        if (normalized) {
          aliasMap.set(normalized, item.id);
        }
      });
    }
  }

  function toStructuredChipKey(chips = []) {
    return Array.from(new Set((chips || []).filter(Boolean))).sort().join('+');
  }

  function toStructuredVerbKey(verbs = []) {
    return Array.from(new Set((verbs || []).filter(Boolean))).sort().join('+');
  }

  function buildStructuredComboKey(chips = [], verbs = []) {
    return `${toStructuredChipKey(chips)}|${toStructuredVerbKey(verbs)}`;
  }

  function normalizeStructuredComboEntry(combo) {
    if (!combo || !Array.isArray(combo.chips) || !Array.isArray(combo.verbs)) return null;
    const chips = Array.from(new Set(combo.chips.filter(Boolean))).sort();
    const verbs = Array.from(new Set(combo.verbs.filter(Boolean))).sort();
    if (!chips.length || !verbs.length) return null;
    return {
      ...combo,
      chips,
      verbs,
      chips_key: toStructuredChipKey(chips),
      verbs_key: toStructuredVerbKey(verbs),
      combo_key: buildStructuredComboKey(chips, verbs),
    };
  }

  function registerStructuredComboIndex() {
    for (const combo of STRUCTURED_COMBO_MAP) {
      const normalized = normalizeStructuredComboEntry(combo);
      if (!normalized) continue;
      STRUCTURED_COMBO_BY_KEY.set(normalized.combo_key, normalized);
      const bucket = STRUCTURED_COMBOS_BY_CHIPS_KEY.get(normalized.chips_key) || [];
      bucket.push(normalized);
      STRUCTURED_COMBOS_BY_CHIPS_KEY.set(normalized.chips_key, bucket);
    }
  }

  function resolveStructuredChipId(tokenValue) {
    const normalized = normalizeCompactToken(String(tokenValue || '').replace(/^@+/, ''));
    return STRUCTURED_CHIP_ALIAS_TO_ID.get(normalized) || '';
  }

  function resolveStructuredVerbId(tokenValue) {
    const normalized = normalizeCompactToken(String(tokenValue || '').replace(/^\/+/, ''));
    return STRUCTURED_VERB_ALIAS_TO_ID.get(normalized) || '';
  }

  function extractStructuredChipIdsFromText(value, maxCount = STRUCTURED_INPUT_MAX_CHIPS) {
    const tokens = String(value || '').match(/@[^\s]+/g) || [];
    const seen = new Set();
    const chipIds = [];
    for (const token of tokens) {
      const chipId = resolveStructuredChipId(token);
      if (!chipId || seen.has(chipId)) continue;
      seen.add(chipId);
      chipIds.push(chipId);
      if (chipIds.length >= Number(maxCount || STRUCTURED_INPUT_MAX_CHIPS)) break;
    }
    return chipIds;
  }

  function extractStructuredVerbIdsFromText(value, maxCount = STRUCTURED_INPUT_MAX_VERBS) {
    const tokens = String(value || '').match(/\/[^\s]+/g) || [];
    const seen = new Set();
    const verbIds = [];
    for (const token of tokens) {
      const verbId = resolveStructuredVerbId(token);
      if (!verbId || seen.has(verbId)) continue;
      seen.add(verbId);
      verbIds.push(verbId);
      if (verbIds.length >= Number(maxCount || STRUCTURED_INPUT_MAX_VERBS)) break;
    }
    return verbIds;
  }

  function hasStructuredForbiddenPair(chips = []) {
    const selected = new Set(chips || []);
    return STRUCTURED_FORBIDDEN_CHIP_PAIRS.some((pair) =>
      Array.isArray(pair) && pair.every((chip) => selected.has(chip))
    );
  }

  function resolveAllowedNextStructuredChipIds(selectedChipIds = []) {
    const normalized = Array.from(new Set((selectedChipIds || []).filter(Boolean))).sort();
    if (normalized.length >= STRUCTURED_INPUT_MAX_CHIPS) {
      return new Set();
    }
    const selectedSet = new Set(normalized);
    const allowed = new Set();
    for (const combo of STRUCTURED_COMBO_MAP) {
      if (!combo || !Array.isArray(combo.chips)) continue;
      const comboChips = Array.from(new Set(combo.chips.filter(Boolean)));
      const includesAllSelected = normalized.every((chipId) => comboChips.includes(chipId));
      if (!includesAllSelected) continue;
      comboChips.forEach((chipId) => {
        if (!selectedSet.has(chipId)) {
          allowed.add(chipId);
        }
      });
    }
    if (!normalized.length) {
      return new Set(STRUCTURED_CHIP_DEFS.map((item) => item.id));
    }
    return allowed;
  }

  function resolveStructuredScopeFromChips(chips = []) {
    const set = new Set(chips || []);
    if (set.has('current_mail')) return 'email';
    if (set.has('all_mailbox')) return 'all';
    return 'systems';
  }

  function resolveStructuredDomainFromChips(chips = []) {
    const set = new Set(chips || []);
    const ordered = ['room', 'schedule', 'todo', 'hr', 'promise', 'finance'];
    const domain = ordered.find((item) => set.has(item));
    return String(domain || '').trim().toLowerCase();
  }

  function buildStructuredLegacyMessage(rawMessage) {
    const text = String(rawMessage || '').trim();
    if (!text.startsWith('@')) return null;

    const parts = text.split(/\s+/).filter(Boolean);
    if (!parts.length) return null;

    const chips = [];
    const verbs = [];
    let idx = 0;
    while (idx < parts.length && parts[idx].startsWith('@')) {
      const chipId = resolveStructuredChipId(parts[idx]);
      if (chipId && !chips.includes(chipId)) chips.push(chipId);
      idx += 1;
    }
    while (idx < parts.length && parts[idx].startsWith('/')) {
      const verbId = resolveStructuredVerbId(parts[idx]);
      if (verbId && !verbs.includes(verbId)) verbs.push(verbId);
      idx += 1;
    }

    const extraContext = parts.slice(idx).join(' ').trim();
    if (!chips.length || !verbs.length) return null;
    if (chips.length > STRUCTURED_INPUT_MAX_CHIPS || verbs.length > STRUCTURED_INPUT_MAX_VERBS) return null;
    if (hasStructuredForbiddenPair(chips)) return null;

    const combo = STRUCTURED_COMBO_BY_KEY.get(buildStructuredComboKey(chips, verbs));
    if (!combo) return null;

    const legacyMessage = extraContext
      ? `${String(combo.legacy_message || '').trim()}\n추가 조건: ${extraContext}`
      : String(combo.legacy_message || '').trim();
    if (!legacyMessage) return null;

    return {
      chips: combo.chips.slice(),
      verbs: combo.verbs.slice(),
      scope: resolveStructuredScopeFromChips(combo.chips),
      domain: resolveStructuredDomainFromChips(combo.chips),
      legacyMessage,
      extraContext,
      combo,
    };
  }

  function buildIntentProbeResultText(rawQuestion = '', intentPayload = null, elapsedMs = 0) {
    const payload = intentPayload && typeof intentPayload === 'object' ? intentPayload : {};
    const intent = String(payload.intent || payload.primary_intent || 'unknown').trim().toLowerCase() || 'unknown';
    const confidence = Number(payload.confidence);
    const confidenceText = Number.isFinite(confidence) ? confidence.toFixed(2) : '-';
    const needsClarification = toBool(payload.needs_clarification);
    const clarificationTier = String(payload.clarification_tier || '').trim().toLowerCase() || '-';
    const clarificationReason = String(payload.clarification_reason || '').trim().toLowerCase() || '-';
    const uiAction = String(payload.ui_action || '').trim().toLowerCase() || '-';
    const searchSlots = payload.search_slots && typeof payload.search_slots === 'object' ? payload.search_slots : {};

    const lines = [];
    lines.push('**NL Intent Probe**');
    lines.push('- source: `@자연어`');
    if (rawQuestion) lines.push(`- 입력: ${rawQuestion}`);
    lines.push(`- intent: \`${intent}\``);
    lines.push(`- confidence: \`${confidenceText}\``);
    lines.push(`- needs_clarification: \`${needsClarification}\``);
    lines.push(`- clarification_tier: \`${clarificationTier}\``);
    lines.push(`- clarification_reason: \`${clarificationReason}\``);
    lines.push(`- ui_action: \`${uiAction}\``);
    if (Object.keys(searchSlots).length) {
      const query = String(searchSlots.query || '').trim();
      const sender = String(searchSlots.sender || '').trim();
      const limit = Number.parseInt(String(searchSlots.limit || ''), 10);
      const sort = String(searchSlots.sort_mode || '').trim();
      if (query) lines.push(`- search.query: ${query}`);
      if (sender) lines.push(`- search.sender: ${sender}`);
      if (Number.isFinite(limit) && limit > 0) lines.push(`- search.limit: ${limit}`);
      if (sort) lines.push(`- search.sort: ${sort}`);
    }
    if (Number.isFinite(Number(elapsedMs)) && Number(elapsedMs) >= 0) {
      lines.push(`- resolve_ms: ${Math.max(0, Math.round(Number(elapsedMs)))}`);
    }
    return lines.join('\n');
  }

  registerStructuredAliasIndex(
    STRUCTURED_CHIP_DEFS,
    STRUCTURED_CHIP_TOKEN_BY_ID,
    STRUCTURED_CHIP_ALIAS_TO_ID,
    /^@+/
  );
  registerStructuredAliasIndex(
    STRUCTURED_VERB_DEFS,
    STRUCTURED_VERB_TOKEN_BY_ID,
    STRUCTURED_VERB_ALIAS_TO_ID,
    /^\/+/
  );
  registerStructuredComboIndex();

  globalThis.TaskpaneStructuredUtils = {
    SCOPE_VALUES,
    SCOPE_SHORTCUTS,
    STRUCTURED_CHIP_DEFS,
    STRUCTURED_VERB_DEFS,
    STRUCTURED_COMBO_MAP,
    STRUCTURED_INPUT_MAX_CHIPS,
    STRUCTURED_INPUT_MAX_VERBS,
    STRUCTURED_FORBIDDEN_CHIP_PAIRS,
    STRUCTURED_CHIP_ALIAS_TO_ID,
    STRUCTURED_CHIP_TOKEN_BY_ID,
    STRUCTURED_VERB_ALIAS_TO_ID,
    STRUCTURED_VERB_TOKEN_BY_ID,
    STRUCTURED_COMBO_BY_KEY,
    STRUCTURED_COMBOS_BY_CHIPS_KEY,
    SYSTEM_SCOPE_LABEL_BY_DOMAIN,
    toBool,
    normalizeScope,
    normalizeShortcutDomain,
    modeFromScope,
    scopeFromMode,
    parseScopeFromMessagePrefix,
    parseNaturalLanguageIntentProbe,
    parseDomainShortcutFromPrefix,
    resolveSystemScopeLabelOverride,
    normalizeCompactToken,
    resolveStructuredChipId,
    resolveStructuredVerbId,
    extractStructuredChipIdsFromText,
    extractStructuredVerbIdsFromText,
    hasStructuredForbiddenPair,
    resolveAllowedNextStructuredChipIds,
    resolveStructuredScopeFromChips,
    resolveStructuredDomainFromChips,
    buildStructuredLegacyMessage,
    buildIntentProbeResultText,
    toStructuredChipKey,
    toStructuredVerbKey,
    buildStructuredComboKey,
  };
})(window);

