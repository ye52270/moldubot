(function initTaskpaneMessagesMetaBasicInfo(global) {
  function create(options) {
    var applyInlineFormatting = options.applyInlineFormatting;
    var normalizeHeadingToken = options.normalizeHeadingToken;
    var normalizeDisplayName = options.normalizeDisplayName;

    function formatBasicInfoDateOnly(raw) {
      var value = String(raw || '').trim();
      if (!value) return '';
      var isoPrefix = /^(\d{4}-\d{2}-\d{2})/.exec(value);
      if (isoPrefix) return isoPrefix[1];
      var dotted = /(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})/.exec(value);
      if (dotted) {
        var month = String(dotted[2]).padStart(2, '0');
        var day = String(dotted[3]).padStart(2, '0');
        return dotted[1] + '-' + month + '-' + day;
      }
      var parsed = new Date(value);
      if (Number.isFinite(parsed.getTime())) {
        var year = String(parsed.getFullYear()).padStart(4, '0');
        var month2 = String(parsed.getMonth() + 1).padStart(2, '0');
        var day2 = String(parsed.getDate()).padStart(2, '0');
        return year + '-' + month2 + '-' + day2;
      }
      return value;
    }

    function splitBasicInfoPeople(raw) {
      var value = String(raw || '').trim();
      if (!value) return [];
      var parts = value.split(/[;,]/);
      var names = [];
      parts.forEach(function (part) {
        var name = normalizeDisplayName(part);
        if (!name || names.indexOf(name) >= 0) return;
        names.push(name);
      });
      return names;
    }

    function formatBasicInfoPerson(raw) {
      var names = splitBasicInfoPeople(raw);
      return names.length ? names[0] : '';
    }

    function formatBasicInfoPeople(raw) {
      var names = splitBasicInfoPeople(raw);
      if (!names.length) return '';
      if (names.length <= 2) return names.join(', ');
      return names.slice(0, 2).join(', ') + ' 외 ' + String(names.length - 2) + '명';
    }

    function normalizeRouteFlowDisplay(raw) {
      var value = String(raw || '').trim();
      if (!value) return '';
      var unquoted = value.replace(/^["'\s]+|["'\s]+$/g, '');
      if (!unquoted) return '';
      var chunks = unquoted.split(/(?:%%|\|\|)/);
      var normalized = chunks.map(function (chunk) {
        var token = String(chunk || '').trim();
        if (!token) return '';
        return token
          .replace(/::/g, ' · ')
          .replace(/=>/g, ' → ')
          .replace(/\s*↠\s*/g, ' ↠ ')
          .replace(/\s+/g, ' ')
          .trim();
      }).filter(function (token) { return Boolean(token); });
      return normalized.join(' ↠ ');
    }

    function formatRouteDateLabel(rawDate) {
      var value = String(rawDate || '').trim();
      if (!value) return '';
      var matched = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
      if (matched) return matched[2] + '.' + matched[3];
      return value;
    }

    function buildRouteNodeInitial(name) {
      var value = String(name || '').trim();
      if (!value) return '•';
      var korean = /[가-힣]/.exec(value);
      if (korean && korean[0]) return korean[0];
      return value.charAt(0).toUpperCase();
    }

    function splitRoutePeople(token) {
      var source = String(token || '').trim();
      if (!source) return [];
      var values = source.split(/[;,]/).map(function (item) { return String(item || '').trim(); }).filter(function (item) { return Boolean(item); });
      var names = [];
      values.forEach(function (item) {
        var normalized = normalizeDisplayName(item);
        if (!normalized || names.indexOf(normalized) >= 0) return;
        names.push(normalized);
      });
      if (names.length) return names;
      return [source];
    }

    function parseRouteTimelineNodes(raw) {
      var source = String(raw || '').trim();
      if (!source) return [];
      var chunks = source.split(/(?:%%|\|\|)/).map(function (item) { return String(item || '').trim(); }).filter(function (item) { return Boolean(item); });
      var nodes = [];
      chunks.forEach(function (chunk) {
        var date = '';
        var payload = chunk;
        var dated = /^(\d{4}-\d{2}-\d{2})\s*::\s*(.+)$/.exec(chunk);
        if (dated) {
          date = String(dated[1] || '').trim();
          payload = String(dated[2] || '').trim();
        }
        var segments = payload.split(/\s*=>\s*/).map(function (item) { return String(item || '').trim(); }).filter(function (item) { return Boolean(item); });
        if (!segments.length) {
          segments = payload.split(/\s*[→↠]\s*/).map(function (item) { return String(item || '').trim(); }).filter(function (item) { return Boolean(item); });
        }
        if (!segments.length) return;
        segments.forEach(function (segment) {
          splitRoutePeople(segment).forEach(function (name) {
            if (!name) return;
            var previous = nodes.length ? nodes[nodes.length - 1] : null;
            if (previous && previous.name === name) {
              if (!previous.date && date) previous.date = date;
              return;
            }
            nodes.push({ name: name, date: date });
          });
        });
      });
      return nodes;
    }

    function buildRouteTimelineHtml(raw) {
      var nodes = parseRouteTimelineNodes(raw);
      if (!nodes.length) return '';
      if (nodes.length === 1) {
        var only = nodes[0];
        return '<div class="basic-info-route-log"><span class="basic-info-route-log-label">커뮤니케이션 흐름</span><span class="basic-info-route-log-value">' + applyInlineFormatting(only.name) + '</span></div>';
      }
      var lineHtml = nodes.map(function (node, index) {
        var isLast = index === (nodes.length - 1);
        return (
          '<div class="basic-info-route-node' + (isLast ? ' is-active' : '') + '">' +
            '<span class="basic-info-route-dot">' + applyInlineFormatting(buildRouteNodeInitial(node.name)) + '</span>' +
            '<span class="basic-info-route-name">' + applyInlineFormatting(node.name) + '</span>' +
            '<span class="basic-info-route-date">' + applyInlineFormatting(formatRouteDateLabel(node.date) || (isLast ? '현재' : '')) + '</span>' +
          '</div>' +
          (isLast ? '' : '<span class="basic-info-route-arrow">→</span>')
        );
      }).join('');
      return (
        '<div class="basic-info-route-timeline">' +
          '<div class="basic-info-route-title">커뮤니케이션 흐름</div>' +
          '<div class="basic-info-route-track">' + lineHtml + '</div>' +
        '</div>'
      );
    }

    function renderBasicInfoRows(headers, rows) {
      var tableHeaders = Array.isArray(headers) ? headers : [];
      var tableRows = Array.isArray(rows) ? rows : [];
      if (!tableRows.length) return '';
      var routeFlowRaw = '';
      var items = tableRows.map(function (row) {
        var cells = Array.isArray(row) ? row : [];
        var key = String(cells[0] || '').trim();
        var value = String(cells[1] || '').trim();
        var keyToken = normalizeHeadingToken(key);
        if (keyToken.indexOf('커뮤니케이션흐름') >= 0 || keyToken.indexOf('메일흐름') >= 0 || keyToken === '흐름') {
          routeFlowRaw = value;
          return '';
        }
        if (!key && !value) return '';
        return '<div class="basic-info-row"><div class="basic-info-key">' + applyInlineFormatting(key || tableHeaders[0] || '항목') + '</div><div class="basic-info-value">' + applyInlineFormatting(value || '-') + '</div></div>';
      }).filter(function (value) { return Boolean(value); }).join('');
      var routeFlowDisplay = normalizeRouteFlowDisplay(routeFlowRaw);
      var flowBlock = '';
      if (routeFlowRaw) {
        flowBlock = buildRouteTimelineHtml(routeFlowRaw);
      } else if (routeFlowDisplay) {
        flowBlock = '<div class="basic-info-route-log"><span class="basic-info-route-log-label">커뮤니케이션 흐름</span><span class="basic-info-route-log-value">' + applyInlineFormatting(routeFlowDisplay) + '</span></div>';
      }
      if (!items && !flowBlock) return '';
      return '<div class="basic-info-list"><div class="basic-info-card">' + items + flowBlock + '</div></div>';
    }

    return { renderBasicInfoRows: renderBasicInfoRows };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  global.TaskpaneMessagesMetaBasicInfo = api;
})(typeof window !== 'undefined' ? window : globalThis);
