/* ========================================
   MolduBot – Taskpane Send Suggestion Formatters
   ======================================== */

(function initTaskpaneSendSuggestionFormatters(global) {
  function decodeHtmlEntityText(value) {
    return String(value || '')
      .replace(/&lt;/gi, '<')
      .replace(/&gt;/gi, '>')
      .replace(/&amp;/gi, '&')
      .replace(/&quot;/gi, '"')
      .replace(/&#39;/gi, "'");
  }

  function normalizeMeetingAttendeeCandidates(attendees) {
    const rows = Array.isArray(attendees) ? attendees : [];
    const seen = new Set();
    const results = [];
    rows.forEach(function (item) {
      const decoded = decodeHtmlEntityText(item).replace(/\s+/g, ' ').trim();
      if (!decoded) return;
      decoded.split(/\s*[,;]\s*/).forEach(function (segment) {
        const normalized = String(segment || '').trim();
        if (!normalized) return;
        const cleaned = normalized.replace(/^['"]|['"]$/g, '').trim();
        const emailMatch = cleaned.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
        const email = emailMatch ? String(emailMatch[0] || '').trim() : '';
        let name = cleaned;
        if (email) {
          const nameOnlyRaw = name.replace(email, '').replace(/[<>]/g, ' ').trim();
          const slashHead = String(nameOnlyRaw.split('/')[0] || '').trim();
          name = slashHead || nameOnlyRaw;
          name = name.replace(/\([^)]*\)/g, ' ');
          name = name.replace(/\s+/g, ' ').trim();
        }
        const compactName = name
          .replace(/^후보\s*[:：]?\s*/i, '')
          .replace(/^[^가-힣a-zA-Z0-9]+/, '')
          .trim();
        const display = email
          ? ((compactName ? (compactName + ' <' + email + '>') : email))
          : compactName;
        if (!display) return;
        const dedupeKey = display.toLowerCase();
        if (seen.has(dedupeKey)) return;
        seen.add(dedupeKey);
        results.push(display);
      });
    });
    return results;
  }

  function buildMeetingSuggestionMessage(proposal) {
    const source = proposal && typeof proposal === 'object' ? proposal : {};
    const summaryText = String(source.summary_text || '').trim();
    const issues = Array.isArray(source.major_issues) ? source.major_issues : [];
    const attendees = Array.isArray(source.attendees) ? source.attendees : [];
    const subject = String(source.meeting_subject || '').trim() || '메일 주요 이슈 논의';
    const lines = ['현재메일 분석 기반 회의 제안입니다.', '', '### 회의 안건(요약)', '- ' + subject];
    if (issues.length) {
      lines.push('', '### 논의할 주요 내용');
      issues.slice(0, 3).forEach(function (item) {
        lines.push('- ' + String(item || '').trim());
      });
    } else if (summaryText) {
      lines.push('', '### 논의할 주요 내용', summaryText);
    } else {
      lines.push('', '### 논의할 주요 내용', '- 저장된 summary가 없습니다.');
    }
    lines.push('', '### 참석자 제안');
    lines.push('- 참석 인원: ' + String(Math.max(1, Number(source.attendee_count || 1))) + '명');
    if (attendees.length) {
      lines.push('- 후보: ' + attendees.slice(0, 5).map(function (item) { return String(item || '').trim(); }).join(', '));
    }
    lines.push('', '아래 카드에서 최종 시간/인원을 확인한 뒤 예약해 주세요.');
    return lines.join('\n');
  }

  function buildMeetingSuggestionMetadata(proposal) {
    const source = proposal && typeof proposal === 'object' ? proposal : {};
    const summaryText = String(source.summary_text || '').trim();
    const issues = Array.isArray(source.major_issues) ? source.major_issues : [];
    const attendees = Array.isArray(source.attendees) ? source.attendees : [];
    const subject = String(source.meeting_subject || '').trim() || '메일 주요 이슈 논의';
    const attendeeCount = String(Math.max(1, Number(source.attendee_count || 1))) + '명';
    const issueItems = issues.length
      ? issues.slice(0, 3).map(function (item) { return String(item || '').trim(); }).filter(function (item) { return Boolean(item); })
      : [summaryText || '저장된 summary가 없습니다.'];
    const attendeeCandidates = normalizeMeetingAttendeeCandidates(attendees).slice(0, 5);
    const attendeeItems = ['참석 인원: ' + attendeeCount];
    if (attendeeCandidates.length) {
      attendeeItems.push('후보: ' + attendeeCandidates.join(', '));
    }
    return {
      answer_format: {
        version: 'v1',
        format_type: 'meeting_suggestion',
        blocks: [
          { type: 'paragraph', text: '현재메일 분석 기반 회의 제안입니다.' },
          { type: 'heading', level: 3, text: '회의 안건(요약)' },
          { type: 'unordered_list', items: [subject] },
          { type: 'heading', level: 3, text: '논의할 주요 내용' },
          { type: 'ordered_list', items: issueItems },
          { type: 'heading', level: 3, text: '참석자 제안' },
          { type: 'unordered_list', items: attendeeItems },
          { type: 'paragraph', text: '아래 카드에서 최종 시간/인원을 확인한 뒤 예약해 주세요.' },
        ],
      },
    };
  }

  function buildSuggestedScheduleDefaults(proposal) {
    const source = proposal && typeof proposal === 'object' ? proposal : {};
    const timeCandidates = Array.isArray(source.time_candidates) ? source.time_candidates : [];
    const firstTime = timeCandidates[0] && typeof timeCandidates[0] === 'object' ? timeCandidates[0] : {};
    const roomCandidates = Array.isArray(source.room_candidates) ? source.room_candidates : [];
    return {
      date: String(firstTime.date || '').trim(),
      start_time: String(firstTime.start_time || '').trim(),
      end_time: String(firstTime.end_time || '').trim(),
      attendee_count: Math.max(1, Number(source.attendee_count || 1)),
      subject: String(source.meeting_subject || '').trim(),
      time_candidates: timeCandidates.slice(0, 3),
      room_candidates: roomCandidates.slice(0, 3),
    };
  }

  function buildCalendarSuggestionMessage(proposal) {
    const source = proposal && typeof proposal === 'object' ? proposal : {};
    const summaryText = String(source.summary_text || '').trim();
    const keyPoints = Array.isArray(source.key_points) ? source.key_points : [];
    const attendees = Array.isArray(source.attendees) ? source.attendees : [];
    const lines = ['현재메일 분석 기반 일정 제안입니다.'];
    if (summaryText) {
      lines.push('', '**주요 내용**', summaryText);
    } else if (keyPoints.length) {
      lines.push('', '**주요 내용**');
      keyPoints.slice(0, 3).forEach(function (item) {
        lines.push('- ' + String(item || '').trim());
      });
    }
    if (attendees.length) {
      lines.push('', '**참석자 후보**');
      lines.push('- ' + attendees.slice(0, 8).map(function (item) { return String(item || '').trim(); }).join(', '));
    }
    lines.push('', '아래 일정 카드에서 제목/시간/참석자를 확인 후 등록해 주세요.');
    return lines.join('\n');
  }

  function buildCalendarSuggestionMetadata(proposal) {
    const source = proposal && typeof proposal === 'object' ? proposal : {};
    const summaryText = String(source.summary_text || '').trim();
    const keyPoints = Array.isArray(source.key_points) ? source.key_points : [];
    const attendees = Array.isArray(source.attendees) ? source.attendees : [];
    const subject = String(source.subject || source.meeting_subject || '').trim() || '현재메일 기반 일정';
    const discussionItems = keyPoints.length
      ? keyPoints.slice(0, 3).map(function (item) { return String(item || '').trim(); }).filter(function (item) { return Boolean(item); })
      : [summaryText || '저장된 summary가 없습니다.'];
    const attendeeCandidates = normalizeMeetingAttendeeCandidates(attendees).slice(0, 8);
    const attendeeItems = attendeeCandidates.length
      ? attendeeCandidates
      : ['저장된 참석자 후보가 없습니다.'];
    return {
      answer_format: {
        version: 'v1',
        format_type: 'calendar_suggestion',
        blocks: [
          { type: 'paragraph', text: '현재메일 분석 기반 일정 제안입니다.' },
          { type: 'heading', level: 3, text: '일정 안건(요약)' },
          { type: 'unordered_list', items: [subject] },
          { type: 'heading', level: 3, text: '논의할 주요 내용' },
          { type: 'ordered_list', items: discussionItems },
          { type: 'heading', level: 3, text: '참석자 제안' },
          { type: 'unordered_list', items: attendeeItems },
          { type: 'paragraph', text: '아래 일정 카드에서 제목/시간/참석자를 확인 후 등록해 주세요.' },
        ],
      },
    };
  }

  function create() {
    return {
      buildMeetingSuggestionMessage: buildMeetingSuggestionMessage,
      buildMeetingSuggestionMetadata: buildMeetingSuggestionMetadata,
      buildSuggestedScheduleDefaults: buildSuggestedScheduleDefaults,
      buildCalendarSuggestionMessage: buildCalendarSuggestionMessage,
      buildCalendarSuggestionMetadata: buildCalendarSuggestionMetadata,
    };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneSendSuggestionFormatters = api;
})(typeof window !== 'undefined' ? window : globalThis);
