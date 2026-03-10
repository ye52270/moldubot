const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const pagePath = path.join(__dirname, '..', 'clients', 'outlook-addin', 'chat-eval.html');

test('chat-eval page keeps simple eval flow and defaults loader', () => {
  const html = fs.readFileSync(pagePath, 'utf8');
  assert.equal(html.includes('function normalizeChatUrl(value)'), true);
  assert.equal(html.includes('function buildApiCandidates(pathname)'), true);
  assert.equal(html.includes('function requestJsonByXhr(url, method, bodyText)'), true);
  assert.equal(html.includes('function requestJsonWithFallback(pathname, method, payload)'), true);
  assert.equal(html.includes('id="runBtn"'), true);
  assert.equal(html.includes('id="stopBtn"'), true);
  assert.equal(html.includes('id="copyBtn"'), true);
  assert.equal(html.includes('id="checkFailedBtn"'), true);
  assert.equal(html.includes('id="currentCase"'), true);
  assert.equal(html.includes('id="progressText"'), true);
  assert.equal(html.includes('id="casesFile"'), true);
  assert.equal(html.includes('id="answerModal"'), true);
  assert.equal(html.includes('id="logModal"'), true);
  assert.equal(html.includes('id="guardFilter"'), true);
  assert.equal(html.includes('id="statusFilter"'), true);
  assert.equal(html.includes('function copyPlainText(text)'), true);
  assert.equal(html.includes('function buildCopyText(report)'), true);
  assert.equal(html.includes('function openAnswerModal(caseId)'), true);
  assert.equal(html.includes('function openLogModal(caseId)'), true);
  assert.equal(html.includes('function buildCaseDebugText(row)'), true);
  assert.equal(html.includes('checkFailedBtn.addEventListener("click", () => {'), true);
  assert.equal(html.includes('statusFilterSelect.addEventListener("change", () => {'), true);
  assert.equal(html.includes('view-log-btn'), true);
  assert.equal(html.includes('function renderAnswerModalHtml(payload)'), true);
  assert.equal(html.includes('function renderAnswerBlocksHtml(blocks)'), true);
  assert.equal(html.includes('answerModalBody.innerHTML = renderAnswerModalHtml({'), true);
  assert.equal(html.includes('class="case-check"'), true);
  assert.equal(html.includes('view-answer-btn'), true);
  assert.equal(html.includes('function copyLatestReport()'), true);
  assert.equal(html.includes('function requestStopRun()'), true);
  assert.equal(html.includes('function setProgress(current, total)'), true);
  assert.equal(html.includes('function loadDefaults()'), true);
  assert.equal(html.includes('function loadCaseCatalog()'), true);
  assert.equal(html.includes('copyBtn.addEventListener("click", copyLatestReport);'), true);
  assert.equal(html.includes('stopBtn.addEventListener("click", requestStopRun);'), true);
  assert.equal(html.includes('ngrok-skip-browser-warning'), true);
  assert.equal(html.includes('xhr_non_json_response'), true);
  assert.equal(html.includes('requestJsonWithFallback("/qa/chat-eval/run", "POST", {'), true);
  assert.equal(html.includes('cases_file: document.getElementById("casesFile").value.trim()'), true);
  assert.equal(html.includes('/qa/chat-eval/cases?cases_file='), true);
  assert.equal(html.includes('requestJsonWithFallback("/qa/chat-eval/defaults", "GET")'), true);
  assert.equal(html.includes('loadDefaults();'), true);
  assert.equal(html.includes('id="pipelineRunBtn"'), false);
  assert.equal(html.includes('id="pipelineLatestBtn"'), false);
});

test('chat-eval page pre-fills selected email and mailbox defaults', () => {
  const html = fs.readFileSync(pagePath, 'utf8');
  assert.equal(
    html.includes('value="AQMkADAwATMwMAExLWE2YjUtZjE0Ny0wMAItMDAKAEYAAANJSop3SqTtRoJYJnLKplmtBwCbo2n1iZWzT4b1yAbcI9xBAAACAQwAAACbo2n1iZWzT4b1yAbcI9xBAAAAFYk6tQAAAA=="'),
    true
  );
  assert.equal(html.includes('id="mailboxUser" value="jaeyoung_dev@outlook.com"'), true);
});
