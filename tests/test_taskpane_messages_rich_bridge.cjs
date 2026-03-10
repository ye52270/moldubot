const test = require('node:test');
const assert = require('node:assert/strict');

const richBridge = require('../clients/outlook-addin/taskpane.messages.rich_bridge.js');

function passthrough(value) {
  return String(value || '');
}

test('rich bridge delegates rendering helpers', () => {
  let highlighted = false;
  const renderer = richBridge.create({
    escapeHtml: passthrough,
    richTextRenderer: {
      isNoiseStructuralToken: (v) => v === '---',
      resolveHeadingClass: () => 'h',
      renderMarkdownTable: () => '<table></table>',
      renderRichText: (v) => '<p>' + passthrough(v) + '</p>',
      applyInlineFormatting: (v) => '<b>' + passthrough(v) + '</b>',
      highlightCodeBlocks: () => { highlighted = true; },
    },
  });
  assert.equal(renderer.isNoiseStructuralToken('---'), true);
  assert.equal(renderer.resolveHeadingClass('x'), 'h');
  assert.match(renderer.renderMarkdownTable('|a|', ['|b|']), /table/);
  assert.match(renderer.renderRichText('ok'), /<p>ok/);
  assert.match(renderer.applyInlineFormatting('x'), /<b>x/);
  renderer.highlightCodeBlocks({});
  assert.equal(highlighted, true);
});
