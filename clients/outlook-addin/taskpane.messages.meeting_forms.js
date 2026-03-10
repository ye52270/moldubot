(function initTaskpaneMessagesMeetingForms(global) {
  function create(options) {
    var escapeAttr = options.escapeAttr;
    var escapeHtml = options.escapeHtml;
    var resolveTodayDateValue = options.resolveTodayDateValue;
    var toTrimmedCsv = options.toTrimmedCsv;
    var buildMeetingTimeCandidateOptions = options.buildMeetingTimeCandidateOptions;
    var buildMeetingRoomCandidateOptions = options.buildMeetingRoomCandidateOptions;

    function normalizeMeetingSchedulePreset(building, floor, roomName, defaults) {
      var preset = defaults && typeof defaults === 'object' ? defaults : {};
      var defaultDate = String(preset.date || '').trim() || resolveTodayDateValue();
      var defaultStart = String(preset.start_time || '').trim() || '10:00';
      var defaultEnd = String(preset.end_time || '').trim() || '11:00';
      return {
        building: String(building || '').trim(),
        floor: Number(floor) || 0,
        roomName: String(roomName || '').trim(),
        subject: String(preset.subject || '').trim(),
        date: defaultDate,
        start: defaultStart,
        end: defaultEnd,
        attendees: Math.max(1, Number(preset.attendee_count || 4)),
        timeCandidates: Array.isArray(preset.time_candidates) ? preset.time_candidates : [],
        roomCandidates: Array.isArray(preset.room_candidates) ? preset.room_candidates : [],
      };
    }

    function buildMeetingScheduleCandidateFields(preset) {
      var selectedTimeValue = preset.date + '|' + preset.start + '|' + preset.end;
      var selectedRoomValue = preset.building + '|' + String(preset.floor) + '|' + preset.roomName;
      return (
        (preset.timeCandidates.length
          ? '<label class="meeting-room-label">시간 제안' +
              '<select class="meeting-room-select" data-role="meeting-time-candidate-select" data-action="meeting-room-time-candidate-change" aria-label="시간 제안">' +
                buildMeetingTimeCandidateOptions(preset.timeCandidates, selectedTimeValue) +
              '</select>' +
            '</label>'
          : '') +
        (preset.roomCandidates.length
          ? '<label class="meeting-room-label">회의실 제안' +
              '<select class="meeting-room-select" data-role="meeting-room-candidate-select" data-action="meeting-room-candidate-change" aria-label="회의실 제안">' +
                buildMeetingRoomCandidateOptions(preset.roomCandidates, selectedRoomValue) +
              '</select>' +
            '</label>'
          : '')
      );
    }

    function buildMeetingScheduleInputFields(preset) {
      var roomDisplay = preset.building + ' ' + String(preset.floor) + '층 ' + preset.roomName;
      return (
        '<label class="meeting-room-label">회의실' +
          '<input type="text" class="meeting-room-input" data-role="meeting-room-display" value="' + escapeAttr(roomDisplay) + '" readonly />' +
        '</label>' +
        '<label class="meeting-room-label">날짜' +
          '<input type="date" class="meeting-room-input" data-role="meeting-date-input" value="' + escapeAttr(preset.date) + '" />' +
        '</label>' +
        '<label class="meeting-room-label">시작' +
          '<input type="time" class="meeting-room-input" data-role="meeting-start-input" value="' + escapeAttr(preset.start) + '" />' +
        '</label>' +
        '<label class="meeting-room-label">종료' +
          '<input type="time" class="meeting-room-input" data-role="meeting-end-input" value="' + escapeAttr(preset.end) + '" />' +
        '</label>' +
        '<label class="meeting-room-label">인원' +
          '<input type="number" class="meeting-room-input" data-role="meeting-attendee-input" min="1" value="' + escapeAttr(String(preset.attendees)) + '" />' +
        '</label>'
      );
    }

    function buildMeetingRoomScheduleCardBody(preset) {
      return (
        '<input type="hidden" data-role="meeting-building-select" value="' + escapeAttr(preset.building) + '" />' +
        '<input type="hidden" data-role="meeting-floor-select" value="' + escapeAttr(String(preset.floor)) + '" />' +
        '<input type="hidden" data-role="meeting-room-select" value="' + escapeAttr(preset.roomName) + '" />' +
        '<input type="hidden" data-role="meeting-subject-input" value="' + escapeAttr(preset.subject) + '" />' +
        buildMeetingScheduleCandidateFields(preset) +
        buildMeetingScheduleInputFields(preset)
      );
    }

    function normalizeCalendarPreset(defaults) {
      var preset = defaults && typeof defaults === 'object' ? defaults : {};
      return {
        subject: String(preset.subject || '').trim(),
        date: String(preset.date || '').trim() || resolveTodayDateValue(),
        start: String(preset.start_time || '').trim() || '10:00',
        end: String(preset.end_time || '').trim() || '11:00',
        body: String(preset.body || '').trim(),
        attendeesText: toTrimmedCsv(Array.isArray(preset.attendees) ? preset.attendees : []),
      };
    }

    function buildCalendarEventCardBody(preset) {
      return (
        '<div class="meeting-room-card-header">' +
          '<div class="meeting-room-card-title">일정 등록</div>' +
          '<button type="button" class="meeting-room-back-btn" data-action="calendar-event-cancel">취소</button>' +
        '</div>' +
        '<div class="meeting-room-form-grid">' +
          '<label class="meeting-room-label">제목' +
            '<input type="text" class="meeting-room-input" data-role="calendar-subject-input" value="' + escapeAttr(preset.subject) + '" placeholder="일정 제목" />' +
          '</label>' +
          '<label class="meeting-room-label">날짜' +
            '<input type="date" class="meeting-room-input" data-role="calendar-date-input" value="' + escapeAttr(preset.date) + '" />' +
          '</label>' +
          '<label class="meeting-room-label">시작' +
            '<input type="time" class="meeting-room-input" data-role="calendar-start-input" value="' + escapeAttr(preset.start) + '" />' +
          '</label>' +
          '<label class="meeting-room-label">종료' +
            '<input type="time" class="meeting-room-input" data-role="calendar-end-input" value="' + escapeAttr(preset.end) + '" />' +
          '</label>' +
          '<label class="meeting-room-label">참석자(쉼표 구분)' +
            '<input type="text" class="meeting-room-input" data-role="calendar-attendees-input" value="' + escapeAttr(preset.attendeesText) + '" placeholder="user1@contoso.com, user2@contoso.com" />' +
          '</label>' +
          '<label class="meeting-room-label">내용' +
            '<textarea class="meeting-room-input" data-role="calendar-body-input" rows="4" placeholder="일정 설명">' + escapeHtml(preset.body) + '</textarea>' +
          '</label>' +
        '</div>' +
        '<div class="report-confirm-actions">' +
          '<button type="button" class="btn-download" data-action="calendar-event-submit">등록</button>' +
        '</div>'
      );
    }

    return {
      normalizeMeetingSchedulePreset: normalizeMeetingSchedulePreset,
      buildMeetingRoomScheduleCardBody: buildMeetingRoomScheduleCardBody,
      normalizeCalendarPreset: normalizeCalendarPreset,
      buildCalendarEventCardBody: buildCalendarEventCardBody,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneMessagesMeetingForms = api;
})(typeof window !== 'undefined' ? window : globalThis);
