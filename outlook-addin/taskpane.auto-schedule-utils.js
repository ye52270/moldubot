/* ========================================
   MolduBot – Auto Schedule Utils Module
   ======================================== */

(function (global) {
  function normalizeScheduleTitleFromSubject(subject) {
    const fallback = '메일 후속 작업';
    const raw = String(subject || '').replace(/\s+/g, ' ').trim();
    if (!raw) return fallback;
    const normalized = raw.replace(/^\[[^\]]+\]\s*/, '').trim();
    return normalized || fallback;
  }

  function compactAutoScheduleSummaryLine(line, maxLen = 72) {
    const normalized = String(line || '').replace(/\s+/g, ' ').trim();
    if (!normalized) return '';
    if (normalized.length <= maxLen) return normalized;
    const clipped = normalized.slice(0, maxLen);
    const lastSpace = clipped.lastIndexOf(' ');
    const safe = lastSpace >= 24 ? clipped.slice(0, lastSpace) : clipped;
    return `${safe.trim()}...`;
  }

  function normalizeAutoScheduleBody(body) {
    return String(body || '')
      .replace(/\\n/g, '\n')
      .replace(/\r\n/g, '\n')
      .replace(/\t/g, ' ')
      .replace(/\u00a0/g, ' ')
      .trim();
  }

  function shouldKeepAutoScheduleRawLine(line) {
    if (!line) return false;
    if (line.length < 6) return false;
    if (/^(?:from|to|cc|bcc|subject|date)\s*[:：]/i.test(line)) return false;
    if (/^(?:보낸사람|받는사람|참조|제목|보낸시간)\s*[:：]/.test(line)) return false;
    if (/^(?:message\s*id|\[메일\s*컨텍스트\])/i.test(line)) return false;
    if (/^(?:안녕하세요|안녕하십니까|감사합니다|잘\s*부탁드립니다|수고하세요|좋은\s*(?:하루|주말)|즐거운\s*(?:설|연휴|명절)|새해\s*복)/i.test(line)) return false;
    if (/^https?:\/\//i.test(line)) return false;
    return true;
  }

  function normalizeAutoScheduleRawLine(line) {
    return String(line || '')
      .replace(/^설명\s*[:：]\s*/i, '')
      .replace(/^추가\s*요청\s*[:：]\s*/i, '')
      .replace(/^추가\s*조건\s*[:：]\s*/i, '')
      .replace(/^\d+[.)]\s*/, '')
      .replace(/^[-*•]\s*/, '')
      .trim();
  }

  function extractAutoScheduleCandidateSegments(lines = []) {
    const candidates = [];
    for (const line of lines) {
      const segments = line.length > 92 ? line.split(/(?<=[.!?])\s+|\s+-\s+/) : [line];
      for (const segment of segments) {
        const cleaned = String(segment || '').replace(/\s+/g, ' ').trim();
        if (!cleaned || cleaned.length < 8) continue;
        if (/^(?:설명|요약|추가요청|추가요청사항)$/i.test(cleaned)) continue;
        candidates.push(cleaned);
      }
    }
    return candidates;
  }

  function prioritizeAutoScheduleLines(lines = []) {
    const priorityRe = /(요청|필요|완료|확인|기한|일정|금액|견적|검토|조치|문의|장애|리스크)/i;
    const prioritized = [];
    const fallback = [];
    for (const line of lines) {
      if (priorityRe.test(line)) prioritized.push(line);
      else fallback.push(line);
    }
    return [...prioritized, ...fallback];
  }

  function pickAutoScheduleSummaryLines(lines = [], limit = 3) {
    const picked = [];
    const seen = new Set();
    for (const line of lines) {
      const compact = compactAutoScheduleSummaryLine(line, 72);
      const normalized = compact.toLowerCase().replace(/[\s.,:;!?'"]/g, '');
      if (!compact || seen.has(normalized)) continue;
      seen.add(normalized);
      picked.push(compact);
      if (picked.length >= limit) break;
    }
    return picked;
  }

  function extractAutoScheduleSummaryLinesFromBody(body, maxItems = 3) {
    const limit = Number.isFinite(Number(maxItems)) ? Math.max(1, Number(maxItems)) : 3;
    const roughLines = normalizeAutoScheduleBody(body)
      .split('\n')
      .map((line) => String(line || '').replace(/\s+/g, ' ').trim())
      .filter(Boolean)
      .filter((line) => shouldKeepAutoScheduleRawLine(line))
      .map((line) => normalizeAutoScheduleRawLine(line))
      .filter(Boolean);

    const candidates = extractAutoScheduleCandidateSegments(roughLines);
    const prioritizedLines = prioritizeAutoScheduleLines(candidates);
    return pickAutoScheduleSummaryLines(prioritizedLines, limit);
  }

  function buildAutoScheduleRegistrationMessage({ emailCtx } = {}) {
    if (!emailCtx || typeof emailCtx !== 'object') return '';
    const subject = String(emailCtx.subject || '').trim();
    const title = normalizeScheduleTitleFromSubject(subject);
    const date = new Date().toISOString().slice(0, 10);
    const start = '09:00';
    const end = '10:00';
    const summaryLines = extractAutoScheduleSummaryLinesFromBody(emailCtx.body || '', 3);
    const summaryText = summaryLines.length
      ? summaryLines.map((line) => `- ${line}`).join('\n')
      : '';
    const noteParts = [];
    if (summaryText) noteParts.push(summaryText);
    const note = noteParts.join('\n').trim();
    return `${date} ${start}부터 ${end}까지 "${title}" 일정 등록해줘${note ? `. 설명: ${note}` : ''}`.trim();
  }

  global.TaskpaneAutoScheduleUtils = {
    buildAutoScheduleRegistrationMessage,
  };
})(window);
