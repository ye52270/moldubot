(function initTaskpaneChatActionChangeHandlers(global) {
  function create(options) {
    const byId = options.byId;
    const chatApi = options.chatApi;
    const messageUi = options.messageUi;
    const state = options.state;
    const helperActions = options.helperActions;

    function handleChatAreaChange(event) {
      const target = event && event.target ? event.target : null;
      if (!target || !target.dataset) return;
      const action = String(target.dataset.action || '').trim();
      if (action === 'meeting-room-building-change') {
        if (!state.pendingMeetingRoomContext) return;
        const building = String(target.value || '').trim();
        if (!building) return;
        void helperActions.moveMeetingRoomToFloor(building);
        return;
      }
      if (action === 'meeting-room-floor-change') {
        if (!state.pendingMeetingRoomContext) return;
        const form = messageUi.getMeetingRoomBookingFormValues();
        const building = String(form && form.building ? form.building : '').trim();
        const floor = Number(target.value || 0);
        if (!building || !floor) return;
        void helperActions.moveMeetingRoomToRoom(building, floor);
        return;
      }
      if (action === 'meeting-room-room-change') {
        if (!state.pendingMeetingRoomContext) return;
        const form = messageUi.getMeetingRoomBookingFormValues();
        const building = String(form && form.building ? form.building : '').trim();
        const floor = Number(form && form.floor ? form.floor : 0);
        const roomName = String(target.value || '').trim();
        if (!building || !floor || !roomName) return;
        helperActions.moveMeetingRoomToSchedule(building, floor, roomName);
        return;
      }
      if (action === 'meeting-room-time-candidate-change') {
        const value = String(target.value || '').trim();
        const pieces = value.split('|');
        if (pieces.length !== 3) return;
        const targetArea = byId('chatArea');
        if (!targetArea || typeof targetArea.querySelector !== 'function') return;
        const dateInput = targetArea.querySelector('[data-role="meeting-date-input"]');
        const startInput = targetArea.querySelector('[data-role="meeting-start-input"]');
        const endInput = targetArea.querySelector('[data-role="meeting-end-input"]');
        if (dateInput) dateInput.value = String(pieces[0] || '').trim();
        if (startInput) startInput.value = String(pieces[1] || '').trim();
        if (endInput) endInput.value = String(pieces[2] || '').trim();
        return;
      }
      if (action === 'meeting-room-candidate-change') {
        const value = String(target.value || '').trim();
        const pieces = value.split('|');
        if (pieces.length !== 3) return;
        const building = String(pieces[0] || '').trim();
        const floor = Number(pieces[1] || 0);
        const roomName = String(pieces[2] || '').trim();
        if (!building || !floor || !roomName) return;
        const targetArea = byId('chatArea');
        if (!targetArea || typeof targetArea.querySelector !== 'function') return;
        const buildingInput = targetArea.querySelector('[data-role="meeting-building-select"]');
        const floorInput = targetArea.querySelector('[data-role="meeting-floor-select"]');
        const roomInput = targetArea.querySelector('[data-role="meeting-room-select"]');
        const roomDisplayInput = targetArea.querySelector('[data-role="meeting-room-display"]');
        if (buildingInput) buildingInput.value = building;
        if (floorInput) floorInput.value = String(floor);
        if (roomInput) roomInput.value = roomName;
        if (roomDisplayInput) roomDisplayInput.value = building + ' ' + String(floor) + '층 ' + roomName;
        if (state.pendingMeetingRoomContext) {
          state.pendingMeetingRoomContext.selectedBuilding = building;
          state.pendingMeetingRoomContext.selectedFloor = floor;
          state.pendingMeetingRoomContext.selectedRoom = roomName;
        }
        return;
      }
      if (action === 'finance-project-change') {
        const projectNumber = String(target.value || '').trim();
        if (!projectNumber) return;
        chatApi.getFinanceProjectBudget(projectNumber).then(function (budget) {
          messageUi.setFinanceBudgetText(
            '총액 ' + String(Number(budget.expense_budget_total || 0).toLocaleString('ko-KR')) +
            '원 / 잔여 ' + String(Number(budget.remaining_amount || 0).toLocaleString('ko-KR')) + '원'
          );
        }).catch(function () {
          messageUi.setFinanceBudgetText('예산 정보를 불러오지 못했습니다.');
        });
      }
    }

    return { handleChatAreaChange: handleChatAreaChange };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  global.TaskpaneChatActionChangeHandlers = api;
})(typeof window !== 'undefined' ? window : globalThis);
