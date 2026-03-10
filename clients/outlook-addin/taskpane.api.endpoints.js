/* ========================================
   MolduBot – Taskpane Chat API Endpoints
   ======================================== */

(function initTaskpaneApiEndpoints(global) {
  function createEndpointApi(options) {
    const fetchRef = options.fetchRef;
    const buildJsonHeaders = options.buildJsonHeaders;

    async function listMeetingRoomBuildings() {
      const response = await fetchRef('/api/meeting-rooms', {
        headers: buildJsonHeaders(false),
      });
      if (!response.ok) throw new Error('meeting rooms request failed: ' + response.status);
      const payload = await response.json();
      const items = payload && Array.isArray(payload.items) ? payload.items : [];
      return items
        .map(function (item) { return String(item && item.building ? item.building : '').trim(); })
        .filter(function (item) { return Boolean(item); });
    }

    async function listMeetingRoomFloors(building) {
      const query = new URLSearchParams({ building: String(building || '') });
      const response = await fetchRef('/api/meeting-rooms?' + query.toString(), {
        headers: buildJsonHeaders(false),
      });
      if (!response.ok) throw new Error('meeting floors request failed: ' + response.status);
      const payload = await response.json();
      const items = payload && Array.isArray(payload.items) ? payload.items : [];
      return items
        .map(function (item) { return Number(item && item.floor); })
        .filter(function (value) { return Number.isFinite(value); });
    }

    async function listMeetingRooms(building, floor) {
      const query = new URLSearchParams({
        building: String(building || ''),
        floor: String(Number(floor || 0)),
      });
      const response = await fetchRef('/api/meeting-rooms?' + query.toString(), {
        headers: buildJsonHeaders(false),
      });
      if (!response.ok) throw new Error('meeting room list request failed: ' + response.status);
      const payload = await response.json();
      const items = payload && Array.isArray(payload.items) ? payload.items : [];
      return items
        .filter(function (item) { return item && typeof item === 'object'; })
        .map(function (item) {
          return {
            room_name: String(item.room_name || '').trim(),
            capacity: Number(item.capacity || 0),
          };
        })
        .filter(function (item) { return Boolean(item.room_name); });
    }

    async function bookMeetingRoom(payload) {
      const response = await fetchRef('/api/meeting-rooms/book', {
        method: 'POST',
        headers: buildJsonHeaders(true),
        body: JSON.stringify(payload || {}),
      });
      if (!response.ok) throw new Error('meeting room booking request failed: ' + response.status);
      return response.json();
    }

    async function suggestMeetingFromCurrentMail(messageId, mailboxUser) {
      const response = await fetchRef('/api/meeting-rooms/suggest-from-current-mail', {
        method: 'POST',
        headers: buildJsonHeaders(true),
        body: JSON.stringify({
          message_id: String(messageId || '').trim(),
          mailbox_user: String(mailboxUser || '').trim(),
        }),
      });
      if (!response.ok) throw new Error('meeting suggestion request failed: ' + response.status);
      return response.json();
    }

    async function suggestCalendarFromCurrentMail(messageId, mailboxUser) {
      const response = await fetchRef('/api/calendar-events/suggest-from-current-mail', {
        method: 'POST',
        headers: buildJsonHeaders(true),
        body: JSON.stringify({
          message_id: String(messageId || '').trim(),
          mailbox_user: String(mailboxUser || '').trim(),
        }),
      });
      if (!response.ok) throw new Error('calendar suggestion request failed: ' + response.status);
      return response.json();
    }

    async function createCalendarEvent(payload) {
      const response = await fetchRef('/api/calendar-events/create', {
        method: 'POST',
        headers: buildJsonHeaders(true),
        body: JSON.stringify(payload || {}),
      });
      if (!response.ok) throw new Error('calendar event request failed: ' + response.status);
      return response.json();
    }

    async function requestChatConfirm(payload) {
      const response = await fetchRef('/search/chat/confirm', {
        method: 'POST',
        headers: buildJsonHeaders(true),
        body: JSON.stringify(payload || {}),
      });
      if (!response.ok) throw new Error('chat confirm request failed: ' + response.status);
      return response.json();
    }

    async function listPromiseProjects() {
      const response = await fetchRef('/api/promise/projects', { headers: buildJsonHeaders(false) });
      if (!response.ok) throw new Error('promise projects request failed: ' + response.status);
      const payload = await response.json();
      return payload && Array.isArray(payload.projects) ? payload.projects : [];
    }

    async function listPromiseSummaries() {
      const response = await fetchRef('/api/promise/summaries', { headers: buildJsonHeaders(false) });
      if (!response.ok) throw new Error('promise summaries request failed: ' + response.status);
      const payload = await response.json();
      return payload && Array.isArray(payload.items) ? payload.items : [];
    }

    async function getPromiseProjectSummary(projectNumber) {
      const response = await fetchRef('/api/promise/projects/' + encodeURIComponent(String(projectNumber || '').trim()) + '/summary', {
        headers: buildJsonHeaders(false),
      });
      if (!response.ok) throw new Error('promise summary request failed: ' + response.status);
      return response.json();
    }

    async function listPromiseDrafts() {
      const response = await fetchRef('/api/promise/drafts', { headers: buildJsonHeaders(false) });
      if (!response.ok) throw new Error('promise drafts request failed: ' + response.status);
      const payload = await response.json();
      return payload && Array.isArray(payload.drafts) ? payload.drafts : [];
    }

    async function submitPromiseDraft(payload) {
      const response = await fetchRef('/api/promise/drafts', {
        method: 'POST',
        headers: buildJsonHeaders(true),
        body: JSON.stringify(payload || {}),
      });
      if (!response.ok) throw new Error('promise draft request failed: ' + response.status);
      return response.json();
    }

    async function listFinanceProjects() {
      const response = await fetchRef('/api/finance/projects', { headers: buildJsonHeaders(false) });
      if (!response.ok) throw new Error('finance projects request failed: ' + response.status);
      const payload = await response.json();
      return payload && Array.isArray(payload.projects) ? payload.projects : [];
    }

    async function getFinanceProjectBudget(projectNumber) {
      const response = await fetchRef('/api/finance/projects/' + encodeURIComponent(String(projectNumber || '').trim()) + '/budget', {
        headers: buildJsonHeaders(false),
      });
      if (!response.ok) throw new Error('finance budget request failed: ' + response.status);
      return response.json();
    }

    async function submitFinanceClaim(payload) {
      const response = await fetchRef('/api/finance/claims', {
        method: 'POST',
        headers: buildJsonHeaders(true),
        body: JSON.stringify(payload || {}),
      });
      if (!response.ok) throw new Error('finance claim request failed: ' + response.status);
      return response.json();
    }

    async function submitHrRequest(payload) {
      const response = await fetchRef('/api/myhr/requests', {
        method: 'POST',
        headers: buildJsonHeaders(true),
        body: JSON.stringify(payload || {}),
      });
      if (!response.ok) throw new Error('myhr request failed: ' + response.status);
      return response.json();
    }

    return {
      listMeetingRoomBuildings: listMeetingRoomBuildings,
      listMeetingRoomFloors: listMeetingRoomFloors,
      listMeetingRooms: listMeetingRooms,
      bookMeetingRoom: bookMeetingRoom,
      suggestMeetingFromCurrentMail: suggestMeetingFromCurrentMail,
      suggestCalendarFromCurrentMail: suggestCalendarFromCurrentMail,
      createCalendarEvent: createCalendarEvent,
      requestChatConfirm: requestChatConfirm,
      listPromiseProjects: listPromiseProjects,
      listPromiseSummaries: listPromiseSummaries,
      getPromiseProjectSummary: getPromiseProjectSummary,
      listPromiseDrafts: listPromiseDrafts,
      submitPromiseDraft: submitPromiseDraft,
      listFinanceProjects: listFinanceProjects,
      getFinanceProjectBudget: getFinanceProjectBudget,
      submitFinanceClaim: submitFinanceClaim,
      submitHrRequest: submitHrRequest,
    };
  }

  const api = { createEndpointApi: createEndpointApi };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  global.TaskpaneApiEndpoints = api;
})(typeof window !== 'undefined' ? window : globalThis);
