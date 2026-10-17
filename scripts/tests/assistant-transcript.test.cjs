const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function transcript() {
  const host = { children: [], append(node) { this.children.push(node); } };
  const context = { window: {}, document: { createElement() { return {}; } } };
  vm.runInNewContext(fs.readFileSync(require.resolve('../../apps/web-v32/assistant-transcript.js'), 'utf8'), context);
  const renderer = { accept(message) { host.append({ ui: message }); } };
  const api = context.window.createAssistantTranscript(host, renderer, (node, text) => { node.textContent = text; });
  return { api, host };
}

test('preserves text/chart/text order during streaming and history replay', () => {
  const live = transcript();
  live.api.token('先读取活动'); live.api.ui({ chart: 1 }); live.api.round();
  live.api.token('完成分析'); live.api.finish('完成分析');
  const history = transcript();
  history.api.restore([{ type: 'text', text: '先读取活动' }, { type: 'ui', index: 0 }, { type: 'round' }, { type: 'text', text: '完成分析' }], [{ chart: 1 }], '完成分析');
  assert.deepEqual(history.host.children, live.host.children);
  assert.equal(history.host.children.length, 3);
});

test('does not repeat the final answer when a UI surface follows its text', () => {
  const { api, host } = transcript();
  api.token('结果'); api.ui({ chart: 1 }); api.finish('结果');
  assert.equal(host.children.length, 2);
});

test('uses the authoritative completion when the streamed final text is partial', () => {
  const { api, host } = transcript(); api.token('已'); api.finish('已完成');
  assert.equal(host.children.length, 1); assert.equal(host.children[0].textContent, '已完成');
});
