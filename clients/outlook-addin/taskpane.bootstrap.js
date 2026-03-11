(function (globalScope) {
  const DEFAULT_SYNC_MS = 900;

  function create(options) {
    const windowRef = options.windowRef || (typeof window !== 'undefined' ? window : null);
    const documentRef = options.documentRef || (typeof document !== 'undefined' ? document : null);
    const byId = options.byId;
    const sender = options.sender;
    const messageUi = options.messageUi;
    const chatApi = options.chatApi;
    const state = options.state;
    const quickPrompts = options.quickPrompts;
    const chatActions = options.chatActions;
    const interactions = options.interactions;
    const runtimeHelpers = options.runtimeHelpers;
    const selectionController = options.selectionController;
    const shortId = options.shortId;
    const logClientEvent = options.logClientEvent;
    const uiBuild = String(options.uiBuild || 'unknown');
    const syncMs = Number(options.selectedMailSyncMs || DEFAULT_SYNC_MS);
    const openEvalPage = typeof options.openEvalPage === 'function' ? options.openEvalPage : function () {};
    const setSendingState = typeof options.setSendingState === 'function' ? options.setSendingState : function () {};
    const fetchFn = typeof options.fetchImpl === 'function'
      ? options.fetchImpl
      : (typeof fetch === 'function' ? fetch : null);

    let isBootstrapped = false;
    let selectedMailSyncTimer = null;
    let lastSyncedSelectionMailId = '';
    let shortcutChipHost = null;

    function parseLeadingShortcutTokens(text) {
      const raw = String(text || '').trim();
      const tokens = [];
      let remaining = raw;
      while (remaining) {
        const matched = /^([/@])([^\s]+)/.exec(remaining);
        if (!matched) break;
        const prefix = String(matched[1] || '');
        const value = String(matched[2] || '').trim();
        if (value) {
          tokens.push({
            prefix: prefix,
            value: value,
            kind: prefix === '@' ? 'app' : 'skill',
          });
        }
        remaining = String(remaining.slice(matched[0].length) || '').trimStart();
      }
      return tokens;
    }

    function ensureShortcutChipHost() {
      if (shortcutChipHost) return shortcutChipHost;
      if (!documentRef || typeof documentRef.querySelector !== 'function') return null;
      const inputArea = documentRef.querySelector('.input-area');
      const inputWrapper = documentRef.querySelector('.input-wrapper');
      if (!inputArea || !inputWrapper || typeof documentRef.createElement !== 'function') return null;
      const host = documentRef.createElement('div');
      host.className = 'composer-shortcut-chips';
      host.setAttribute('hidden', 'hidden');
      host.setAttribute('aria-hidden', 'true');
      inputArea.insertBefore(host, inputWrapper);
      shortcutChipHost = host;
      return shortcutChipHost;
    }

    function renderShortcutChips(inputValue) {
      const host = ensureShortcutChipHost();
      if (!host) return;
      const tokens = parseLeadingShortcutTokens(inputValue);
      if (!tokens.length) {
        host.innerHTML = '';
        host.setAttribute('hidden', 'hidden');
        host.setAttribute('aria-hidden', 'true');
        return;
      }
      const chips = tokens.map(function (token) {
        const label = token.prefix + token.value;
        return (
          '<span class="composer-shortcut-chip ' +
          (token.kind === 'app' ? 'is-app' : 'is-skill') +
          '">' +
          escapeHtml(label) +
          '</span>'
        );
      }).join('');
      host.innerHTML = chips;
      host.removeAttribute('hidden');
      host.setAttribute('aria-hidden', 'false');
    }

    async function fetchSelectedMailContext(selectionContext) {
      const emailId = String(selectionContext && selectionContext.emailId ? selectionContext.emailId : '').trim();
      const mailboxUser = String(selectionContext && selectionContext.mailboxUser ? selectionContext.mailboxUser : '').trim();
      if (!emailId || !mailboxUser || !fetchFn) {
        messageUi.renderSelectedMailBanner(null);
        return;
      }
      const response = await fetchFn('/mail/context', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message_id: emailId,
          mailbox_user: mailboxUser,
        }),
      });
      if (!response || !response.ok) {
        messageUi.renderSelectedMailBanner(null);
        return;
      }
      const payload = await response.json();
      const mail = payload && payload.mail && typeof payload.mail === 'object' ? payload.mail : null;
      if (!mail) {
        messageUi.renderSelectedMailBanner(null);
        return;
      }
      messageUi.renderSelectedMailBanner({
        messageId: String(mail.message_id || ''),
        subject: String(mail.subject || ''),
        fromAddress: String(mail.from_address || ''),
        fromDisplayName: String(mail.from_display_name || ''),
        recipients: Array.isArray(mail.to_recipients) ? mail.to_recipients : [],
        receivedDate: String(mail.received_date || ''),
        bodyText: String(mail.body_text || ''),
        webLink: String(mail.web_link || ''),
        importance: String(mail.importance || ''),
        category: String(mail.category || ''),
      });
    }

    function startSelectedMailBannerSync() {
      if (!windowRef || selectedMailSyncTimer) return;
      selectedMailSyncTimer = windowRef.setInterval(function () {
        const snapshot = selectionController.getSelectionStateSnapshot();
        const nextEmailId = String(snapshot && snapshot.cachedEmailId ? snapshot.cachedEmailId : '').trim();
        const nextMailboxUser = String(snapshot && snapshot.cachedMailboxUser ? snapshot.cachedMailboxUser : '').trim();
        if (!nextEmailId || !nextMailboxUser) {
          if (lastSyncedSelectionMailId) {
            lastSyncedSelectionMailId = '';
            messageUi.renderSelectedMailBanner(null);
          }
          return;
        }
        if (nextEmailId === lastSyncedSelectionMailId) return;
        lastSyncedSelectionMailId = nextEmailId;
        void fetchSelectedMailContext({
          emailId: nextEmailId,
          mailboxUser: nextMailboxUser,
        });
      }, syncMs);
    }

    function bindUi() {
      const sendBtn = byId('sendBtn');
      const input = byId('chatInput');
      const newSessionBtn = byId('newSessionBtn');
      const openEvalBtn = byId('openEvalBtn');
      const marketPlusBtn = byId('marketPlusBtn');
      if (sendBtn) sendBtn.addEventListener('click', sender.sendMessage);
      if (input) {
        const currentPlaceholder = String(input.getAttribute('placeholder') || '').trim();
        if (!currentPlaceholder) {
          input.setAttribute('placeholder', '메시지를 입력하세요. /로 스킬, @로 앱을 선택할 수 있습니다.');
        }
        input.addEventListener('keydown', function (event) {
          if (quickPrompts && quickPrompts.handleKeydown(event)) {
            if (windowRef && typeof windowRef.setTimeout === 'function') {
              windowRef.setTimeout(function () {
                renderShortcutChips(input.value);
              }, 0);
            }
            return;
          }
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sender.sendMessage();
          }
        });
        input.addEventListener('input', function () {
          renderShortcutChips(input.value);
        });
        input.addEventListener('focus', function () {
          renderShortcutChips(input.value);
        });
        if (quickPrompts && typeof quickPrompts.bindInput === 'function') {
          quickPrompts.bindInput(input);
        }
      }
      if (newSessionBtn) {
        newSessionBtn.addEventListener('click', function () {
          messageUi.resetSession();
          if (chatApi && typeof chatApi.resetThread === 'function') chatApi.resetThread();
          if (state && typeof state.clearExecutedNextActions === 'function') state.clearExecutedNextActions();
        });
      }
      if (openEvalBtn) openEvalBtn.addEventListener('click', openEvalPage);
      if (marketPlusBtn) {
        if (quickPrompts && typeof quickPrompts.bindPlusButton === 'function') {
          quickPrompts.bindPlusButton(marketPlusBtn);
        } else {
          marketPlusBtn.addEventListener('click', function () {
            messageUi.addMessage('assistant', '현재 마켓 기능은 준비 중입니다.');
          });
        }
      }

      function handleSelectedMailOpen(event) {
        const target = event && event.target ? event.target : null;
        const button = target && target.closest
          ? target.closest('[data-action="selected-mail-open"]')
          : null;
        if (!button) return;
        if (event && typeof event.preventDefault === 'function') {
          event.preventDefault();
        }
        const messageId = String(button.dataset.messageId || '').trim();
        if (!messageId) return;
        runtimeHelpers.openEvidenceMail(messageId).catch(function () {
          logClientEvent('warning', 'selected_mail_open_failed', {
            message_id_present: Boolean(messageId),
          });
        });
      }

      const selectedMailBanner = byId('selectedMailBanner');
      if (selectedMailBanner) {
        selectedMailBanner.addEventListener('click', handleSelectedMailOpen);
      }
      if (documentRef && typeof documentRef.addEventListener === 'function') {
        documentRef.addEventListener('click', handleSelectedMailOpen);
        documentRef.addEventListener('click', function (event) {
          const target = event && event.target && event.target.closest
            ? event.target.closest('[data-role="hub-shortcut-item"]')
            : null;
          if (!target || !input || !windowRef || typeof windowRef.setTimeout !== 'function') return;
          windowRef.setTimeout(function () {
            renderShortcutChips(input.value);
          }, 0);
        });
      }

      chatActions.bindChatAreaActions();
      interactions.bindMessageActions();
    }

    function bootstrap() {
      if (isBootstrapped) return;
      isBootstrapped = true;

      bindUi();
      logClientEvent('info', 'ui_build_loaded', { build: uiBuild });
      messageUi.syncWelcomeLayoutState();
      void selectionController.observeSelectionChanges();
      selectionController.startSelectionPolling();
      selectionController.clearSelectionCache('bootstrap');

      selectionController.resolveSelectionContextOnce().then(function (context) {
        if (context.emailId || context.mailboxUser) {
          selectionController.setCachedSelectionContextForTest(context);
          void fetchSelectedMailContext(context);
          lastSyncedSelectionMailId = String(context.emailId || '').trim();
        }
        logClientEvent('info', 'selection_context_bootstrap', {
          email_id_present: Boolean(context.emailId),
          mailbox_user_present: Boolean(context.mailboxUser),
          reason: String(context.reason || ''),
          email_id: shortId(context.emailId),
          direct_item_id: shortId(context.directItemId || ''),
          async_item_id: shortId(context.asyncItemId || ''),
          selected_item_id: shortId(context.selectedItemId || ''),
        });
      }).catch(function () {
        return null;
      });
      startSelectedMailBannerSync();
    }

    return {
      bootstrap: bootstrap,
      fetchSelectedMailContext: fetchSelectedMailContext,
      _isBootstrapped: function () { return isBootstrapped; },
    };
  }

  const exported = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = exported;
    return;
  }
  globalScope.TaskpaneBootstrap = exported;
})(typeof window !== 'undefined' ? window : globalThis);
