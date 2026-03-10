(function initTaskpaneSelectionContext(globalScope) {
  function createContextResolver(options) {
    const windowRef = options.windowRef;
    const sleep = options.sleep;
    const config = options.config;
    const emptySelectionContext = options.emptySelectionContext;

    let officeReadyPromise = null;

    function readMailboxUser(mailbox) {
      const userProfile = mailbox && mailbox.userProfile ? mailbox.userProfile : {};
      return String(userProfile.emailAddress || '').trim();
    }

    function getOfficeMailbox() {
      if (!windowRef.Office || !windowRef.Office.context) return null;
      return windowRef.Office.context.mailbox || null;
    }

    async function ensureOfficeReady() {
      if (!windowRef.Office || typeof windowRef.Office.onReady !== 'function') {
        return;
      }
      if (!officeReadyPromise) {
        officeReadyPromise = new Promise(function (resolve) {
          let settled = false;
          const done = function () {
            if (settled) return;
            settled = true;
            resolve();
          };
          try {
            windowRef.Office.onReady(done);
          } catch (_error) {
            done();
            return;
          }
          setTimeout(done, config.officeReadyWaitMs);
        });
      }
      await officeReadyPromise;
    }

    function convertToRestId(mailbox, rawId) {
      const normalizedRawId = String(rawId || '').trim();
      if (!normalizedRawId) return '';
      const enums = windowRef.Office && windowRef.Office.MailboxEnums ? windowRef.Office.MailboxEnums : null;
      if (!mailbox || !mailbox.convertToRestId || !enums || !enums.RestVersion || !enums.RestVersion.v2_0) {
        return normalizedRawId;
      }
      try {
        return String(mailbox.convertToRestId(normalizedRawId, enums.RestVersion.v2_0) || normalizedRawId).trim();
      } catch (_error) {
        return normalizedRawId;
      }
    }

    function getItemIdAsync(mailbox) {
      return new Promise(function (resolve) {
        if (!mailbox || !mailbox.item || !mailbox.item.getItemIdAsync) {
          resolve('');
          return;
        }
        mailbox.item.getItemIdAsync(function (result) {
          if (!result || result.status !== windowRef.Office.AsyncResultStatus.Succeeded) {
            resolve('');
            return;
          }
          resolve(String(result.value || '').trim());
        });
      });
    }

    async function resolveMailboxWithRetry() {
      await ensureOfficeReady();
      for (let attempt = 1; attempt <= config.officeMailboxRetryCount; attempt += 1) {
        const mailbox = getOfficeMailbox();
        if (mailbox) return mailbox;
        if (attempt < config.officeMailboxRetryCount) {
          await sleep(config.officeMailboxRetryDelayMs);
        }
      }
      return null;
    }

    async function resolveMailboxItemWithRetry(mailbox) {
      for (let attempt = 1; attempt <= config.officeItemRetryCount; attempt += 1) {
        const item = mailbox && mailbox.item ? mailbox.item : null;
        if (item) return item;
        if (attempt < config.officeItemRetryCount) {
          await sleep(config.officeItemRetryDelayMs);
        }
      }
      return null;
    }

    async function resolveSelectionContextOnce() {
      const mailbox = await resolveMailboxWithRetry();
      if (!mailbox) {
        return emptySelectionContext('office_mailbox_unavailable');
      }
      const item = await resolveMailboxItemWithRetry(mailbox);
      const mailboxUser = readMailboxUser(mailbox);
      if (!item) {
        return {
          ...emptySelectionContext('mailbox_item_missing'),
          mailboxUser: mailboxUser,
        };
      }
      const directItemId = String(item.itemId || '').trim();
      const asyncItemId = await getItemIdAsync(mailbox);
      const selectedId = asyncItemId || directItemId;
      if (!selectedId) {
        return {
          ...emptySelectionContext('item_id_missing'),
          mailboxUser: mailboxUser,
        };
      }
      return {
        emailId: convertToRestId(mailbox, selectedId),
        mailboxUser: mailboxUser,
        reason: asyncItemId ? 'ok_async' : 'ok_direct',
        directItemId: directItemId,
        asyncItemId: asyncItemId,
        selectedItemId: selectedId,
      };
    }

    return {
      ensureOfficeReady: ensureOfficeReady,
      getOfficeMailbox: getOfficeMailbox,
      readMailboxUser: readMailboxUser,
      resolveMailboxWithRetry: resolveMailboxWithRetry,
      resolveSelectionContextOnce: resolveSelectionContextOnce,
    };
  }

  const api = { createContextResolver: createContextResolver };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
    return;
  }
  globalScope.TaskpaneSelectionContext = api;
})(typeof window !== 'undefined' ? window : globalThis);
