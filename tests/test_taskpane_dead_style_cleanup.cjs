const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

function readOutlookFile(relPath) {
  return fs.readFileSync(path.join(__dirname, '..', 'clients', 'outlook-addin', relPath), 'utf8');
}

test('chat actions css no longer imports legacy streaming preview stylesheet', () => {
  const source = readOutlookFile('taskpane.chat.actions.css');
  assert.equal(source.includes('taskpane.chat.actions.streaming.css'), false);
});

test('report widget css no longer contains legacy streaming message selector', () => {
  const source = readOutlookFile('taskpane.chat.rich.widgets.report.css');
  assert.equal(source.includes('.streaming-message .msg-body'), false);
  assert.equal(source.includes('.streaming-message .msg-body::after'), false);
});

test('header toolbar aligns settings/new-session controls to the right', () => {
  const source = readOutlookFile('taskpane.layout.header.css');
  assert.equal(source.includes('justify-content: flex-start;'), true);
  assert.equal(source.includes('margin-left: auto;'), true);
});
