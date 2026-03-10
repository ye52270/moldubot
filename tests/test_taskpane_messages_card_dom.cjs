const test = require('node:test');
const assert = require('node:assert/strict');

const modulePath = '../clients/outlook-addin/taskpane.messages.card_dom.js';

function loadModule() {
  delete require.cache[require.resolve(modulePath)];
  return require(modulePath);
}

test('card dom helper appends assistant card html', () => {
  const moduleRef = loadModule();
  const calls = [];
  const chatArea = {
    insertAdjacentHTML(position, html) {
      calls.push({ position, html: String(html || '') });
    },
    querySelectorAll() { return []; },
  };
  const api = moduleRef.create({ byId: (id) => (id === 'chatArea' ? chatArea : null) });
  api.appendAssistantCard(chatArea, 'custom-message', 'custom-content', '<div>본문</div>');

  assert.equal(calls.length, 1);
  assert.equal(calls[0].position, 'beforeend');
  assert.equal(calls[0].html.includes('custom-message'), true);
  assert.equal(calls[0].html.includes('custom-content'), true);
  assert.equal(calls[0].html.includes('<div>본문</div>'), true);
});

test('card dom helper disables controls and removes matched nodes', () => {
  const moduleRef = loadModule();
  const removable = { removed: false, remove() { this.removed = true; } };
  const disabledControl = { disabled: false };
  const chatArea = {
    insertAdjacentHTML() {},
    querySelectorAll(selector) {
      if (selector === '.remove-me') return [removable];
      if (selector === '.disable-me') return [disabledControl];
      return [];
    },
  };
  const api = moduleRef.create({ byId: (id) => (id === 'chatArea' ? chatArea : null) });
  api.removeCardsBySelector('.remove-me');
  api.disableControls('.disable-me');

  assert.equal(removable.removed, true);
  assert.equal(disabledControl.disabled, true);
});
