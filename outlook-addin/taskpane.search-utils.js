/* ========================================
   MolduBot - Shared Search Query Utils
   ======================================== */

(function initSearchQueryUtils(globalScope) {
  if (!globalScope) return;

  function normalizeSpaces(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function sanitizeSearchPrefillQuery(source) {
    const stripped = String(source || '')
      .replace(/(메일|이메일|mail|email)/gi, ' ')
      .replace(/(?:최대\s*)?\d+\s*(?:개|건)\s*(?:만)?(?:에서|중|내)?/gi, ' ')
      .replace(
        /(?:관련도\s*순|정확도\s*순|최근\s*(?:메일)?\s*순|최신\s*(?:메일)?\s*순|오래된\s*순|과거\s*순|oldest|recent|latest|newest|최근\s*\d+\s*(?:개|건)\s*(?:기준)?)(?:\s*(?:으로|로))?/gi,
        ' '
      )
      .replace(
        /(관련되어|관련된|관련해서|관련하여|관련해|조회|검색|찾아줘|찾아|보여줘|보여|목록|리스트|관련|요약|insight|인사이트|분석|보고서|리포트|추출|핵심|핵심만|요점|액션아이템|액션\s*아이템)/gi,
        ' '
      )
      .replace(
        /(해줘|해주세요|해줘요|만들어줘|만들어줘요|작성해줘|작성해주세요|정리해줘|분석해서|분석해줘|추출해줘|형식으로|보고서로|부탁해|뽑아줘|뽑아주세요|추려줘|추려주세요)/gi,
        ' '
      )
      .replace(/[.,!?()[\]{}]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();

    if (!stripped) return '';

    return stripped
      .split(/\s+/)
      .map((token) =>
        token.replace(
          /(께서는|에게는|한테는|으로는|로는|께서|에게|한테|에서|으로|로|은|는|이|가|을|를|의|도|만)$/g,
          ''
        )
      )
      .filter(
        (token) =>
          token &&
          !/^\d+(?:개|건)?$/.test(token) &&
          !/^(은|는|이|가|을|를|에|에서|로|으로|와|과|및|좀|줘|요|해서|형식|형식으로|된|관련된|관련하여|관련해|관련해서|관련되어)$/.test(
            token
          )
      )
      .join(' ')
      .trim();
  }

  function extractSearchSortMode(source) {
    const text = String(source || '').trim();
    if (!text) return '';
    if (/(?:오래된\s*순|과거\s*순|oldest)/i.test(text)) return 'oldest';
    if (/(?:최근\s*(?:메일)?\s*순|최신\s*(?:메일)?\s*순|최근\s*\d+\s*(?:개|건)\s*(?:기준)?|recent|latest|newest)/i.test(text)) return 'recent';
    if (/(?:관련도\s*순|정확도\s*순|relevance|score)/i.test(text)) return 'relevance';
    return '';
  }

  function extractSearchResultLimit(source, options) {
    const text = String(source || '').trim();
    if (!text) return 0;
    const opts = options && typeof options === 'object' ? options : {};
    const min = Number.isFinite(Number(opts.min)) ? Number(opts.min) : 1;
    const max = Number.isFinite(Number(opts.max)) ? Number(opts.max) : 20;
    const match = text.match(/(?:최대\s*)?(\d+)\s*(?:개|건)\s*(?:만)?(?:에서|중|내)?/i);
    if (!match || !match[1]) return 0;
    const parsed = Number.parseInt(match[1], 10);
    if (!Number.isFinite(parsed) || parsed <= 0) return 0;
    const clamped = Math.max(min, Math.min(parsed, max));
    return clamped;
  }

  function normalizeSenderForSearchSlot(sender) {
    const text = String(sender || '').trim();
    if (!text) return '';
    return text
      .replace(/(님께서|님이|께서|이|가|은|는)$/g, '')
      .replace(/(님|팀장|부장|차장|과장|책임|수석|매니저|manager)$/gi, '')
      .trim();
  }

  function formatDateForSlot(dateObj) {
    const yyyy = String(dateObj.getFullYear());
    const mm = String(dateObj.getMonth() + 1).padStart(2, '0');
    const dd = String(dateObj.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  }

  function normalizeDateTokenForSearchSlot(token) {
    const text = String(token || '').trim();
    if (!text) return '';

    const isoMatch = text.match(/^(\d{4})[./-](\d{1,2})[./-](\d{1,2})$/);
    if (isoMatch) {
      const [, y, m, d] = isoMatch;
      return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    }

    const ymdMatch = text.match(/^(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일?$/);
    if (ymdMatch) {
      const [, y, m, d] = ymdMatch;
      return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    }

    const mdMatch = text.match(/^(\d{1,2})\s*월\s*(\d{1,2})\s*일?$/);
    if (mdMatch) {
      const [, m, d] = mdMatch;
      const year = String(new Date().getFullYear());
      return `${year}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    }

    return '';
  }

  function extractMailSearchSlots(source) {
    const text = String(source || '').trim();
    if (!text) return { sender: '', dateFrom: '', dateTo: '' };

    let sender = '';
    const senderEq = text.match(/(?:발신자|sender)\s*[:=]\s*([^\n,;]+)/i);
    if (senderEq && senderEq[1]) {
      sender = normalizeSenderForSearchSlot(senderEq[1]);
    }
    if (!sender) {
      const senderPhrase = text.match(/([A-Za-z0-9._%+\-@가-힣 ]+?)\s*보낸\s*메일/i);
      if (senderPhrase && senderPhrase[1]) {
        sender = normalizeSenderForSearchSlot(senderPhrase[1]);
      }
    }
    if (!sender) {
      const senderRelated = text.match(
        /([가-힣]{2,3}(?:님|팀장|부장|차장|과장|책임|수석|매니저)?)\s*(?:과|와)?\s*관련(?:되어|된|해서|하여|해)?\s*메일/i
      );
      if (senderRelated && senderRelated[1]) {
        sender = normalizeSenderForSearchSlot(senderRelated[1]);
      }
    }
    if (!sender) {
      const senderByMailQuery = text.match(
        /([가-힣]{2,3}(?:님|팀장|부장|차장|과장|책임|수석|매니저)?)\s*(?:메일|이메일)\s*(?:조회|검색|찾아|찾기|보여줘|보여주|보여)/i
      );
      if (senderByMailQuery && senderByMailQuery[1]) {
        sender = normalizeSenderForSearchSlot(senderByMailQuery[1]);
      }
    }

    let dateFrom = '';
    let dateTo = '';

    const isoRange = text.match(
      /(\d{4}[./-]\d{1,2}[./-]\d{1,2})\s*(?:부터|~|to|-)\s*(\d{4}[./-]\d{1,2}[./-]\d{1,2})/i
    );
    if (isoRange) {
      dateFrom = normalizeDateTokenForSearchSlot(isoRange[1]);
      dateTo = normalizeDateTokenForSearchSlot(isoRange[2]);
    }

    if (!dateFrom && !dateTo) {
      const mdRange = text.match(
        /(\d{1,2}\s*월\s*\d{1,2}\s*일?)\s*(?:부터|~|to|-)\s*(\d{1,2}\s*월\s*\d{1,2}\s*일?)/i
      );
      if (mdRange) {
        dateFrom = normalizeDateTokenForSearchSlot(mdRange[1]);
        dateTo = normalizeDateTokenForSearchSlot(mdRange[2]);
      }
    }

    const today = new Date();
    const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    if (!dateFrom && !dateTo) {
      if (/오늘/.test(text)) {
        dateFrom = formatDateForSlot(startOfToday);
        dateTo = dateFrom;
      } else if (/어제/.test(text)) {
        const yesterday = new Date(startOfToday);
        yesterday.setDate(yesterday.getDate() - 1);
        dateFrom = formatDateForSlot(yesterday);
        dateTo = dateFrom;
      } else if (/이번\s*주/.test(text)) {
        const day = (startOfToday.getDay() + 6) % 7;
        const weekStart = new Date(startOfToday);
        weekStart.setDate(weekStart.getDate() - day);
        const weekEnd = new Date(weekStart);
        weekEnd.setDate(weekEnd.getDate() + 6);
        dateFrom = formatDateForSlot(weekStart);
        dateTo = formatDateForSlot(weekEnd);
      } else if (/지난\s*주/.test(text)) {
        const day = (startOfToday.getDay() + 6) % 7;
        const thisWeekStart = new Date(startOfToday);
        thisWeekStart.setDate(thisWeekStart.getDate() - day);
        const lastWeekStart = new Date(thisWeekStart);
        lastWeekStart.setDate(lastWeekStart.getDate() - 7);
        const lastWeekEnd = new Date(thisWeekStart);
        lastWeekEnd.setDate(lastWeekEnd.getDate() - 1);
        dateFrom = formatDateForSlot(lastWeekStart);
        dateTo = formatDateForSlot(lastWeekEnd);
      }
    }

    if (!dateFrom && !dateTo) {
      const singleDateMatch = text.match(
        /(\d{4}[./-]\d{1,2}[./-]\d{1,2}|\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일?|\d{1,2}\s*월\s*\d{1,2}\s*일?)/
      );
      if (singleDateMatch) {
        dateFrom = normalizeDateTokenForSearchSlot(singleDateMatch[1]);
        dateTo = dateFrom;
      }
    }

    return {
      sender: sender || '',
      dateFrom: dateFrom || '',
      dateTo: dateTo || '',
    };
  }

  function looksLikeMailSearchIntent(message, options) {
    const text = String(message || '').trim();
    if (!text) return false;
    if (
      /(?:이|현재|해당|본|지금)\s*(?:메일|이메일|mail|email)|(?:this|current)\s*(?:mail|email)/i.test(
        text
      )
    ) {
      return false;
    }

    const compact = text.toLowerCase().replace(/\s+/g, '');
    if (
      compact.includes('메일조회') ||
      compact.includes('메일검색') ||
      compact.includes('이메일조회') ||
      compact.includes('이메일검색')
    ) {
      return true;
    }

    const hasExplicitGlobalScope = /(?:전체\s*(?:사서함|메일|이메일)|전체(?:사서함|메일|이메일)|모든\s*(?:메일|이메일)|all\s*(?:mail|emails?|mailbox)|mailbox\s*(?:wide|search)|@\s*(?:전체\s*사서함|전체사서함|all))/i.test(
      text
    );
    if (hasExplicitGlobalScope) {
      return true;
    }

    const hasInsightToken = /(?:insight|인사이트|분석|보고서|리포트|추출|요약|정리|브리핑)/i.test(text);
    const hasMailToken = /(?:메일|이메일|mail|email)/i.test(text);
    if (hasMailToken && hasInsightToken) {
      return true;
    }

    const allowRelatedInsightWithoutMail = Boolean(
      options && options.allowRelatedInsightWithoutMail
    );
    if (allowRelatedInsightWithoutMail && hasInsightToken && /(?:관련|related|relation)/i.test(text)) {
      return true;
    }

    return (
      /(?:메일|이메일|mail|email).*(?:조회|검색|찾아|찾기|보여줘|보여주|찾아줘)/i.test(text) ||
      /(?:보낸|받은|관련)\s*(?:메일|이메일|mail|email).*(?:조회|검색|찾아|찾기)/i.test(text) ||
      /(?:메일|이메일|mail|email).*(?:요약|정리|브리핑)/i.test(text)
    );
  }

  function hasMailInsightIntent(text) {
    const value = String(text || '').trim();
    if (!value) return false;
    return /(?:insight|인사이트|분석|보고서|리포트|추출|요약)/i.test(value);
  }

  function hasActionSummaryIntent(text) {
    const value = String(text || '').trim();
    if (!value) return false;
    return /(?:할\\s*행동|할\\s*일|액션|action\\s*item|action-item|우선순위\\s*정리)/i.test(
      value
    );
  }

  function deriveMailSearchResponseMode(rawMessage, intentResult) {
    const text = String(rawMessage || '').trim();
    const subIntents = Array.isArray(intentResult && intentResult.sub_intents)
      ? intentResult.sub_intents.map((v) => String(v || '').trim().toLowerCase())
      : [];

    const includeInsight = hasMailInsightIntent(text);
    const includeActionSummary =
      subIntents.includes('action_summary') || hasActionSummaryIntent(text);

    return {
      includeInsight: Boolean(includeInsight),
      includeActionSummary: Boolean(includeActionSummary),
    };
  }

  function buildSearchQueryPlan(rawMessage, intentResult, options) {
    const opts = options && typeof options === 'object' ? options : {};
    const entities =
      intentResult &&
      typeof intentResult === 'object' &&
      intentResult.entities &&
      typeof intentResult.entities === 'object'
        ? intentResult.entities
        : {};

    const rawQueryFromIntent = normalizeSpaces(
      entities.raw_query || entities.mail_query_raw || entities.mail_query || ''
    );
    const rawQuery = rawQueryFromIntent || normalizeSpaces(rawMessage || '');

    const prefillSanitizer =
      typeof opts.prefillSanitizer === 'function'
        ? opts.prefillSanitizer
        : (value) => normalizeSpaces(value);

    const prefillFromIntent = normalizeSpaces(
      entities.prefill_query || entities.mail_query_prefill || ''
    );
    const prefillQuery = prefillFromIntent || normalizeSpaces(prefillSanitizer(rawQuery));

    const includeMailSlots = Boolean(opts.includeMailSlots);
    let slots = { sender: '', dateFrom: '', dateTo: '' };
    if (includeMailSlots) {
      const parsedSlots = extractMailSearchSlots(rawQuery);
      slots = {
        sender: normalizeSpaces(entities.mail_sender || '') || parsedSlots.sender || '',
        dateFrom:
          normalizeDateTokenForSearchSlot(normalizeSpaces(entities.mail_date_from || '')) ||
          parsedSlots.dateFrom ||
          '',
        dateTo:
          normalizeDateTokenForSearchSlot(normalizeSpaces(entities.mail_date_to || '')) ||
          parsedSlots.dateTo ||
          '',
      };
    }

    return {
      rawQuery,
      prefillQuery: prefillQuery || rawQuery,
      semanticQuery: rawQuery,
      slots,
    };
  }

  const api = {
    sanitizeSearchPrefillQuery,
    sanitizeMailSearchQuery: sanitizeSearchPrefillQuery,
    extractSearchSortMode,
    extractSearchResultLimit,
    normalizeDateTokenForSearchSlot,
    extractMailSearchSlots,
    looksLikeMailSearchIntent,
    hasMailInsightIntent,
    hasActionSummaryIntent,
    deriveMailSearchResponseMode,
    buildSearchQueryPlan,
  };

  globalScope.__searchQueryUtils = {
    ...(globalScope.__searchQueryUtils || {}),
    ...api,
  };

  globalScope.__mailIntentUtils = {
    ...(globalScope.__mailIntentUtils || {}),
    sanitizeMailSearchQuery: sanitizeSearchPrefillQuery,
    extractSearchSortMode,
    extractMailSearchSlots,
    buildSearchQueryPlan,
    looksLikeMailSearchIntent,
  };
})(typeof window !== 'undefined' ? window : typeof globalThis !== 'undefined' ? globalThis : null);
