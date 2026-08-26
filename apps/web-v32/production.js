(function () {
  'use strict';
  const mount = location.pathname.startsWith('/ceair-marketing') ? '/ceair-marketing' : '';
  const sessionKey = 'ceair-production-session';
  const tenantKey = 'ceair-production-tenant';
  let session = null;
  let tenantId = null;
  let tenantData = { campaigns: [], graph: { nodes: [], edges: [] }, imports: [], providers: [], domains: [], runs: [] };
  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function activeTenant() { return session?.tenants?.find(item => item.id === tenantId) || session?.tenants?.[0]; }
  async function request(path, options = {}, form = false) {
    const response = await fetch(`${mount}${path}`, {
      ...options,
      headers: {
        ...(form ? {} : {'Content-Type':'application/json'}),
        Authorization: `Bearer ${session?.access_token || ''}`,
        'X-Tenant-ID': String(activeTenant()?.id || ''),
        ...(options.headers || {})
      }
    });
    if (response.status === 401) { logout(); throw new Error('登录已失效，请重新登录'); }
    const body = response.status === 204 ? null : await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body?.detail || `请求失败（${response.status}）`);
    return body;
  }

  function createLogin() {
    q('.app').style.visibility = 'hidden';
    const layer = document.createElement('div');
    layer.className = 'production-login';
    layer.innerHTML = `<section class="production-login-brand">
<img src="./brand/ceair-wordmark.svg" alt="??????">
<div>
<h1>东航智慧营销云</h1>
<p>面向航空营销全生命周期的运营、智能决策与治理平台</p>
</div>
</section>
<form class="production-login-form">
<h2>登录营销运营工作台</h2>
<label>???<input name="username" value="admin" autocomplete="username">
</label>
<label>??<input name="password" type="password" autocomplete="current-password" autofocus>
</label>
<p class="production-login-error" hidden>
</p>
<button class="btn primary">????</button>
</form>`;
    document.body.appendChild(layer);
    q('form', layer).addEventListener('submit', async event => {
      event.preventDefault(); const button = q('button', layer); const error = q('.production-login-error', layer);
      button.disabled = true; button.textContent = '正在验证...'; error.hidden = true;
      try {
        const body = Object.fromEntries(new FormData(event.currentTarget));
        const response = await fetch(`${mount}/api/auth/login`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const value = await response.json(); if (!response.ok) throw new Error(value.detail || '登录失败');
        session = value; tenantId = Number(localStorage.getItem(tenantKey)) || value.tenants[0]?.id;
        localStorage.setItem(sessionKey, JSON.stringify(value)); layer.remove(); q('.app').style.visibility = 'visible'; await initializeSession();
      } catch (cause) { error.textContent = cause.message || '登录失败'; error.hidden = false; }
      finally { button.disabled = false; button.textContent = '登录平台'; }
    });
  }

  function logout() { localStorage.removeItem(sessionKey); localStorage.removeItem(tenantKey); location.reload(); }
  function injectNavigation() {
    if (typeof titles !== 'undefined') Object.assign(titles, { imports: '\u6570\u636e\u63a5\u5165', models: '\u6a21\u578b\u914d\u7f6e', tenants: '\u79df\u6237\u4e0e\u7528\u6237' });
    const governance = qa('.menu-group').find(group => q('[data-menu="governance"]', group));
    const submenu = q('.submenu', governance);
    if (!q('[data-view="imports"]')) submenu.insertAdjacentHTML('beforeend', `<button data-view="imports">
<i data-lucide="database">
</i>????</button>
<button data-view="models">
<i data-lucide="server-cog">
</i>????</button>
<button class="production-admin-only" data-view="tenants">
<i data-lucide="building-2">
</i>?????</button>`);
    const content = q('.content');
    if (!q('#imports')) content.insertAdjacentHTML('beforeend', `<section id="imports" class="view">
<div class="page-head">
<div>
<h1>????</h1>
<p>????????????????????????????</p>
</div>
</div>
<div class="production-grid">
<div class="panel">
<div class="panel-head">
<h2>??????</h2>
<span>CSV / JSON ? ??10MB</span>
</div>
<div class="panel-body">
<div class="production-upload">
<b>实体数据</b>
<p>external_id?entity_type?label?attributes?source?confidence</p>
<input type="file" id="entityFile" accept=".csv,.json">
<button class="btn primary" data-production-import="entities">???????</button>
</div>
<div class="production-upload">
<b>????</b>
<p>source_external_id?relation_type?target_external_id?evidence?confidence</p>
<input type="file" id="relationFile" accept=".csv,.json">
<button class="btn" data-production-import="relations">???????</button>
</div>
<div id="importStatus">
</div>
</div>
</div>
<div class="panel">
<div class="panel-head">
<h2>??????</h2>
<span>????</span>
</div>
<div class="panel-body">
<div class="control-list">
<div class="control-item">
<i data-lucide="shield-check">
</i>
<div>
<b>????</b>
<span>????????????????</span>
</div>
</div>
<div class="control-item">
<i data-lucide="refresh-cw">
</i>
<div>
<b>????</b>
<span>? external_id ?????</span>
</div>
</div>
<div class="control-item">
<i data-lucide="alert-triangle">
</i>
<div>
<b>????</b>
<span>???????????????</span>
</div>
</div>
</div>
</div>
</div>
</div>
<div class="panel">
<div class="panel-head">
<h2>????</h2>
<span id="importCount">0???</span>
</div>
<div class="panel-body">
<table class="table" id="importTable">
</table>
</div>
</div>
</section>`);
    if (!q('#models')) content.insertAdjacentHTML('beforeend', `<section id="models" class="view">
<div class="page-head">
<div>
<h1>????</h1>
<p>?????????????????????????????</p>
</div>
</div>
<div class="production-grid">
<div class="panel">
<div class="panel-head">
<h2>??????</h2>
<span id="modelCount">0?</span>
</div>
<div class="panel-body">
<table class="table" id="modelTable">
</table>
</div>
</div>
<div class="panel">
<div class="panel-head">
<h2>??????</h2>
<span>OpenAI????</span>
</div>
<form class="production-form" id="modelForm">
<label>????<input name="display_name" required placeholder="??????????">
</label>
<label>????<select name="provider_type">
<option value="openai-compatible">OpenAI Compatible</option>
<option value="mock">??????</option>
</select>
</label>
<label>????<input name="base_url" placeholder="https://.../v1">
</label>
<label>????<input name="model_name" required placeholder="????">
</label>
<label>API Key<input name="api_key" type="password">
</label>
<label>
<input name="is_default" type="checkbox">??????</label>
<button class="btn primary">??????</button>
</form>
</div>
</div>
</section>`);
    if (!q('#tenants')) content.insertAdjacentHTML('beforeend', `<section id="tenants" class="view">
<div class="page-head">
<div>
<h1>?????</h1>
<p>?????????????????????</p>
</div>
</div>
<div class="production-grid">
<div class="panel">
<div class="panel-head">
<h2>????</h2>
<span id="tenantCount">0?</span>
</div>
<div class="panel-body">
<table class="table" id="tenantTable">
</table>
</div>
</div>
<div class="panel">
<div class="panel-head">
<h2>??????</h2>
<span>?????</span>
</div>
<form class="production-form" id="tenantForm">
<label>????<input name="code" required placeholder="CEA-NORTH">
</label>
<label>????<input name="name" required placeholder="????????">
</label>
<button class="btn primary">????</button>
</form>
</div>
</div>
<div class="panel">
<div class="panel-head">
<h2>???????</h2>
<span id="userCount">0?</span>
</div>
<div class="panel-body">
<table class="table" id="userTable">
</table>
</div>
</div>
</section>`);
    qa('[data-view]').forEach(button => { if (button.dataset.productionBound) return; button.dataset.productionBound='1'; button.addEventListener('click', () => { if (typeof window.activate === 'function') window.activate(button.dataset.view); if (button.dataset.view === 'imports') renderImports(); if (button.dataset.view === 'models') renderModels(); if (button.dataset.view === 'tenants') loadPlatform(); }); });
    if (window.lucide) lucide.createIcons();
  }

  function updateIdentity() {
    const tenant = activeTenant(); const user = q('.user');
    q('b', user).textContent = tenant?.name || '??????';
    q('span', user).textContent = `?????${session.display_name} ? ${tenant?.role || ''}`;
    document.body.classList.toggle('platform-admin', !!session.is_platform_admin);
    const actions = q('.top-actions');
    let select = q('.production-tenant', actions);
    if (!select) { select=document.createElement('select'); select.className='production-tenant'; actions.prepend(select); select.addEventListener('change', async () => { tenantId=Number(select.value); localStorage.setItem(tenantKey,String(tenantId)); await loadTenantData(); }); }
    select.innerHTML = session.tenants.map(item => `<option value="${item.id}" ${item.id===tenant.id?'selected':''}>${escapeHtml(item.name)}</option>`).join('');
  }

  function renderCampaigns() {
    const campaigns = tenantData.campaigns; const overviewKpis = qa('#overview .kpi b');
    if (overviewKpis[0]) overviewKpis[0].textContent = campaigns.length;
    if (overviewKpis[2]) overviewKpis[2].textContent = campaigns.reduce((sum,item)=>sum+item.audience_size,0).toLocaleString('zh-CN');
    const navCount = q('[data-view="campaigns"] .nav-count'); if (navCount) navCount.textContent = campaigns.length;
    const rows = campaigns.map(item => `<tr>
<td>${escapeHtml(item.id)}</td>
<td>
<strong>${escapeHtml(item.name)}</strong>
</td>
<td>${escapeHtml(item.stage)}</td>
<td>${escapeHtml(item.version)}</td>
<td>${escapeHtml(item.owner)}</td>
<td>??</td>
<td>
<span class="status ${item.status.includes('??')?'good':'warn'}">${escapeHtml(item.status)}</span>
</td>
<td class="action" data-open-campaign="${escapeHtml(item.name)}">????</td>
</tr>`).join('');
    const campaignTable = q('#campaigns .table'); if (campaignTable) campaignTable.innerHTML = `<tr>
<th>????</th>
<th>????</th>
<th>????</th>
<th>????</th>
<th>???</th>
<th>????</th>
<th>??</th>
<th>??</th>
</tr>${rows}`;
    const overviewTable = q('#overview .table'); if (overviewTable) overviewTable.innerHTML = `<tr>
<th>??</th>
<th>????</th>
<th>???</th>
<th>??</th>
<th>??</th>
<th>??</th>
</tr>${campaigns.map(item=>`<tr>
<td>
<strong>${escapeHtml(item.name)}</strong>
</td>
<td>${escapeHtml(item.stage)}</td>
<td>${escapeHtml(item.owner)}</td>
<td>${escapeHtml(item.version)}</td>
<td>
<span class="status ${item.status.includes('??')?'good':'warn'}">${escapeHtml(item.status)}</span>
</td>
<td class="action" data-open-campaign="${escapeHtml(item.name)}">??</td>
</tr>`).join('')}`;
  }

  function renderDynamicGraph() {
    const canvas=q('#graphCanvas'); if (!canvas || !window.d3) return; canvas.innerHTML='';
    const source=tenantData.graph; if (!source.nodes.length) { canvas.innerHTML='<div class="graph-empty">????????????????????????????</div>'; return; }
    const box=canvas.getBoundingClientRect(), width=box.width||900, height=box.height||500;
    const nodes=source.nodes.map(item=>({...item,title:item.label,type:String(item.type||'entity').toLowerCase(),w:154,h:52}));
    const byId=new Map(nodes.map(item=>[item.id,item])); const links=source.edges.filter(item=>byId.has(item.source)&&byId.has(item.target)).map(item=>({...item,source:byId.get(item.source),target:byId.get(item.target),label:item.relation}));
    const svg=d3.select(canvas).append('svg').attr('width',width).attr('height',height), defs=svg.append('defs');
    defs.append('marker').attr('id','production-arrow').attr('viewBox','0 0 8 8').attr('refX',7).attr('refY',4).attr('markerWidth',6).attr('markerHeight',6).attr('orient','auto').append('path').attr('d','M0,0 L8,4 L0,8 z').attr('fill','#93b2c4');
    const root=svg.append('g'); svg.call(d3.zoom().scaleExtent([.55,2]).on('zoom',event=>root.attr('transform',event.transform)));
    const edge=root.append('g').selectAll('path').data(links).join('path').attr('class','graph-edge').attr('marker-end','url(#production-arrow)');
    const labels=root.append('g').selectAll('text').data(links).join('text').attr('class','edge-label').text(item=>item.label);
    const node=root.append('g').selectAll('g').data(nodes).join('g').attr('class',item=>`graph-node dynamic ${item.type}`).call(d3.drag().on('start',(event,item)=>{if(!event.active)simulation.alphaTarget(.25).restart();item.fx=item.x;item.fy=item.y}).on('drag',(event,item)=>{item.fx=event.x;item.fy=event.y}).on('end',(event,item)=>{if(!event.active)simulation.alphaTarget(0);item.fx=null;item.fy=null}));
    node.append('rect').attr('x',item=>-item.w/2).attr('y',item=>-item.h/2).attr('width',item=>item.w).attr('height',item=>item.h).attr('rx',4);
    node.append('text').attr('class','title').attr('x',item=>-item.w/2+10).attr('y',-3).text(item=>item.title.slice(0,18)); node.append('text').attr('class','type').attr('x',item=>-item.w/2+10).attr('y',14).text(item=>item.type);
    node.on('click',(event,item)=>{event.stopPropagation();q('#entityDetail').innerHTML=`<div class="entity-title">
<b>${escapeHtml(item.title)}</b>
<span>${escapeHtml(item.type)}</span>
</div>
<dl>
<dt>??ID</dt>
<dd>${escapeHtml(item.id)}</dd>
<dt>????</dt>
<dd>${escapeHtml(item.source)}</dd>
<dt>???</dt>
<dd>${Math.round((item.confidence||0)*100)}%</dd>
</dl>
<div class="ai-result">
<b>????</b>
<p>${escapeHtml(JSON.stringify(item.attributes||{}))}</p>
</div>`;});
    const simulation=d3.forceSimulation(nodes).force('link',d3.forceLink(links).id(item=>item.id).distance(145).strength(.7)).force('charge',d3.forceManyBody().strength(-420)).force('collide',d3.forceCollide().radius(90)).force('center',d3.forceCenter(width/2,height/2)).on('tick',()=>{edge.attr('d',item=>`M${item.source.x},${item.source.y} L${item.target.x},${item.target.y}`);labels.attr('x',item=>(item.source.x+item.target.x)/2).attr('y',item=>(item.source.y+item.target.y)/2-5);node.attr('transform',item=>`translate(${item.x},${item.y})`)});
    node.filter((_,index)=>index===0).dispatch('click');
  }

  function renderImports() { const table=q('#importTable'); if (!table) return; q('#importCount').textContent=`${tenantData.imports.length}???`; table.innerHTML=`<tr>
<th>??</th>
<th>??</th>
<th>???</th>
<th>??</th>
<th>??</th>
<th>??</th>
<th>??</th>
</tr>${tenantData.imports.map(item=>`<tr>
<td>
<strong>${escapeHtml(item.file_name)}</strong>
<small>${escapeHtml(item.id)}</small>
</td>
<td>${item.dataset_type==='entities'?'??':'??'}</td>
<td>${item.total_rows}</td>
<td>${item.accepted_rows}</td>
<td>${item.rejected_rows}</td>
<td>
<span class="status ${item.rejected_rows?'warn':'good'}">${escapeHtml(item.status)}</span>
</td>
<td>${new Date(item.created_at).toLocaleString('zh-CN')}</td>
</tr>`).join('')}`; }
  function renderModels() { const table=q('#modelTable'); if (!table) return; q('#modelCount').textContent=`${tenantData.providers.length}?`; table.innerHTML=`<tr>
<th>??</th>
<th>??</th>
<th>??</th>
<th>??</th>
<th>??</th>
<th>??</th>
</tr>${tenantData.providers.map(item=>`<tr>
<td>
<strong>${escapeHtml(item.display_name)}</strong>
</td>
<td>${escapeHtml(item.provider_type)}</td>
<td>${escapeHtml(item.model_name)}</td>
<td>
<span class="status ${item.enabled?'good':'warn'}">${item.enabled?'??':'??'}</span>
</td>
<td>${item.is_default?'?':'?'}</td>
<td>
<div class="production-actions">
<button class="btn" data-provider-test="${item.id}">??</button>${item.is_default?'':`<button class="btn" data-provider-default="${item.id}">????</button>`}</div>
</td>
</tr>`).join('')}`; }

  async function upload(datasetType) { const input=q(datasetType==='entities'?'#entityFile':'#relationFile'); if (!input?.files?.[0]) return toast('????CSV?JSON??'); const form=new FormData(); form.append('dataset_type',datasetType); form.append('file',input.files[0]); q('#importStatus').innerHTML='<div class="production-status">???????...</div>'; try { const result=await request('/api/imports',{method:'POST',body:form},true); q('#importStatus').innerHTML=`<div class="production-status">??????? ${result.accepted_rows} ???? ${result.rejected_rows} ??</div>`; await loadTenantData(); renderImports(); } catch(cause){q('#importStatus').innerHTML=`<div class="production-status">${escapeHtml(cause.message)}</div>`;} }
  async function loadPlatform() { if(!session.is_platform_admin) return; const [tenants,users]=await Promise.all([request('/api/platform/tenants'),request('/api/platform/users')]); q('#tenantCount').textContent=`${tenants.length}?`; q('#userCount').textContent=`${users.length}?`; q('#tenantTable').innerHTML=`<tr>
<th>??</th>
<th>????</th>
<th>??</th>
</tr>${tenants.map(item=>`<tr>
<td>${escapeHtml(item.code)}</td>
<td>
<strong>${escapeHtml(item.name)}</strong>
</td>
<td>${escapeHtml(item.role)}</td>
</tr>`).join('')}`; q('#userTable').innerHTML=`<tr>
<th>??</th>
<th>???</th>
<th>????</th>
<th>????</th>
</tr>${users.map(item=>`<tr>
<td>
<strong>${escapeHtml(item.display_name)}</strong>
</td>
<td>${escapeHtml(item.username)}</td>
<td>${item.memberships.map(m=>`${escapeHtml(m.name)}?${escapeHtml(m.role)}?`).join('?')}</td>
<td>${item.is_platform_admin?'?????':'????'}</td>
</tr>`).join('')}`; }

  function bindProductionActions() {
    document.addEventListener('click', async event => {
      const button=event.target.closest('button'); if(!button) return;
      if(button.dataset.productionImport) return upload(button.dataset.productionImport);
      if(button.dataset.providerTest){const result=await request(`/api/model-providers/${button.dataset.providerTest}/test`,{method:'POST'});toast(result.message||'??????');}
      if(button.dataset.providerDefault){await request(`/api/model-providers/${button.dataset.providerDefault}/default`,{method:'POST'});toast('???????');await loadTenantData();renderModels();}
      const agentMap={scanOpportunity:'opportunity-insight',naturalAudience:'audience-insight',calculateAudience:'audience-insight',useProduct:'product-match',aiOrchestrate:'activity-orchestration',generateContent:'content-generation',generateReview:'effect-analysis'};
      const domain=agentMap[button.dataset.action]; if(domain&&tenantData.campaigns[0]) request('/api/agent-runs',{method:'POST',body:JSON.stringify({campaign_id:tenantData.campaigns[0].id,domain_id:domain,operator:session.display_name})}).then(result=>toast(result.summary)).catch(cause=>toast(cause.message));
    });
    q('.user-switch').addEventListener('click',event=>{event.stopImmediatePropagation();showWorkspace();},true);
    q('#modelForm').addEventListener('submit',async event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.currentTarget));values.enabled=true;values.is_default=!!values.is_default;values.timeout_seconds=60;values.temperature=.3;values.max_tokens=2048;await request('/api/model-providers',{method:'POST',body:JSON.stringify(values)});event.currentTarget.reset();toast('???????');await loadTenantData();renderModels();});
    q('#tenantForm').addEventListener('submit',async event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.currentTarget));values.code=String(values.code).toUpperCase();await request('/api/platform/tenants',{method:'POST',body:JSON.stringify(values)});event.currentTarget.reset();toast('?????');await loadPlatform();});
  }

  function showWorkspace(){const layer=document.createElement('div');layer.className='production-modal';layer.innerHTML=`<div class="production-modal-card">
<div class="production-modal-head">
<b>????????</b>
<button class="btn" data-close>??</button>
</div>
<div class="production-modal-body">${session.tenants.map(item=>`<button class="workspace-option ${item.id===activeTenant().id?'active':''}" data-tenant="${item.id}">
<span>
<b>${escapeHtml(item.name)}</b>
<small>${escapeHtml(item.code)} ? ${escapeHtml(item.role)}</small>
</span>
<em>${item.id===activeTenant().id?'??':'??'}</em>
</button>`).join('')}<button class="btn" data-logout>????</button>
</div>
</div>`;document.body.appendChild(layer);layer.addEventListener('click',async event=>{if(event.target===layer||event.target.closest('[data-close]'))layer.remove();const option=event.target.closest('[data-tenant]');if(option){tenantId=Number(option.dataset.tenant);localStorage.setItem(tenantKey,String(tenantId));layer.remove();await loadTenantData();}if(event.target.closest('[data-logout]'))logout();});}

  async function loadTenantData(){updateIdentity();tenantData=await Promise.all(['/api/campaigns','/api/graph','/api/imports','/api/model-providers','/api/agent-domains','/api/agent-runs'].map(path=>request(path))).then(([campaigns,graph,imports,providers,domains,runs])=>({campaigns,graph,imports,providers,domains,runs}));renderCampaigns();renderDynamicGraph();renderImports();renderModels();}
  async function initializeSession(){injectNavigation();bindProductionActions();await loadTenantData();if(window.lucide)lucide.createIcons();}
  function boot(){try{session=JSON.parse(localStorage.getItem(sessionKey)||'null');}catch{session=null;}if(!session)return createLogin();tenantId=Number(localStorage.getItem(tenantKey))||session.tenants?.[0]?.id;q('.app').style.visibility='visible';initializeSession().catch(cause=>{console.error(cause);toast(cause.message||'????????');});}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
