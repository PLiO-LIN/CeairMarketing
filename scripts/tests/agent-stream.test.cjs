const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chat } = require('../../apps/web-v32/agent-stream.js');
const encoder = new TextEncoder();
const sse = text => new Response(text, { headers: { 'Content-Type': 'text/event-stream' } });

test('handles fragmented UTF-8 and CRLF frames; completes without a done event', async () => {
  const events = [], bytes = encoder.encode('event: token\r\ndata: {"text":"东航"}\r\n\r\nevent: complete\r\ndata: {"answer":"东航结果"}\r\n\r\n');
  const body = new ReadableStream({ start(c) { for (let i = 0; i < bytes.length; i += 3) c.enqueue(bytes.slice(i, i + 3)); c.close(); } });
  const result = await chat('/chat', { fetchImpl: async () => new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }), onEvent: (type, value) => events.push([type, value]) });
  assert.equal(result.answer, '东航结果'); assert.equal(events[0][1].text, '东航');
});

test('reports premature stream closure instead of treating partial tokens as success', async () => {
  await assert.rejects(chat('/chat', { fetchImpl: async () => sse('event: token\ndata: {"text":"partial"}\n\n') }), error => error.code === 'interrupted');
});

test('propagates backend errors immediately', async () => {
  await assert.rejects(chat('/chat', { fetchImpl: async () => sse('event: error\ndata: {"message":"模型未配置"}\n\n') }), error => error.code === 'backend' && error.message === '模型未配置');
});

test('reports login expiry and rejects HTML responses', async () => {
  await assert.rejects(chat('/chat', { fetchImpl: async () => new Response('{}', { status: 401 }) }), error => error.status === 401);
  await assert.rejects(chat('/chat', { fetchImpl: async () => new Response('<html>login</html>') }), error => error.code === 'protocol');
});

test('idle timeout and manual cancellation release pending requests', async () => {
  const hanging = async (url, options) => new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true }));
  await assert.rejects(chat('/chat', { fetchImpl: hanging, idleTimeoutMs: 10 }), error => error.code === 'timeout');
  const controller = new AbortController();
  const pending = chat('/chat', { fetchImpl: hanging, signal: controller.signal });
  controller.abort();
  await assert.rejects(pending, error => error.code === 'cancelled');
});
