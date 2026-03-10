const test = require('node:test');
const assert = require('node:assert/strict');

const modulePath = '../clients/outlook-addin/taskpane.js';

function loadTaskpaneModule(officeMock) {
  global.window = { Office: officeMock };
  global.document = undefined;
  delete require.cache[require.resolve(modulePath)];
  return require(modulePath);
}

test('readMailboxUser returns trimmed email', () => {
  const helpers = loadTaskpaneModule({});
  const value = helpers._readMailboxUser({
    userProfile: { emailAddress: '  user@example.com  ' },
  });
  assert.equal(value, 'user@example.com');
});

test('resolveSelectionContextOnce uses item.itemId when present', async () => {
  const officeMock = {
    MailboxEnums: { RestVersion: { v2_0: 'v2.0' }, AsyncResultStatus: { Succeeded: 'succeeded' } },
    context: {
      mailbox: {
        userProfile: { emailAddress: 'dev@outlook.com' },
        item: { itemId: 'abc123' },
        convertToRestId: (value) => `rest-${value}`,
      },
    },
  };
  const helpers = loadTaskpaneModule(officeMock);
  const result = await helpers._resolveSelectionContextOnce();
  assert.equal(result.mailboxUser, 'dev@outlook.com');
  assert.equal(result.emailId, 'rest-abc123');
});

test('resolveSelectionContextOnce falls back to getItemIdAsync', async () => {
  const officeMock = {
    AsyncResultStatus: { Succeeded: 'succeeded' },
    MailboxEnums: { RestVersion: { v2_0: 'v2.0' } },
    context: {
      mailbox: {
        userProfile: { emailAddress: 'dev@outlook.com' },
        item: {
          itemId: '',
          getItemIdAsync: (callback) => callback({ status: 'succeeded', value: 'from-async' }),
        },
        convertToRestId: (value) => `rest-${value}`,
      },
    },
  };
  const helpers = loadTaskpaneModule(officeMock);
  const result = await helpers._resolveSelectionContextOnce();
  assert.equal(result.emailId, 'rest-from-async');
  assert.equal(result.mailboxUser, 'dev@outlook.com');
});

test('resolveSelectionContextOnce prefers getItemIdAsync over direct itemId', async () => {
  const officeMock = {
    AsyncResultStatus: { Succeeded: 'succeeded' },
    MailboxEnums: { RestVersion: { v2_0: 'v2.0' } },
    context: {
      mailbox: {
        userProfile: { emailAddress: 'dev@outlook.com' },
        item: {
          itemId: 'stale-direct-id',
          getItemIdAsync: (callback) => callback({ status: 'succeeded', value: 'fresh-async-id' }),
        },
        convertToRestId: (value) => `rest-${value}`,
      },
    },
  };
  const helpers = loadTaskpaneModule(officeMock);
  const result = await helpers._resolveSelectionContextOnce();
  assert.equal(result.emailId, 'rest-fresh-async-id');
});

test('resolveSelectionContextOnce waits for mailbox context after onReady', async () => {
  const officeMock = {
    AsyncResultStatus: { Succeeded: 'succeeded' },
    MailboxEnums: { RestVersion: { v2_0: 'v2.0' } },
    onReady: (callback) => {
      setTimeout(() => {
        officeMock.context = {
          mailbox: {
            userProfile: { emailAddress: 'late@outlook.com' },
            item: { itemId: 'late-id' },
            convertToRestId: (value) => `rest-${value}`,
          },
        };
        callback();
      }, 20);
    },
  };
  const helpers = loadTaskpaneModule(officeMock);
  const result = await helpers._resolveSelectionContextOnce();
  assert.equal(result.emailId, 'rest-late-id');
  assert.equal(result.mailboxUser, 'late@outlook.com');
});

test('buildMessageHtml includes user meta row with retry/edit/copy actions', () => {
  const helpers = loadTaskpaneModule({});
  const html = helpers._buildMessageHtml('user', 'hello');
  assert.equal(html.includes('data-action="copy"'), true);
  assert.equal(html.includes('data-action="retry"'), true);
  assert.equal(html.includes('data-action="edit"'), true);
  assert.equal(html.includes('msg-meta-time'), true);
});

test('buildMessageHtml includes assistant feedback and copy actions', () => {
  const helpers = loadTaskpaneModule({});
  const html = helpers._buildMessageHtml('assistant', 'answer');
  assert.equal(html.includes('data-action="copy"'), true);
  assert.equal(html.includes('data-action="up"'), true);
  assert.equal(html.includes('data-action="down"'), true);
});

test('isCurrentMailQuery detects current mail phrases', () => {
  const helpers = loadTaskpaneModule({});
  assert.equal(helpers._isCurrentMailQuery('현재메일 요약'), true);
  assert.equal(helpers._isCurrentMailQuery('현재 메일 요약해줘'), true);
  assert.equal(helpers._isCurrentMailQuery('회의실 예약해줘'), false);
});

test('shortId shortens long ids for logging', () => {
  const helpers = loadTaskpaneModule({});
  const value = helpers._shortId('AQMkADAwATMwMAExLWE2YjUtZjE0Ny0wMAItMDAKAEYAAANJSop3');
  assert.equal(value.includes('...'), true);
  assert.equal(helpers._shortId('abc123'), 'abc123');
});

test('stale selection helper exists and returns boolean', () => {
  const helpers = loadTaskpaneModule({});
  const result = helpers._isStaleCurrentMailSelection('현재메일 요약', {
    emailId: 'id-1',
  });
  assert.equal(typeof result, 'boolean');
});

