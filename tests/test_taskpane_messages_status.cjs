const test = require('node:test');
const assert = require('node:assert/strict');

const status = require('../clients/outlook-addin/taskpane.messages.status.js');

test('status module renders elapsed divider and clears progress', () => {
  const chatArea = {
    scrollTop: 0,
    scrollHeight: 50,
    html: '',
    querySelectorAll: () => [],
    insertAdjacentHTML(_pos, html) { this.html += html; },
  };
  const nodes = {
    chatArea,
    chatProgressInline: { removeCalled: false, remove() { this.removeCalled = true; } },
  };
  const renderer = status.create({
    byId: (id) => nodes[id] || null,
    escapeHtml: (v) => String(v || ''),
    escapeAttr: (v) => String(v || ''),
    removeWelcomeStateIfExists: () => {},
    scrollToBottom: () => { chatArea.scrollTop = chatArea.scrollHeight; },
    syncWelcomeLayoutState: () => {},
  });

  renderer.addElapsedDivider(6200);
  assert.match(chatArea.html, /msg-elapsed/);
  renderer.clearProgressStatus();
  assert.equal(nodes.chatProgressInline.removeCalled, true);
});

test('status module resetSession writes welcome state', () => {
  const chatArea = { innerHTML: '' };
  let synced = false;
  const renderer = status.create({
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    escapeHtml: (v) => String(v || ''),
    escapeAttr: (v) => String(v || ''),
    removeWelcomeStateIfExists: () => {},
    scrollToBottom: () => {},
    syncWelcomeLayoutState: () => { synced = true; },
  });

  renderer.resetSession();
  assert.match(chatArea.innerHTML, /welcome-state/);
  assert.equal(synced, true);
});
