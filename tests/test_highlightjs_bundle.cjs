const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const bundlePath = path.join(
  __dirname,
  '..',
  'clients',
  'outlook-addin',
  'vendor',
  'highlightjs',
  'common.min.js'
);

function loadHighlightBundle() {
  const source = fs.readFileSync(bundlePath, 'utf8');
  const sandbox = { window: {}, self: {}, globalThis: {}, console };
  vm.runInNewContext(source, sandbox, { timeout: 3000 });
  return sandbox.hljs || sandbox.window.hljs || sandbox.self.hljs || sandbox.globalThis.hljs;
}

test('highlightjs vendor bundle loads in browser-like context', () => {
  const hljs = loadHighlightBundle();
  assert.equal(typeof hljs, 'object');
  assert.equal(typeof hljs.highlightElement, 'function');
  assert.equal(typeof hljs.getLanguage, 'function');
});

test('highlightjs vendor bundle supports python and javascript', () => {
  const hljs = loadHighlightBundle();
  assert.equal(Boolean(hljs.getLanguage('python')), true);
  assert.equal(Boolean(hljs.getLanguage('javascript')), true);
});
