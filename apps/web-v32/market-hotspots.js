(function () {
  'use strict';
  const sessionKey = 'ceair-production-session';
  const tenantKey = 'ceair-production-tenant';
  const mount = location.pathname.startsWith('/ceair-marketing') ? '/ceair-marketing' : '';
  const q = (s, r = document) => r.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const statusText = {awaiting_confirmation:'待确认本体', updated:'本体已更新', knowledge_only:'仅知识保留', rejected:'已驳回'};
  const readSession = () => { try { return JSON.parse(localStorage.getItem(sessionKey) || 'null'); } catch { return null; } };
  const headers = () => { const session = readSession(); return {'Content-Type':'application/json', Authorization:`Bearer ${session?.access_token || ''}`, 'X-Tenant-ID':String(localStorage.getItem(tenantKey) || session?.tenants?.[0]?.id || '')}; };
  async function api(path, options = {}) { const response = await fetch(`${mount}${path}`, {...options, headers:{...headers(), ...(options.headers || {})}}); const body = response.status === 204 ? null : await response.json().catch(() => ({})); if (!response.ok) throw new Error(body?.detail || `请求失败（${response.status}）`); return body; }
  function inject() {
    const opportunity = q('#opportunities');
    if (!opportunity) return;
    if (!q('#hotspots')) {
      const section = document.createElement('section');
      section.id = 'hotspots';
      section.className = 'hotspots-inline';
      section.innerHTML = '<div class="panel"><div class="panel-head"><h2>\u5e02\u573a\u70ed\u70b9\u4fe1\u53f7</h2><div class="head-actions"><span id="hotspotSummary">0 \u6761</span><button class="btn" data-hotspot-refresh title="\u5237\u65b0\u5e02\u573a\u70ed\u70b9"><i data-lucide="refresh-cw"></i>\u5237\u65b0</button><button class="btn" data-hotspot-ingest title="\u4ece\u6570\u636e\u63a5\u5165\u6d41\u6c34\u7ebf\u5bfc\u5165"><i data-lucide="plus"></i>\u5bfc\u5165\u70ed\u70b9</button></div></div><div class="panel-body"><div class="hotspot-filters"><select id="hotspotStatusFilter"><option value="all">\u5168\u90e8\u72b6\u6001</option><option value="awaiting_confirmation">\u5f85\u786e\u8ba4\u672c\u4f53</option><option value="updated">\u672c\u4f53\u5df2\u66f4\u65b0</option><option value="knowledge_only">\u4ec5\u77e5\u8bc6\u4fdd\u7559</option><option value="rejected">\u5df2\u9a73\u56de</option></select><input id="hotspotSearch" placeholder="\u641c\u7d22\u6807\u9898\u3001\u6765\u6e90\u6216\u4e3b\u9898"></div><div class="hotspot-layout"><div><div id="hotspotList" class="hotspot-list"></div></div><aside class="hotspot-detail-panel"><div class="panel-head"><h3>\u4fe1\u53f7\u8be6\u60c5</h3><span>\u8bc1\u636e\u4e0e Agent \u8f68\u8ff9</span></div><div class="panel-body" id="hotspotDetail"><div class="empty-action">\u9009\u62e9\u4e00\u6761\u70ed\u70b9\u67e5\u770b\u5904\u7406\u7ed3\u679c</div></div></aside></div></div></div>';
      opportunity.appendChild(section);
      bind();
    }
    if (!q('[data-hotspot-entry]')) {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.hotspotEntry = '1';
      button.className = 'opportunity-tool-link';
      button.innerHTML = '<i data-lucide="radar"></i>\u5e02\u573a\u70ed\u70b9\u4fe1\u53f7';
      button.title = '\u673a\u4f1a\u6d1e\u5bdf\u4e2d\u7684\u5e02\u573a\u70ed\u70b9\u4fe1\u53f7';
      const target = q('#opportunities .head-actions');
      if (target) target.appendChild(button);
      button.addEventListener('click', () => open());
    }
    if (window.lucide) window.lucide.createIcons();
  }
  function open() { const section = q('#hotspots'); if (!section) return; if (typeof activate === 'function') activate('opportunities'); section.scrollIntoView({behavior:'smooth', block:'start'}); load(); }
  function render(rows) { const list = q('#hotspotList'); if (!list) return; const term = (q('#hotspotSearch')?.value || '').toLowerCase(); const status = q('#hotspotStatusFilter')?.value || 'all'; const values = rows.filter(x => (status === 'all' || x.ontology_status === status) && (!term || [x.title,x.source_name,(x.topics || []).join(' ')].join(' ').toLowerCase().includes(term))); q('#hotspotSummary').textContent = `${values.length} 条`; list.innerHTML = values.length ? values.map(x => `<button class="hotspot-row" data-id="${esc(x.id)}"><div><strong>${esc(x.title)}</strong><small>${esc(x.source_name)} · ${x.published_at ? new Date(x.published_at).toLocaleString('zh-CN') : '未知时间'}</small></div><b>${Math.round((x.relevance_score || 0) * 100)}<small>相关</small></b><em class="status ${x.ontology_status === 'awaiting_confirmation' ? 'warn' : x.ontology_status === 'updated' ? 'good' : ''}">${statusText[x.ontology_status] || x.ontology_status}</em></button>`).join('') : '<div class="empty-action">暂无符合条件的市场热点</div>'; }
  function detail(item) { const box = q('#hotspotDetail'); if (!box) return; const gate = item.decision?.ontology_gate || {}; box.innerHTML = `<article class="hotspot-detail"><div class="detail-block"><h3>${esc(item.title)}</h3><div class="tag-row">${(item.topics || []).map(x => `<span class="tag blue">${esc(x)}</span>`).join('')}<span class="tag green">相关 ${Math.round((item.relevance_score || 0) * 100)}</span></div></div><div class="detail-grid"><span>来源</span><b>${esc(item.source_name)}</b><span>趋势分</span><b>${Math.round((item.trend_score || 0) * 100)}</b><span>本体准入</span><b>${esc(gate.decision || item.ontology_status)}</b><span>Agent Run</span><b>${esc(item.agent_run_id || '无')}</b></div><div class="hotspot-evidence"><b>原始证据</b><p>${esc(item.summary || item.content || '暂无摘要')}</p>${item.canonical_url ? `<a href="${esc(item.canonical_url)}" target="_blank" rel="noreferrer">查看来源</a>` : ''}</div><div class="hotspot-trace"><h4>Agent 处理轨迹</h4>${(item.trace || []).map(x => `<div class="hotspot-trace-row"><i></i><div><b>${esc(x.event || '处理步骤')}</b><small>${new Date(x.timestamp).toLocaleTimeString('zh-CN')}</small><p>${esc(JSON.stringify(x.payload || {}))}</p></div></div>`).join('')}</div><div class="business-actions">${item.ontology_status === 'awaiting_confirmation' ? `<button class="btn" data-review="reject" data-id="${esc(item.id)}">仅保留知识</button><button class="btn primary" data-review="approve" data-id="${esc(item.id)}">确认更新本体</button>` : ''}${item.ontology_status === 'updated' ? `<button class="btn primary" data-opportunity="${esc(item.id)}">形成营销机会</button>` : ''}<button class="btn" data-process="${esc(item.id)}">重新处理</button></div></article>`; }
  async function load() { try { render(await api('/api/market-hotspots')); } catch (e) { const list = q('#hotspotList'); if (list) list.innerHTML = `<div class="empty-action">${esc(e.message)}</div>`; } }
  function bind() { q('#hotspotSearch')?.addEventListener('input', () => load()); q('#hotspotStatusFilter')?.addEventListener('change', () => load()); q('[data-hotspot-refresh]')?.addEventListener('click', load); q('[data-hotspot-ingest]')?.addEventListener('click', () => alert('请通过数据接入或接口流水线提交市场热点数据。')); q('#hotspotList')?.addEventListener('click', async e => { const row = e.target.closest('[data-id]'); if (row) { const item = await api(`/api/market-hotspots/${row.dataset.id}`); detail(item); } }); q('#hotspotDetail')?.addEventListener('click', async e => { const b = e.target.closest('button'); if (!b) return; try { if (b.dataset.review) await api(`/api/market-hotspots/${b.dataset.id}/review`, {method:'POST', body:JSON.stringify({decision:b.dataset.review, note:'营销人员在线确认'})}); if (b.dataset.opportunity) await api(`/api/market-hotspots/${b.dataset.opportunity}/opportunity`, {method:'POST', body:JSON.stringify({})}); if (b.dataset.process) await api(`/api/market-hotspots/${b.dataset.process}/process`, {method:'POST'}); await load(); alert('操作已完成'); } catch (e) { alert(e.message); } }); }
  document.addEventListener('DOMContentLoaded', inject); if (document.readyState !== 'loading') inject(); window.ceairHotspots = {open, load};
}());
