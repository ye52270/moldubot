(function initTaskpaneMessagesMeetingOptions(globalScope) {
  function create(options) {
    var escapeHtml = options.escapeHtml;
    var escapeAttr = options.escapeAttr;

    function mapOptions(items, renderItem) {
      return (Array.isArray(items) ? items : [])
        .map(renderItem)
        .filter(function (value) { return Boolean(value); })
        .join('');
    }

    function buildMeetingRoomBuildingOptions(buildings) {
      return mapOptions(buildings, function (building, index) {
        var value = String(building || '').trim();
        if (!value) return '';
        var selected = index === 0 ? ' selected' : '';
        return '<option value="' + escapeAttr(value) + '"' + selected + '>' + escapeHtml(value) + '</option>';
      });
    }

    function buildMeetingRoomFloorOptions(floors) {
      return mapOptions(floors, function (floor, index) {
        var value = Number(floor);
        if (!Number.isFinite(value)) return '';
        var selected = index === 0 ? ' selected' : '';
        return '<option value="' + String(value) + '"' + selected + '>' + String(value) + '층</option>';
      });
    }

    function buildMeetingRoomRoomOptions(rooms) {
      return mapOptions(rooms, function (room, index) {
        var roomName = String(room && room.room_name ? room.room_name : '').trim();
        if (!roomName) return '';
        var capacity = Number(room && room.capacity ? room.capacity : 0);
        var suffix = capacity > 0 ? ' (정원 ' + String(capacity) + ')' : '';
        var selected = index === 0 ? ' selected' : '';
        return '<option value="' + escapeAttr(roomName) + '"' + selected + '>' + escapeHtml(roomName + suffix) + '</option>';
      });
    }

    function buildMeetingTimeCandidateOptions(candidates, selectedValue) {
      return mapOptions(candidates, function (candidate) {
        if (!candidate || typeof candidate !== 'object') return '';
        var dateText = String(candidate.date || '').trim();
        var startText = String(candidate.start_time || '').trim();
        var endText = String(candidate.end_time || '').trim();
        if (!dateText || !startText || !endText) return '';
        var value = dateText + '|' + startText + '|' + endText;
        var label = String(candidate.label || '').trim() || (dateText + ' ' + startText + '-' + endText);
        var selected = value === selectedValue ? ' selected' : '';
        return '<option value="' + escapeAttr(value) + '"' + selected + '>' + escapeHtml(label) + '</option>';
      });
    }

    function buildMeetingRoomCandidateOptions(candidates, selectedValue) {
      return mapOptions(candidates, function (candidate) {
        if (!candidate || typeof candidate !== 'object') return '';
        var building = String(candidate.building || '').trim();
        var floor = Number(candidate.floor || 0);
        var roomName = String(candidate.room_name || '').trim();
        if (!building || !Number.isFinite(floor) || floor <= 0 || !roomName) return '';
        var value = building + '|' + String(floor) + '|' + roomName;
        var label = String(candidate.label || '').trim() || (building + ' ' + String(floor) + '층 ' + roomName);
        var selected = value === selectedValue ? ' selected' : '';
        return '<option value="' + escapeAttr(value) + '"' + selected + '>' + escapeHtml(label) + '</option>';
      });
    }

    return {
      buildMeetingRoomBuildingOptions: buildMeetingRoomBuildingOptions,
      buildMeetingRoomFloorOptions: buildMeetingRoomFloorOptions,
      buildMeetingRoomRoomOptions: buildMeetingRoomRoomOptions,
      buildMeetingTimeCandidateOptions: buildMeetingTimeCandidateOptions,
      buildMeetingRoomCandidateOptions: buildMeetingRoomCandidateOptions,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
    return;
  }
  globalScope.TaskpaneMessagesMeetingOptions = api;
})(typeof window !== 'undefined' ? window : globalThis);
