/* Shared SSE transport for the homepage and floating assistant. */
(function (root) {
  'use strict';
  class ChatError extends Error {
    constructor(message, code = 'connection', status = 0) {
      super(message); this.name = 'ChatError'; this.code = code; this.status = status;
    }
  }
  async function chat(url, options = {}) {
    const controller = new AbortController();
    let reader, idleTimer, reason;
    const abort = (message, code) => { reason = new ChatError(message, code); controller.abort(); };
    const cancel = () => abort('已停止等待；已提交的后台任务可在运行记录中查看。', 'cancelled');
    const resetIdle = () => {
      clearTimeout(idleTimer);
      idleTimer = setTimeout(() => abort('连接长时间没有响应，请检查网络后重试。', 'timeout'), options.idleTimeoutMs ?? 90000);
    };
    const totalTimer = setTimeout(() => abort('智能体响应超时，请查看运行记录后再重试。', 'timeout'), options.timeoutMs ?? 240000);
    options.signal?.addEventListener('abort', cancel, { once: true });
    if (options.signal?.aborted) cancel();
    resetIdle();
    try {
      const response = await (options.fetchImpl || fetch)(url, {
        method: 'POST', headers: options.headers,
        body: JSON.stringify(options.payload), signal: controller.signal
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const detail = Array.isArray(body.detail) ? body.detail.map(item => item.msg).join('；') : body.detail;
        const message = response.status === 401 ? '登录已失效，请重新登录。' : [502,503,504].includes(response.status) ? '智能体服务暂不可用，请稍后重试。' : detail || `智能体连接失败（${response.status}）`;
        throw new ChatError(message, 'http', response.status);
      }
      if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream')) {
        throw new ChatError('后台未返回对话流，请刷新页面后重试。', 'protocol');
      }
      reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '', result;
      function frame(text) {
        const lines = text.split(/\r?\n/);
        const event = (lines.find(line => line.startsWith('event:')) || 'event: message').slice(6).trim();
        const data = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
        if (!data) return;
        let value;
        try { value = JSON.parse(data); } catch { throw new ChatError('对话数据格式异常，请重试。', 'protocol'); }
        if (event === 'error') throw new ChatError(value.message || '智能体运行失败，请重试。', 'backend');
        if (event === 'complete') result = value;
        options.onEvent?.(event, value);
      }
      while (!result) {
        const part = await reader.read();
        if (part.value?.length) resetIdle();
        buffer += decoder.decode(part.value || new Uint8Array(), { stream: !part.done });
        const frames = buffer.split(/\r?\n\r?\n/);
        buffer = frames.pop() || '';
        for (const text of frames) { frame(text); if (result) break; }
        if (part.done) { if (!result && buffer.trim()) frame(buffer); break; }
      }
      if (!result) throw new ChatError('连接已中断，未收到完整结果。请查看运行记录后重试。', 'interrupted');
      return result;
    } catch (error) {
      if (reason) throw reason;
      if (error instanceof ChatError) throw error;
      throw new ChatError('无法连接智能体服务，请检查网络后重试。', 'connection');
    } finally {
      clearTimeout(idleTimer); clearTimeout(totalTimer);
      options.signal?.removeEventListener('abort', cancel);
      if (reader) await reader.cancel().catch(() => {});
    }
  }
  root.CeairAgentStream = { chat, ChatError };
  if (typeof module !== 'undefined') module.exports = root.CeairAgentStream;
})(globalThis);
