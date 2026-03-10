const test = require('node:test');
const assert = require('node:assert/strict');

const loaderFactory = require('../clients/outlook-addin/taskpane.module_loader.js');

test('module loader createRenderer falls back when module is missing', () => {
  const loader = loaderFactory.create();
  const fallback = { ok: true };
  const rendered = loader.createRenderer(null, {}, fallback);
  assert.equal(rendered, fallback);
});

test('module loader delegate binds module method', () => {
  const loader = loaderFactory.create();
  const moduleObj = {
    value: 3,
    sum(delta) {
      return this.value + delta;
    },
  };
  const delegated = loader.delegate(moduleObj, 'sum');
  assert.equal(delegated(4), 7);
});