test('waitForSelectionChange helper exists', () => {
  const helpers = loadTaskpaneModule({});
  assert.equal(typeof helpers._waitForSelectionChange, 'function');
});

test('observeSelectionChanges registers ItemChanged handler when API exists', async () => {
  let called = false;
  const officeMock = {
    AsyncResultStatus: { Succeeded: 'succeeded' },
    MailboxEnums: { EventType: { ItemChanged: 'itemChanged' } },
    context: {
      mailbox: {
        addHandlerAsync: (eventType, handler, callback) => {
          called = true;
          assert.equal(eventType, 'itemChanged');
          assert.equal(typeof handler, 'function');
          callback({ status: 'succeeded' });
        },
      },
    },
  };
  const helpers = loadTaskpaneModule(officeMock);
  await helpers._observeSelectionChanges();
  assert.equal(called, true);
});

test('observeSelectionChanges exits safely when addHandlerAsync is missing', async () => {
  const officeMock = {
    MailboxEnums: { EventType: { ItemChanged: 'itemChanged' } },
    context: { mailbox: {} },
  };
  const helpers = loadTaskpaneModule(officeMock);
  await assert.doesNotReject(async () => {
    await helpers._observeSelectionChanges();
  });
});

test('observeSelectionChanges does not register handler twice', async () => {
  let callCount = 0;
  const officeMock = {
    AsyncResultStatus: { Succeeded: 'succeeded' },
    MailboxEnums: { EventType: { ItemChanged: 'itemChanged' } },
    context: {
      mailbox: {
        addHandlerAsync: (eventType, handler, callback) => {
          callCount += 1;
          callback({ status: 'succeeded' });
        },
      },
    },
  };
  const helpers = loadTaskpaneModule(officeMock);
  await helpers._observeSelectionChanges();
  await helpers._observeSelectionChanges();
  assert.equal(callCount, 1);
});

test('observeSelectionChanges falls back to SelectedItemsChanged when ItemChanged is unavailable', async () => {
  let registeredEvent = '';
  const officeMock = {
    AsyncResultStatus: { Succeeded: 'succeeded' },
    MailboxEnums: { EventType: { SelectedItemsChanged: 'selectedItemsChanged' } },
    context: {
      mailbox: {
        addHandlerAsync: (eventType, handler, callback) => {
          registeredEvent = String(eventType || '');
          callback({ status: 'succeeded' });
        },
      },
    },
  };
  const helpers = loadTaskpaneModule(officeMock);
  await helpers._observeSelectionChanges();
  assert.equal(registeredEvent, 'selectedItemsChanged');
});

test('observeSelectionChanges uses Office.EventType when MailboxEnums.EventType is missing', async () => {
  let registeredEvent = '';
  const officeMock = {
    AsyncResultStatus: { Succeeded: 'succeeded' },
    EventType: { ItemChanged: 'officeItemChanged' },
    context: {
      mailbox: {
        addHandlerAsync: (eventType, handler, callback) => {
          registeredEvent = String(eventType || '');
          callback({ status: 'succeeded' });
        },
      },
      requirements: {
        isSetSupported: () => true,
      },
    },
  };
  const helpers = loadTaskpaneModule(officeMock);
  await helpers._observeSelectionChanges();
  assert.equal(registeredEvent, 'officeItemChanged');
});

test('pollSelectionContext updates cached email id when selection changes', async () => {
  const officeMock = {
    AsyncResultStatus: { Succeeded: 'succeeded' },
    MailboxEnums: { RestVersion: { v2_0: 'v2.0' } },
    context: {
      mailbox: {
        userProfile: { emailAddress: 'dev@outlook.com' },
        item: { itemId: 'new-id' },
        convertToRestId: (value) => `rest-${value}`,
      },
    },
  };
  const helpers = loadTaskpaneModule(officeMock);
  helpers._setCachedSelectionContextForTest({
    emailId: 'rest-old-id',
    mailboxUser: 'dev@outlook.com',
  });
  await helpers._pollSelectionContext();
  const state = helpers._getSelectionStateSnapshot();
  assert.equal(state.cachedEmailId, 'rest-new-id');
  assert.equal(state.selectionRevision > 0, true);
});

test('mapProgressMessage maps processing to generic status text', () => {
  const helpers = loadTaskpaneModule({});
  const mapped = helpers._mapProgressMessage({ phase: 'processing' });
  assert.equal(mapped.phase, 'processing');
  assert.equal(mapped.text, '요청을 처리 중입니다.');
  assert.equal(mapped.step, 0);
  assert.equal(mapped.total, 0);
});

test('mapProgressMessage prefers server provided progress message', () => {
  const helpers = loadTaskpaneModule({});
  const mapped = helpers._mapProgressMessage({
    phase: 'analyzing',
    message: '메일 요약을 준비하고 있어요.',
    detail: '핵심 문장을 추출하는 중입니다.',
    step: 3,
    total_steps: 6,
  });
  assert.equal(mapped.phase, 'analyzing');
  assert.equal(mapped.text, '메일 요약을 준비하고 있어요.');
  assert.equal(mapped.detail, '핵심 문장을 추출하는 중입니다.');
  assert.equal(mapped.step, 3);
  assert.equal(mapped.total, 6);
});

test('mapProgressMessage hides label on completed phase', () => {
  const helpers = loadTaskpaneModule({});
  const mapped = helpers._mapProgressMessage({ phase: 'completed' });
  assert.equal(mapped.phase, 'completed');
  assert.equal(mapped.text, '');
});
