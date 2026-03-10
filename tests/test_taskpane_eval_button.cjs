const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const taskpaneHtmlPath = path.join(__dirname, '..', 'clients', 'outlook-addin', 'taskpane.html');
const taskpaneModulePath = '../clients/outlook-addin/taskpane.js';

function loadTaskpaneModule() {
  global.window = { Office: {} };
  global.document = undefined;
  delete require.cache[require.resolve(taskpaneModulePath)];
  return require(taskpaneModulePath);
}

test('taskpane header includes eval button next to new session', () => {
  const html = fs.readFileSync(taskpaneHtmlPath, 'utf8');
  assert.equal(html.includes('id="openEvalBtn"'), true);
  assert.equal(html.includes('id="newSessionBtn"'), true);
  assert.equal(html.indexOf('id="openEvalBtn"') < html.indexOf('id="newSessionBtn"'), true);
});

test('taskpane module exposes eval page path', () => {
  const helpers = loadTaskpaneModule();
  assert.equal(helpers._openEvalPagePath, '/addin/chat-eval.html');
});
