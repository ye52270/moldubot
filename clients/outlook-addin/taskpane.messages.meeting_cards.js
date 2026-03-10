(function initTaskpaneMessagesMeetingCards(global) {
  var cardDomApi = global.TaskpaneMessagesCardDom || null;
  if (!cardDomApi && typeof module !== 'undefined' && module.exports && typeof require === 'function') {
    try {
      cardDomApi = require('./taskpane.messages.card_dom.js');
    } catch (error) {
      cardDomApi = null;
    }
  }
  var meetingFormsApi = global.TaskpaneMessagesMeetingForms || null;
  if (!meetingFormsApi && typeof module !== 'undefined' && module.exports && typeof require === 'function') {
    try {
      meetingFormsApi = require('./taskpane.messages.meeting_forms.js');
    } catch (error) {
      meetingFormsApi = null;
    }
  }
  var meetingOptionsApi = global.TaskpaneMessagesMeetingOptions || null;
  if (!meetingOptionsApi && typeof module !== 'undefined' && module.exports && typeof require === 'function') {
    try {
      meetingOptionsApi = require('./taskpane.messages.meeting_options.js');
    } catch (error) {
      meetingOptionsApi = null;
    }
  }

  function create(options) {
    var byId = options.byId;
    var escapeHtml = options.escapeHtml;
    var escapeAttr = options.escapeAttr;
    var scrollToBottom = options.scrollToBottom;
    var removeWelcomeStateIfExists = options.removeWelcomeStateIfExists;

    var cardDom = cardDomApi && typeof cardDomApi.create === 'function'
      ? cardDomApi.create({ byId: byId })
      : null;
    if (!cardDom) return {};
    var meetingOptions = meetingOptionsApi && typeof meetingOptionsApi.create === 'function'
      ? meetingOptionsApi.create({ escapeHtml: escapeHtml, escapeAttr: escapeAttr })
      : null;
    if (!meetingOptions) return {};

    function resolveTodayDateValue() {
      var today = new Date();
      return [
        String(today.getFullYear()),
        String(today.getMonth() + 1).padStart(2, '0'),
        String(today.getDate()).padStart(2, '0'),
      ].join('-');
    }

    function clearMeetingRoomCards() {
      cardDom.removeCardsBySelector('.meeting-room-confirm-message');
    }

    function clearCalendarEventCards() {
      cardDom.removeCardsBySelector('.calendar-confirm-message');
    }

    function clearMeetingBookingTransientMessages() {
      var chatArea = cardDom.getChatArea();
      if (!chatArea || typeof chatArea.querySelectorAll !== 'function') return;
      clearMeetingRoomCards();
      clearCalendarEventCards();
      var messages = chatArea.querySelectorAll('.message.assistant');
      messages.forEach(function (node) {
        if (!node || typeof node.querySelector !== 'function') return;
        if (node.querySelector('.hitl-confirm-block') || node.classList.contains('report-ready-message')) {
          if (typeof node.remove === 'function') node.remove();
        }
      });
    }

    function buildMeetingRoomHeader(title, backAction) {
      return (
        '<div class="meeting-room-card-header">' +
          '<div class="meeting-room-card-title">' + escapeHtml(String(title || '')) + '</div>' +
          '<button type="button" class="meeting-room-back-btn" data-action="' + escapeAttr(String(backAction || '')) + '">돌아가기</button>' +
        '</div>'
      );
    }

    var meetingForms = meetingFormsApi && typeof meetingFormsApi.create === 'function'
      ? meetingFormsApi.create({
          escapeAttr: escapeAttr,
          escapeHtml: escapeHtml,
          resolveTodayDateValue: resolveTodayDateValue,
          toTrimmedCsv: function (values) {
            return (Array.isArray(values) ? values : [])
              .map(function (item) { return String(item || '').trim(); })
              .filter(function (item) { return Boolean(item); })
              .join(', ');
          },
          buildMeetingTimeCandidateOptions: meetingOptions.buildMeetingTimeCandidateOptions,
          buildMeetingRoomCandidateOptions: meetingOptions.buildMeetingRoomCandidateOptions,
        })
      : null;

    function insertMeetingRoomCard(title, backAction, bodyHtml) {
      var chatArea = cardDom.getChatArea();
      if (!chatArea) return;
      removeWelcomeStateIfExists();
      clearMeetingRoomCards();
      cardDom.appendAssistantCard(
        chatArea,
        'meeting-room-confirm-message',
        'report-confirm-card meeting-room-confirm-card',
        buildMeetingRoomHeader(title, backAction) +
          '<div class="meeting-room-form-grid">' + bodyHtml + '</div>'
      );
      scrollToBottom();
    }

    function addMeetingRoomBuildingCard(buildings) {
      insertMeetingRoomCard(
        '건물',
        'meeting-room-book-cancel',
        '<div class="meeting-room-label">' +
            '<select class="meeting-room-select" data-role="meeting-building-select" data-action="meeting-room-building-change" aria-label="건물">' +
            meetingOptions.buildMeetingRoomBuildingOptions(buildings) +
          '</select>' +
        '</div>'
      );
    }

    function addMeetingRoomFloorCard(building, floors) {
      insertMeetingRoomCard(
        '층',
        'meeting-room-back-to-building',
        '<input type="hidden" data-role="meeting-building-select" value="' + escapeAttr(String(building || '').trim()) + '" />' +
        '<div class="meeting-room-label">' +
          '<select class="meeting-room-select" data-role="meeting-floor-select" data-action="meeting-room-floor-change" aria-label="층">' +
            meetingOptions.buildMeetingRoomFloorOptions(floors) +
          '</select>' +
        '</div>'
      );
    }

    function addMeetingRoomDetailCard(building, floor, rooms) {
      insertMeetingRoomCard(
        '회의실',
        'meeting-room-back-to-floor',
        '<input type="hidden" data-role="meeting-building-select" value="' + escapeAttr(String(building || '').trim()) + '" />' +
        '<input type="hidden" data-role="meeting-floor-select" value="' + escapeAttr(String(Number(floor) || 0)) + '" />' +
        '<div class="meeting-room-label">' +
          '<select class="meeting-room-select" data-role="meeting-room-select" data-action="meeting-room-room-change" aria-label="회의실">' +
            meetingOptions.buildMeetingRoomRoomOptions(rooms) +
          '</select>' +
        '</div>'
      );
    }

    function addMeetingRoomScheduleCard(building, floor, roomName, defaults) {
      if (!meetingForms) return;
      var preset = meetingForms.normalizeMeetingSchedulePreset(building, floor, roomName, defaults);
      insertMeetingRoomCard(
        '일정',
        'meeting-room-back-to-room',
        meetingForms.buildMeetingRoomScheduleCardBody(preset) +
        '<div class="report-confirm-actions">' +
          '<button type="button" class="btn-download" data-action="meeting-room-book-confirm">예약</button>' +
        '</div>'
      );
    }

    function addMeetingRoomBookingCard(buildings) {
      addMeetingRoomBuildingCard(buildings);
    }

    function setMeetingRoomFloorOptions(floors) {
      var chatArea = cardDom.getChatArea();
      if (!chatArea) return;
      var select = chatArea.querySelector('[data-role="meeting-floor-select"]');
      if (!select) return;
      select.innerHTML = meetingOptions.buildMeetingRoomFloorOptions(floors);
    }

    function setMeetingRoomOptions(rooms) {
      var chatArea = cardDom.getChatArea();
      if (!chatArea) return;
      var select = chatArea.querySelector('[data-role="meeting-room-select"]');
      if (!select) return;
      select.innerHTML = meetingOptions.buildMeetingRoomRoomOptions(rooms);
    }

    function getMeetingRoomBookingFormValues() {
      var chatArea = cardDom.getChatArea();
      if (!chatArea) return null;
      var building = chatArea.querySelector('[data-role="meeting-building-select"]');
      var floor = chatArea.querySelector('[data-role="meeting-floor-select"]');
      var room = chatArea.querySelector('[data-role="meeting-room-select"]');
      var date = chatArea.querySelector('[data-role="meeting-date-input"]');
      var start = chatArea.querySelector('[data-role="meeting-start-input"]');
      var end = chatArea.querySelector('[data-role="meeting-end-input"]');
      var attendee = chatArea.querySelector('[data-role="meeting-attendee-input"]');
      var subject = chatArea.querySelector('[data-role="meeting-subject-input"]');
      return {
        building: String(building && building.value ? building.value : '').trim(),
        floor: Number(floor && floor.value ? floor.value : 0),
        room_name: String(room && room.value ? room.value : '').trim(),
        date: String(date && date.value ? date.value : '').trim(),
        start_time: String(start && start.value ? start.value : '').trim(),
        end_time: String(end && end.value ? end.value : '').trim(),
        attendee_count: Math.max(1, Number(attendee && attendee.value ? attendee.value : 1)),
        subject: String(subject && subject.value ? subject.value : '').trim(),
      };
    }

    function disableMeetingRoomBookingControls() {
      cardDom.disableControls(
        '.meeting-room-confirm-card [data-role], ' +
        '.meeting-room-confirm-card [data-action="meeting-room-building-change"], ' +
        '.meeting-room-confirm-card [data-action="meeting-room-floor-change"], ' +
        '.meeting-room-confirm-card [data-action="meeting-room-room-change"], ' +
        '.meeting-room-confirm-card [data-action="meeting-room-back-to-building"], ' +
        '.meeting-room-confirm-card [data-action="meeting-room-back-to-floor"], ' +
        '.meeting-room-confirm-card [data-action="meeting-room-back-to-room"], ' +
        '.meeting-room-confirm-card [data-action="meeting-room-book-cancel"], ' +
        '.meeting-room-confirm-card [data-action="meeting-room-book-confirm"]'
      );
    }

    function addCalendarEventCard(defaults) {
      if (!meetingForms) return;
      var preset = meetingForms.normalizeCalendarPreset(defaults);
      cardDom.withChatArea(function (chatArea) {
        removeWelcomeStateIfExists();
        clearCalendarEventCards();
        cardDom.appendAssistantCard(
          chatArea,
          'calendar-confirm-message',
          'report-confirm-card calendar-event-confirm-card',
          meetingForms.buildCalendarEventCardBody(preset)
        );
        scrollToBottom();
      });
    }

    function getCalendarEventFormValues() {
      var chatArea = cardDom.getChatArea();
      if (!chatArea) return null;
      var subject = chatArea.querySelector('[data-role="calendar-subject-input"]');
      var date = chatArea.querySelector('[data-role="calendar-date-input"]');
      var start = chatArea.querySelector('[data-role="calendar-start-input"]');
      var end = chatArea.querySelector('[data-role="calendar-end-input"]');
      var body = chatArea.querySelector('[data-role="calendar-body-input"]');
      var attendees = chatArea.querySelector('[data-role="calendar-attendees-input"]');
      var attendeeList = String(attendees && attendees.value ? attendees.value : '')
        .split(',')
        .map(function (item) { return String(item || '').trim(); })
        .filter(function (item) { return Boolean(item); });
      return {
        subject: String(subject && subject.value ? subject.value : '').trim(),
        date: String(date && date.value ? date.value : '').trim(),
        start_time: String(start && start.value ? start.value : '').trim(),
        end_time: String(end && end.value ? end.value : '').trim(),
        body: String(body && body.value ? body.value : '').trim(),
        attendees: attendeeList,
      };
    }

    function disableCalendarEventControls() {
      cardDom.disableControls(
        '.calendar-event-confirm-card [data-role], ' +
        '.calendar-event-confirm-card [data-action="calendar-event-submit"], ' +
        '.calendar-event-confirm-card [data-action="calendar-event-cancel"]'
      );
    }

    return {
      addMeetingRoomBuildingCard: addMeetingRoomBuildingCard,
      addMeetingRoomFloorCard: addMeetingRoomFloorCard,
      addMeetingRoomDetailCard: addMeetingRoomDetailCard,
      addMeetingRoomScheduleCard: addMeetingRoomScheduleCard,
      addMeetingRoomBookingCard: addMeetingRoomBookingCard,
      setMeetingRoomFloorOptions: setMeetingRoomFloorOptions,
      setMeetingRoomOptions: setMeetingRoomOptions,
      getMeetingRoomBookingFormValues: getMeetingRoomBookingFormValues,
      disableMeetingRoomBookingControls: disableMeetingRoomBookingControls,
      clearMeetingBookingTransientMessages: clearMeetingBookingTransientMessages,
      clearCalendarEventCards: clearCalendarEventCards,
      addCalendarEventCard: addCalendarEventCard,
      getCalendarEventFormValues: getCalendarEventFormValues,
      disableCalendarEventControls: disableCalendarEventControls,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneMessagesMeetingCards = api;
})(typeof window !== 'undefined' ? window : globalThis);
