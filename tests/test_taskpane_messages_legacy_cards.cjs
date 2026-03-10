const test = require('node:test');
const assert = require('node:assert/strict');

const legacyCards = require('../clients/outlook-addin/taskpane.messages.legacy_cards.js');

test('legacy cards module exposes stable api after split', () => {
  const renderer = legacyCards.create({
    byId: () => null,
    escapeHtml: (v) => String(v || ''),
    escapeAttr: (v) => String(v || ''),
    scrollToBottom: () => {},
    removeWelcomeStateIfExists: () => {},
  });

  assert.equal(typeof renderer.addPromiseBudgetCard, 'function');
  assert.equal(typeof renderer.addFinanceSettlementCard, 'function');
  assert.equal(typeof renderer.addHrApplyCard, 'function');

  renderer.addPromiseBudgetCard();
  renderer.addFinanceSettlementCard([]);
  renderer.addHrApplyCard();
  assert.equal(renderer.getPromiseCardValues(), null);
  assert.equal(renderer.getFinanceCardValues(), null);
  assert.equal(renderer.getHrCardValues(), null);
});
