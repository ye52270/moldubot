const test = require('node:test');
const assert = require('node:assert/strict');

const modulePath = '../clients/outlook-addin/taskpane.quick_prompts.js';

function loadModule() {
  delete require.cache[require.resolve(modulePath)];
  return require(modulePath);
}

function createLocalStorageMock() {
  const store = new Map();
  return {
    getItem(key) {
      return store.has(key) ? String(store.get(key)) : null;
    },
    setItem(key, value) {
      store.set(String(key), String(value));
    },
  };
}

test('quick prompts agent hub registers apps/skills and suggests by trigger', () => {
  const localStorage = createLocalStorageMock();
  global.window = { localStorage };
  global.document = {};
  const moduleRef = loadModule();
  const instance = moduleRef.create({
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
    isQuickPromptTrigger: () => false,
    getQuickPromptTemplates: () => [],
  });

  instance.registerApp('실행예산');
  instance.registerSkill('보고서');
  instance.registerSkill('주간보고');

  assert.deepEqual(instance.getRegisteredApps(), ['실행예산']);
  assert.deepEqual(instance.getRegisteredSkills(), ['보고서', '주간보고']);
  assert.deepEqual(instance.getShortcutSuggestions('@실'), ['실행예산']);
  assert.equal(instance.getShortcutSuggestions('/보').includes('보고서'), true);
});

test('quick prompts agent hub persists registry in localStorage', () => {
  const localStorage = createLocalStorageMock();
  global.window = { localStorage };
  global.document = {};
  const moduleRef = loadModule();
  const first = moduleRef.create({
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
    isQuickPromptTrigger: () => false,
    getQuickPromptTemplates: () => [],
  });
  first.registerApp('회의실');
  first.registerSkill('번역');
  first.createAgent({ name: '메일 정리 에이전트', behavior: '요약 후 할일 등록', sequence: '요약→등록' });

  const second = moduleRef.create({
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
    isQuickPromptTrigger: () => false,
    getQuickPromptTemplates: () => [],
  });

  assert.deepEqual(second.getRegisteredApps(), ['회의실']);
  assert.deepEqual(second.getRegisteredSkills(), ['번역']);
  assert.equal(second.getRegisteredAgents().length, 1);
  assert.equal(second.getRegisteredAgents()[0].name, '메일 정리 에이전트');
});

test('quick prompts exposes app/skill catalog with descriptions', () => {
  global.window = { localStorage: createLocalStorageMock() };
  global.document = {};
  const moduleRef = loadModule();
  const instance = moduleRef.create({
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
    isQuickPromptTrigger: () => false,
    getQuickPromptTemplates: () => [],
  });
  const appCatalog = instance.getCatalogEntries('app');
  const skillCatalog = instance.getCatalogEntries('skill');
  assert.equal(appCatalog.length > 0, true);
  assert.equal(skillCatalog.length > 0, true);
  assert.equal(typeof appCatalog[0].description, 'string');
  assert.equal(typeof skillCatalog[0].description, 'string');
  assert.equal(skillCatalog.some((item) => String(item && item.name || '') === '코드분석'), true);
  assert.equal(skillCatalog.some((item) => String(item && item.name || '') === '메일요약'), true);
});

test('quick prompts createAgent derives sequence from node titles', () => {
  global.window = { localStorage: createLocalStorageMock() };
  global.document = {};
  const moduleRef = loadModule();
  const instance = moduleRef.create({
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
    isQuickPromptTrigger: () => false,
    getQuickPromptTemplates: () => [],
  });
  const saved = instance.createAgent({
    name: '노드 기반 에이전트',
    behavior: 'PoC',
    nodes: [{ title: '실행예산 조회' }, { title: '알림 메일 발송' }],
  });
  assert.equal(saved, true);
  assert.equal(instance.getRegisteredAgents()[0].sequence, '실행예산 조회 → 알림 메일 발송');
});
