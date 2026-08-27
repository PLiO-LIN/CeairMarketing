(function () {
  'use strict';
  const mount = location.pathname.startsWith('/ceair-marketing') ? '/ceair-marketing' : '';
  const sessionKey = 'ceair-production-session';
  const tenantKey = 'ceair-production-tenant';
  let session = null;
  let tenantId = null;
  let tenantData = { campaigns: [], graph: { nodes: [], edges: [] }, imports: [], pipelines: [], providers: [], domains: [], runs: [], mineru: null };
  const pipelineFiles = new Map();
  let pipelinePollTimer = null;
  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const displayText = (value, fallback) => /^\?+$/.test(String(value ?? '').trim()) ? fallback : String(value ?? fallback);
  const statusClass = value => /待|暂停|失败|停用|未配置/.test(String(value || '')) ? 'warn' : 'good';

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
<img src="./brand/ceair-wordmark.svg" alt="中国东方航空">
<div>
<h1>东航智慧营销云</h1>
<p>面向航空营销全生命周期的运营、智能决策与治理平台</p>
</div>
</section>
<form class="production-login-form">
<h2>登录营销运营工作台</h2>
<label>用户名<input name="username" value="admin" autocomplete="username">
</label>
<label>密码<input name="password" type="password" autocomplete="current-password" autofocus>
</label>
<p class="production-login-error" hidden>
</p>
<button class="btn primary">登录平台</button>
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
</i>数据接入</button>
<button data-view="models">
<i data-lucide="server-cog">
</i>模型配置</button>
<button class="production-admin-only" data-view="tenants">
<i data-lucide="building-2">
</i>租户与用户</button>`);
    const content = q('.content');
    if (!q('#imports')) content.insertAdjacentHTML('beforeend', `<section id="imports" class="view">
<div class="page-head"><div><h1>\u6570\u636e\u63a5\u5165</h1><p>\u6295\u9012\u6587\u6863\u3001\u8868\u683c\u548c\u7ed3\u6784\u5316\u6570\u636e\uff0c\u7cfb\u7edf\u81ea\u52a8\u89e3\u6790\u5e76\u66f4\u65b0\u77e5\u8bc6\u5e95\u5ea7</p></div><button class="btn" id="refreshPipelines"><i data-lucide="refresh-cw"></i>\u5237\u65b0\u72b6\u6001</button></div>
<div class="ingestion-workbench">
<div class="panel ingestion-entry"><div class="panel-head"><h2>\u6295\u9012\u6570\u636e\u6587\u4ef6</h2><span>\u5355\u6587\u4ef6\u4e0d\u8d85\u8fc7 20MB</span></div><div class="panel-body">
<div class="pipeline-dropzone" id="pipelineDropzone" tabindex="0" role="button" aria-label="\u9009\u62e9\u6216\u62d6\u62fd\u6587\u4ef6"><input id="pipelineFiles" type="file" multiple accept=".txt,.md,.json,.csv,.pdf,.png,.jpg,.jpeg,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.html"><span class="dropzone-icon"><i data-lucide="cloud-upload"></i></span><b>\u5c06\u6587\u4ef6\u62d6\u5230\u8fd9\u91cc</b><p>\u6216\u70b9\u51fb\u9009\u62e9\u6587\u4ef6\uff0c\u53ef\u4e00\u6b21\u6295\u9012\u591a\u4e2a</p><small>PDF / Word / Excel / PPT / CSV / JSON / TXT / \u56fe\u7247</small></div>
<div class="pipeline-flow"><span><i data-lucide="file-check-2"></i>\u63a5\u6536</span><i data-lucide="chevron-right"></i><span><i data-lucide="scan-text"></i>\u89e3\u6790</span><i data-lucide="chevron-right"></i><span><i data-lucide="sparkles"></i>AI\u62bd\u53d6</span><i data-lucide="chevron-right"></i><span><i data-lucide="shield-check"></i>\u6821\u9a8c</span><i data-lucide="chevron-right"></i><span><i data-lucide="database-zap"></i>\u5165\u5e93</span></div>
</div></div>
<div class="panel pipeline-queue-panel"><div class="panel-head"><h2>\u5904\u7406\u961f\u5217</h2><span id="pipelineQueueCount">0 \u4e2a\u4efb\u52a1</span></div><div class="panel-body pipeline-queue" id="pipelineQueue"><div class="pipeline-empty"><i data-lucide="inbox"></i><b>\u5c1a\u65e0\u5904\u7406\u4efb\u52a1</b><span>\u62d6\u5165\u6587\u4ef6\u540e\u5c06\u5728\u8fd9\u91cc\u663e\u793a\u8fdb\u5ea6</span></div></div></div>
<div class="panel pipeline-history-panel"><div class="panel-head"><h2>\u5904\u7406\u8bb0\u5f55</h2><span id="importCount">0 \u4e2a\u6279\u6b21</span></div><div class="panel-body"><table class="table pipeline-history" id="importTable"></table></div></div>
</div></section>`);
    if (!q('#models')) content.insertAdjacentHTML('beforeend', `<section id="models" class="view">
<div class="page-head">
<div>
<h1>模型配置</h1>
<p>为当前租户配置可替换的大模型服务，智能域运行时按租户选择模型</p>
</div>
</div>
<div class="production-grid">
<div class="panel">
<div class="panel-head">
<h2>模型服务清单</h2>
<span id="modelCount">0 个</span>
</div>
<div class="panel-body">
<table class="table" id="modelTable">
</table>
</div>
</div>
<div class="panel">
<div class="panel-head">
<h2>新增模型服务</h2>
<span>OpenAI 兼容接口</span>
</div>
<form class="production-form" id="modelForm">
<label>配置名称<input name="display_name" required placeholder="例如：营销主模型">
</label>
<label>服务类型<select name="provider_type">
<option value="openai-compatible">OpenAI Compatible</option>
</select>
</label>
<label>服务地址<input name="base_url" placeholder="https://.../v1">
</label>
<label>模型名称<input name="model_name" required placeholder="输入模型标识">
</label>
<label>API Key<input name="api_key" type="password">
</label>
<label>
<input name="is_default" type="checkbox">设为默认模型</label>
<button class="btn primary">保存模型配置</button>
</form>
</div>
<div class="panel model-detail-panel">
<div class="panel-head"><h2>模型可用性与用量</h2><span id="modelDetailProvider">选择一个模型服务</span></div>
<div class="panel-body" id="modelDetail"><div class="production-status">点击“可用模型”或“用量”查看实时信息。</div></div>
</div>
<div class="panel mineru-panel">
<div class="panel-head"><h2>MinerU 文档解析</h2><span id="mineruState">未配置</span></div>
<form class="production-form" id="mineruForm">
<label>服务地址<input name="base_url" value="https://mineru.net"></label>
<label>API Key<input name="api_key" type="password" placeholder="留空表示不修改"></label>
<label><input name="enabled" type="checkbox">启用文档解析</label>
<button class="btn primary">保存 MinerU 配置</button>
</form>
</div>
</div>
</section>`);
    if (!q('#tenants')) content.insertAdjacentHTML('beforeend', `<section id="tenants" class="view">
<div class="page-head">
<div>
<h1>租户与用户</h1>
<p>管理营销运营组织、账号、角色和数据权限边界</p>
</div>
</div>
<div class="production-grid">
<div class="panel">
<div class="panel-head">
<h2>租户清单</h2>
<span id="tenantCount">0 个</span>
</div>
<div class="panel-body">
<table class="table" id="tenantTable">
</table>
</div>
</div>
<div class="panel">
<div class="panel-head">
<h2>新建运营租户</h2>
<span>平台管理员</span>
</div>
<form class="production-form" id="tenantForm">
<label>租户编码<input name="code" required placeholder="CEA-NORTH">
</label>
<label>租户名称<input name="name" required placeholder="例如：华北营销中心">
</label>
<button class="btn primary">创建租户</button>
</form>
</div>
</div>
<div class="panel">
<div class="panel-head">
<h2>用户与租户授权</h2>
<span id="userCount">0 人</span>
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
    q('b', user).textContent = tenant?.name || '营销工作空间';
    q('span', user).textContent = `当前用户：${session.display_name} · ${tenant?.role || ''}`;
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
<td>刚刚</td>
<td>
<span class="status ${statusClass(item.status)}">${escapeHtml(item.status)}</span>
</td>
<td class="action" data-open-campaign="${escapeHtml(item.name)}">进入活动</td>
</tr>`).join('');
    const campaignTable = q('#campaigns .table'); if (campaignTable) campaignTable.innerHTML = `<tr>
<th>活动编号</th>
<th>活动名称</th>
<th>当前节点</th>
<th>当前版本</th>
<th>负责人</th>
<th>最近变更</th>
<th>状态</th>
<th>操作</th>
</tr>${rows}`;
    const overviewTable = q('#overview .table'); if (overviewTable) overviewTable.innerHTML = `<tr>
<th>活动</th>
<th>当前节点</th>
<th>负责人</th>
<th>版本</th>
<th>状态</th>
<th>操作</th>
</tr>${campaigns.map(item=>`<tr>
<td>
<strong>${escapeHtml(item.name)}</strong>
</td>
<td>${escapeHtml(item.stage)}</td>
<td>${escapeHtml(item.owner)}</td>
<td>${escapeHtml(item.version)}</td>
<td>
<span class="status ${statusClass(item.status)}">${escapeHtml(item.status)}</span>
</td>
<td class="action" data-open-campaign="${escapeHtml(item.name)}">查看</td>
</tr>`).join('')}`;
  }

  function renderDynamicGraph() {
    const canvas=q('#graphCanvas'); if (!canvas || !window.d3) return; canvas.innerHTML='';
    const source=tenantData.graph; if (!source.nodes.length) { canvas.innerHTML='<div class="graph-empty">当前工作空间暂无营销知识数据，请先在数据接入中投递业务文件。</div>'; return; }
    const box=canvas.getBoundingClientRect(), width=box.width||900, height=box.height||500;
    const nodes=source.nodes.map(item=>({...item,title:displayText(item.label,'未命名对象'),type:String(item.type||'entity').toLowerCase(),w:154,h:52}));
    const byId=new Map(nodes.map(item=>[item.id,item])); const links=source.edges.filter(item=>byId.has(item.source)&&byId.has(item.target)).map(item=>({...item,source:byId.get(item.source),target:byId.get(item.target),label:displayText(item.relation,'关联')}));
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
<dt>对象 ID</dt>
<dd>${escapeHtml(item.id)}</dd>
<dt>数据来源</dt>
<dd>${escapeHtml(displayText(item.source,'未知来源'))}</dd>
<dt>置信度</dt>
<dd>${Math.round((item.confidence||0)*100)}%</dd>
</dl>
<div class="ai-result">
<b>对象属性</b>
<p>${escapeHtml(JSON.stringify(item.attributes||{}))}</p>
</div>`;});
    const simulation=d3.forceSimulation(nodes).force('link',d3.forceLink(links).id(item=>item.id).distance(145).strength(.7)).force('charge',d3.forceManyBody().strength(-420)).force('collide',d3.forceCollide().radius(90)).force('center',d3.forceCenter(width/2,height/2)).on('tick',()=>{edge.attr('d',item=>`M${item.source.x},${item.source.y} L${item.target.x},${item.target.y}`);labels.attr('x',item=>(item.source.x+item.target.x)/2).attr('y',item=>(item.source.y+item.target.y)/2-5);node.attr('transform',item=>`translate(${item.x},${item.y})`)});
    node.filter((_,index)=>index===0).dispatch('click');
  }

  const pipelineStages={queued:['\u7b49\u5f85\u5904\u7406',6],received:['\u6587\u4ef6\u68c0\u67e5',16],extracting:['\u5185\u5bb9\u89e3\u6790',32],extracted:['\u6e05\u6d17\u5207\u5206',48],classifying:['AI \u8bed\u4e49\u62bd\u53d6',65],classified:['\u4e1a\u52a1\u6821\u9a8c',78],persisting:['\u77e5\u8bc6\u5165\u5e93',90],'ontology-updated':['\u5904\u7406\u5b8c\u6210',100],failed:['\u5904\u7406\u5931\u8d25',100]};
  const pipelineStatusText={queued:'\u6392\u961f\u4e2d',running:'\u5904\u7406\u4e2d',completed:'\u5df2\u5b8c\u6210',failed:'\u5931\u8d25'};
  const formatBytes=value=>value>=1048576?(value/1048576).toFixed(1)+' MB':Math.max(1,Math.round(value/1024))+' KB';
  function stageInfo(item){const value=pipelineStages[item.current_stage]||[item.current_stage||'\u5904\u7406\u4e2d',item.status==='completed'?100:12];return {label:value[0],progress:value[1]};}
  function renderImports(){const table=q('#importTable');if(!table)return;const items=tenantData.pipelines||[];q('#importCount').textContent=items.length+' \u4e2a\u6279\u6b21';let html='<tr><th>\u6587\u4ef6</th><th>\u683c\u5f0f</th><th>\u5904\u7406\u7ed3\u679c</th><th>\u72b6\u6001</th><th>\u5b8c\u6210\u65f6\u95f4</th></tr>';items.forEach(item=>{html+='<tr><td><strong>'+escapeHtml(item.file_name)+'</strong><small>'+escapeHtml(item.id)+'</small></td><td>'+escapeHtml((item.file_format||'').toUpperCase())+'</td><td>\u4e1a\u52a1\u5bf9\u8c61 '+item.accepted_entities+' \u00b7 \u5173\u7cfb '+item.accepted_relations+(item.rejected_items?' \u00b7 \u5f85\u590d\u6838 '+item.rejected_items:'')+'</td><td><span class="status '+(item.status==='failed'?'warn':'good')+'">'+escapeHtml(pipelineStatusText[item.status]||item.status)+'</span>'+(item.error_message?'<small class="pipeline-error">'+escapeHtml(item.error_message)+'</small>':'')+'</td><td>'+new Date(item.completed_at||item.created_at).toLocaleString('zh-CN')+'</td></tr>';});table.innerHTML=html;}
  function renderPipelineQueue(){const queue=q('#pipelineQueue');if(!queue)return;const active=(tenantData.pipelines||[]).filter(item=>['queued','running'].includes(item.status));const local=[...pipelineFiles.values()].filter(item=>!item.job||['uploading','failed'].includes(item.status));const merged=[...local,...active.filter(item=>!local.some(localItem=>localItem.job&&localItem.job.id===item.id))];q('#pipelineQueueCount').textContent=merged.length+' \u4e2a\u4efb\u52a1';if(!merged.length){queue.innerHTML='<div class="pipeline-empty"><i data-lucide="inbox"></i><b>\u6682\u65e0\u5904\u7406\u4efb\u52a1</b><span>\u62d6\u5165\u6587\u4ef6\u540e\u5c06\u5728\u8fd9\u91cc\u663e\u793a\u8fdb\u5ea6</span></div>';}else{queue.innerHTML=merged.map(item=>{const job=item.job||item;const info=item.status==='uploading'?{label:'\u6b63\u5728\u4e0a\u4f20',progress:item.progress||8}:stageInfo(job);const failed=item.status==='failed'||job.status==='failed';return '<article class="pipeline-task '+(failed?'is-failed':'')+'"><div class="pipeline-file-icon"><i data-lucide="file-text"></i></div><div class="pipeline-task-main"><div class="pipeline-task-title"><b>'+escapeHtml(item.file?item.file.name:job.file_name)+'</b><span>'+(item.file?formatBytes(item.file.size):escapeHtml((job.file_format||'').toUpperCase()))+'</span></div><div class="pipeline-progress"><i style="width:'+info.progress+'%"></i></div><div class="pipeline-task-meta"><span>'+(failed?'\u5904\u7406\u5931\u8d25':info.label)+'</span><small>'+(failed?escapeHtml(item.error||job.error_message||'\u8bf7\u68c0\u67e5\u6587\u4ef6\u540e\u91cd\u8bd5'):info.progress+'% \u00b7 \u7cfb\u7edf\u6b63\u5728\u81ea\u52a8\u5904\u7406')+'</small></div></div>'+(failed&&item.file?'<button class="btn" data-pipeline-retry="'+item.localId+'"><i data-lucide="rotate-ccw"></i>\u91cd\u8bd5</button>':'')+'</article>';}).join('');}if(window.lucide)lucide.createIcons();}
  async function refreshPipelines(){tenantData.pipelines=await request('/api/data-pipelines');for(const [localId,entry] of pipelineFiles){if(!entry.job)continue;const latest=tenantData.pipelines.find(item=>item.id===entry.job.id);if(!latest)continue;entry.job=latest;if(latest.status==='failed'){entry.status='failed';entry.error=latest.error_message;}else if(latest.status==='completed'){pipelineFiles.delete(localId);}}renderPipelineQueue();renderImports();const hasActive=tenantData.pipelines.some(item=>['queued','running'].includes(item.status));clearTimeout(pipelinePollTimer);if(hasActive)pipelinePollTimer=setTimeout(()=>refreshPipelines().catch(()=>{}),1500);}
  async function uploadPipelineFile(entry){entry.status='uploading';entry.progress=8;renderPipelineQueue();const form=new FormData();form.append('file',entry.file);try{const result=await request('/api/data-pipelines',{method:'POST',body:form},true);entry.job=result.job;entry.status='queued';entry.progress=10;await refreshPipelines();}catch(cause){entry.status='failed';entry.error=cause.message||'\u4e0a\u4f20\u5931\u8d25';renderPipelineQueue();}}
  function queuePipelineFiles(files){const allowed=/\.(txt|md|json|csv|pdf|png|jpe?g|docx?|pptx?|xlsx?|html)$/i;[...files].forEach(file=>{const localId=Date.now()+'-'+Math.random().toString(16).slice(2);if(!allowed.test(file.name)){toast('\u4e0d\u652f\u6301\u6587\u4ef6\uff1a'+file.name);return;}if(file.size>20*1024*1024){toast('\u6587\u4ef6\u8d85\u8fc7 20MB\uff1a'+file.name);return;}const entry={localId,file,status:'queued',progress:0};pipelineFiles.set(localId,entry);uploadPipelineFile(entry);});}

  async function showProviderModels(providerId) {
    const provider=tenantData.providers.find(item=>item.id===providerId);
    q('#modelDetailProvider').textContent=provider?.display_name||'模型服务';
    q('#modelDetail').innerHTML='<div class="production-status">正在查询可用模型...</div>';
    try {
      const result=await request(`/api/model-providers/${providerId}/models`);
      q('#modelDetail').innerHTML=result.models.length?`<div class="model-chip-grid">${result.models.map(item=>`<button type="button" class="model-chip" data-model-name="${escapeHtml(item.id)}"><b>${escapeHtml(item.id)}</b><span>${escapeHtml(item.owned_by||'OpenAI Compatible')}</span></button>`).join('')}</div>`:'<div class="production-status">服务商未返回可用模型。</div>';
    } catch(cause) { q('#modelDetail').innerHTML=`<div class="production-status">${escapeHtml(cause.message)}</div>`; }
  }

  async function showProviderUsage(providerId) {
    const provider=tenantData.providers.find(item=>item.id===providerId);
    q('#modelDetailProvider').textContent=provider?.display_name||'模型服务';
    q('#modelDetail').innerHTML='<div class="production-status">正在统计调用量...</div>';
    try {
      const value=await request(`/api/model-providers/${providerId}/usage`);
      q('#modelDetail').innerHTML=`<div class="usage-metrics"><div><span>请求次数</span><b>${value.request_count.toLocaleString()}</b></div><div><span>输入 Token</span><b>${value.prompt_tokens.toLocaleString()}</b></div><div><span>输出 Token</span><b>${value.completion_tokens.toLocaleString()}</b></div><div><span>总 Token</span><b>${value.total_tokens.toLocaleString()}</b></div></div>${value.by_model.length?`<table class="table usage-table"><tr><th>模型</th><th>请求</th><th>总 Token</th></tr>${value.by_model.map(item=>`<tr><td>${escapeHtml(item.model_name)}</td><td>${item.request_count}</td><td>${item.total_tokens.toLocaleString()}</td></tr>`).join('')}</table>`:''} `;
    } catch(cause) { q('#modelDetail').innerHTML=`<div class="production-status">${escapeHtml(cause.message)}</div>`; }
  }

  function renderMineru() {
    const panel=q('.mineru-panel'); if(!panel) return;
    panel.hidden=activeTenant()?.role!=='admin';
    const config=tenantData.mineru; if(!config) return;
    const form=q('#mineruForm'); form.base_url.value=config.base_url||'https://mineru.net'; form.enabled.checked=!!config.enabled;
    q('#mineruState').textContent=config.api_key_configured?(config.enabled?'已启用':'已配置未启用'):'未配置密钥';
  }
  function renderModels() { const table=q('#modelTable'); if (!table) return; q('#modelCount').textContent=`${tenantData.providers.length} 个`; table.innerHTML=`<tr>
<th>名称</th>
<th>类型</th>
<th>模型</th>
<th>状态</th>
<th>默认</th>
<th>操作</th>
</tr>${tenantData.providers.map(item=>`<tr>
<td>
<strong>${escapeHtml(item.display_name===['内置','演示模型'].join('')?'内置测试模型':item.display_name)}</strong>
</td>
<td>${escapeHtml(item.provider_type)}</td>
<td>${escapeHtml(item.model_name)}</td>
<td>
<span class="status ${item.enabled?'good':'warn'}">${item.enabled?'启用':'停用'}</span>
</td>
<td>${item.is_default?'是':'否'}</td>
<td>
<div class="production-actions">
<button class="btn" data-provider-test="${item.id}">测试</button><button class="btn" data-provider-models="${item.id}">可用模型</button><button class="btn" data-provider-usage="${item.id}">用量</button>${item.is_default?'':`<button class="btn" data-provider-default="${item.id}">设为默认</button>`}</div>
</td>
</tr>`).join('')}`; }


  async function loadPlatform() { if(!session.is_platform_admin) return; const [tenants,users]=await Promise.all([request('/api/platform/tenants'),request('/api/platform/users')]); q('#tenantCount').textContent=`${tenants.length} 个`; q('#userCount').textContent=`${users.length} 人`; q('#tenantTable').innerHTML=`<tr>
<th>编码</th>
<th>租户名称</th>
<th>角色</th>
</tr>${tenants.map(item=>`<tr>
<td>${escapeHtml(item.code)}</td>
<td>
<strong>${escapeHtml(item.name)}</strong>
</td>
<td>${escapeHtml(item.role)}</td>
</tr>`).join('')}`; q('#userTable').innerHTML=`<tr>
<th>姓名</th>
<th>用户名</th>
<th>租户授权</th>
<th>平台权限</th>
</tr>${users.map(item=>`<tr>
<td>
<strong>${escapeHtml(item.display_name===['内置','演示模型'].join('')?'内置测试模型':item.display_name)}</strong>
</td>
<td>${escapeHtml(item.username)}</td>
<td>${item.memberships.map(m=>`${escapeHtml(m.name)}（${escapeHtml(m.role)}）`).join('、')}</td>
<td>${item.is_platform_admin?'平台管理员':'普通用户'}</td>
</tr>`).join('')}`; }

  function bindProductionActions() {
    document.addEventListener('click', async event => {
      const button=event.target.closest('button'); if(!button) return;
      if(button.dataset.pipelineRetry){const entry=pipelineFiles.get(button.dataset.pipelineRetry);if(entry){entry.error='';uploadPipelineFile(entry);}return;}
      if(button.dataset.providerTest){const result=await request(`/api/model-providers/${button.dataset.providerTest}/test`,{method:'POST'});toast(result.message||'模型连接正常');}
      if(button.dataset.providerModels){await showProviderModels(Number(button.dataset.providerModels));}
      if(button.dataset.providerUsage){await showProviderUsage(Number(button.dataset.providerUsage));}
      if(button.dataset.providerDefault){await request(`/api/model-providers/${button.dataset.providerDefault}/default`,{method:'POST'});toast('默认模型已更新');await loadTenantData();renderModels();}
      const agentMap={scanOpportunity:'opportunity-insight',naturalAudience:'audience-insight',calculateAudience:'audience-insight',useProduct:'product-match',aiOrchestrate:'activity-orchestration',generateContent:'content-generation',generateReview:'effect-analysis'};
      const domain=agentMap[button.dataset.action]; if(domain&&tenantData.campaigns[0]) request('/api/agent-runs',{method:'POST',body:JSON.stringify({campaign_id:tenantData.campaigns[0].id,domain_id:domain,operator:session.display_name})}).then(result=>toast(result.summary)).catch(cause=>toast(cause.message));
    });
    const dropzone=q('#pipelineDropzone'),fileInput=q('#pipelineFiles');
    dropzone.addEventListener('click',()=>fileInput.click());
    dropzone.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();fileInput.click();}});
    fileInput.addEventListener('change',()=>{queuePipelineFiles(fileInput.files);fileInput.value='';});
    ['dragenter','dragover'].forEach(name=>dropzone.addEventListener(name,event=>{event.preventDefault();dropzone.classList.add('is-dragging');}));
    ['dragleave','drop'].forEach(name=>dropzone.addEventListener(name,event=>{event.preventDefault();dropzone.classList.remove('is-dragging');}));
    dropzone.addEventListener('drop',event=>queuePipelineFiles(event.dataTransfer.files));
    q('#refreshPipelines').addEventListener('click',()=>refreshPipelines().then(()=>toast('\u5904\u7406\u72b6\u6001\u5df2\u5237\u65b0')).catch(cause=>toast(cause.message)));
    q('.user-switch').addEventListener('click',event=>{event.stopImmediatePropagation();showWorkspace();},true);
    q('#modelForm').addEventListener('submit',async event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.currentTarget));values.enabled=true;values.is_default=!!values.is_default;values.timeout_seconds=60;values.temperature=.3;values.max_tokens=2048;await request('/api/model-providers',{method:'POST',body:JSON.stringify(values)});event.currentTarget.reset();toast('模型配置已保存');await loadTenantData();renderModels();});
    q('#mineruForm').addEventListener('submit',async event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.currentTarget));await request('/api/integrations/mineru',{method:'PUT',body:JSON.stringify({display_name:'MinerU 文档解析',base_url:values.base_url||'https://mineru.net',api_key:values.api_key||'',enabled:!!values.enabled,config:{model_version:'vlm',enable_table:true,is_ocr:false}})});event.currentTarget.api_key.value='';toast('MinerU 配置已保存');await loadTenantData();});
    q('#tenantForm').addEventListener('submit',async event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.currentTarget));values.code=String(values.code).toUpperCase();await request('/api/platform/tenants',{method:'POST',body:JSON.stringify(values)});event.currentTarget.reset();toast('租户已创建');await loadPlatform();});
  }

  function showWorkspace(){const layer=document.createElement('div');layer.className='production-modal';layer.innerHTML=`<div class="production-modal-card">
<div class="production-modal-head">
<b>切换营销工作空间</b>
<button class="btn" data-close>关闭</button>
</div>
<div class="production-modal-body">${session.tenants.map(item=>`<button class="workspace-option ${item.id===activeTenant().id?'active':''}" data-tenant="${item.id}">
<span>
<b>${escapeHtml(item.name)}</b>
<small>${escapeHtml(item.code)} · ${escapeHtml(item.role)}</small>
</span>
<em>${item.id===activeTenant().id?'当前':'切换'}</em>
</button>`).join('')}<button class="btn" data-logout>退出登录</button>
</div>
</div>`;document.body.appendChild(layer);layer.addEventListener('click',async event=>{if(event.target===layer||event.target.closest('[data-close]'))layer.remove();const option=event.target.closest('[data-tenant]');if(option){tenantId=Number(option.dataset.tenant);localStorage.setItem(tenantKey,String(tenantId));layer.remove();await loadTenantData();}if(event.target.closest('[data-logout]'))logout();});}

  async function loadTenantData(){updateIdentity();const paths=['/api/campaigns','/api/graph','/api/imports','/api/data-pipelines','/api/model-providers','/api/agent-domains','/api/agent-runs'];const values=await Promise.all(paths.map(path=>request(path)));let mineru=null;if(activeTenant()?.role==='admin'){try{mineru=await request('/api/integrations/mineru');}catch{mineru=null;}}const [campaigns,graph,imports,pipelines,providers,domains,runs]=values;tenantData={campaigns,graph,imports,pipelines,providers,domains,runs,mineru};renderCampaigns();renderDynamicGraph();renderPipelineQueue();renderImports();renderModels();renderMineru();const hasActive=pipelines.some(item=>['queued','running'].includes(item.status));clearTimeout(pipelinePollTimer);if(hasActive)pipelinePollTimer=setTimeout(()=>refreshPipelines().catch(()=>{}),1500);}
  async function initializeSession(){injectNavigation();bindProductionActions();await loadTenantData();if(window.lucide)lucide.createIcons();}
  function boot(){try{session=JSON.parse(localStorage.getItem(sessionKey)||'null');}catch{session=null;}if(!session)return createLogin();tenantId=Number(localStorage.getItem(tenantKey))||session.tenants?.[0]?.id;q('.app').style.visibility='visible';initializeSession().catch(cause=>{console.error(cause);toast(cause.message||'工作空间加载失败，请稍后重试');});}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
