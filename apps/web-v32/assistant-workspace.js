(function () {
  'use strict';
  window.createAssistantWorkspace = function (panel, api) {
    const { request, escapeHtml: esc } = api;
    const $ = (s, root = panel) => root.querySelector(s);
    const rail = document.createElement('aside'); rail.className = 'assistant-workspace-rail';
    rail.innerHTML = '<div class="assistant-workspace-head"><b>东东工作空间</b><button type="button" class="btn" data-new-chat>＋ 新对话</button></div><div class="assistant-history-tabs"><button type="button" class="active" data-history-tab="conversations">对话</button><button type="button" data-history-tab="tasks">任务</button><button type="button" data-history-tab="memories">记忆</button></div><div class="assistant-workspace-list" role="status"></div>';
    panel.insertBefore(rail, $('.assistant-messages'));
    const toolbar = document.createElement('div'); toolbar.className = 'assistant-workspace-toolbar';
    toolbar.innerHTML = '<button class="btn" type="button" data-rail-toggle>历史与任务</button><b data-chat-title>新对话</b><span class="assistant-workspace-status" data-chat-status>就绪</span><button class="btn" type="button" data-new-chat>＋ 新对话</button>';
    panel.insertBefore(toolbar, $('.assistant-messages'));
    const list = $('.assistant-workspace-list'), messages = $('.assistant-messages');
    let tab = 'conversations', revision = 0;
    const names = { pending_confirmation: '待确认', running: '执行中', completed: '已完成', failed: '失败', cancelled: '已取消' };
    const localTime = value => new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : value + 'Z').toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
    function formatAnswer(anchor, text) {
      const inline = value => esc(value).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>');
      const lines = String(text || '').split('\n'); let result = '';
      for (let index = 0; index < lines.length; index++) {
        const line = lines[index];
        if (/^\|/.test(line) && /^\|[\s:|\-]+\|?$/.test(lines[index + 1] || '')) {
          const cells = value => value.replace(/^\||\|$/g, '').split('|').map(c => c.trim());
          result += '<div class="assistant-markdown-table"><table class="table"><thead><tr>' + cells(line).map(c => '<th>' + inline(c) + '</th>').join('') + '</tr></thead><tbody>'; index++;
          while (index + 1 < lines.length && /^\|/.test(lines[index + 1])) result += '<tr>' + cells(lines[++index]).map(c => '<td>' + inline(c) + '</td>').join('') + '</tr>';
          result += '</tbody></table></div>';
        } else if (/^#{1,3}\s/.test(line)) result += '<h3>' + inline(line.replace(/^#+\s/, '')) + '</h3>';
        else if (/^[-*]\s/.test(line)) result += '<div class="assistant-markdown-item">• ' + inline(line.slice(2)) + '</div>';
        else if (line.trim()) result += '<div>' + inline(line) + '</div>';
        else result += '<div class="assistant-paragraph-gap"></div>';
      }
      anchor.innerHTML = result; anchor.classList.add('assistant-formatted');
    }
    function newChat() { if (api.busy()) return; api.setConversation('', []); messages.innerHTML = '<div class="assistant-welcome"><img src="./brand/dongdong-robot.svg" alt="东东"><h2>今天想完成什么营销任务？</h2><p>查询数据、分析统计，或创建一个任务。</p></div>'; $('[data-chat-title]').textContent = '新对话'; api.focus(); }
    function widgets(items, anchor) {
      for (const item of items || []) {
        if (item.type === 'navigation') { const card = document.createElement('button'); card.className = 'btn assistant-widget'; card.type = 'button'; card.textContent = '打开' + item.title; card.onclick = () => api.navigate(item.page); anchor.after(card); continue; }
        if (item.type === 'table') { const card = document.createElement('section'); card.className = 'assistant-widget'; card.innerHTML = `<div class="assistant-widget-head"><b>${esc(item.title)}</b><button class="btn" type="button">查看全部（${Number(item.total)}）</button></div><div class="assistant-markdown-table"><table class="table"><thead><tr>${item.columns.map(c => '<th>' + esc(c) + '</th>').join('')}</tr></thead><tbody>${item.rows.map(row => '<tr>' + row.map(c => '<td>' + esc(c) + '</td>').join('') + '</tr>').join('')}</tbody></table></div>`; $('button', card).onclick = () => api.navigate(item.page); anchor.after(card); continue; }
        if (item.type !== 'bar' || !Array.isArray(item.labels) || !Array.isArray(item.values)) continue;
        const max = Math.max(...item.values.map(Number), 1), card = document.createElement('section'); card.className = 'assistant-widget assistant-chart-card';
        card.innerHTML = `<div class="assistant-widget-head"><b>${esc(item.title)}</b><div><button class="btn" type="button" data-chart-mode="chart">图表</button><button class="btn" type="button" data-chart-mode="table">数据</button><button class="btn" type="button" data-chart-export>导出</button></div></div><div data-chart><div class="assistant-chart-bars">${item.labels.map((label, i) => `<div class="assistant-chart-row"><span title="${esc(label)}">${esc(label)}</span><i><em style="width:${Math.max(1, Number(item.values[i] || 0) / max * 100)}%"></em></i><b>${Number(item.values[i] || 0).toLocaleString()}${esc(item.unit || '')}</b></div>`).join('') || '<span>当前没有统计记录</span>'}</div></div><div data-chart-table hidden><table class="table"><thead><tr><th>分类</th><th>数值（${esc(item.unit || '条')}）</th></tr></thead><tbody>${item.labels.map((label, i) => `<tr><td>${esc(label)}</td><td>${Number(item.values[i] || 0).toLocaleString()}</td></tr>`).join('')}</tbody></table></div><small class="assistant-widget-note">${esc(item.source || '当前工作区后台记录')}</small>`;
        card.onclick = e => { const mode = e.target.closest('[data-chart-mode]'); if (mode) { $('[data-chart]', card).hidden = mode.dataset.chartMode === 'table'; $('[data-chart-table]', card).hidden = mode.dataset.chartMode !== 'table'; } if (e.target.closest('[data-chart-export]')) { const csv = '\ufeff分类,数值\r\n' + item.labels.map((l, i) => '"' + String(l).replace(/"/g, '""') + '",' + Number(item.values[i] || 0)).join('\r\n'); const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })); const a = document.createElement('a'); a.href = url; a.download = (item.title || '统计') + '.csv'; a.click(); URL.revokeObjectURL(url); } };
        anchor.after(card);
      }
    }
    function task(item, anchor) {
      const card = document.createElement('section'); card.className = 'assistant-widget assistant-task-card';
      const draw = () => { card.innerHTML = `<div class="assistant-widget-head"><b>${esc(item.title)}</b><span>${names[item.status] || esc(item.status)}</span></div><details><summary>任务参数</summary><pre>${esc(JSON.stringify(item.payload || {}, null, 2))}</pre></details>${item.status === 'pending_confirmation' ? '<div class="assistant-task-actions"><button type="button" class="btn primary" data-confirm-task>确认执行</button><button class="btn" type="button" data-cancel-task>取消</button></div>' : ''}<div class="assistant-task-result" role="status">${esc(item.result?.error || item.result?.summary || (item.status === 'completed' ? '任务执行完成。' : ''))}</div>${item.status === 'completed' ? `<details><summary>执行结果</summary><pre>${esc(JSON.stringify(item.result, null, 2))}</pre></details>` : ''}`; };
      draw(); anchor.after(card);
      const update = async () => { const all = await request('/api/assistant/tasks'); item = all.find(t => t.id === item.id) || item; draw(); schedule(); };
      let timer;
      function schedule() { clearTimeout(timer); if (item.status === 'running' && card.isConnected) timer = setTimeout(async () => { if (!card.isConnected) return; try { await update(); if (item.status !== 'running') { await api.refreshBusiness(); await refresh(); } } catch (error) { $('.assistant-task-result', card).textContent = error.message; } }, 5000); }
      schedule();
      card.onclick = async e => { const button = e.target.closest('[data-confirm-task],[data-cancel-task]'); if (!button) return; card.querySelectorAll('button').forEach(b => b.disabled = true); try { item = await request(`/api/assistant/tasks/${encodeURIComponent(item.id)}/${button.hasAttribute('data-confirm-task') ? 'confirm' : 'cancel'}`, { method: 'POST' }); draw(); schedule(); await api.refreshBusiness(); await refresh(); } catch (error) { $('.assistant-task-result', card).textContent = error.message; card.querySelectorAll('button').forEach(b => b.disabled = false); } };
    }
    async function loadConversation(id) {
      if (api.busy()) return;
      try {
        const value = await request('/api/assistant/conversations/' + encodeURIComponent(id));
        api.setConversation(value.id, value.messages.filter(m => m.status === 'completed').slice(-12)); $('[data-chat-title]').textContent = value.title; messages.innerHTML = '';
        const seenTasks = new Set();
        for (const msg of value.messages) {
          const wrapper = document.createElement('div'); wrapper.className = 'assistant-message ' + msg.role + (msg.status === 'failed' ? ' has-error' : '');
          wrapper.innerHTML = `<div class="${msg.role === 'assistant' ? 'assistant-live-body' : 'assistant-user-body'}"><p class="assistant-answer">${esc(msg.content)}</p></div>`;
          messages.append(wrapper); const answer = $('.assistant-answer', wrapper); if (msg.role === 'assistant') formatAnswer(answer, msg.content);
          if (msg.status === 'failed') answer.setAttribute('role', 'alert');
          widgets(msg.detail?.widgets, answer);
          for (const saved of msg.detail?.tasks || []) { task(value.tasks.find(t => t.id === saved.id) || saved, answer); seenTasks.add(saved.id); }
        }
        const remaining = value.tasks.filter(item => !seenTasks.has(item.id));
        if (remaining.length) { const wrapper = document.createElement('div'); wrapper.className = 'assistant-message assistant'; wrapper.innerHTML = '<div class="assistant-live-body"><p class="assistant-answer">任务记录</p></div>'; messages.append(wrapper); remaining.forEach(item => task(item, $('.assistant-answer', wrapper))); }
        messages.scrollTop = messages.scrollHeight;
      } catch (error) { api.toast(error.message); }
    }
    async function refresh() {
      const current = ++revision; list.textContent = '正在加载…';
      try {
        const items = await request('/api/assistant/' + tab); if (current !== revision || !panel.isConnected) return;
        if (tab === 'conversations') list.innerHTML = items.map(item => `<button type="button" class="assistant-history-item ${api.conversationId() === item.id ? 'active' : ''}" data-conversation="${esc(item.id)}"><b>${esc(item.title)}</b><small>${localTime(item.updated_at)}</small></button>`).join('') || '<div class="assistant-history-empty">暂无对话</div>';
        if (tab === 'tasks') { list.innerHTML = items.map(item => `<button class="assistant-history-item" type="button" data-conversation="${esc(item.conversation_id)}"><b>${esc(item.title)}</b><small>${names[item.status] || esc(item.status)}</small></button>`).join('') || '<div class="assistant-history-empty">暂无任务</div>'; }
        if (tab === 'memories') list.innerHTML = '<button class="btn" type="button" data-add-memory>＋ 添加偏好</button>' + items.map(item => `<article class="assistant-memory-item"><p>${esc(item.content)}</p><button class="btn" type="button" data-delete-memory="${item.id}">删除</button></article>`).join('');
      } catch (error) { if (current === revision) list.textContent = error.message; }
    }
    panel.addEventListener('click', async e => {
      if (e.target.closest('[data-new-chat]')) newChat();
      if (e.target.closest('[data-rail-toggle]')) { panel.classList.toggle('show-history'); refresh(); }
      const mode = e.target.closest('[data-history-tab]'); if (mode) { tab = mode.dataset.historyTab; rail.querySelectorAll('[data-history-tab]').forEach(b => b.classList.toggle('active', b === mode)); refresh(); }
      const history = e.target.closest('[data-conversation]'); if (history) loadConversation(history.dataset.conversation);
      const memory = e.target.closest('[data-delete-memory]'); if (memory) { try { await request('/api/assistant/memories/' + memory.dataset.deleteMemory, { method: 'DELETE' }); refresh(); } catch (error) { api.toast(error.message); } }
      if (e.target.closest('[data-add-memory]')) {
        const layer = document.createElement('div'); layer.className = 'production-modal'; layer.innerHTML = '<div class="production-modal-card"><div class="production-modal-head"><b>记忆偏好</b><button class="btn" type="button" data-close>关闭</button></div><form class="production-modal-body provider-form"><label>下次对话希望东东记住什么？<textarea name="content" required maxlength="1000" placeholder="例如：我关注上海出发的家庭出游客群，统计优先显示图表"></textarea></label><span role="status"></span><button class="btn primary" type="submit">保存记忆</button></form></div>'; document.body.append(layer); api.bindModal(layer);
        $('form', layer).onsubmit = async event => { event.preventDefault(); try { await request('/api/assistant/memories', { method: 'POST', body: JSON.stringify({ content: event.target.elements.content.value }) }); layer.__closeProductionModal(); refresh(); } catch (error) { $('[role=status]', layer).textContent = error.message; } };
      }
    });
    newChat(); refresh();
    return { refresh, widgets, task, formatAnswer, newChat, setTitle: value => { if ($('[data-chat-title]').textContent === '新对话') $('[data-chat-title]').textContent = String(value).slice(0, 80); }, show: () => { panel.classList.toggle('show-history'); refresh(); } };
  };
})();
