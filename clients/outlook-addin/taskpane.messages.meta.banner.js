/* ========================================
   MolduBot – Taskpane Messages Meta Banner
   ======================================== */

(function initTaskpaneMessagesMetaBanner(global) {
  function create(options) {
    var byId = options.byId;
    var escapeHtml = options.escapeHtml;
    var escapeAttr = options.escapeAttr || options.escapeHtml;
    var normalizeDisplayName = options.normalizeDisplayName;

    function extractRecipientsFromBodyText(bodyText) {
      var normalized = String(bodyText || '').replace(/\r/g, '\n');
      var matched = /To:\s*(.+?)(?:Cc:|Subject:|From:|$)/is.exec(normalized);
      if (!matched) return [];
      var raw = String(matched[1] || '').replace(/\n/g, ' ');
      var parts = raw.split(/[;,]/);
      var unique = [];
      parts.forEach(function (part) {
        var name = normalizeDisplayName(part);
        if (!name || unique.indexOf(name) >= 0) return;
        unique.push(name);
      });
      return unique;
    }

    function formatRecipientSummaryLabel(recipients) {
      var items = Array.isArray(recipients) ? recipients : [];
      var cleaned = items
        .map(function (item) { return normalizeDisplayName(item); })
        .filter(function (item) { return Boolean(item); });
      if (!cleaned.length) return '-';
      if (cleaned.length <= 2) return cleaned.join(', ');
      return cleaned.slice(0, 2).join(', ') + ' 외 ' + String(cleaned.length - 2) + '명';
    }

    function formatReceivedDateLabel(raw) {
      var value = String(raw || '').trim();
      if (!value) return '';
      var parsed = new Date(value);
      if (!Number.isFinite(parsed.getTime())) return value;
      var monthDay = new Intl.DateTimeFormat('ko-KR', {
        month: '2-digit',
        day: '2-digit',
      }).format(parsed).replace(/\.\s?/g, '.').replace(/\.$/, '');
      var time = new Intl.DateTimeFormat('ko-KR', {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
      }).format(parsed);
      return monthDay + ' ' + time;
    }

    function resolveImportanceBadges(mail) {
      var source = String(
        (mail && (mail.importance || mail.category)) || '',
      ).replace(/\s/g, '');
      if (!source) {
        return [{ key: 'normal', icon: '○', text: '일반' }];
      }
      if (
        source.indexOf('긴급') >= 0
        || source.indexOf('urgent') >= 0
        || source.indexOf('critical') >= 0
      ) {
        return [{ key: 'urgent', icon: '⚡', text: '긴급' }];
      }
      if (source.indexOf('중요') >= 0 || source.indexOf('important') >= 0 || source.indexOf('high') >= 0) {
        return [{ key: 'important', icon: '★', text: '중요' }];
      }
      if (source.indexOf('회신필요') >= 0 || source.indexOf('회신요망') >= 0 || source.indexOf('reply') >= 0) {
        return [{ key: 'reply', icon: '↩', text: '회신요망' }];
      }
      if (source.indexOf('일반') >= 0 || source.indexOf('normal') >= 0 || source.indexOf('보통') >= 0) {
        return [{ key: 'normal', icon: '○', text: '일반' }];
      }
      return [{ key: 'normal', icon: '○', text: '일반' }];
    }

    function buildImportanceBadgesHtml(mail) {
      var badges = resolveImportanceBadges(mail);
      if (!badges.length) return '';
      return '<div class="selected-mail-banner-badges">'
        + badges.map(function (badge) {
          return ''
            + '<span class="selected-mail-banner-badge selected-mail-banner-badge-' + badge.key + '">'
            +   '<span class="selected-mail-banner-badge-icon" aria-hidden="true">' + badge.icon + '</span>'
            +   '<span class="selected-mail-banner-badge-text">' + escapeHtml(badge.text) + '</span>'
            + '</span>';
        }).join('')
        + '</div>';
    }

    function ensureSelectedMailBannerNode() {
      var existing = byId('selectedMailBanner');
      if (existing) return existing;
      if (typeof document === 'undefined' || typeof document.createElement !== 'function') return null;
      var appRoot = document.querySelector('.app');
      if (!appRoot) return null;
      var toolbar = appRoot.querySelector('.chat-toolbar');
      var node = document.createElement('div');
      node.id = 'selectedMailBanner';
      node.className = 'selected-mail-banner';
      node.hidden = true;
      if (toolbar && toolbar.nextSibling) {
        appRoot.insertBefore(node, toolbar.nextSibling);
      } else if (toolbar) {
        appRoot.appendChild(node);
      } else {
        appRoot.insertBefore(node, appRoot.firstChild);
      }
      return node;
    }

    function renderSelectedMailBanner(mail) {
      var banner = ensureSelectedMailBannerNode();
      if (!banner) return;
      banner.className = 'selected-mail-banner';
      var item = mail && typeof mail === 'object' ? mail : {};
      var subject = String(item.subject || '').trim();
      if (!subject) {
        banner.innerHTML = '';
        banner.hidden = true;
        return;
      }
      var sender = normalizeDisplayName(item.fromDisplayName || item.fromAddress) || '-';
      var recipientsRaw = Array.isArray(item.recipients) && item.recipients.length
        ? item.recipients
        : extractRecipientsFromBodyText(item.bodyText || '');
      var recipientLabel = formatRecipientSummaryLabel(recipientsRaw);
      var dateLabel = formatReceivedDateLabel(item.receivedDate || '');
      var meta = sender + ' → ' + recipientLabel + (dateLabel ? ' · ' + dateLabel : '');
      var messageId = String(item.messageId || '').trim();
      var webLink = String(item.webLink || '').trim();
      var disabledAttr = messageId || webLink ? '' : ' disabled';
      var badgeHtml = buildImportanceBadgesHtml(item);
      banner.hidden = false;
      banner.innerHTML = ''
        + '<div class="selected-mail-banner-icon" aria-hidden="true">✉️</div>'
        + '<div class="selected-mail-banner-main">'
        +   '<div class="selected-mail-banner-subject">' + escapeHtml(subject) + '</div>'
        +   '<div class="selected-mail-banner-meta">' + escapeHtml(meta) + '</div>'
        +   badgeHtml
        + '</div>'
        + '<button type="button" class="selected-mail-open-btn" data-action="selected-mail-open" '
        +   'data-message-id="' + escapeAttr(messageId) + '" '
        +   'data-web-link="' + escapeAttr(webLink) + '"'
        +   disabledAttr + ' aria-label="선택 메일 열기" title="선택 메일 열기">'
        +   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        +     '<path d="M7 17L17 7"/><path d="M8 7h9v9"/>'
        +   '</svg>'
        + '</button>';
    }

    return {
      renderSelectedMailBanner: renderSelectedMailBanner,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneMessagesMetaBanner = api;
})(typeof window !== 'undefined' ? window : globalThis);
