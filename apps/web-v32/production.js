(function () {
  'use strict';
  window.ceairProductionV32 = true;
  const productionActions = new Set(['newAudience', 'newProduct', 'newContent', 'generateContent', 'naturalAudience', 'calculateAudience', 'aiOrchestrate', 'scanOpportunity', 'useProduct', 'generateReview', 'refreshExecution', 'pauseCampaign', 'viewAudienceSnapshot']);
  window.productionHandlesAction = action => productionActions.has(action);
  const mount = location.pathname.startsWith('/ceair-marketing') ? '/ceair-marketing' : '';
  const sessionKey = 'ceair-production-session';
  const tenantKey = 'ceair-production-tenant';
  let session = null;
  let tenantId = null;
  let tenantDataReady = false;
  let selectedExecutionCampaignId = '';
  let selectedExecutionBatchId = '';
  let selectedExecutionChannel = '';
  let selectedEffectCampaignId = '';
  let effectRequestId = 0;
  let tenantData = { campaigns: [], graph: { nodes: [], edges: [] }, imports: [], pipelines: [], providers: [], domains: [], runs: [], opportunitySources: [], opportunityRuns: [], mineru: null, opportunities: [], audienceTags: [], audiencePackages: [], personaDimensions: [], personaSegments: [], productPackages: [], productCatalog: {products: []}, contentAssets: [], audienceSnapshots: [], approvals: [], executionBatches: [], documents: [] };
  const pipelineFiles = new Map();
  const roleLabels = { admin: '租户管理员', manager: '营销经理', analyst: '营销分析师', viewer: '只读用户' };
  let pipelinePollTimer = null;
  let opportunityPollTimer = null;
  let contentGenerationContext = { campaign_id: '', audience_package_id: '', product_package_id: '', channel: 'App', objective: '提升转化', instruction: '' };
  let selectedContentAssetId = '';
  let selectedPreviewChannel = 'App';
  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  function bindProductionModal(layer, { closeSelector = '[data-close]', onClose } = {}) {
    if (!layer || layer.dataset.modalBound === 'true') return layer?.__closeProductionModal;
    const previousFocus = document.activeElement;
    let closed = false;
    const close = () => {
      if (closed) return;
      closed = true;
      layer.hidden = true;
      layer.setAttribute('aria-hidden', 'true');
      layer.remove();
      onClose?.();
      if (previousFocus && typeof previousFocus.focus === 'function' && document.contains(previousFocus)) previousFocus.focus();
    };
    layer.dataset.modalBound = 'true';
    layer.__closeProductionModal = close;
    layer.setAttribute('role', 'dialog');
    layer.setAttribute('aria-modal', 'true');
    layer.setAttribute('aria-hidden', 'false');
    layer.addEventListener('click', event => {
      const closeButton = event.target.closest?.(closeSelector);
      if (event.target === layer || closeButton) {
        event.preventDefault();
        event.stopPropagation();
        close();
      }
    }, true);
    layer.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
      }
    });
    requestAnimationFrame(() => {
      if (!closed) q(closeSelector, layer)?.focus?.();
    });
    return close;
  }
  document.addEventListener('click', event => {
    const layer = event.target.closest?.('.production-modal');
    if (!layer || layer.querySelector('.business-editor-card')) return;
    const closeButton = event.target.closest?.('[data-close],[data-campaign-detail-close]');
    if (event.target !== layer && !closeButton) return;
    event.preventDefault();
    event.stopPropagation();
    if (typeof layer.__closeProductionModal === 'function') layer.__closeProductionModal();
    else layer.remove();
  }, true);
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const layers = qa('.production-modal:not([hidden])');
    const layer = layers[layers.length - 1];
    if (!layer || layer.querySelector('.business-editor-card')) return;
    event.preventDefault();
    if (typeof layer.__closeProductionModal === 'function') layer.__closeProductionModal();
    else layer.remove();
  });
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const decodeEscapedText = value => {
    let text = String(value ?? '');
    for (let pass = 0; pass < 2; pass += 1) {
      const next = text
        .replace(/\\u([0-9a-fA-F]{4})/g, (_, code) => String.fromCharCode(parseInt(code, 16)))
        .replace(/\\(n|r|t)/g, (_, code) => ({ n: '\n', r: '\r', t: '\t' }[code]));
      if (next === text) break;
      text = next;
    }
    return text;
  };
  const displayText = (value, fallback = '') => {
    const text = decodeEscapedText(value);
    return !text.trim() || /^\?+$/.test(text.trim()) ? fallback : text;
  };
  const statusClass = value => /待|草稿|暂停|失败|停用|未配置/.test(String(value || '')) ? 'warn' : 'good';
  const channelOptions = [['App', '东航 App'], ['官网', '官网 / 活动页'], ['微信', '微信 / 小程序'], ['短信', '短信'], ['邮件', '邮件'], ['客服外呼', '客服外呼']];
  const domainLabels = { 'opportunity-insight': '机会洞察智能域', 'content-generation': '内容生成智能域', 'audience-insight': '客群洞察智能域', 'product-match': '产品匹配智能域', 'activity-orchestration': '活动编排智能域', 'effect-analysis': '效果分析智能域' };
  // SQLite serializes persisted UTC timestamps without a timezone suffix.
  function businessTime(value, timeOnly = false) {
    const raw = String(value ?? '');
    const utc = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(raw) && !/(Z|[+-]\d{2}:?\d{2})$/i.test(raw) ? raw + 'Z' : value;
    const date = new Date(utc);
    if (Number.isNaN(date.getTime())) return '暂无时间';
    const options = { timeZone: 'Asia/Shanghai', hour12: false };
    return timeOnly ? date.toLocaleTimeString('zh-CN', options) : date.toLocaleString('zh-CN', options);
  }

  const businessSubviewState = new Map();
  const businessSubviewDefinitions = {
    opportunities: [['domain','洞察智能域','多个智能体协同分析市场信号并形成机会候选','sparkles'],['list','机会清单','评估、编辑并转化可运营机会','list-filter'],['signals','洞察信号','配置网站、接口和人工关注点','radio-tower'],['runs','运行记录','查看每次洞察的步骤与溯源','history']],
    audiences: [['personas','画像字段','职业、年龄、地域、订单与航线等底层画像','contact-round'],['packages','客群包','组合画像字段后形成可执行客群','users-round'],['selection','圈选记录','保存圈选条件与冻结快照','scan-search']],
    products: [['catalog','基础产品','查看产品管理平台同步的可售对象','ticket'],['packages','活动产品包','组合机票、卡券、权益与辅营服务','package-open'],['services','服务与履约','校验资格并跟踪产品交付','badge-check']],
    contents: [['assets','内容资产','管理可审核、可追溯的内容版本','files'],['tasks','生成任务','查看内容生成智能域运行过程','wand-sparkles'],['preview','渠道预览','按 App、短信和微信样式预览','smartphone']],
    campaigns: [['list','活动清单','贯穿机会到复盘的营销主对象','list-checks'],['runs','编排运行','查看活动编排智能域执行记录','workflow']],
    approvals: [['pending','待我审批','处理产品、预算、内容与合规节点','inbox'],['history','审批记录','查询已处理节点和审批留痕','history']],
    execution: [['batches','执行批次','查看活动版本生成的执行批次','layers-3'],['channels','渠道任务','跟踪分发、送达和渠道状态','radio'],['receipts','回执与补偿','回流结果并处理失败任务','refresh-cw']],
    feedback: [['overview','效果总览','查看触达、点击、转化与收入','chart-no-axes-combined'],['attribution','转化归因','分析活动、客群、产品与渠道贡献','git-branch'],['learning','策略学习','沉淀复盘建议并更新营销关系','brain-circuit']],
    graph: [['schema','本体结构','查看类、属性和关系定义','network'],['instances','本体实例','查看当前租户业务对象与关系','waypoints'],['documents','知识文档','管理进入知识底座的来源文档','book-open-text']],
    imports: [['upload','数据投递','拖入文档、表格和结构化文件','cloud-upload'],['queue','处理队列','查看解析、抽取、校验与入库进度','list-restart'],['history','处理记录','追溯历史批次和本体更新结果','history']],
    permissions: [['roles','角色权限','查看当前账号在工作区的授权','user-cog'],['audit','处理记录','追溯审批、数据导入与智能域运行','scroll-text']]
  };

  function subviewContains(element,key){return String(element?.dataset?.subviewPanel||'').split(/\s+/).includes(key);}
  function activateBusinessSubview(viewId,key,options={}){
    const view=q('#'+viewId),definitions=businessSubviewDefinitions[viewId]; if(!view||!definitions)return;
    const selected=definitions.some(item=>item[0]===key)?key:definitions[0][0]; businessSubviewState.set(viewId,selected);
    qa('[data-business-subview]',view).forEach(button=>{const active=button.dataset.businessSubview===selected;button.classList.toggle('active',active);button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;});
    qa('[data-subview-panel]',view).forEach(element=>{element.hidden=!subviewContains(element,selected);}); view.dataset.activeSubview=selected;
    if(viewId==='audiences'){
      const list=q('#audiences [data-audience-list]');
      const heading=q('.panel-head h2',list),hint=q('.panel-head span',list);
      if(heading)heading.textContent=selected==='packages'?'客群包':'画像字段';
      if(hint)hint.remove();
    }
    if(viewId==='graph'&&(selected==='schema'||selected==='instances')){const target=q(`[data-knowledge-view=${selected}]`,view);if(target&&!target.classList.contains('active'))target.click();}
    if(viewId==='graph'&&selected==='instances')requestAnimationFrame(()=>renderDynamicGraph());
    if(!options.silent)q(`[data-business-subview=${selected}]`,view)?.focus({preventScroll:true});
  }
  function ensureBusinessSubviewNavigation(viewId){
    const view=q('#'+viewId),definitions=businessSubviewDefinitions[viewId]; if(!view||!definitions)return;
    let nav=q(':scope > .business-subview-shell',view); if(!nav){nav=document.createElement('div');nav.className='business-subview-shell';nav.setAttribute('role','tablist');nav.setAttribute('aria-label',(q('.page-head h1',view)?.textContent||'业务')+'子页面');q(':scope > .page-head',view)?.insertAdjacentElement('afterend',nav);}
    nav.innerHTML=`<div class=business-subview-tabs>${definitions.map(item=>`<button type=button role=tab data-business-subview=${item[0]}><i data-lucide=${item[3]}></i><span>${item[1]}</span></button>`).join('')}</div>`;
    activateBusinessSubview(viewId,businessSubviewState.get(viewId)||definitions[0][0],{silent:true});
    if(viewId==='approvals')renderApprovalHistoryPanel();
    if(viewId==='execution')renderExecutionBatchPanel();
    if(window.lucide)lucide.createIcons();
  }
  function renderAgentRunPanel(hostId,domains,emptyText){
    const host=q('#'+hostId);if(!host)return;const runs=(tenantData.runs||[]).filter(item=>domains.includes(item.domain_id));
    const statusLabel=value=>{const text=String(value||'');if(['queued','running','processing'].includes(text.toLowerCase()))return '处理中';if(text==='needs_approval')return '待人工审核';if(text==='completed')return '已完成';if(text==='failed')return '处理失败';return displayText(text,'已完成');};
    host.innerHTML='<div class=panel-head><h2>任务进度</h2><span>'+runs.length+' 次运行</span></div><div class=panel-body>'+(runs.length?'<div class=run-card-list>'+runs.map(item=>{const active=['queued','running','processing'].includes(String(item.status).toLowerCase());return '<article class="run-card '+(active?'is-running':'')+'"><span class="live-state '+(active?'is-active':'')+'"><i></i>'+(active?'正在处理':escapeHtml(statusLabel(item.status)))+' </span><div><b>'+escapeHtml(displayText(item.summary,domainLabels[item.domain_id]||'智能营销任务'))+'</b><small>'+escapeHtml(domainLabels[item.domain_id]||'智能营销任务')+' · '+escapeHtml(item.campaign_id||'未关联活动')+'</small></div><time>'+(item.created_at?businessTime(item.created_at):'刚刚')+'</time></article>';}).join('')+'</div>':'<div class=empty-action>'+escapeHtml(emptyText)+'</div>')+'</div>';
    qa('.run-card',host).forEach((card,index)=>{
      const button=document.createElement('button');button.className='btn';button.textContent='查看结果';button.title='查看已保存的智能域结果';
      button.addEventListener('click',async()=>{
        try{showAgentTrace(await request('/api/agent-runs/'+encodeURIComponent(runs[index].id)));}
        catch(cause){toast(cause.message||'结果读取失败');}
      });
      card.appendChild(button);
    });
  }

  function renderApprovalHistoryPanel(){
    const view=q('#approvals'); if(!view)return;
    let panel=q('#approvalHistoryPanel');
    if(!panel){panel=document.createElement('div');panel.id='approvalHistoryPanel';panel.className='panel';view.appendChild(panel);}
    panel.dataset.subviewPanel='history';
    panel.hidden=(businessSubviewState.get('approvals')||'pending')!=='history';
    const items=(tenantData.approvals||[]).filter(item=>!approvalIsPending(item));
    const rows=items.map(item=>'<article><b>'+escapeHtml(item.external_id||item.id)+'</b><span>'+escapeHtml(item.approver_role||'审批节点')+' · '+escapeHtml(item.status||'未知')+'</span><time>'+escapeHtml(item.decided_at?businessTime(item.decided_at):'暂无时间')+'</time></article>').join('');
    panel.innerHTML='<div class=panel-head><h2>审批处理记录</h2><span>'+items.length+' 条已处理</span></div><div class=panel-body>'+(rows?'<div class=history-list>'+rows+'</div>':'<div class=empty-action>暂无审批历史。活动提交后，处理结果会在这里留痕。</div>')+'</div>';
  }

  function renderExecutionBatchPanel(){
    const view=q('#execution'); if(!view)return;
    let panel=q('#executionBatchPanel');
    if(!panel){panel=document.createElement('div');panel.id='executionBatchPanel';panel.className='panel';const anchor=q('.toolbar-strip',view);if(anchor)anchor.insertAdjacentElement('afterend',panel);else view.appendChild(panel);}
    panel.dataset.subviewPanel='batches';
    panel.hidden=(businessSubviewState.get('execution')||'batches')!=='batches';
    const batch=currentExecutionBatch();
    const title=batch?(batch.external_id||batch.id):'等待审批通过';
    const body=batch?'<div class=batch-summary><strong>'+escapeHtml(batch.external_id||batch.id)+'</strong><span>目标名单 '+Number(batch.target_size||0).toLocaleString('zh-CN')+' 人</span><span>渠道送达 '+Number(batch.delivered_count||0).toLocaleString('zh-CN')+' 次</span><span>点击与转化 '+Number(batch.feedback_count||0).toLocaleString('zh-CN')+' 次事件</span></div>':'<div class=empty-action>暂无执行批次。审批通过后，系统会按活动版本和渠道自动生成批次。</div>';
    panel.innerHTML='<div class=panel-head><h2>执行批次概览</h2><span>'+escapeHtml(title)+'</span></div><div class=panel-body>'+body+'</div>';
  }

  function applyBusinessSubviewLayouts(){
    const mark=(selector,keys)=>{const element=q(selector);if(element)element.dataset.subviewPanel=keys;};
    mark('#opportunities > .toolbar-strip','list'); mark('#opportunities > .grid2','list');
    const insight=q('#opportunityInsightPanel'); if(insight){insight.dataset.subviewPanel='domain signals runs';const source=q('.insight-source-config',insight),run=q('.insight-run-config',insight),history=q('.insight-history',insight);if(source)source.dataset.subviewPanel='signals';if(run)run.dataset.subviewPanel='domain';if(history)history.dataset.subviewPanel='runs';}
    const insightTitle=q('#opportunityInsightPanel h2'); if(insightTitle)insightTitle.textContent='洞察智能域';
    qa('#opportunityInsightPanel .insight-history .status').forEach(node=>{if(/queued|running|处理|processing/i.test(node.textContent||''))node.classList.add('is-live');});
    mark('#audiences > .toolbar-strip','personas packages'); /* 工作台三栏与圈选记录面板已在 index.html 上直接标注 data-subview-panel，不再用 .grid2 位置推断 */
    mark('#products > .toolbar-strip','catalog packages services'); mark('#products > .panel','catalog packages'); mark('#products > .grid3','services'); mark('#productCatalog','catalog');
    const productTable=q('#products > .panel .table'); if(productTable)productTable.dataset.subviewPanel='packages';
    mark('#contents > .toolbar-strip','assets tasks preview'); const contentPanels=qa('#contents > .grid2 > .panel'); if(contentPanels[0])contentPanels[0].dataset.subviewPanel='assets'; if(contentPanels[1])contentPanels[1].dataset.subviewPanel='preview'; q('#contents > .grid2')?.classList.add('single-workbench-grid'); let contentTasks=q('#contentGenerationPanel'); if(!contentTasks){contentTasks=document.createElement('div');contentTasks.id='contentGenerationPanel';contentTasks.className='panel';q('#contents')?.appendChild(contentTasks);} contentTasks.dataset.subviewPanel='tasks'; renderAgentRunPanel('contentGenerationPanel',['content-generation'],'暂无内容生成任务，点击“重新生成”后会在这里显示 Agent 过程。');
    mark('#campaigns > .toolbar-strip','list runs'); const campaignPanel=q('#campaigns > .panel'); if(campaignPanel)campaignPanel.dataset.subviewPanel='list'; let campaignRuns=q('#campaignRunPanel'); if(!campaignRuns){campaignRuns=document.createElement('div');campaignRuns.id='campaignRunPanel';campaignRuns.className='panel';q('#campaigns')?.appendChild(campaignRuns);} campaignRuns.dataset.subviewPanel='runs'; renderAgentRunPanel('campaignRunPanel',['activity-orchestration'],'暂无活动编排运行记录，活动创建与编排后会在这里显示智能域过程。');
    mark('#approvals > .kpis','pending history'); mark('#approvals > .approval-layout','pending');
    mark('#execution > .toolbar-strip','batches channels receipts'); mark('#execution > .kpis','batches'); const executionPanels=qa('#execution > .grid2 > .panel'); if(executionPanels[0])executionPanels[0].dataset.subviewPanel='channels'; if(executionPanels[1])executionPanels[1].dataset.subviewPanel='receipts';
    mark('#feedback > .toolbar-strip','overview attribution learning'); mark('#feedback > .kpis','overview'); const feedbackPanels=qa('#feedback > .grid2 > .panel'); if(feedbackPanels[0])feedbackPanels[0].dataset.subviewPanel='attribution'; if(feedbackPanels[1])feedbackPanels[1].dataset.subviewPanel='learning'; const feedbackFlow=q('#feedback > .panel'); if(feedbackFlow)feedbackFlow.dataset.subviewPanel='learning';
    const graphPanel=q('#graph .graph-panel'); if(graphPanel)graphPanel.dataset.subviewPanel='schema instances'; const entity=q('#graph .entity'); if(entity)entity.dataset.subviewPanel='schema instances'; mark('#knowledgeDocuments','documents');
    mark('#imports .ingestion-entry','upload'); mark('#imports .pipeline-queue-panel','queue'); mark('#imports .pipeline-history-panel','history');
    qa('#permissions .panel').forEach((panel,index)=>{panel.dataset.subviewPanel=index===0?'roles':'audit';});
    Object.keys(businessSubviewDefinitions).forEach(ensureBusinessSubviewNavigation);
  }

  function activeTenant() { return session?.tenants?.find(item => item.id === tenantId) || session?.tenants?.[0]; }
  function canWrite() { return ['admin', 'manager', 'analyst'].includes(activeTenant()?.role); }
  function isTenantAdmin() { return activeTenant()?.role === 'admin'; }
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
    if (!response.ok) {
      const detail = body?.detail;
      const message = Array.isArray(detail) ? detail.map(item => `${(item.loc || []).filter(part => part !== 'body').join('.')}: ${item.msg || '字段校验失败'}`).join('；') : detail;
      throw new Error(message || `请求失败（${response.status}）`);
    }
    return body;
  }

  async function refreshAfterBusinessSave() {
    try { await loadTenantData(); }
    catch { toast('修改已保存，但列表刷新失败，请刷新页面查看；无需重复保存'); }
  }

  window.ceairSaveVisual = async (asset, visual) => {
    if (!canWrite()) throw new Error('当前角色无内容编辑权限');
    // Keep approved references immutable. Every visual edit becomes a new reviewable draft.
    const body = {
      name: (asset.name + '·视觉草稿').slice(0,160), campaign_id: asset.campaign_id,
      audience_package_id: asset.audience_package_id, product_package_id: asset.product_package_id,
      channel: asset.channel, version: 'V1', status: '待审核', title: asset.title, body: asset.body,
      generation_objective: asset.generation_objective || '提升转化', generated_by: 'visual-template',
      generation_context: {...asset.generation_context, visual, derived_from: asset.external_id}
    };
    const saved = await request('/api/content-assets', {method:'POST',body:JSON.stringify(body)});
    await loadTenantData(); toast('已另存为待审核视觉草稿：' + saved.name);
    return saved;
  };

  function editorValue(value, type) {
    if (type === 'json') {
      if (value === null || value === undefined || value === '') return '';
      if (typeof value === 'string') return value;
      return JSON.stringify(value, null, 2);
    }
    if (type === 'datetime-local' && value) {
      const date = new Date(value);
      if (!Number.isNaN(date.getTime())) {
        const offset = date.getTimezoneOffset() * 60000;
        return new Date(date.getTime() - offset).toISOString().slice(0, 16);
      }
    }
    return value ?? '';
  }

  function openBusinessEditor({ title, subtitle, item, fields, save, width = 'business-editor-card', saveLabel = '保存修改' }) {
    const layer = document.createElement('div');
    layer.className = 'production-modal';
    layer.innerHTML = `<div class="production-modal-card business-editor-card ${width}" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
      <div class="production-modal-head"><div><b>${escapeHtml(title)}</b><small>${escapeHtml(subtitle || '编辑后保存将立即同步到当前租户')}</small></div><button class="btn" type="button" data-close>关闭</button></div>
      <form class="production-modal-body business-editor-form">
        <div class="business-editor-grid">${fields.map(field => {
          const value = editorValue(item?.[field.name], field.parseJson ? 'json' : field.type);
          const required = field.required === false ? '' : ' required';
          const label = `<span>${escapeHtml(field.label)}${field.required === false ? '' : '<em>*</em>'}</span>`;
          if (field.type === 'textarea') return `<label class="business-editor-field full-field">${label}<textarea name="${escapeHtml(field.name)}" rows="${field.rows || 4}"${required} placeholder="${escapeHtml(field.placeholder || '')}">${escapeHtml(value)}</textarea>${field.help ? `<small>${escapeHtml(field.help)}</small>` : ''}</label>`;
          if (field.type === 'select') { const options = [...(field.options || [])]; if (value !== '' && !options.some(option => String(typeof option === 'string' ? option : option.value) === String(value))) options.unshift({ value, label: `${value}（当前值）` }); return `<label class="business-editor-field">${label}<select name="${escapeHtml(field.name)}"${required}>${options.map(option => { const optionValue = typeof option === 'string' ? option : option.value; const optionLabel = typeof option === 'string' ? option : option.label; return `<option value="${escapeHtml(optionValue)}"${String(optionValue) === String(value) ? ' selected' : ''}>${escapeHtml(optionLabel)}</option>`; }).join('')}</select>${field.help ? `<small>${escapeHtml(field.help)}</small>` : ''}</label>`; }
          if (field.type === 'multiselect') {
            const selected = (Array.isArray(value) ? value : []).map(String);
            const options = (field.options || []).map(option => typeof option === 'string' ? {value: option, label: option} : option);
            selected.filter(id => !options.some(option => String(option.value) === id)).forEach(id => options.push({value: id, label: `已关联项目 #${id}（当前不可用）`}));
            return `<fieldset class="business-editor-field full-field business-editor-choices"><legend>${label}</legend><div>${options.map(option => `<label><input type="checkbox" name="${escapeHtml(field.name)}" value="${escapeHtml(option.value)}"${selected.includes(String(option.value)) ? ' checked' : ''}><span>${escapeHtml(option.label)}</span></label>`).join('') || '<small>暂无可选项</small>'}</div>${field.help ? `<small>${escapeHtml(field.help)}</small>` : ''}</fieldset>`;
          }
          if (field.readOnly) return `<label class="business-editor-field">${label}<input name="${escapeHtml(field.name)}" value="${escapeHtml(field.displayValue || value)}" readonly></label>`;
          if (field.type === 'checkbox') return `<label class="business-editor-field business-editor-check"><input type="checkbox" name="${escapeHtml(field.name)}"${value ? ' checked' : ''}><span>${escapeHtml(field.label)}</span>${field.help ? `<small>${escapeHtml(field.help)}</small>` : ''}</label>`;
          return `<label class="business-editor-field">${label}<input name="${escapeHtml(field.name)}" type="${field.type || 'text'}" value="${escapeHtml(value)}"${required} min="${field.min ?? ''}" max="${field.max ?? ''}" step="${field.step ?? ''}" placeholder="${escapeHtml(field.placeholder || '')}">${field.help ? `<small>${escapeHtml(field.help)}</small>` : ''}</label>`;
        }).join('')}</div>
        <p class="business-editor-error" role="alert" hidden></p>
        <div class="business-editor-foot"><span>带 <em>*</em> 为必填项</span><div><button type="button" class="btn" data-close>取消</button><button type="submit" class="btn primary">${escapeHtml(saveLabel)}</button></div></div>
      </form>
    </div>`;
    document.body.appendChild(layer);
    const previousFocus = document.activeElement;
    let saving = false;
    const close = () => { if (saving) return; layer.remove(); previousFocus?.focus(); };
    layer.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.preventDefault(); close(); }
      if (event.key === 'Tab') {
        const controls = qa('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled)', layer);
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    });
    layer.addEventListener('click', event => { if (event.target === layer || event.target.closest('[data-close]')) close(); });
    q('form', layer).addEventListener('submit', async event => {
      event.preventDefault();
      if (saving) return;
      const form = event.currentTarget;
      if (!form.reportValidity()) return;
      const error = q('.business-editor-error', layer);
      error.hidden = true;
      const button = q('button[type="submit"]', form);
      const formData = new FormData(form);
      const raw = Object.fromEntries(formData);
      const values = {};
      let invalidJson = false;
      fields.forEach(field => {
        const control = form.elements[field.name];
        if (field.readOnly) return;
        if (field.type === 'checkbox') values[field.name] = !!control.checked;
        else if (field.type === 'multiselect') values[field.name] = formData.getAll(field.name).map(value => Number.isNaN(Number(value)) ? value : Number(value));
        else if (field.type === 'number') values[field.name] = raw[field.name] === '' ? 0 : Number(raw[field.name]);
        else if (field.parseJson || field.type === 'json') {
          try {
            values[field.name] = raw[field.name] ? JSON.parse(raw[field.name]) : {};
            if (!values[field.name] || Array.isArray(values[field.name]) || typeof values[field.name] !== 'object') throw new Error();
          } catch { invalidJson = true; error.textContent = `${field.label}必须是有效的 JSON 对象`; error.hidden = false; control.focus(); }
        } else if (field.type === 'datetime-local') values[field.name] = raw[field.name] ? (raw[field.name] === editorValue(item?.[field.name], field.type) ? item[field.name] : new Date(raw[field.name]).toISOString()) : null;
        else values[field.name] = field.type === 'textarea' || field.type === 'password' ? (raw[field.name] ?? '') : String(raw[field.name] ?? '').trim();
        if (field.required !== false && field.type !== 'checkbox' && typeof values[field.name] === 'string' && !values[field.name].trim()) { invalidJson = true; error.textContent = `请填写${field.label}`; error.hidden = false; control.focus(); }
        if (field.required !== false && field.type === 'multiselect' && !values[field.name].length) { invalidJson = true; error.textContent = `请选择${field.label}`; error.hidden = false; q(`input[name="${field.name}"]`, form)?.focus(); }
      });
      if (invalidJson) return;
      saving = true; button.disabled = true; button.textContent = '正在保存...';
      try { await save(values); saving = false; close(); } catch (cause) { error.textContent = cause.message || '保存失败'; error.hidden = false; error.scrollIntoView({block:'nearest'}); } finally { saving = false; button.disabled = false; button.textContent = saveLabel; }
    });
    if (window.lucide) lucide.createIcons();
    q('input,select,textarea', layer)?.focus();
  }

  function showProductEditor(item) {
    const creating = !item.id;
    openBusinessEditor({
      title: creating ? '新建活动产品包' : '编辑活动产品包', subtitle: item.external_id || '活动产品包', item,
      fields: [
        { name: 'name', label: '产品包名称', type: 'text' },
        { name: 'product_type', label: '产品类型', type: 'select', options: ['机票组合', '辅营组合', '卡券权益', '会员权益', '空铁联运', '企业差旅'] },
        { name: 'version', label: '产品版本', type: 'text' },
        { name: 'status', label: '状态', type: 'select', options: ['草稿', '待审批', '可用', '停用'] },
        { name: 'valid_from', label: '生效时间', type: 'datetime-local', required: false },
        { name: 'valid_to', label: '失效时间', type: 'datetime-local', required: false },
        { name: 'description', label: '产品组合与权益说明', type: 'textarea', rows: 4, required: false, placeholder: '例如：机票、预付费行李、优选座位、贵宾室或卡券权益的组合方式' },
        { name: 'eligibility', label: '适用条件与限制', type: 'textarea', rows: 4, required: false, placeholder: '航线、舱位、库存、会员等级、渠道、出行日期等限制条件' },
      ],
      save: async values => { await request(creating ? '/api/product-packages' : `/api/product-packages/${item.id}`, { method: creating ? 'POST' : 'PUT', body: JSON.stringify(values) }); toast(`产品包“${values.name}”已${creating ? '创建' : '更新'}`); await refreshAfterBusinessSave(); }
    });
  }

  function showContentEditor(item) {
    const creating = !item.id;
    openBusinessEditor({
      title: creating ? '新建营销内容' : '编辑营销内容', subtitle: item.external_id || '内容资产', item,
      fields: [
        { name: 'name', label: '内容资产名称', type: 'text' },
        { name: 'campaign_id', label: '关联活动', type: 'select', required: false, options: [{value:'',label:'未关联活动'}, ...(tenantData.campaigns || []).map(campaign => ({value:campaign.id,label:`${campaign.name} · ${campaign.id}`}))] },
        { name: 'audience_package_id', label: '目标客群包', type: 'select', required: false, options: [{value:'',label:'未关联客群包'}, ...(tenantData.audiencePackages || []).map(item => ({value:item.id,label:`${item.name} · ${Number(item.estimated_size||0).toLocaleString('zh-CN')}人`}))] },
        { name: 'product_package_id', label: '活动产品包', type: 'select', required: false, options: [{value:'',label:'未关联产品包'}, ...(tenantData.productPackages || []).map(item => ({value:item.id,label:`${item.name} · ${item.version||'V1'}`}))] },
        { name: 'channel', label: '触达渠道', type: 'select', options: [{value:'App',label:'东航 App'}, '东航App', '短信', '微信', '邮件', '小程序', '官网', '客服外呼', '企业渠道'] },
        { name: 'version', label: '内容版本', type: 'text' },
        { name: 'generation_objective', label: '内容目标', type: 'text', required: false },
        { name: 'status', label: '内容状态', type: 'select', options: ['草稿', '待审核', '停用'], help: '已审核内容变更后需重新审核。' },
        { name: 'generated_by', label: '生成来源', type: 'text', required: false, readOnly: true, displayValue: ({manual:'人工创建','content-generation':'内容生成智能域',template:'模板生成'})[item.generated_by] },
        { name: 'title', label: '展示标题', type: 'text', required: false },
        { name: 'body', label: '内容正文', type: 'textarea', rows: 8, required: false, placeholder: '填写短信、App 卡片、微信图文或客服话术的完整内容' },
      ],
      save: async values => { values.campaign_id = String(values.campaign_id || '').trim() || null; values.audience_package_id = values.audience_package_id ? Number(values.audience_package_id) : null; values.product_package_id = values.product_package_id ? Number(values.product_package_id) : null; const result = await request(creating ? '/api/content-assets' : `/api/content-assets/${item.id}`, { method: creating ? 'POST' : 'PUT', body: JSON.stringify({...values, generated_by: item.generated_by, generation_context: item.generation_context || {}}) }); toast(creating ? '营销内容已创建为草稿' : result.status !== values.status ? '营销内容已更新，状态已退回草稿，请重新审核' : '营销内容已完整更新'); await refreshAfterBusinessSave(); }
    });
  }

  function showOpportunityEditor(item) {
    openBusinessEditor({
      title: '编辑营销机会', subtitle: `${item.id} · 机会洞察完整信息`, item,
      fields: [
        { name: 'name', label: '机会名称', type: 'text' },
        { name: 'market_scope', label: '市场范围', type: 'select', options: ['国内', '国际及地区', 'ToB 企业', '会员经营', '辅营服务'] },
        { name: 'route', label: '关联航线/区域', type: 'text', required: false, placeholder: '例如：SHA-SYX、上海、东南亚' },
        { name: 'status', label: '机会状态', type: 'select', options: ['待评估', '分析中', '已确认', '已转活动', '已关闭'] },
        { name: 'score', label: '机会评分', type: 'number', min: 0, max: 100 },
        { name: 'estimated_audience', label: '预计可触达客群', type: 'number', min: 0 },
        { name: 'estimated_revenue_yuan', label: '预计增量收入（元）', type: 'number', min: 0 },
        { name: 'owner', label: '负责人', type: 'text', required: false },
        { name: 'signal_summary', label: '机会信号与判断依据', type: 'textarea', rows: 6, required: false, placeholder: '说明航班、客座率、价格、市场热点、用户行为或经营数据形成的机会判断' },
      ],
      save: async values => { await request(`/api/opportunities/${encodeURIComponent(item.id)}`, { method: 'PUT', body: JSON.stringify(values) }); toast('营销机会已完整更新'); await refreshAfterBusinessSave(); }
    });
  }

  function audienceDimensionOptions() {
    return (tenantData.personaDimensions || []).map(item => ({ value: item.id, label: `${displayText(item.module_name, '画像维度')} · ${displayText(item.field_name, '未命名字段')}` }));
  }

  function expressionDimensionIds(item) {
    const ids = item?.expression?.dimension_ids;
    return Array.isArray(ids) ? ids.map(Number).filter(Number.isFinite) : [];
  }

  function audiencePackageFields(item) {
    const tagOptions = (tenantData.audienceTags || []).filter(tag => tag.enabled || (item.tag_ids || []).includes(tag.id)).map(tag => ({ value: tag.id, label: `${tag.name} · ${tag.enabled ? (tag.category || '画像标签') : '已停用'}` }));
    return [
      { name: 'name', label: '客群包名称', type: 'text', placeholder: '例如：暑期亲子出行转化包' },
      { name: 'selection_mode', label: '组合方式', type: 'select', options: [{ value: 'tag-combination', label: '画像条件组合' }, { value: 'ai-selection', label: 'AI 智能圈选' }] },
      { name: 'estimated_size', label: '预计客群规模', type: 'number', min: 0 },
      { name: 'status', label: '客群包状态', type: 'select', options: ['草稿', '可用', '停用'] },
      { name: 'dimension_ids', label: '组合画像字段', type: 'multiselect', required: false, options: audienceDimensionOptions(), help: '从职业、性别、年龄、地域、订单、航线等底层画像字段中选择组合条件。' },
      { name: 'tag_ids', label: '关联画像标签', type: 'multiselect', required: false, options: tagOptions, help: '可选。画像标签是对底层字段的业务化封装，历史快照不会被修改。' },
      { name: 'expression', label: 'AI 圈选条件（JSON）', type: 'textarea', rows: 5, required: false, parseJson: true, placeholder: '{"route":"SHA-SYX","age":{"gte":25,"lte":40}}', help: '用于保存自然语言圈选后的结构化条件；画像字段选择会同步写入组合关系。' },
    ];
  }

  function audiencePackagePayload(values) {
    const dimensionIds = (values.dimension_ids || []).map(value => Number(value)).filter(Number.isFinite);
    const expression = { ...(values.expression || {}), dimension_ids: dimensionIds, dimension_logic: values.expression?.dimension_logic || 'AND' };
    const next = { ...values, tag_ids: values.tag_ids || [], expression };
    delete next.dimension_ids;
    return next;
  }

  function showAudiencePackageEditor(item) {
    openBusinessEditor({
      title: '编辑客群包', subtitle: `${item.external_id || '客群包'} · 由画像字段组合形成`, item: { ...item, dimension_ids: expressionDimensionIds(item) },
      fields: audiencePackageFields(item),
      save: async values => { const payload = audiencePackagePayload(values); await request(`/api/audience-packages/${item.id}`, { method: 'PUT', body: JSON.stringify(payload) }); toast(`客群包“${values.name}”已更新`); await refreshAfterBusinessSave(); }
    });
  }

  function showAudiencePackageCreator() {
    const item = { name: '', selection_mode: 'tag-combination', estimated_size: 0, status: '草稿', dimension_ids: [], tag_ids: [], expression: {} };
    openBusinessEditor({
      title: '新建客群包', subtitle: '先组合底层画像，再生成可供活动引用的客群对象', item,
      fields: audiencePackageFields(item),
      save: async values => { const payload = audiencePackagePayload(values); const result = await request('/api/audience-packages', { method: 'POST', body: JSON.stringify(payload) }); toast(`客群包“${result.name || values.name}”已创建`); await refreshAfterBusinessSave(); }
    });
  }
  function showAudienceTagEditor(item) {
    openBusinessEditor({
      title: '编辑画像标签', subtitle: `${item.code || '画像标签'} · 客群包可复用的底层条件`, item,
      fields: [
        { name: 'code', label: '标签编码', type: 'text' },
        { name: 'name', label: '标签名称', type: 'text' },
        { name: 'category', label: '标签分类', type: 'text', placeholder: '例如：出行行为、会员价值、渠道偏好' },
        { name: 'source', label: '数据来源', type: 'text', placeholder: '例如：用户画像接口、携程、飞猪' },
        { name: 'description', label: '标签说明', type: 'textarea', rows: 5, required: false, placeholder: '说明标签的业务含义、更新口径和可用于哪些客群包' },
        { name: 'enabled', label: '启用标签', type: 'checkbox', required: false, help: '停用后不能用于新建或编辑客群包，历史快照不受影响。' },
      ],
      save: async values => { await request(`/api/audience-tags/${item.id}`, { method: 'PUT', body: JSON.stringify(values) }); toast(`画像标签“${values.name}”已更新`); await refreshAfterBusinessSave(); }
    });
  }

  function showKnowledgeDocumentEditor(item) {
    openBusinessEditor({
      title: '编辑知识文档', subtitle: `${item.external_id || '知识文档'} · 编辑元数据，不改动原始溯源`, item,
      fields: [
        { name: 'title', label: '文档标题', type: 'text' },
        { name: 'classification', label: '知识分类', type: 'select', options: [{value:'internal',label:'内部知识'},{value:'product',label:'产品知识'},{value:'service',label:'服务知识'},{value:'marketing',label:'营销知识'},{value:'policy',label:'政策规则'},{value:'operation',label:'运营知识'},{value:'other',label:'其他'}] },
      ],
      save: async values => { await request(`/api/knowledge/documents/${item.id}`, { method: 'PUT', body: JSON.stringify(values) }); toast('知识文档元数据已更新'); await refreshAfterBusinessSave(); }
    });
  }

  let providerSettings = null;
  function getProviderSettings() {
    return providerSettings || (providerSettings = window.createProviderSettings({
      request, escapeHtml, bindModal: bindProductionModal,
      providers: () => tenantData.providers || [], tenant: () => activeTenant()?.id,
      canEdit: isTenantAdmin, onSaved: refreshAfterBusinessSave, toast,
    }));
  }
  function showProviderCreateEditor() { getProviderSettings().create(); }

  function showMineruEditor() {
    const item = tenantData.mineru || { base_url: 'https://mineru.net', api_key: '', enabled: false };
    openBusinessEditor({
      title: '配置 MinerU 文档解析', subtitle: '文档进入数据处理智能体前的解析服务', item,
      fields: [
        { name: 'base_url', label: '服务地址', type: 'url', placeholder: 'https://mineru.net' },
        { name: 'api_key', label: 'API Key', type: 'password', required: false, placeholder: item.api_key_configured ? '留空表示保持当前 Key' : '请输入 MinerU API Key' },
        { name: 'enabled', label: '启用文档解析', type: 'checkbox' },
      ],
      save: async values => { const payload = { display_name: 'MinerU 文档解析', base_url: values.base_url || 'https://mineru.net', enabled: !!values.enabled, config: { model_version: 'vlm', enable_table: true, is_ocr: false } }; if (values.api_key) payload.api_key = values.api_key; await request('/api/integrations/mineru', { method: 'PUT', body: JSON.stringify(payload) }); toast('MinerU 配置已保存'); await refreshAfterBusinessSave(); }
    });
  }

  function showTenantCreateEditor() {
    openBusinessEditor({
      title: '新建运营租户', subtitle: '平台管理员 · 创建后可继续配置成员和数据权限', item: { code: '', name: '' },
      fields: [
        { name: 'code', label: '租户编码', type: 'text', placeholder: '例如：CEA-NORTH' },
        { name: 'name', label: '租户名称', type: 'text', placeholder: '例如：华北营销中心' },
      ],
      save: async values => { values.code = String(values.code || '').toUpperCase(); await request('/api/platform/tenants', { method: 'POST', body: JSON.stringify(values) }); toast('租户已创建'); await loadPlatform(); }
    });
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
        session = value; tenantId = value.tenants?.[0]?.id || null; localStorage.removeItem(tenantKey);
        localStorage.setItem(sessionKey, JSON.stringify(value)); layer.remove(); q('.app').style.visibility = 'visible'; await initializeSession();
      } catch (cause) { error.textContent = cause.message || '登录失败'; error.hidden = false; }
      finally { button.disabled = false; button.textContent = '登录平台'; }
    });
  }

  function logout() { localStorage.removeItem(sessionKey); location.reload(); }
  function injectNavigation() {
    if (typeof titles !== 'undefined') Object.assign(titles, { imports: '\u6570\u636e\u63a5\u5165', models: '\u6a21\u578b\u914d\u7f6e', tenants: '\u79df\u6237\u4e0e\u7528\u6237' });
    const governance = qa('.menu-group').find(group => q('[data-menu="governance"]', group));
    const submenu = q('.submenu', governance);
    if (!q('[data-view="imports"]')) submenu.insertAdjacentHTML('beforeend', `<button data-view="imports">
<i data-lucide="database">
</i>数据接入</button>
<button class="tenant-admin-only" data-view="models">
<i data-lucide="server-cog">
</i>模型配置</button>
<button class="production-admin-only" data-view="tenants">
<i data-lucide="building-2">
</i>租户与用户</button>`);
    const content = q('.content');
    if (!q('#imports')) content.insertAdjacentHTML('beforeend', `<section id="imports" class="view">
<div class="page-head"><div><h1>\u6570\u636e\u63a5\u5165</h1></div><div class="page-actions"><button class="btn" id="syncNdcFlight"><i data-lucide="plane-takeoff"></i>同步 NDC24.1 模拟航班</button><button class="btn" id="refreshPipelines"><i data-lucide="refresh-cw"></i>\u5237\u65b0\u72b6\u6001</button></div></div>
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
</div>
</div>
<div id="providerSettings" class="provider-settings panel">
<aside class="provider-sidebar"><div class="provider-sidebar-head"><h2>模型服务</h2><span id="modelCount"></span></div><div id="modelTable" class="provider-list"></div><button class="btn provider-add" type="button" data-action="newProvider">＋ 添加模型服务</button></aside>
<div id="providerConfig" class="provider-config"></div>
</div>
<div class="panel mineru-panel mineru-settings-row"><div class="panel-head"><h2>MinerU 文档解析</h2><span id="mineruState">未配置</span><button type="button" class="btn" data-action="editMineru">配置</button></div></div>
</section>`);
    if (!q('#tenants')) content.insertAdjacentHTML('beforeend', `<section id="tenants" class="view">
<div class="page-head">
<div>
<h1>租户与用户</h1>
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
    normalizeConfigurationEntries();
    qa('[data-view]').forEach(button => { if (button.dataset.productionBound) return; button.dataset.productionBound='1'; button.addEventListener('click', () => { if (typeof window.activate === 'function') window.activate(button.dataset.view); if (button.dataset.view === 'imports') renderImports(); if (button.dataset.view === 'models') renderModels(); if (button.dataset.view === 'tenants') loadPlatform(); }); });
    if (window.lucide) lucide.createIcons();
  }

  function normalizeConfigurationEntries() {
    const tenantForm = q('#tenantForm');
    if (tenantForm && !tenantForm.dataset.normalized) {
      tenantForm.dataset.normalized = 'true';
      const tenantPanel = tenantForm.closest('.panel');
      if (tenantPanel) {
        tenantForm.hidden = true;
        const tenantBody = document.createElement('div');
        tenantBody.className = 'config-entry-body';
        const tenantCard = document.createElement('div');
        tenantCard.className = 'config-entry-card';
        tenantCard.innerHTML = '<div class=config-entry-icon><i data-lucide=building-2></i></div><div><b>创建新的营销运营组织</b><p>租户创建后，再从用户与租户授权中配置成员、角色和数据范围。</p><small>租户之间的数据、模型和智能域运行记录相互隔离</small></div>';
        const tenantButton = document.createElement('button');
        tenantButton.type = 'button'; tenantButton.className = 'btn primary config-entry-button'; tenantButton.dataset.action = 'newTenant';
        tenantButton.innerHTML = '<i data-lucide=plus></i>新建运营租户';
        tenantBody.append(tenantCard, tenantButton);
        tenantPanel.append(tenantBody);
      }
    }
    if (window.lucide) lucide.createIcons();
  }

  function updateIdentity() {
    session.tenants = (session.tenants || []).filter(item => item.code !== 'CEA-ECOM' && !String(item.name || '').includes('电商运营中心'));
    if (!session.tenants.some(item => item.id === tenantId)) tenantId = session.tenants[0]?.id;
    const tenant = activeTenant(); const user = q('.user');
    user.dataset.displayName = session.display_name || session.username;
    q('b', user).textContent = tenant?.name || '未选择租户';
    q('span', user).textContent = `${session.display_name} · 当前角色：${roleLabels[tenant?.role] || tenant?.role || '未授权'}`;
    let workspace = q('#workspaceSelect');
    if (!workspace) {
      const label = document.createElement('label');
      label.className = 'workspace-switch';
      label.innerHTML = '<span>当前工作区</span><select id="workspaceSelect" aria-label="切换工作区"></select>';
      q('.top-actions').prepend(label);
      workspace = q('select', label);
      workspace.addEventListener('change', () => {
        const next = Number(workspace.value);
        if (!session.tenants.some(item => item.id === next)) return;
        localStorage.setItem(tenantKey, String(next));
        // Reload clears pending requests, drafts and cached objects from the previous workspace.
        location.reload();
      });
    }
    workspace.innerHTML = session.tenants.map(item => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join('');
    workspace.value = String(tenantId);
    document.body.classList.toggle('platform-admin', !!session.is_platform_admin);
    document.body.classList.toggle('tenant-admin', isTenantAdmin());
    document.body.classList.toggle('tenant-readonly', !canWrite());
    qa('[data-action="createCampaign"], [data-action="aiOrchestrate"]').forEach(button => {
      button.disabled = !canWrite();
      button.title = canWrite() ? '' : '当前为只读权限，不能创建或修改活动';
    });
    const dropzone = q('#pipelineDropzone');
    if (dropzone) {
      dropzone.classList.toggle('is-readonly', !canWrite());
      dropzone.setAttribute('aria-disabled', String(!canWrite()));
      dropzone.title = canWrite() ? '' : '当前为只读权限，不能上传数据';
    }
  }

  const cleanText = (value, fallback = '') => {
    const text = decodeEscapedText(value).trim();
    return !text || /\?{2,}|�/.test(text) ? fallback : text;
  };
  const roleText = value => ({admin:'\u79df\u6237\u7ba1\u7406\u5458',manager:'\u8425\u9500\u7ecf\u7406',analyst:'\u8425\u9500\u5206\u6790\u5e08',viewer:'\u53ea\u8bfb\u7528\u6237'}[value] || cleanText(value, '\u672a\u6388\u6743'));

  function renderOpportunities(){
    const table=q('#opportunities .opportunity-table'); if(!table)return; const rows=tenantData.opportunities||[]; if(!rows.length){table.innerHTML='<tr><th>\u673a\u4f1a\u540d\u79f0</th><th>\u4fe1\u53f7</th><th>\u5ba2\u7fa4</th><th>\u4ef7\u503c</th><th>\u72b6\u6001</th><th>\u64cd\u4f5c</th></tr><tr><td colspan="6"><div class="empty-action">\u6682\u65e0\u8425\u9500\u673a\u4f1a\u3002\u53ef\u901a\u8fc7\u5e02\u573a\u70ed\u70b9\u91c7\u96c6\u6216\u4e0a\u4f20\u7ecf\u8425\u6570\u636e\u751f\u6210\u673a\u4f1a\u5019\u9009\u3002</div></td></tr>';return;}
    table.innerHTML='<tr><th>\u673a\u4f1a\u540d\u79f0</th><th>\u4fe1\u53f7</th><th>\u5ba2\u7fa4</th><th>\u4ef7\u503c</th><th>\u72b6\u6001</th><th>\u64cd\u4f5c</th></tr>'+rows.map(item=>'<tr><td><strong>'+escapeHtml(cleanText(item.name,'\u672a\u547d\u540d\u673a\u4f1a'))+'</strong><small>'+escapeHtml(cleanText(item.market_scope,'\u56fd\u5185'))+' · '+escapeHtml(cleanText(item.route,'\u822a\u7ebf\u5f85\u8865\u5145'))+'</small></td><td>'+escapeHtml(cleanText(item.signal_summary,'\u5f85\u8865\u5145\u4fe1\u53f7'))+'</td><td>'+Number(item.estimated_audience||0).toLocaleString('zh-CN')+'</td><td class="score">'+item.score+'</td><td><span class="status '+(item.status==='\u5f85\u8bc4\u4f30'||item.status==='\u5f85\u5904\u7406'?'warn':'good')+'">'+escapeHtml(cleanText(item.status,'\u5f85\u8bc4\u4f30'))+'</span></td><td class="production-actions"><button class="btn" data-opportunity-edit="'+escapeHtml(item.id)+'">\u7f16\u8f91</button><button class="btn danger" data-opportunity-delete="'+escapeHtml(item.id)+'">\u5220\u9664</button></td></tr>').join('');
  }
  function showInsightRunDetail(run){
    const agents=(run.result?.agents||[]).map(item=>`<article class="insight-agent-card"><div><b>${escapeHtml(displayText(item.agent_name,'洞察智能体'))}</b><span class="status good">评分 ${Number(item.score||0)}</span></div><p>${escapeHtml(displayText(item.summary,'暂无分析摘要'))}</p><small>${escapeHtml(displayText(item.topic,'未提取主题'))} · ${item.evidence_count||0} 条证据 · ${escapeHtml(item.execution||'待确认')}</small></article>`).join('');
    const steps=(run.steps||[]).map(item=>`<li><span class="insight-step-dot"></span><div><b>${escapeHtml(displayText(item.stage,'处理步骤'))}</b><small>${escapeHtml(displayText(item.detail,''))}</small></div><em>${item.status==='failed'?'失败':item.status==='completed'?'完成':'处理中'}</em></li>`).join('');
    const layer=document.createElement('div'); layer.className='production-modal'; layer.innerHTML=`<div class="production-modal-card insight-run-detail"><div class="production-modal-head"><div><b>商机洞察任务</b><small>${escapeHtml(run.id)} · ${escapeHtml(run.status)} · ${escapeHtml(run.current_stage)}</small></div><button class="btn" data-close>关闭</button></div><div class="production-modal-body"><div class="insight-run-grid"><section><h3>智能体进度</h3><ol class="insight-step-list">${steps||'<li>暂无执行记录</li>'}</ol></section><section><h3>并行洞察结果</h3><div class="insight-agent-list">${agents||'<div class="empty-action">任务尚未形成结果</div>'}</div></section></div>${run.error_message?`<div class="inline-error">${escapeHtml(run.error_message)}</div>` :''}</div></div>`; document.body.appendChild(layer); layer.addEventListener('click',event=>{if(event.target===layer||event.target.closest('[data-close]'))layer.remove();});
  }
  function renderOpportunityInsightPanel(){
    const view=q('#opportunities'); if(!view)return;
    let panel=q('#opportunityInsightPanel'); if(!panel){panel=document.createElement('div');panel.id='opportunityInsightPanel';panel.className='panel opportunity-insight-console';view.insertBefore(panel,view.firstElementChild?.nextElementSibling||view.firstElementChild);}
    const sources=tenantData.opportunitySources||[], runs=tenantData.opportunityRuns||[];
    const sourceRows=sources.map(item=>`<div class="insight-source-row"><label><input type="checkbox" data-insight-source value="${item.id}" ${item.enabled?'checked':''}><span><b>${escapeHtml(displayText(item.name,'未命名来源'))}</b><small>${escapeHtml(displayText(item.focus,'未配置关注点'))}</small></span></label><em>${escapeHtml(item.schedule||'manual')}</em><button class="btn compact" data-insight-source-edit="${item.id}">编辑</button><button class="btn compact danger" data-insight-source-delete="${item.id}">删除</button></div>`).join('');
    const runRows=runs.map(item=>`<tr><td><strong>${escapeHtml(item.id)}</strong><small>${escapeHtml(displayText(item.prompt,'未填写洞察要求'))}</small></td><td>${escapeHtml(item.current_stage)}</td><td><span class="status ${statusClass(item.status)}">${escapeHtml(item.status)}</span></td><td>${item.step_count||0}</td><td><button class="btn compact" data-insight-run-view="${item.id}">查看进度</button></td></tr>`).join('');
    panel.innerHTML=`<div class="panel-head"><div><h2>商机洞察智能体</h2></div><span class="insight-badge"><i data-lucide="sparkles"></i> AgentScope · 多智能体</span></div><div class="panel-body"><div class="insight-console-grid"><section class="insight-source-config"><div class="section-kicker">洞察来源</div><div class="insight-source-list">${sourceRows||'<div class="empty-action">暂无来源，请先新增一个网站或人工信号来源</div>'}</div><form id="opportunitySourceForm" class="insight-source-form"><input type="hidden" name="source_id"><input name="name" placeholder="来源名称，例如：三亚文旅官方动态" required><input name="source_url" placeholder="网站地址，可留空使用人工描述"><select name="source_type"><option value="web">网站</option><option value="api">接口</option><option value="manual">人工信号</option><option value="social">社媒</option></select><input name="schedule" value="manual" placeholder="采集方式，例如 manual / daily"><textarea name="focus" placeholder="希望重点关注什么：航线需求、节假日热度、产品机会、竞品变化等"></textarea><div class="insight-form-actions"><button type="submit" class="btn primary" data-action="saveOpportunitySource">保存来源</button><button type="button" class="btn" data-action="resetOpportunitySource">清空</button></div></form></section><section class="insight-run-config"><div class="section-kicker">业务洞察要求</div><textarea id="opportunityInsightPrompt" class="insight-prompt" placeholder="例如：围绕国庆前上海—三亚航线，关注客座率、价格、目的地热度、家庭客群和行李/选座辅营机会">围绕东航重点航线和近期市场热点，识别可落地的营销商机，并说明证据、适配客群和可引用产品。</textarea><div class="insight-run-actions"><button class="btn primary" data-action="runOpportunityInsight"><i data-lucide="play"></i>开始多智能体洞察</button></div><div class="insight-agent-lane"><span>市场信号</span><i>＋</i><span>航线经营</span><i>＋</i><span>产品商业化</span><b>→ 商机候选</b></div></section></div><div class="insight-history"><div class="section-kicker">洞察历史与溯源</div><table class="table compact-table"><tr><th>任务</th><th>当前阶段</th><th>状态</th><th>步骤</th><th>操作</th></tr>${runRows||'<tr><td colspan="5" class="muted">暂无洞察任务</td></tr>'}</table></div></div>`;
    if(window.lucide)lucide.createIcons();
  }
  function renderKnowledgeDocuments(){
    const host=q('#graph .graph-layout'); if(!host)return; let panel=q('#knowledgeDocuments'); if(!panel){panel=document.createElement('div');panel.id='knowledgeDocuments';panel.className='panel knowledge-documents';host.appendChild(panel);} const docs=tenantData.documents||[];
    panel.innerHTML='<div class="panel-head"><h2>\u77e5\u8bc6\u6587\u6863</h2><span>'+docs.length+' \u4e2a\u6587\u6863 · \u5220\u9664\u5c06\u540c\u6b65\u6e05\u7406\u672c\u4f53\u5bf9\u8c61</span></div><div class="panel-body">'+(docs.length?'<table class="table"><tr><th>\u6587\u6863</th><th>\u6765\u6e90</th><th>\u5207\u7247</th><th>\u672c\u4f53\u5bf9\u8c61</th><th>\u7248\u672c</th><th>\u64cd\u4f5c</th></tr>'+docs.map(d=>'<tr><td><strong>'+escapeHtml(cleanText(d.title,'\u672a\u547d\u540d\u6587\u6863'))+'</strong><small>'+escapeHtml(d.external_id)+'</small></td><td>'+escapeHtml(cleanText(d.source_name,d.source_type))+'</td><td>'+d.chunk_count+'</td><td>'+d.entity_count+'</td><td>V'+d.version+'</td><td class="production-actions"><button class="btn" data-document-edit="'+d.id+'">\u7f16\u8f91</button><button class="btn danger" data-document-delete="'+d.id+'">\u5220\u9664</button></td></tr>').join('')+'</table>':'<div class="empty-action">\u6682\u65e0\u77e5\u8bc6\u6587\u6863\u3002\u4e0a\u4f20\u6587\u4ef6\u540e\uff0c\u5904\u7406\u7ed3\u679c\u4f1a\u5728\u8fd9\u91cc\u5f62\u6210\u77e5\u8bc6\u4e0e\u672c\u4f53\u3002</div>')+'</div>';
  }
  /* 客群工作台分面：只过滤已在内存的画像字段，不新增任何请求。
     业务顺序编码在 module_name 的中文序号里（一、基础信息 …），
     按 Object.values 的插入序渲染会得到 一/三/二/五/六/四 的乱序。 */
  const audienceFacetState = { module: '', source: '', frequency: '', expanded: {} };
  const AUDIENCE_NUMERAL = { '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10 };

  function audienceModuleRank(name) {
    const head = String(name || '').trim().match(/^([一二三四五六七八九十]+)/);
    return head ? (AUDIENCE_NUMERAL[head[1][0]] ?? 99) : 99;
  }
  const audienceModuleLabel = name => String(name || '').replace(/^[一二三四五六七八九十]+\s*[、.．]\s*/, '').trim() || '画像维度';

  function audienceFacetCounts(dimensions, field) {
    const counts = new Map();
    dimensions.forEach(item => {
      const raw = String(item[field] ?? '').trim();
      if (raw) counts.set(raw, (counts.get(raw) || 0) + 1);
    });
    return [...counts.entries()].sort((a, b) => field === 'module_name'
      ? audienceModuleRank(a[0]) - audienceModuleRank(b[0])
      : b[1] - a[1] || a[0].localeCompare(b[0], 'zh-CN'));
  }

  function audienceFiltered(dimensions) {
    return dimensions.filter(item =>
      (!audienceFacetState.module || String(item.module_name ?? '').trim() === audienceFacetState.module)
      && (!audienceFacetState.source || String(item.collection_method ?? '').trim() === audienceFacetState.source)
      && (!audienceFacetState.frequency || String(item.update_frequency ?? '').trim() === audienceFacetState.frequency));
  }

  const AUDIENCE_FACET_LIMIT = 6;
  function renderAudienceRail(dimensions) {
    const host = q('#audiences [data-audience-rail]'); if (!host) return;
    /* 采集来源实测有 19 个取值，全列在侧栏对年长读者是负担：默认只留 6 项，可展开 */
    const groups = [
      { title: '维度模块', field: 'module_name', key: 'module' },
      { title: '采集来源', field: 'collection_method', key: 'source' },
      { title: '更新频率', field: 'update_frequency', key: 'frequency' },
    ].map(group => ({ ...group, values: audienceFacetCounts(dimensions, group.field) })).filter(group => group.values.length > 1);
    const signature = JSON.stringify(groups.map(group => [group.key, group.values]));
    if (host.dataset.railSignature !== signature) {
      host.dataset.railSignature = signature;
      host.innerHTML = groups.map(group => {
        const rows = group.values.map(([raw, count], index) => `<button type="button" class="v-facet${index >= AUDIENCE_FACET_LIMIT ? ' is-overflow' : ''}" data-audience-facet="${group.key}" data-audience-facet-value="${escapeHtml(raw)}" aria-pressed="false"><span>${escapeHtml(group.field === 'module_name' ? audienceModuleLabel(raw) : raw)}</span><b>${count}</b></button>`).join('');
        const more = group.values.length > AUDIENCE_FACET_LIMIT ? `<button type="button" class="v-facet-more" data-audience-expand="${group.key}"></button>` : '';
        return `<div class="v-rail__group" data-audience-group="${group.key}"><p class="v-rail__title">${group.title}</p>${rows}${more}</div>`;
      }).join('') + '<button type="button" class="btn v-rail__clear" data-audience-facet-clear><i data-lucide="filter-x"></i>清除筛选</button>';
      if (window.lucide) lucide.createIcons();
    }
    syncAudienceRail();
  }

  /* 只改状态不改节点：换掉整个导轨会把用户正在操作的按钮从 DOM 里摘走，
     键盘与读屏用户的焦点会掉回 <body>，端到端测试里缓存的句柄也会失效。 */
  function syncAudienceRail() {
    const host = q('#audiences [data-audience-rail]'); if (!host) return;
    qa('.v-facet', host).forEach(button => {
      const active = audienceFacetState[button.dataset.audienceFacet] === button.dataset.audienceFacetValue;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    qa('[data-audience-group]', host).forEach(group => {
      const open = !!audienceFacetState.expanded[group.dataset.audienceGroup];
      group.classList.toggle('is-open', open);
      const toggle = q('[data-audience-expand]', group);
      if (toggle) toggle.textContent = open ? `收起，只看前 ${AUDIENCE_FACET_LIMIT} 项` : `展开全部 ${qa('.v-facet', group).length} 项`;
    });
    const clear = q('[data-audience-facet-clear]', host);
    if (clear) clear.classList.toggle('is-shown', !!(audienceFacetState.module || audienceFacetState.source || audienceFacetState.frequency));
  }

  function bindAudienceFacets() {
    const host = q('#audiences [data-audience-rail]');
    if (!host || host.dataset.facetBound === 'true') return;
    host.dataset.facetBound = 'true';
    host.addEventListener('click', event => {
      if (event.target.closest('[data-audience-facet-clear]')) {
        audienceFacetState.module = ''; audienceFacetState.source = ''; audienceFacetState.frequency = '';
        renderAudienceStructure();
        return;
      }
      const toggle = event.target.closest('[data-audience-expand]');
      if (toggle) {
        const key = toggle.dataset.audienceExpand;
        audienceFacetState.expanded[key] = !audienceFacetState.expanded[key];
        syncAudienceRail();
        return;
      }
      const button = event.target.closest('[data-audience-facet]');
      if (!button) return;
      const key = button.dataset.audienceFacet, value = button.dataset.audienceFacetValue;
      audienceFacetState[key] = audienceFacetState[key] === value ? '' : value;
      renderAudienceStructure();
    });
  }

  function renderAudienceStructure() {
    mountStandardSync('audiences','/api/integrations/profile/audiences');
    const view = q('#audiences');
    const listPanel = q('[data-audience-list]', view);
    const detailPanel = q('[data-audience-detail]', view);
    const panel = q('.panel-body', listPanel);
    if (!view || !listPanel || !detailPanel || !panel) return;

    const packages = tenantData.audiencePackages || [];
    const tags = tenantData.audienceTags || [];
    const snapshots = tenantData.audienceSnapshots || [];
    const dimensions = tenantData.personaDimensions || [];
    const segments = tenantData.personaSegments || [];
    const visible = audienceFiltered(dimensions);
    const filtered = visible.length !== dimensions.length;

    const dimensionRows = visible.map(item => `<tr>
      <td><strong>${escapeHtml(displayText(item.field_name, '未命名画像字段'))}</strong><small>${escapeHtml(displayText(item.field_code, 'FIELD'))} · ${escapeHtml(audienceModuleLabel(item.module_name))}</small></td>
      <td>${escapeHtml(displayText(item.allowed_values, displayText(item.data_type, '按规则计算')))}</td>
      <td>${escapeHtml(displayText(item.collection_method, '系统分析'))}<small>${escapeHtml(displayText(item.update_frequency, '按日更新'))}</small></td>
      <td><button class="btn compact" data-audience-dimension="${escapeHtml(item.id)}">查看定义</button></td>
    </tr>`).join('');
    const packageRows = packages.map(item => {
      const protectedPackage = ['已冻结', '已使用', '执行中', '已归档'].includes(item.status);
      const dimensionCount = expressionDimensionIds(item).length;
      const composition = [dimensionCount ? `${dimensionCount} 项画像` : '', (item.tag_ids || []).length ? `${item.tag_ids.length} 个标签` : '', item.selection_mode === 'ai-selection' ? 'AI 条件' : '规则组合'].filter(Boolean).join(' + ');
      return `<tr>
        <td><strong>${escapeHtml(displayText(item.name, '未命名客群包'))}</strong><small>${escapeHtml(displayText(item.external_id, 'PACKAGE'))} <span class="package-source-tag created">已创建</span></small></td>
        <td>${Number(item.estimated_size || 0).toLocaleString('zh-CN')} 人</td>
        <td>${escapeHtml(composition || '待配置画像')}</td>
        <td><span class="status ${statusClass(item.status)}">${escapeHtml(displayText(item.status, '草稿'))}</span></td>
        <td class="production-actions"><button class="btn" data-audience-edit="${item.id}"${protectedPackage ? ' disabled title="已冻结或已投入执行的客群包不可直接编辑"' : ''}>编辑</button><button class="btn" data-audience-snapshot="${item.id}"${protectedPackage ? ' disabled' : ''}>冻结快照</button></td>
      </tr>`;
    }).join('');
    const presetRows = segments.map(item => `<tr>
      <td><strong>${escapeHtml(displayText(item.segment_name, '预置客群包'))}</strong><small>${escapeHtml(displayText(item.segment_code, 'PRESET'))} · ${escapeHtml(displayText(item.primary_persona_name, '客户类型'))} <span class="package-source-tag preset">预置组合</span></small></td>
      <td>按规则</td>
      <td>${item.rules?.length || 0} 项画像条件 · ${escapeHtml(displayText((item.recommended_products || [])[0], '待匹配产品包'))}</td>
      <td><span class="status good">可复用</span></td>
      <td class="production-actions"><button class="btn" data-audience-persona="${escapeHtml(item.id)}">查看组合</button></td>
    </tr>`).join('');
    const tagsHtml = tags.map(tag => `<div class="audience-tag-item"><div><strong>${escapeHtml(displayText(tag.name, '未命名标签'))}</strong><small>${escapeHtml(displayText(tag.code, 'TAG'))} · ${escapeHtml(displayText(tag.category, '画像标签'))} · ${escapeHtml(displayText(tag.source, '画像平台'))}</small></div><span class="status ${tag.enabled === false ? 'warn' : 'good'}">${tag.enabled === false ? '停用' : '启用'}</span><button class="btn" data-audience-tag-edit="${tag.id}">编辑</button></div>`).join('');

    panel.innerHTML = `<div data-audience-pane="personas" data-subview-panel="personas">
      <div class="catalog-summary"><div><b>底层画像字段</b><span>职业、性别、年龄、地域、订单特征、航线偏好等字段来自用户画像平台，可作为客群组合条件。</span></div><div class="catalog-summary-stats"><strong>${visible.length}</strong><small>${filtered ? `/ ${dimensions.length} 个画像字段` : '个画像字段'}</small><button class="btn" data-action="refreshAudienceCatalog"><i data-lucide="refresh-cw"></i>同步画像</button></div></div>
      <div class="catalog-section-head"><div><b>画像字段明细</b><span>画像字段是客群包的底层条件，不直接作为活动客群使用</span></div><span class="catalog-count">${visible.length} 个</span></div>
      <div class="v-scroll-x"><table class="table compact-table audience-dimension-table"><thead><tr><th>画像字段</th><th>取值 / 口径</th><th>采集来源 · 更新频率</th><th>操作</th></tr></thead><tbody>${dimensionRows || '<tr><td colspan="4"><div class="empty-action">没有符合筛选条件的画像字段，请清除左侧筛选</div></td></tr>'}</tbody></table></div>
    </div>
    <div data-audience-pane="packages" data-subview-panel="packages">
      <div class="catalog-summary"><div><b>可执行客群包</b><span>由多个画像字段、画像标签或 AI 圈选条件组合形成，可被营销活动直接引用。</span></div><div class="catalog-summary-stats"><strong>${packages.length + segments.length}</strong><small>个客群包</small><button class="btn primary" data-action="newAudience"><i data-lucide="plus"></i>新建客群包</button></div></div>
      <div class="catalog-section-head"><div><b>客群包清单</b><span>自定义客群包与系统预置组合统一管理</span></div><span class="catalog-count">${packages.length + segments.length} 个</span></div>
      <div class="v-scroll-x"><table class="table compact-table audience-package-table"><thead><tr><th>客群包</th><th>规模</th><th>组合内容</th><th>状态</th><th>操作</th></tr></thead><tbody>${packageRows}${presetRows || '<tr><td colspan="5"><div class="empty-action">暂无客群包，请先组合画像字段</div></td></tr>'}</tbody></table></div>
      <details class="audience-tag-details"><summary>画像标签维护 · ${tags.length} 个</summary><div class="audience-tag-list">${tagsHtml || '<div class="empty-action">暂无画像标签；客群包可直接使用底层画像字段。</div>'}</div></details>
      <div class="catalog-foot"><span>${dimensions.length} 个画像字段 · ${segments.length} 个预置客群包 · ${snapshots.length} 个已冻结快照</span><span>冻结快照后才能进入活动执行</span></div>
    </div>`;

    renderAudienceRail(dimensions);
    bindAudienceFacets();

    if (window.lucide) lucide.createIcons();
  }

  function showAudienceSelectionModal() {
    const snapshots = tenantData.audienceSnapshots || [];
    const rows = snapshots.map(item => `<tr><td><strong>${escapeHtml(displayText(item.external_id, `快照 #${item.id}`))}</strong><small>${escapeHtml(displayText(item.selection_logic, '已保存的客群圈选条件'))}</small></td><td>${Number(item.estimated_size || item.population || 0).toLocaleString('zh-CN')} 人</td><td>${escapeHtml(displayText(item.status, '已冻结'))}</td><td>${escapeHtml(item.frozen_at ? businessTime(item.frozen_at) : '暂无时间')}</td><td>${escapeHtml(displayText(item.created_by, '系统'))}</td></tr>`).join('');
    const layer = document.createElement('div');
    layer.className = 'production-modal';
    layer.innerHTML = `<div class="production-modal-card audience-selection-modal"><div class="production-modal-head"><div><b>圈选记录</b><small>查看已保存的圈选条件与冻结快照</small></div><button class="btn" data-close>关闭</button></div><div class="production-modal-body"><div class="query-builder"><span class="query-label">当前圈选示例</span><span class="query-chip">目的地意向 = 三亚</span><span class="query-chip">近7天搜索 ≥ 2次</span><span class="query-chip">出票状态 = 未出票</span><span class="query-chip">排除营销疲劳</span><button class="btn ai" data-action="calculateAudience">计算人数</button></div><div class="catalog-section-head"><div><b>已保存圈选快照</b><span>快照是活动执行时使用的客群版本</span></div><span class="catalog-count">${snapshots.length} 条</span></div>${rows ? `<table class="table compact-table"><thead><tr><th>快照</th><th>人数</th><th>状态</th><th>冻结时间</th><th>创建人</th></tr></thead><tbody>${rows}</tbody></table>` : '<div class="empty-action">暂无圈选快照，完成 AI 圈选并冻结客群包后会出现在这里。</div>'}</div></div>`;
    document.body.appendChild(layer);
    bindProductionModal(layer);
    if (window.lucide) lucide.createIcons();
  }

  function showAgentTrace(run){
    if(run?.output && Object.keys(run.output).length){showAgentResult(run);return;}
    const html=window.ceairTraceHTML(run)+'<p>'+escapeHtml(run.summary||'运行结束')+'</p>';
    const layer=document.createElement('div');layer.className='production-modal';layer.innerHTML='<div class="production-modal-card"><div class="production-modal-head"><b>\u667a\u80fd\u57df\u8fc7\u7a0b\u8ffd\u8e2a</b><button class="btn" data-close>\u5173\u95ed</button></div><div class="production-modal-body">'+html+'</div></div>';document.body.appendChild(layer);layer.addEventListener('click',e=>{if(e.target===layer||e.target.closest('[data-close]'))layer.remove();});if(window.lucide)lucide.createIcons();
  }
  function showAgentResult(run){
    const layer=document.createElement('div');layer.className='production-modal';
    const output=run.output||{}, text=output.body||output.text||run.summary;
    const modelNote=output.provider_type==='mock'?'竞赛流程验证模型 · 受控样例':output.execution==='deterministic-fallback'?'规则降级结果 · 模型调用失败':'模型建议';
    const objectNames={ValueProposition:'价值主张',StrategyPlan:'策略计划',Review:'效果复盘',Recommendation:'机会建议',CustomerAggregate:'客群圈选',ContentAsset:'内容资产'};
    const structured=output.structured||output.selection;
    layer.innerHTML='<div class="production-modal-card"><div class="production-modal-head"><b>'+escapeHtml(objectNames[output.object_type]||'智能域结果')+'</b><button class="btn" data-close>关闭</button></div><div class="production-modal-body"><p class="toolbar-note">'+escapeHtml(modelNote)+' · '+escapeHtml(run.applied_object?'已人工确认':'待人工确认')+'</p><h3>'+escapeHtml(output.title||domainLabels[run.domain_id]||'业务建议')+'</h3><p style="white-space:pre-wrap">'+escapeHtml(text)+'</p>'+(output.visual?'<button class="btn" data-output-visual>预览视觉模板</button>':'')+(structured?'<details open><summary>结构化业务对象</summary><pre>'+escapeHtml(JSON.stringify(structured,null,2))+'</pre></details>':'')+'<details><summary>业务依据</summary><pre>'+escapeHtml(JSON.stringify(output.context||{},null,2))+'</pre></details><details open><summary>运行过程与治理</summary>'+window.ceairTraceHTML(run)+'</details><p data-result-state>'+escapeHtml(run.applied_object?'已保存：'+run.applied_object.label:'等待人工确认')+'</p><button class="btn primary" data-result-accept '+(run.applied_object||!canWrite()||output.selection?.supported===false?'disabled':'')+'>确认并保存草稿</button></div></div>';
    document.body.appendChild(layer);bindProductionModal(layer);
    q('[data-output-visual]',layer)?.addEventListener('click',()=>window.ceairOpenVisual({external_id:run.id,title:output.title,name:'智能体候选视觉',body:output.body,campaign_id:run.campaign_id,audience_package_id:output.context?.audience?.id,product_package_id:output.context?.product?.id,channel:output.context?.channel||'App',generation_context:{...output.context,visual:output.visual}}));
    q('[data-result-accept]',layer)?.addEventListener('click',async event=>{
      const button=event.currentTarget;button.disabled=true;
      try{const saved=await request('/api/agent-runs/'+encodeURIComponent(run.id)+'/accept',{method:'POST'});q('[data-result-state]',layer).textContent='已保存：'+saved.label;await loadTenantData();toast('结果已保存为草稿');}
      catch(cause){button.disabled=false;toast(cause.message||'结果保存失败');}
    });
    if(window.lucide)lucide.createIcons();
  }
  function mountStandardSync(viewId,path){
    const head=q('#'+viewId+' .page-head');
    if(!head)return;
    let host=q('.head-actions',head);
    if(!host&&head){host=document.createElement('div');host.className='head-actions';qa(':scope > button',head).forEach(button=>host.appendChild(button));head.appendChild(host);}
    const existing=host?.querySelector('[data-standard-sync]');
    if(existing)existing.hidden=!isTenantAdmin();
    if(!host||existing||!isTenantAdmin())return;
    const button=document.createElement('button');button.className='btn';button.dataset.standardSync='true';button.title='导入上游系统 JSON';button.innerHTML='<i data-lucide="upload"></i>同步业务数据';
    const input=document.createElement('input');input.type='file';input.accept='.json';input.hidden=true;host.append(button,input);
    button.addEventListener('click',()=>input.click());
    input.addEventListener('change',async()=>{
      const file=input.files[0];if(!file)return;
      button.disabled=true;
      try{if(file.size>5*1024*1024)throw new Error('文件不能超过5MB');const payload=JSON.parse(await file.text());const result=await request(path,{method:'POST',body:JSON.stringify(payload)});toast('同步完成：新增'+result.created+'，更新'+result.updated+'，未变化'+result.unchanged);await loadTenantData();}
      catch(cause){toast(cause.message||'数据同步失败');}
      finally{input.value='';button.disabled=false;}
    });
  }
  function showDomainRequest(domain){
    if(!canWrite())return;
    const campaigns=tenantData.campaigns.filter(item=>item.status!=='已归档');
    if(!campaigns.length){toast('请先创建营销活动');return;}
    openBusinessEditor({
      title:domainLabels[domain]||'运行智能域',item:{campaign_id:campaigns[0].id,instruction:''},
      fields:[
        {name:'campaign_id',label:'关联活动',type:'select',options:campaigns.map(item=>({value:item.id,label:item.name}))},
        {name:'instruction',label:'业务要求',type:'textarea',required:true}
      ],
      save:async values=>{
        const run=await request('/api/agent-runs',{method:'POST',body:JSON.stringify({campaign_id:values.campaign_id,domain_id:domain,instruction:values.instruction})});
        if(run.status==='failed')throw new Error(run.summary);
        await loadTenantData();setTimeout(()=>showAgentResult(run),0);
      }
    });
  }
  function campaignActions(item){
    const archived=item.status==='已归档';
    const editable=['草稿','待修改'].includes(item.status);
    const removable=archived || ['草稿','待修改'].includes(item.status);
    return `<button class="btn" data-production-campaign-view="${escapeHtml(item.id)}">查看</button>${editable?`<button class="btn" data-production-campaign-edit="${escapeHtml(item.id)}">编辑</button>`:''}${archived?'<button class="btn danger" data-production-campaign-delete="'+escapeHtml(item.id)+'">删除</button>':removable?'<button class="btn danger" data-production-campaign-delete="'+escapeHtml(item.id)+'">删除</button>':'<button class="btn" data-production-campaign-archive="'+escapeHtml(item.id)+'">归档</button>'}`;
  }
  function renderCampaigns(){
    const campaigns = tenantData.campaigns;
    const activeKpi = q('#overview [data-kpi-slot="active"] b');
    const audienceKpi = q('#overview [data-kpi-slot="audience"] b');
    if (activeKpi) activeKpi.textContent = campaigns.length;
    if (audienceKpi) audienceKpi.textContent = campaigns.reduce((sum,item)=>sum+item.audience_size,0).toLocaleString('zh-CN');
    const rows = campaigns.map(item => `<tr>
<td>${escapeHtml(item.id)}</td>
<td>
<strong>${escapeHtml(item.name)}</strong>
</td>
<td>${escapeHtml(item.stage)}</td>
<td>${escapeHtml(item.version)}</td>
<td>${escapeHtml(item.owner)}</td>
<td>
<span class="status ${statusClass(item.status)}">${escapeHtml(item.status)}</span>
</td>
<td class="production-actions">${campaignActions(item)}</td>
</tr>`).join('');
    const campaignTable = q('#campaigns .table'); if (campaignTable) campaignTable.innerHTML = `<tr>
<th>活动编号</th>
<th>活动名称</th>
<th>当前节点</th>
<th>当前版本</th>
<th>负责人</th>
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
    const lower = q('#campaigns .campaign-lower'); if (lower) lower.hidden = true;
    renderProducts();
  }

  function dashboardEmpty(message, action, label) {
    const button = action ? `<button class="btn" data-action="${escapeHtml(action)}">${escapeHtml(label || '去处理')}</button>` : '';
    return `<div class="empty-action"><b>${escapeHtml(message)}</b>${button}</div>`;
  }

  function resetDashboard() {
    const overview = q('#overview');
    if (!overview) return;
    const kpiDefaults = { active: '0', opportunity: '0', audience: '0', revenue: '等待回流', roi: '等待回流' };
    qa('[data-kpi-slot]', overview).forEach(card => {
      const value = q('b', card); const note = q('em', card);
      if (value) value.textContent = kpiDefaults[card.dataset.kpiSlot] ?? '0';
      if (note) note.textContent = '正在加载当前租户数据';
    });
    const slot = name => q(`[data-ov-slot="${name}"]`, overview);
    const activity = q('.table', slot('activity'));
    if (activity) activity.innerHTML = `<tr><td colspan="6">${dashboardEmpty('正在加载活动数据')}</td></tr>`;
    const todo = q('.panel-body', slot('todo'));
    if (todo) todo.innerHTML = dashboardEmpty('正在加载智能域任务');
    const bars = q('.opportunity-bars', slot('bars'));
    if (bars) bars.innerHTML = dashboardEmpty('正在加载机会数据');
    const health = q('.metric-list', slot('health'));
    if (health) health.innerHTML = dashboardEmpty('正在加载执行健康度');
  }

  function dashboardState() {
    const campaigns = tenantData.campaigns || [];
    const opportunities = tenantData.opportunities || [];
    const audiencePackages = tenantData.audiencePackages || [];
    const productPackages = tenantData.productPackages || [];
    const approvals = tenantData.approvals || [];
    const channelTasks = tenantData.channelTasks || [];
    const executionBatches = tenantData.executionBatches || [];
    return {
      campaigns, opportunities, audiencePackages, productPackages, approvals, channelTasks, executionBatches,
      activeCampaigns: campaigns.filter(item => !/草稿|待修改|已完成|已归档|已取消|完成|归档|取消/.test(item.status || '')),
      visibleCampaigns: campaigns.filter(item => !/已归档|归档/.test(item.status || '')),
      openOpportunities: opportunities.filter(item => !/已转活动|已关闭|关闭/.test(item.status || '')),
      pendingApprovals: approvals.filter(approvalIsPending)
    };
  }

  function renderDashboardKpis(state) {
    const setKpi = (slot, value, note, tone) => {
      const card = q(`#overview [data-kpi-slot="${slot}"]`); if (!card) return;
      const valueNode = q('b', card); const noteNode = q('em', card);
      if (valueNode) valueNode.textContent = value;
      if (noteNode) { noteNode.textContent = note; noteNode.className = `trend${tone ? ` ${tone}` : ''}`; }
    };
    const usableAudiences=state.audiencePackages.filter(item=>['可用','已冻结'].includes(item.status));
    const audienceSize = usableAudiences.reduce((sum, item) => sum + Number(item.estimated_size || 0), 0);
    setKpi('active', state.activeCampaigns.length.toLocaleString('zh-CN'), state.pendingApprovals.length ? `${state.pendingApprovals.length}个待审批` : '无待审批', state.pendingApprovals.length ? 'amber' : '');
    setKpi('opportunity', state.openOpportunities.length.toLocaleString('zh-CN'), '待人工评估的机会', state.openOpportunities.length ? '' : 'amber');
    setKpi('audience', audienceSize.toLocaleString('zh-CN'), usableAudiences.length ? `${usableAudiences.length}个可用包 · 规模合计未去重` : '暂无客群包', state.audiencePackages.length ? '' : 'amber');
    const revenueFields = ['attributed_revenue_yuan', 'revenue_yuan', 'converted_revenue_yuan'];
    const revenueSources = [...state.campaigns, ...state.channelTasks];
    const hasRevenue = revenueSources.some(item => revenueFields.some(key => Number(item[key]) > 0));
    const revenue = revenueSources.reduce((sum, item) => sum + Number(item.attributed_revenue_yuan || item.revenue_yuan || item.converted_revenue_yuan || 0), 0);
    setKpi('revenue', hasRevenue ? `¥${(revenue / 10000).toFixed(1)}万` : '待回流', hasRevenue ? '基于已回传订单归因' : '需接入交易归因', hasRevenue ? '' : 'amber');
    const budget = state.campaigns.reduce((sum, item) => sum + Number(item.budget_yuan || 0), 0);
    setKpi('roi', hasRevenue && budget > 0 ? (revenue / budget).toFixed(2) : '待回流', hasRevenue && budget > 0 ? '收入归因 / 执行预算' : '归因数据完善后计算', hasRevenue && budget > 0 ? '' : 'amber');
  }

  function renderDashboardActivity(state) {
    const panel=q('#overview [data-ov-slot="activity"]'), table=q('.table',panel);
    if(table){
      const rows=state.visibleCampaigns.slice(0,8).map(item=>`<tr><td><strong>${escapeHtml(item.name)}</strong></td><td>${escapeHtml(item.stage||'未设置')}</td><td>${escapeHtml(item.owner||'未指定')}</td><td>${escapeHtml(item.version||'V1')}</td><td><span class='status ${statusClass(item.status)}'>${escapeHtml(item.status||'草稿')}</span></td><td class='action' data-open-campaign='${escapeHtml(item.name)}'>查看</td></tr>`).join('');
      table.innerHTML=`<thead><tr><th>活动</th><th>当前节点</th><th>负责人</th><th>版本</th><th>状态</th><th>操作</th></tr></thead><tbody>${rows||`<tr><td colspan='6'>${dashboardEmpty('当前租户暂无活动','createCampaign','新建活动')}</td></tr>`}</tbody>`;
    }
    const head=q('.panel-head span',panel);if(head)head.textContent=`${state.visibleCampaigns.length} 个活动`;
  }

  function renderDashboardTodos(state) {
    const body=q('.panel-body',q('#overview [data-ov-slot="todo"]'));if(!body)return;
    const todos=[];
    if(state.openOpportunities.length)todos.push(['radar','机会洞察',`${state.openOpportunities.length}条待处理机会，请由人工确认是否转为活动`,'useOpportunity','查看']);
    const audiences=state.audiencePackages.filter(item=>/草稿|待复核|待审批/.test(item.status||''));
    if(audiences.length)todos.push(['users-round','客群洞察',`${audiences.length}个客群包需要复核或冻结快照`,'useAudience','复核']);
    const products=state.productPackages.filter(item=>/草稿|待复核|待审批/.test(item.status||''));
    if(products.length)todos.push(['package','产品匹配',`${products.length}个活动产品包待完成复核`,'useProduct','查看']);
    if(state.pendingApprovals.length)todos.push(['clipboard-check','审批与合规',`${state.pendingApprovals.length}个审批任务等待人工决策`,'useApproval','处理']);
    body.innerHTML=todos.length?todos.map(item=>`<div class='todo'><span class='todo-icon'><i data-lucide='${item[0]}'></i></span><div><b>${item[1]}</b><small>${item[2]}</small></div><button class='btn' data-action='${item[3]}'>${item[4]}</button></div>`).join(''):dashboardEmpty('当前没有待处理的智能域任务');
    if(window.lucide)lucide.createIcons();
  }

  function renderDashboardCharts(state) {
    const barsPanel=q('#overview [data-ov-slot="bars"]'),bars=q('.opportunity-bars',barsPanel);
    if(bars){
      const groups=new Map();state.opportunities.forEach(item=>{const key=item.market_scope||'未分类',value=groups.get(key)||{count:0,score:0};value.count+=1;value.score+=Number(item.score||0);groups.set(key,value);});
      const values=[...groups.entries()].sort((a,b)=>(b[1].score/b[1].count)-(a[1].score/a[1].count)).slice(0,6),max=Math.max(...values.map(([,v])=>v.score/v.count),1);
      bars.innerHTML=values.length?`${values.map(([name,value])=>{const score=value.score/value.count;return `<div><span>${escapeHtml(name)}</span><i><em style='width:${Math.round(score/max*100)}%'></em></i><b>${value.count}</b></div>`;}).join('')}`:dashboardEmpty('当前暂无机会数据','scanOpportunity','扫描机会');
    }
    const head=q('.panel-head span',barsPanel);if(head)head.textContent=state.opportunities.length?`${state.opportunities.length} 条机会`:'当前租户暂无机会';
  }

  function renderDashboardHealth(state) {
    const body=q('.metric-list',q('#overview [data-ov-slot="health"]'));if(!body)return;
    const target=state.channelTasks.reduce((sum,item)=>sum+Number(item.target_count||0),0),delivered=state.channelTasks.reduce((sum,item)=>sum+Number(item.delivered_count||0),0);
    const delivery=target?Math.min(100,delivered/target*100):null,approval=state.approvals.length?state.approvals.filter(item=>!approvalIsPending(item)).length/state.approvals.length*100:null;
    const metric=(label,rate,tone)=>`<div class='metric'><label>${label}</label><b>${rate===null?'待产生':`${rate.toFixed(1)}%`}</b></div><div class='bar ${tone||''}'><i style='width:${rate===null?0:rate}%'></i></div>`;
    const withReceipts=state.channelTasks.filter(item=>item.last_feedback_at).length;
    body.innerHTML=metric('渠道送达率',delivery,'green')+metric('渠道任务回执覆盖率',state.channelTasks.length?withReceipts/state.channelTasks.length*100:null,'')+metric('审批处理率',approval,'amber');
  }

  function renderDashboard() {
    const state=dashboardState();
    renderDashboardKpis(state);renderDashboardActivity(state);renderDashboardTodos(state);renderDashboardCharts(state);renderDashboardHealth(state);
  }

  function renderProducts(){
    mountStandardSync('products','/api/integrations/products/packages');
    const table=q('#products .table'); if(!table)return;
    const products=tenantData.productPackages||[];
    const body=table.parentElement;
    let baseCatalog=q('#productCatalog');
    if(!baseCatalog){baseCatalog=document.createElement('div');baseCatalog.id='productCatalog';baseCatalog.className='base-product-catalog';body.insertBefore(baseCatalog,table);}
    const baseProducts=tenantData.productCatalog?.products||[];
    baseCatalog.innerHTML=`<div class="catalog-section-head"><div><b>基础产品目录</b><span>来自产品管理平台的可售产品，是产品包组合和活动匹配的底层对象</span></div><span class="catalog-count">${baseProducts.length} 个</span></div><div class="catalog-grid product-catalog-grid">${baseProducts.map(item=>`<div class="catalog-card product-card"><div class="catalog-card-top"><span class="catalog-icon"><i data-lucide="ticket"></i></span><span class="status good">可引用</span></div><strong>${escapeHtml(displayText(item.name,'未命名产品'))}</strong><small>${escapeHtml(displayText(item.category,'航空产品'))} · ${escapeHtml(displayText(item.code,'产品编码'))}</small><div class="catalog-card-meta"><span>${(item.benefits||[]).length} 项权益</span><button class="btn" data-product-catalog-view="${escapeHtml(item.code)}">查看产品</button></div></div>`).join('')||'<div class="empty-action">暂无基础产品，可从产品管理平台同步</div>'}</div>`;
    q('.catalog-section-head span',baseCatalog).textContent='联调产品目录；实际价格、库存与权益等待上游核验';
    const services=q('#products > .grid3');
    if(services)services.innerHTML='<div class="small-panel"><b>产品资格</b><span>价格、库存、航班与权益</span><em>等待上游可售校验</em></div><div class="small-panel"><b>标准接口</b><span>产品包导入、版本与来源追踪</span><em>可通过同步业务数据导入</em></div><div class="small-panel"><b>履约回流</b><span>购买、使用与异常状态</span><em>等待实际履约系统接入</em></div>';
    if(window.lucide)lucide.createIcons();
    const rows=products.map(item=>`<tr>
<td><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.product_type||'组合产品')} · ${escapeHtml(item.external_id)}</small></td>
<td>${escapeHtml(item.description||'待补充组合产品')}</td>
<td>${escapeHtml(item.eligibility||'待补充资格条件')}</td>
<td>${escapeHtml(item.version||'V1')}</td>
<td><span class="status ${statusClass(item.status)}">${escapeHtml(item.status||'草稿')}</span></td>
<td>${tenantData.campaigns.filter(campaign=>campaign.product_package===item.name).length}</td>
<td class="production-actions"><button class="btn" data-product-view="${item.id}">查看</button><button class="btn" data-product-edit="${item.id}">编辑</button><button class="btn danger" data-product-delete="${item.id}">删除</button></td>
</tr>`).join('');
    table.innerHTML=`<tr><th>产品包</th><th>组合产品</th><th>资格条件</th><th>版本</th><th>状态</th><th>引用活动</th><th>操作</th></tr>${rows||'<tr><td colspan="7"><div class="empty-action">暂无活动产品包。可从产品管理平台同步，或新建活动产品包。</div></td></tr>'}`;
  }

  function contentContextValues(){
    const form=q('#contentGenerationContextForm');
    if(!form)return {...contentGenerationContext};
    const values=Object.fromEntries(new FormData(form));
    contentGenerationContext={...contentGenerationContext,campaign_id:String(values.campaign_id||''),audience_package_id:String(values.audience_package_id||''),product_package_id:String(values.product_package_id||''),channel:String(values.channel||'App'),objective:String(values.objective||'提升转化'),instruction:String(values.instruction||'').trim()};
    return {...contentGenerationContext};
  }
  function contentContextSummary(context){
    const campaign=(tenantData.campaigns||[]).find(item=>item.id===context.campaign_id);
    const audience=(tenantData.audiencePackages||[]).find(item=>String(item.id)===String(context.audience_package_id));
    const product=(tenantData.productPackages||[]).find(item=>String(item.id)===String(context.product_package_id));
    return { campaign, audience, product, channel:context.channel, objective:context.objective, instruction:context.instruction };
  }
  function renderContentGenerationContext(){
    const view=q('#contents'); if(!view)return;
    let panel=q('#contentGenerationContext');
    if(!panel){panel=document.createElement('section');panel.id='contentGenerationContext';panel.className='panel content-generation-context';const anchor=q('#contents > .toolbar-strip');anchor?.insertAdjacentElement('afterend',panel);}
    const campaigns=tenantData.campaigns||[], audiences=tenantData.audiencePackages||[], products=tenantData.productPackages||[];
    const options=(items,value,label)=>items.map(item=>`<option value="${escapeHtml(value(item))}"${String(value(item))===String(contentGenerationContext[label]||'')?' selected':''}>${escapeHtml(label==='campaign_id'?`${item.name} · ${item.id}`:label==='audience_package_id'?`${item.name} · ${Number(item.estimated_size||0).toLocaleString('zh-CN')}人`: `${item.name} · ${item.version||'V1'}`)}</option>`).join('');
    const channel=channelOptions.map(item=>`<option value="${item[0]}"${item[0]===contentGenerationContext.channel?' selected':''}>${item[1]}</option>`).join('');
    const objectives=['提升转化','促进出票','提升辅营购买','会员权益激活','航线淡季促销','企业客户线索转化'];
    const objectiveOptions=objectives.map(item=>`<option${item===contentGenerationContext.objective?' selected':''}>${item}</option>`).join('');
    const ready=Boolean(contentGenerationContext.campaign_id&&contentGenerationContext.audience_package_id&&contentGenerationContext.product_package_id&&contentGenerationContext.channel);
    const contextHTML=`<div class="panel-head"><div><h2>生成配置</h2></div><span class="context-readiness ${ready?'ready':'pending'}">${ready?'配置完成':'待补齐必要信息'}</span></div><div class="panel-body"><form id="contentGenerationContextForm" class="content-context-form"><label><span>关联活动 <em>*</em></span><select name="campaign_id"><option value="">${campaigns.length?'请选择活动':'暂无活动，请先创建'}</option>${options(campaigns,item=>item.id,'campaign_id')}</select></label><label><span>目标客群包 <em>*</em></span><select name="audience_package_id"><option value="">${audiences.length?'请选择客群包':'暂无客群包，请先组合画像'}</option>${options(audiences,item=>item.id,'audience_package_id')}</select></label><label><span>活动产品包 <em>*</em></span><select name="product_package_id"><option value="">${products.length?'请选择产品包':'暂无产品包，请先创建'}</option>${options(products,item=>item.id,'product_package_id')}</select></label><label><span>目标渠道 <em>*</em></span><select name="channel">${channel}</select></label><label><span>内容目标</span><select name="objective">${objectiveOptions}</select></label><label class="context-instruction"><span>补充要求</span><input name="instruction" value="${escapeHtml(contentGenerationContext.instruction)}" placeholder="例如：突出行李权益，不使用最低价表述"/></label><button class="btn ai content-generate-trigger" type="button" data-action="generateContent" ${ready?'':'disabled'}><i data-lucide="wand-sparkles"></i>按当前上下文生成</button></form></div>`;
    panel.dataset.subviewPanel='assets tasks';
    panel.innerHTML='<div class="panel-head"><h2>生成配置</h2><span class="context-readiness '+(ready?'ready':'pending')+'">'+(ready?'已配置':'待配置')+'</span><button class="btn" type="button" data-content-configure>配置与生成</button></div>';
    q('[data-content-configure]',panel).onclick=()=>{
      const layer=document.createElement('div');layer.className='production-modal content-config-modal';
      layer.innerHTML='<div class="production-modal-card"><div class="production-modal-head"><b>内容生成</b><button class="btn" type="button" data-close>关闭</button></div><div class="production-modal-body">'+contextHTML+'</div></div>';
      document.body.append(layer);bindProductionModal(layer,{onClose:renderContentGenerationContext});
      const form=q('#contentGenerationContextForm',layer);
      const update=()=>{const values=contentContextValues();const valid=Boolean(values.campaign_id&&values.audience_package_id&&values.product_package_id&&values.channel);q('.content-generate-trigger',form).disabled=!valid;const state=q('.context-readiness',layer);state.textContent=valid?'已配置':'待配置';state.classList.toggle('ready',valid);state.classList.toggle('pending',!valid);};
      form.addEventListener('change',update);form.addEventListener('input',update);
      form.addEventListener('submit',event=>{event.preventDefault();const trigger=q('.content-generate-trigger',form);if(!trigger.disabled)trigger.click();});
      if(window.lucide)lucide.createIcons();
    };
    if(window.lucide)lucide.createIcons();
  }
  function renderContentPreview(item){
    const selected=item||null;
    const channels=channelOptions.map(option=>`<button type="button" class="preview-channel ${selectedPreviewChannel===option[0]?'active':''}" data-preview-channel="${option[0]}">${option[1]}</button>`).join('');
    const previewItem=selected?{...selected,channel:selectedPreviewChannel}:null;
    const host=q('#contentPreviewHost');
    if(!host)return;
    host.innerHTML=`<div class="preview-channel-tabs">${channels}</div>${previewItem?renderContentChannelPreview(previewItem):'<div class="empty-action">选择一条内容资产后，可切换 App、官网、微信、短信等渠道查看实际样式。</div>'}`;
    qa('[data-preview-channel]',host).forEach(button=>button.addEventListener('click',()=>{selectedPreviewChannel=button.dataset.previewChannel||'App';renderContentPreview(selected);}));
  }
  function renderContents(){
    const table=q('#contents .table'); if(!table)return;
    const assets=tenantData.contentAssets||[];
    const rows=assets.map(item=>`<tr class="${String(item.id)===String(selectedContentAssetId)?'selected-row':''}"><td><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.title||'')}</small></td><td>${escapeHtml(item.campaign_id||'未关联活动')}</td><td>${escapeHtml(item.channel)}</td><td>${escapeHtml(item.version)}</td><td><span class="status ${statusClass(item.status)}">${escapeHtml(item.status)}</span></td><td class="production-actions"><button class="btn" data-content-view="${item.id}">查看</button><button class="btn" type="button" data-content-actions="${item.id}">更多</button></td></tr>`).join('');
    table.innerHTML=`<tr><th>内容名称</th><th>活动</th><th>渠道</th><th>版本</th><th>状态</th><th>操作</th></tr>${rows||'<tr><td colspan="6"><div class="empty-action">暂无内容资产。请先选择活动、客群包、产品包和渠道，再生成内容。</div></td></tr>'}`;
    const selected=assets.find(item=>String(item.id)===String(selectedContentAssetId))||assets[0];
    if(selected)selectedContentAssetId=String(selected.id);
    const previewPanel=q('#contents .grid2 .panel:nth-child(2)');
    if(previewPanel){previewPanel.dataset.subviewPanel='preview';const body=previewPanel.querySelector('.panel-body');if(body){body.innerHTML='<div id="contentPreviewHost"></div><div class="check-inline"><span>待事实审核</span><span>待合规审核</span><span>待渠道校验</span></div>';renderContentPreview(selected);}}
    renderContentGenerationContext();
    if(window.lucide)lucide.createIcons();
  }
  async function generateContentFromContext(button){
    if(!canWrite())return;
    if(!button.classList.contains('content-generate-trigger')){q('[data-content-configure]')?.click();return;}
    const context=contentContextValues();
    const missing=[];
    if(!context.campaign_id)missing.push('活动');
    if(!context.audience_package_id)missing.push('客群包');
    if(!context.product_package_id)missing.push('产品包');
    if(!context.channel)missing.push('渠道');
    if(missing.length){toast(`请先选择：${missing.join('、')}`);q('#contentGenerationContext')?.scrollIntoView({behavior:'smooth',block:'center'});return;}
    const {campaign,audience,product,channel,objective,instruction}=contentContextSummary(context);
    if(!campaign||!audience||!product){toast('当前选择已失效，请重新选择活动、客群包和产品包');renderContentGenerationContext();return;}
    const label=button.querySelector('span')?.textContent||button.textContent||'按当前上下文生成';
    q('.content-config-modal')?.__closeProductionModal?.();
    const previous=button.innerHTML;button.disabled=true;button.classList.add('is-loading');button.innerHTML='<i data-lucide="loader-circle" class="spin"></i>正在生成';
    const generationPanel=q('#contentGenerationPanel');
    if(generationPanel){generationPanel.innerHTML=`<div class="panel-head"><h2>任务进度</h2><span class="live-state is-active"><i></i>正在处理</span></div><div class="panel-body"><div class="content-progress"><div class="content-progress-head"><b>正在读取业务上下文</b><span>1/4</span></div><div class="content-progress-bar"><i style="width:22%"></i></div><ol><li class="active">读取活动：${escapeHtml(campaign.name)}</li><li>分析客群包：${escapeHtml(audience.name)}</li><li>校验产品包：${escapeHtml(product.name)}</li><li>生成 ${escapeHtml(channel)} 内容版本</li></ol></div></div>`;}
    if(window.lucide)lucide.createIcons();
    try{
      const run=await request('/api/agent-runs',{method:'POST',body:JSON.stringify({campaign_id:campaign.id,domain_id:'content-generation',audience_package_id:Number(audience.id),product_package_id:Number(product.id),channel,objective,instruction})});
      if(run.status==='failed')throw new Error(run.summary);
      await loadTenantData();showAgentResult(run);
    }catch(cause){toast(cause.message||'内容生成失败');if(generationPanel)renderAgentRunPanel('contentGenerationPanel',['content-generation'],'内容生成任务尚未开始');}
    finally{button.disabled=false;button.classList.remove('is-loading');button.innerHTML=previous||label;if(window.lucide)lucide.createIcons();}
  }

  function currentExecutionBatch(){
    const batches=tenantData.executionBatches||[];
    const chosen=batches.find(item=>String(item.id)===selectedExecutionBatchId);
    const batch=chosen||batches.find(item=>item.campaign_id===selectedExecutionCampaignId)||batches[0];
    selectedExecutionBatchId=batch?String(batch.id):'';
    selectedExecutionCampaignId=batch?.campaign_id||'';
    return batch;
  }
  function renderExecution(){
    const section=q('#execution'); if(!section)return;
    const batches=tenantData.executionBatches||[]; const batch=currentExecutionBatch();
    const selects=qa('.toolbar-strip select',section);
    const campaignIds=[...new Set(batches.map(item=>item.campaign_id))];
    if(selects[0]){selects[0].setAttribute('aria-label','执行活动');selects[0].innerHTML=campaignIds.length?campaignIds.map(id=>`<option value="${escapeHtml(id)}">${escapeHtml(tenantData.campaigns.find(item=>item.id===id)?.name||id)}</option>`).join(''):'<option>暂无可执行活动</option>';selects[0].value=selectedExecutionCampaignId;}
    const channels=batch?.channels||[];
    if(!channels.includes(selectedExecutionChannel))selectedExecutionChannel='';
    if(selects[1]){selects[1].setAttribute('aria-label','执行渠道');selects[1].innerHTML='<option value="">全部渠道</option>'+channels.map(channel=>`<option value="${escapeHtml(channel)}">${escapeHtml(channel)}</option>`).join('');selects[1].value=selectedExecutionChannel;}
    if(selects[2]){selects[2].setAttribute('aria-label','执行批次');selects[2].innerHTML=batch?batches.filter(item=>item.campaign_id===batch.campaign_id).map(item=>`<option value="${item.id}">${escapeHtml(item.external_id)} · ${escapeHtml(item.status)}</option>`).join(''):'<option>暂无执行批次</option>';selects[2].value=selectedExecutionBatchId;}
    const labels=['目标名单','渠道送达','互动事件','渠道失败','执行状态'];
    qa('.kpi > span',section).forEach((node,index)=>node.textContent=labels[index]);
    const executeButton=q('[data-action="refreshExecution"]',section);
    const pauseButton=q('[data-action="pauseCampaign"]',section);
    if(executeButton){executeButton.innerHTML='<i data-lucide="play"></i>执行联调';executeButton.disabled=!canWrite()||!batch||!['待执行','已暂停'].includes(batch.status);executeButton.title='生成虚构渠道回执，用于流程验证';if(batch)executeButton.dataset.batchId=batch.id;else delete executeButton.dataset.batchId;}
    if(pauseButton){pauseButton.disabled=!canWrite()||!batch||!['待执行','执行中'].includes(batch.status);if(batch)pauseButton.dataset.batchId=batch.id;else delete pauseButton.dataset.batchId;}
    const trends=qa('.kpi .trend',section);
    ['冻结快照规模','渠道任务送达计数','点击与转化事件','渠道失败计数',batch?'批次实际状态':'等待审批'].forEach((label,index)=>{if(trends[index])trends[index].textContent=label;});
    if(!batch){const kpis=qa('.kpi b',section);kpis.forEach((node,index)=>{node.textContent=index===4?'待产生':'0';});const selects=qa('.toolbar-strip select',section);selects.forEach(select=>{select.innerHTML='<option>暂无可执行数据</option>';});const table=q('#execution .table');if(table)table.innerHTML='<tr><th>渠道</th><th>任务数</th><th>成功</th><th>失败</th><th>回执延迟</th><th>状态</th></tr><tr><td colspan="6" class="table-empty">暂无执行批次，审批通过后将按活动版本渠道自动生成</td></tr>';const control=q('.grid2 > .panel:nth-child(2) .panel-body',section);if(control)control.innerHTML='<div class="empty-action">暂无执行控制项，活动进入执行阶段后可进行暂停、快照和失败补偿。</div>';const head=q('.grid2 > .panel:first-child .panel-head span',section);if(head)head.textContent='等待活动进入执行阶段';return;}
    const kpis=qa('.kpi b',section); if(kpis[0])kpis[0].textContent=Number(batch.target_size||0).toLocaleString('zh-CN'); if(kpis[1])kpis[1].textContent=Number(batch.delivered_count||0).toLocaleString('zh-CN'); if(kpis[2])kpis[2].textContent=Number(batch.feedback_count||0).toLocaleString('zh-CN'); if(kpis[3])kpis[3].textContent=Number(batch.failed_count||0).toLocaleString('zh-CN'); if(kpis[4])kpis[4].textContent=batch.status;
    const action=qa('#execution [data-action]'); action.filter(button=>['pauseCampaign','refreshExecution'].includes(button.dataset.action)).forEach(button=>{button.dataset.batchId=batch.id;});
    const tasks=(tenantData.channelTasks||[]).filter(item=>item.batch_id===batch.id&&(!selectedExecutionChannel||item.channel===selectedExecutionChannel));
    const control=q('.grid2 > .panel:nth-child(2) .panel-body',section);
    if(control)control.innerHTML=`<div class="control-item"><b>执行批次</b><span>${escapeHtml(batch.external_id)} · ${escapeHtml(batch.status)}</span></div><div class="control-item"><b>冻结规模</b><span>${Number(batch.target_size||0).toLocaleString('zh-CN')} 人 · 活动版本 #${Number(batch.campaign_version_id)}</span><button class="btn" data-action="viewAudienceSnapshot">查看快照</button></div><div class="control-item"><b>渠道联调</b><span>${escapeHtml((batch.channels||[]).join('、'))} · 虚构回执用于流程验证</span></div>`;
    const head=q('.grid2 > .panel:first-child .panel-head span',section);if(head)head.textContent=batch.external_id;
    const table=q('#execution .table');
    if(table){const rows=tasks.length?tasks.map(item=>`<tr><td><strong>${escapeHtml(item.channel)}</strong><small class="table-subline">${escapeHtml(item.external_id)}</small></td><td>${Number(item.target_count||0).toLocaleString('zh-CN')}</td><td>${Number(item.delivered_count||0).toLocaleString('zh-CN')}</td><td>${Number(item.failed_count||0).toLocaleString('zh-CN')}</td><td>${item.last_feedback_at?businessTime(item.last_feedback_at,true):'待回执'}</td><td><span class="status ${item.status==='失败'?'bad':item.status==='执行中'?'good':'warn'}">${escapeHtml(item.status)}</span> <button class="btn compact" data-channel-feedback="${item.id}">录入回执</button></td></tr>`).join(''):'<tr><td colspan="6" class="table-empty">当前渠道暂无任务</td></tr>';table.innerHTML=`<tr><th>渠道</th><th>任务数</th><th>送达</th><th>失败</th><th>最近回执时间</th><th>状态</th></tr>${rows}`;}
    renderExecutionBatchPanel();
  }
  function renderFeedback(){
    const section=q('#feedback'); if(!section)return;
    const summary=tenantData.effectSummary||{};
    const hasBatch=Boolean(summary.batch_count);
    const campaign=(tenantData.campaigns||[]).find(item=>item.id===summary.campaign_id);
    const latest=(tenantData.executionBatches||[]).find(item=>item.campaign_id===summary.campaign_id);
    const format=value=>Number(value||0).toLocaleString('zh-CN');
    const values=hasBatch?[format(summary.target_count),`${Number(summary.click_rate||0).toFixed(1)}%`,`${Number(summary.conversion_rate||0).toFixed(1)}%`,'待回流','待回流']:['0','0%','0%','待回流','待回流'];
    const labels=['目标名单','点击率','点击后转化率','增量收入','活动ROI'];
    const notes=['渠道任务目标计数','点击 / 送达','转化 / 点击','等待交易归因','等待收入与成本归因'];
    qa('.kpi',section).forEach((card,index)=>{
      const label=q('span',card),value=q('b',card),note=q('em',card);
      if(label)label.textContent=labels[index];if(value)value.textContent=values[index];if(note)note.textContent=notes[index];
    });
    const selects=qa('.toolbar-strip select',section);
    if(selects[0]){selects[0].setAttribute('aria-label','复盘活动');selects[0].innerHTML=(tenantData.campaigns||[]).map(item=>`<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join('')||'<option>暂无可复盘活动</option>';selects[0].value=selectedEffectCampaignId;}
    if(selects[1]){selects[1].setAttribute('aria-label','复盘批次');selects[1].innerHTML=`<option>${escapeHtml(latest?.external_id||'暂无执行批次')}</option>`;}
    let sourceNote=q('.feedback-data-note',section);
    if(!sourceNote){sourceNote=document.createElement('div');sourceNote.className='feedback-data-note';section.insertBefore(sourceNote,q('.kpis',section));}
    const receiptLabel=summary.sent_count?(summary.execution_mode==='synthetic'?'虚构回执（流程验证）':'渠道回执已汇总'):'等待批次执行';
    const explanation=hasBatch?`当前展示最新执行批次；送达率 ${Number(summary.delivery_rate||0)}%，点击率 ${Number(summary.click_rate||0)}%，点击后转化率 ${Number(summary.conversion_rate||0)}%。${summary.execution_mode==='synthetic'?'数值仅用于流程验证，不代表实际经营结果。':''}收入与 ROI 等待交易归因回流。`:'活动审批并执行后展示渠道回执，收入与 ROI 等待交易归因回流。';
    sourceNote.innerHTML=`<b>${hasBatch?receiptLabel:'暂无渠道回执'}</b><p>${escapeHtml(explanation)}</p>`;
    const funnel=q('.grid2 > .panel:first-child .metric-list',section);
    const funnelNote=q('.grid2 > .panel:first-child .panel-head span',section);if(funnelNote)funnelNote.textContent='按目标任务计数；不代表旅客去重归因';
    if(funnel){const counts=[summary.target_count,summary.delivered_count,summary.clicked_count,summary.converted_count],rates=counts.map(value=>summary.target_count?Number(value||0)/summary.target_count*100:0);funnel.innerHTML=hasBatch?['目标任务','送达','点击','转化'].map((name,index)=>`<div class="metric"><label>${name}</label><b>${format(counts[index])}</b></div><div class="bar"><i style="width:${Math.max(0,Math.min(100,Number(rates[index]||0)))}%"></i></div>`).join(''):'<div class="empty-state"><b>暂无渠道回执</b><span>执行活动后查看渠道任务统计</span></div>';}
    const box=q('#reviewBox');if(box)box.innerHTML=hasBatch?`<div class="review-summary"><b>${receiptLabel}</b><p>${escapeHtml(explanation)}</p><div class="review-tags"><span>送达 ${format(summary.delivered_count)}</span><span>点击 ${format(summary.clicked_count)}</span><span>转化 ${format(summary.converted_count)}</span><span>失败 ${format(summary.failed_count)}</span></div></div>`:'<div class="empty-state"><b>暂无渠道回执</b><span>执行活动后查看复盘依据</span></div>';
    if(window.lucide)lucide.createIcons();
  }
  let selectedProductionApprovalId = null;

  function approvalIsPending(item) {
    return /待审批|待处理|处理中/.test(String(item?.status || ''));
  }

  function approvalCampaign(approval) {
    return (tenantData.campaigns || []).find(item => String(item.id) === String(approval?.campaign_id));
  }

  async function showProductionApprovalDetail(approvalId) {
    const approval = (tenantData.approvals || []).find(item => String(item.id) === String(approvalId));
    const detail = q('#approvalDetail');
    const no = q('#approvalNo');
    if (!approval || !detail) return;
    selectedProductionApprovalId = approval.id;
    const campaign = approvalCampaign(approval) || {};
    let version = null;
    try {
      const versions = await request(`/api/campaigns/${encodeURIComponent(approval.campaign_id)}/versions`);
      version = (versions || []).find(item => String(item.id) === String(approval.campaign_version_id)) || versions?.[0] || null;
    } catch {
      version = null;
    }
    const audience = version?.audience_snapshot_id ? (tenantData.audienceSnapshots || []).find(item => String(item.id) === String(version.audience_snapshot_id)) : null;
    const product = version?.product_package_id ? (tenantData.productPackages || []).find(item => String(item.id) === String(version.product_package_id)) : null;
    const contentIds = version?.content_asset_ids || [];
    const contents = (tenantData.contentAssets || []).filter(item => contentIds.map(String).includes(String(item.id)));
    const audienceSize = audience?.estimated_size ?? campaign.audience_size ?? 0;
    const productName = product?.name || campaign.product_package || (version?.product_package_id ? `产品包 #${version.product_package_id}` : '未绑定产品包');
    const channels = version?.channels || [];
    const status = displayText(approval.status, '待审批');
    const pending = approvalIsPending(approval);
    if (no) no.textContent = displayText(approval.external_id, `审批任务 #${approval.id}`);
    detail.dataset.title = displayText(campaign.name, approval.campaign_id);
    detail.innerHTML = `<div class="approval-detail-hero"><span class="approval-icon activity"><i data-lucide="megaphone"></i></span><div><h3>${escapeHtml(displayText(campaign.name, approval.campaign_id))}</h3><p>${escapeHtml(approval.approver_role || '营销审批')} · ${escapeHtml(displayText(version?.version, campaign.version || '当前版本'))} · ${escapeHtml(displayText(approval.external_id, '审批任务'))}</p></div><span class="pill ${pending ? 'red' : 'blue'}">${escapeHtml(status)}</span></div><div class="approval-detail-grid"><div><b>活动阶段</b><span>${escapeHtml(displayText(campaign.stage, '未设置'))} · ${escapeHtml(displayText(campaign.status, '未设置'))}</span></div><div><b>负责人</b><span>${escapeHtml(displayText(campaign.owner, '未设置'))}</span></div><div><b>客群范围</b><span>${Number(audienceSize || 0).toLocaleString('zh-CN')} 人${audience ? ` · ${escapeHtml(audience.name || audience.package_name || '客群快照')}` : ''}</span></div><div><b>产品包</b><span>${escapeHtml(productName)}</span></div><div><b>预算</b><span>¥${Number(version?.budget_yuan ?? campaign.budget_yuan ?? 0).toLocaleString('zh-CN')}</span></div><div><b>触达渠道</b><span>${escapeHtml(channels.join('、') || '未配置')}</span></div></div><div class="approval-content-preview"><b>版本与内容</b><p>${version ? `版本 ${escapeHtml(version.version || '未命名')} · ${contents.length} 个内容资产 · ${escapeHtml(version.status || '未设置')}` : '版本详情暂不可用，请刷新后重试。'}</p>${contents.slice(0, 3).map(item => `<div class="approval-content-item"><span>${escapeHtml(item.channel || '渠道')}</span><b>${escapeHtml(displayText(item.title || item.name, '未命名内容'))}</b></div>`).join('')}</div><div class="approval-checks"><div class="approval-check"><i><i data-lucide="check"></i></i><span><b>客群快照关联</b><small>${audience ? '已绑定客群快照，可追溯冻结规模与生成时间' : '未绑定客群快照，请补充活动客群'}</small></span></div><div class="approval-check"><i><i data-lucide="${product ? 'check' : 'alert-circle'}"></i></i><span><b>产品版本关联</b><small>${product ? '已关联当前产品版本；实际价格、库存与权益仍需上游核验' : '未关联产品包，请补充活动产品'}</small></span></div><div class="approval-check"><i><i data-lucide="${channels.length ? 'check' : 'alert-circle'}"></i></i><span><b>渠道配置</b><small>${channels.length ? `已配置 ${channels.length} 个触达渠道` : '尚未配置触达渠道'}</small></span></div><div class="approval-check"><i><i data-lucide="${approval.comment ? 'message-square-check' : 'clock-3'}"></i></i><span><b>审批意见</b><small>${escapeHtml(approval.comment || (pending ? '等待审批人处理' : '暂无审批意见'))}</small></span></div></div>${pending ? '<div class="approval-actions"><button class="btn danger" data-production-approval-action="reject">退回修改</button><button class="btn primary" data-production-approval-action="approve" disabled>通过并进入执行</button></div>' : ''}`;
    if (window.lucide) lucide.createIcons();
    try {
      const readiness=await request('/api/campaigns/'+encodeURIComponent(approval.campaign_id)+'/readiness?version_id='+approval.campaign_version_id);
      if(String(selectedProductionApprovalId)!==String(approval.id))return;
      q('.approval-checks',detail).innerHTML=readiness.checks.map(c=>'<div class="approval-check"><i><i data-lucide="'+(c.passed?'check':'alert-circle')+'"></i></i><span><b>'+escapeHtml(c.label)+' · '+(c.passed?'通过':'待补齐')+'</b><small>'+escapeHtml(c.detail)+'</small></span></div>').join('');
      const approve=q('[data-production-approval-action="approve"]',detail);if(approve)approve.disabled=!readiness.ready;
      if(window.lucide)lucide.createIcons();
    }catch(error){q('.approval-checks',detail).textContent='校验加载失败：'+error.message;const approve=q('[data-production-approval-action="approve"]',detail);if(approve)approve.disabled=true;}

  }

  window.showProductionApprovalDetail = showProductionApprovalDetail;

  function bindProductionApprovalCapture() {
    if (document.documentElement.dataset.productionApprovalCapture) return;
    document.documentElement.dataset.productionApprovalCapture = 'true';
    document.addEventListener('click', event => {
      const approvalButton = event.target.closest?.('[data-approval]');
      const actionButton = event.target.closest?.('[data-production-approval-action]');
      if (approvalButton) {
        event.preventDefault();
        event.stopImmediatePropagation();
        qa('.approval-item').forEach(item => item.classList.toggle('active', item === approvalButton));
        showProductionApprovalDetail(approvalButton.dataset.approval);
        return;
      }
      const modal = q('#decisionModal');
      const decisionChoice = event.target.closest?.('[data-decision]');
      const confirmButton = event.target.closest?.('#confirmDecision');
      if (modal?.dataset.productionApprovalId && decisionChoice) {
        event.preventDefault();
        event.stopImmediatePropagation();
        modal.dataset.productionDecision = decisionChoice.dataset.decision;
        qa('.decision-choice').forEach(item => item.classList.toggle('active', item === decisionChoice));
        const comment = q('#decisionComment');
        if (comment) comment.value = decisionChoice.dataset.decision === 'approve' ? '\u914d\u7f6e\u5df2\u6838\u9a8c\uff0c\u540c\u610f\u8fdb\u5165\u6267\u884c\u9636\u6bb5\u3002' : '\u8bf7\u8865\u5145\u6d3b\u52a8\u6750\u6599\u540e\u91cd\u65b0\u63d0\u4ea4\u5ba1\u6279\u3002';
        return;
      }
      if (modal?.dataset.productionApprovalId && confirmButton) {
        event.preventDefault();
        event.stopImmediatePropagation();
        decideProductionApproval(modal.dataset.productionDecision || 'approve', q('#decisionComment')?.value || '');
        return;
      }
      if (!actionButton) return;
      const approval = (tenantData.approvals || []).find(item => String(item.id) === String(selectedProductionApprovalId));
      if (!approval || !approvalIsPending(approval)) { event.preventDefault(); event.stopImmediatePropagation(); toast('\u8be5\u5ba1\u6279\u4efb\u52a1\u5df2\u5904\u7406\uff0c\u8bf7\u5237\u65b0\u5217\u8868'); return; }
      event.preventDefault();
      event.stopImmediatePropagation();
      if (!modal) return;
      modal.dataset.productionApprovalId = String(approval.id);
      modal.dataset.productionDecision = actionButton.dataset.productionApprovalAction;
      q('#decisionSubtitle')?.replaceChildren(document.createTextNode(displayText(approvalCampaign(approval)?.name, approval.campaign_id)));
      const comment = q('#decisionComment');
      if (comment) comment.value = actionButton.dataset.productionApprovalAction === 'approve' ? '\u914d\u7f6e\u5df2\u6838\u9a8c\uff0c\u540c\u610f\u8fdb\u5165\u6267\u884c\u9636\u6bb5\u3002' : '\u8bf7\u8865\u5145\u6d3b\u52a8\u6750\u6599\u540e\u91cd\u65b0\u63d0\u4ea4\u5ba1\u6279\u3002';
      openLayer('decisionModal');
    }, true);
  }

  async function decideProductionApproval(decision, comment) {
    const approvalId = q('#decisionModal')?.dataset.productionApprovalId || selectedProductionApprovalId;
    const approval = (tenantData.approvals || []).find(item => String(item.id) === String(approvalId));
    if (!approval) { toast('\u5ba1\u6279\u4efb\u52a1\u5df2\u4e0d\u5b58\u5728\uff0c\u8bf7\u5237\u65b0\u5ba1\u6279\u5217\u8868'); return; }
    if (!canWrite()) return;
    try {
      await request(`/api/approvals/${encodeURIComponent(approval.id)}/decision`, { method: 'POST', body: JSON.stringify({ decision, comment: String(comment || '').trim() }) });
      const modal = q('#decisionModal');
      closeLayer('decisionModal');
      if (modal) { delete modal.dataset.productionApprovalId; delete modal.dataset.productionDecision; }
      toast(decision === 'approve' ? '\u5ba1\u6279\u5df2\u901a\u8fc7\uff0c\u6267\u884c\u6279\u6b21\u5df2\u751f\u6210' : '\u5ba1\u6279\u5df2\u9000\u56de\uff0c\u6d3b\u52a8\u8fd4\u56de\u4fee\u6539\u6d41\u7a0b');
      await loadTenantData();
    } catch (cause) {
      toast(cause.message || '\u5ba1\u6279\u5904\u7406\u5931\u8d25');
    }
  }

  function renderApprovalsLegacy(){
    const list=q('#approvals .approval-list'); if(!list)return;
    const approvals=tenantData.approvals||[];
    const reviewedCount=approvals.filter(item=>!approvalIsPending(item)).length;
    const pendingProductCount=approvals.filter(item=>String(item.approver_role||'').includes('\u4ea7\u54c1')&&approvalIsPending(item)).length;
    const pendingContentCount=approvals.filter(item=>String(item.approver_role||'').includes('\u5185\u5bb9')&&approvalIsPending(item)).length;
    const approvalNotes=qa('#approvals .kpi em');
    if(approvalNotes[0])approvalNotes[0].textContent=approvals.some(approvalIsPending)?'\\u5b58\\u5728\\u5f85\\u5904\\u7406\\u4efb\\u52a1':'\\u5f53\\u524d\\u65e0\\u5f85\\u5ba1\\u6279';
    if(approvalNotes[1])approvalNotes[1].textContent=pendingProductCount?'\\u5e93\\u5b58\\u4e0e\\u6743\\u76ca\\u6821\\u9a8c':'\\u5f53\\u524d\\u65e0\\u4ea7\\u54c1\\u786e\\u8ba4';
    if(approvalNotes[2])approvalNotes[2].textContent=pendingContentCount?'\\u654f\\u611f\\u8bcd\\u4e0e\\u4e8b\\u5b9e\\u6821\\u9a8c':'\\u5f53\\u524d\\u65e0\\u5185\\u5bb9\\u5408\\u89c4\\u4efb\\u52a1';
    if(approvalNotes[3])approvalNotes[3].textContent=reviewedCount?'\\u5df2\\u5904\\u7406 '+reviewedCount+' \\u6761':'\\u6682\\u65e0\\u5df2\\u5904\\u7406\\u4efb\\u52a1';
    if(approvalNotes[4])approvalNotes[4].textContent=approvals.length?'\\u6309\\u5f53\\u524d\\u5ba1\\u6279\\u8bb0\\u5f55\\u8ba1\\u7b97':'\\u6682\\u65e0\\u7edf\\u8ba1\\u57fa\\u6570';
    const approvalKpiValues=qa('#approvals .kpi b');
    if(approvalKpiValues[3])approvalKpiValues[3].textContent=reviewedCount;
    if(approvalKpiValues[4])approvalKpiValues[4].textContent=approvals.length?((reviewedCount/approvals.length*100).toFixed(1)+'%'):'\\u5f85\\u4ea7\\u751f';
    const approvalNoteText=value=>JSON.parse('"'+value+'"');
    if(approvalNotes[0])approvalNotes[0].textContent=approvals.some(approvalIsPending)?approvalNoteText('\\u5b58\\u5728\\u5f85\\u5904\\u7406\\u4efb\\u52a1'):approvalNoteText('\\u5f53\\u524d\\u65e0\\u5f85\\u5ba1\\u6279');
    if(approvalNotes[1])approvalNotes[1].textContent=pendingProductCount?approvalNoteText('\\u5e93\\u5b58\\u4e0e\\u6743\\u76ca\\u6821\\u9a8c'):approvalNoteText('\\u5f53\\u524d\\u65e0\\u4ea7\\u54c1\\u786e\\u8ba4');
    if(approvalNotes[2])approvalNotes[2].textContent=pendingContentCount?approvalNoteText('\\u654f\\u611f\\u8bcd\\u4e0e\\u4e8b\\u5b9e\\u6821\\u9a8c'):approvalNoteText('\\u5f53\\u524d\\u65e0\\u5185\\u5bb9\\u5408\\u89c4\\u4efb\\u52a1');
    if(approvalNotes[3])approvalNotes[3].textContent=reviewedCount?approvalNoteText('\\u5df2\\u5904\\u7406')+' '+reviewedCount+' '+approvalNoteText('\\u6761'):approvalNoteText('\\u6682\\u65e0\\u5df2\\u5904\\u7406\\u4efb\\u52a1');
    if(approvalNotes[4])approvalNotes[4].textContent=approvals.length?approvalNoteText('\\u6309\\u5f53\\u524d\\u5ba1\\u6279\\u8bb0\\u5f55\\u8ba1\\u7b97'):approvalNoteText('\\u6682\\u65e0\\u7edf\\u8ba1\\u57fa\\u6570');

    if(!approvals.length){list.innerHTML='<div class="empty-action">暂无待处理审批。活动版本提交审批后会出现在这里。</div>';const detail=q('#approvalDetail');if(detail)detail.innerHTML='<div class="empty-action">暂无审批详情，提交活动版本后可查看完整的客群、产品、内容、预算与合规信息。</div>';const no=q('#approvalNo');if(no)no.textContent='暂无审批';return;}
    list.innerHTML=approvals.map(item=>{const campaign=approvalCampaign(item);return `<button class="approval-item ${approvalIsPending(item)?'active':''}" data-approval="${item.id}"><span class="approval-icon activity"><i data-lucide="megaphone"></i></span><span><b>${escapeHtml(displayText(campaign?.name, item.campaign_id))}</b><small>${escapeHtml(item.approver_role)} · ${escapeHtml(item.external_id)}</small></span><em class="pill ${approvalIsPending(item)?'red':'blue'}">${escapeHtml(displayText(item.status, '待审批'))}</em></button>`;}).join('');
    if(window.lucide)lucide.createIcons();
    const selected=approvals.find(approvalIsPending)||approvals[0];
    if(selected) showProductionApprovalDetail(selected.id);
  }

  function renderApprovals(){
    const list = q('#approvals .approval-list');
    if (!list) return;
    const approvals = tenantData.approvals || [];
    const pending = approvals.filter(approvalIsPending);
    const reviewed = approvals.filter(item => !approvalIsPending(item));
    const pendingProductCount = pending.filter(item => displayText(item.approver_role, '').includes('产品')).length;
    const pendingContentCount = pending.filter(item => displayText(item.approver_role, '').includes('内容')).length;
    const approvalNotes = qa('#approvals .kpi em');
    const noteValues = [
      pending.length ? '存在待处理任务' : '当前无待审批',
      pendingProductCount ? '库存与权益校验' : '当前无产品确认',
      pendingContentCount ? '敏感词与事实校验' : '当前无内容合规任务',
      reviewed.length ? `已处理 ${reviewed.length} 条` : '暂无已处理任务',
      approvals.length ? '按当前审批记录计算' : '暂无统计数据'
    ];
    approvalNotes.forEach((node, index) => { node.textContent = noteValues[index] || ''; });
    const approvalKpiValues = qa('#approvals .kpi b');
    qa('#approvals .kpi > span').forEach((node,index)=>node.textContent=['待审批任务','待产品确认','待内容合规','已处理任务','审批处理率'][index]);
    if (approvalKpiValues[0]) approvalKpiValues[0].textContent = pending.length;
    if (approvalKpiValues[1]) approvalKpiValues[1].textContent = pendingProductCount;
    if (approvalKpiValues[2]) approvalKpiValues[2].textContent = pendingContentCount;
    if (approvalKpiValues[3]) approvalKpiValues[3].textContent = reviewed.length;
    if (approvalKpiValues[4]) approvalKpiValues[4].textContent = approvals.length ? `${(reviewed.length / approvals.length * 100).toFixed(1)}%` : '暂无数据';
    if (!approvals.length) {
      list.innerHTML = '<div class="empty-action">暂无待处理审批。活动版本提交审批后会出现在这里。</div>';
      const detail = q('#approvalDetail');
      if (detail) detail.innerHTML = '<div class="empty-action">暂无审批详情，提交活动版本后可查看完整的客群、产品、内容、预算与合规信息。</div>';
      const no = q('#approvalNo');
      if (no) no.textContent = '暂无审批';
      return;
    }
    list.innerHTML = approvals.map(item => {
      const campaign = approvalCampaign(item);
      const status = displayText(item.status, approvalIsPending(item) ? '待审批' : '已处理');
      return `<button class="approval-item ${approvalIsPending(item) ? 'active' : ''}" data-approval="${item.id}"><span class="approval-icon activity"><i data-lucide="megaphone"></i></span><span><b>${escapeHtml(displayText(campaign?.name, item.campaign_id))}</b><small>${escapeHtml(displayText(item.approver_role, '审批节点'))} · ${escapeHtml(displayText(item.external_id, `审批 #${item.id}`))}</small></span><em class="pill ${approvalIsPending(item) ? 'red' : 'blue'}">${escapeHtml(status)}</em></button>`;
    }).join('');
    if (window.lucide) lucide.createIcons();
    const selected = approvals.find(approvalIsPending) || approvals[0];
    if (selected) showProductionApprovalDetail(selected.id);
  }

  function renderContentChannelPreview(item){
    const channel=String(item.channel||'').toLowerCase();
    const title=escapeHtml(displayText(item.title||item.name,'\u4e1c\u822a\u8425\u9500\u6d3b\u52a8'));
    const body=escapeHtml(displayText(item.body,'\u6682\u65e0\u6b63\u6587')).replace(/\r?\n/g,'<br>');
    const action='<button class="preview-cta" disabled title="演示预览">\u7acb\u5373\u67e5\u770b</button>';
    if(channel.includes('\u77ed\u4fe1')) return `<div class="channel-preview sms-preview"><div class="preview-device-bar"><span>China Mobile</span><span>Just now</span></div><div class="preview-sms-bubble"><b>${title}</b><p>${body}</p></div></div>`;
    if(channel.includes('\u5fae\u4fe1')||channel.includes('\u516c\u4f17\u53f7')) return `<div class="channel-preview wechat-preview"><div class="preview-wechat-head"><span class="preview-avatar">\u4e1c</span><b>\u4e2d\u56fd\u4e1c\u65b9\u822a\u7a7a</b><small>\u516c\u4f17\u53f7\u6d88\u606f</small></div><div class="preview-wechat-card"><b>${title}</b><p>${body}</p>${action}</div></div>`;
    if(channel.includes('app')||channel.includes('\u5c0f\u7a0b\u5e8f')) return `<div class="channel-preview app-preview"><div class="preview-app-head"><span>CEAir App</span><small>\u8425\u9500\u6d88\u606f</small></div><div class="preview-app-card"><span class="preview-app-tag">\u4e13\u5c5e\u63a8\u8350</span><h4>${title}</h4><p>${body}</p>${action}</div></div>`;
    if(channel.includes('\u90ae\u4ef6')) return `<div class="channel-preview email-preview"><div class="preview-email-head"><b>\u6536\u4ef6\u7bb1</b><span>\u4e1c\u822a\u8425\u9500\u8fd0\u8425\u4e2d\u5fc3</span></div><article><small>\u4e3b\u9898</small><h4>${title}</h4><p>${body}</p>${action}</article></div>`;
    if(channel.includes('ota')||channel.includes('ndc')||channel.includes('\u5b98\u7f51')) return `<div class="channel-preview offer-preview"><div class="preview-offer-head"><b>\u53ef\u552e\u4ea7\u54c1\u63a8\u8350</b><span>${escapeHtml(item.channel||'\u5b98\u7f51')}</span></div><div class="preview-offer-body"><h4>${title}</h4><p>${body}</p><div class="preview-offer-foot"><span>\u4e1c\u65b9\u822a\u7a7a</span>${action}</div></div></div>`;
    return `<div class="channel-preview generic-preview"><span class="preview-channel-label">${escapeHtml(item.channel||'\u8425\u9500\u6e20\u9053')}</span><h4>${title}</h4><p>${body}</p>${action}</div>`;
  }
  function showContentDetail(item){
    const audience=(tenantData.audiencePackages||[]).find(value=>String(value.id)===String(item.audience_package_id));
    const product=(tenantData.productPackages||[]).find(value=>String(value.id)===String(item.product_package_id));
    const context=item.generation_context||{};
    const layer=document.createElement('div');layer.className='production-modal';layer.innerHTML=`<div class="production-modal-card content-detail-card"><div class="production-modal-head"><div><b>${escapeHtml(displayText(item.name,'营销内容'))}</b><small>${escapeHtml(displayText(item.channel,'营销渠道'))} · ${escapeHtml(displayText(item.version,'V1'))} · ${escapeHtml(displayText(item.status,'草稿'))}</small></div><button class="btn" data-close>关闭</button></div><div class="production-modal-body"><div class="content-preview-layout"><section class="content-preview-stage"><div class="content-preview-stage-head"><div><b>渠道预览</b><small>按实际触达渠道模拟展示</small></div><span>${escapeHtml(displayText(item.channel,'营销渠道'))}</span></div>${renderContentChannelPreview(item)}</section><section class="content-detail-copy"><div class="campaign-detail-summary"><span><b>活动</b>${escapeHtml(item.campaign_id||context.campaign_name||'未关联活动')}</span><span><b>客群包</b>${escapeHtml(audience?.name||context.audience_name||'未关联')}</span><span><b>产品包</b>${escapeHtml(product?.name||context.product_name||'未关联')}</span><span><b>内容目标</b>${escapeHtml(item.generation_objective||context.objective||'提升转化')}</span></div><h3>${escapeHtml(item.title||'内容正文')}</h3><p class="content-body-copy">${escapeHtml(item.body||'暂无正文')}</p><div class="content-evidence-note"><i data-lucide="shield-check"></i><span>生成上下文已保存，可在编辑中调整内容后重新提交审核。</span></div></section></div></div></div>`;document.body.appendChild(layer);layer.addEventListener('click',event=>{if(event.target===layer||event.target.closest('[data-close]'))layer.remove();});if(window.lucide)lucide.createIcons();
  }
  /* 工作台第三栏就是主从详情栏：查看定义 / 查看组合写进 #audienceDetail，
     不再弹模态——400px 的常驻栏位若永远空着，比没有这一栏更糟。 */
  function writeAudienceDetail(name, code, body) {
    const box = q('#audienceDetail'), head = q('#audiences [data-audience-detail] .panel-head h2'), subtitle = q('#audienceDetailTitle');
    if (!box) return;
    if (head) head.textContent = name;
    if (subtitle) subtitle.textContent = code;
    box.innerHTML = body;
    box.scrollTop = 0;
    if (window.lucide) lucide.createIcons();
  }
  function showAudienceDimensionDetail(item) {
    const applicable = Array.isArray(item.applicable_personas) ? item.applicable_personas.join('、') : displayText(item.applicable_personas, '全部客群');
    writeAudienceDetail(displayText(item.field_name, '画像字段'), `${displayText(item.field_code, 'FIELD')} · 底层画像定义`, `<div class="campaign-detail-summary"><span><b>维度分类</b>${escapeHtml(audienceModuleLabel(item.module_name))}</span><span><b>数据类型</b>${escapeHtml(displayText(item.data_type, '枚举'))}</span><span><b>更新频率</b>${escapeHtml(displayText(item.update_frequency, '按日更新'))}</span></div><section class="detail-block"><h3>业务口径</h3><dl class="v-detail"><dt>取值范围</dt><dd>${escapeHtml(displayText(item.allowed_values, '按用户行为和业务规则计算'))}</dd><dt>采集方式</dt><dd>${escapeHtml(displayText(item.collection_method, '系统分析'))}</dd><dt>来源类型</dt><dd>${escapeHtml(displayText(item.source_data_type, '画像接口'))}</dd><dt>适用客群</dt><dd>${escapeHtml(applicable)}</dd></dl></section><section class="detail-block"><h3>营销使用</h3><p>该画像字段可与其他画像字段组合形成客群包，例如「职业类型 + 年龄 + 航线偏好 + 近期开票状态」组合为可执行的航空营销客群。</p><span class="dimension-detail-hint"><i data-lucide="combine"></i>可在新建客群包时作为组合条件</span></section>`);
  }
  function showPersonaDetail(item) {
    const rules = (item.rules || []).map(rule => `<li><b>${escapeHtml(displayText(rule.dimension_name, '画像条件'))}</b><span>${escapeHtml(displayText(rule.condition_expression, `${rule.condition_operator || '='} ${rule.condition_value || ''}`))}</span><small>来源：${escapeHtml(displayText(rule.data_source, '画像接口'))}</small></li>`).join('');
    writeAudienceDetail(displayText(item.segment_name, '预置客群包'), `${displayText(item.segment_code, 'PRESET')} · 预置客群包组合`, `<div class="campaign-detail-summary"><span><b>客群包类型</b>${escapeHtml(displayText(item.primary_persona_name, '未分类'))}</span><span><b>画像条件</b>${item.rules?.length || 0} 项</span><span><b>推荐触达</b>${escapeHtml((item.recommended_channels || []).join('、') || '待配置')}</span></div><section class="detail-block"><h3>组合画像条件</h3><ul class="catalog-detail-list">${rules || '<li><span>暂无明细条件</span></li>'}</ul></section><section class="detail-block"><h3>推荐产品与使用方式</h3><p>${escapeHtml((item.recommended_products || []).join('、') || '可在活动中继续匹配产品包')}。该预置客群包由多个底层画像字段组合而成，运营人员可以据此新建租户客群包并继续调整条件。</p></section>`);
  }  function showBaseProductDetail(item){
    const layer=document.createElement('div'); layer.className='production-modal';
    layer.innerHTML=`<div class="production-modal-card"><div class="production-modal-head"><div><b>${escapeHtml(displayText(item.name,'\u57fa\u7840\u4ea7\u54c1'))}</b><small>${escapeHtml(displayText(item.code,'\u4ea7\u54c1\u7f16\u7801'))} · \u4ea7\u54c1\u7ba1\u7406\u5e73\u53f0</small></div><button class="btn" data-close>\u5173\u95ed</button></div><div class="production-modal-body"><div class="campaign-detail-summary"><span><b>\u4ea7\u54c1\u7c7b\u522b</b>${escapeHtml(displayText(item.category,'\u822a\u7a7a\u4ea7\u54c1'))}</span><span><b>\u6743\u76ca\u9879</b>${(item.benefits||[]).length} \u9879</span></div><section><h3>\u9002\u7528\u6761\u4ef6</h3><p>${escapeHtml(displayText(item.eligibility,'\u4ee5\u4ea7\u54c1\u7ba1\u7406\u5e73\u53f0\u5b9e\u9645\u8d44\u683c\u89c4\u5219\u4e3a\u51c6'))}</p></section><section><h3>\u5305\u542b\u6743\u76ca</h3><ul class="catalog-detail-list">${(item.benefits||[]).map(value=>`<li><span>${escapeHtml(value)}</span><small>\u53ef\u88ab\u4ea7\u54c1\u5305\u7ec4\u5408</small></li>`).join('')||'<li><span>\u6682\u65e0\u6743\u76ca\u660e\u7ec6</span></li>'}</ul></section></div></div>`;
    document.body.appendChild(layer); layer.addEventListener('click',event=>{if(event.target===layer||event.target.closest('[data-close]'))layer.remove();}); if(window.lucide)lucide.createIcons();
  }
  function showProductDetail(item){
    const layer=document.createElement('div');layer.className='production-modal';
    const validPeriod=item.valid_from||item.valid_to?`${item.valid_from?new Date(item.valid_from).toLocaleDateString('zh-CN'):'不限'} 至 ${item.valid_to?new Date(item.valid_to).toLocaleDateString('zh-CN'):'不限'}`:'长期有效';
    layer.innerHTML=`<div class="production-modal-card"><div class="production-modal-head"><div><b>${escapeHtml(item.name)}</b><small>${escapeHtml(item.external_id)} · ${escapeHtml(item.version)}</small></div><button class="btn" data-close>关闭</button></div><div class="production-modal-body"><div class="campaign-detail-summary"><span><b>产品类型</b>${escapeHtml(item.product_type)}</span><span><b>状态</b>${escapeHtml(item.status)}</span><span><b>有效期</b>${escapeHtml(validPeriod)}</span></div><section><h3>产品包内容</h3><p>${escapeHtml(item.description||'待补充组合产品')}</p><h3>适用与资格条件</h3><p>${escapeHtml(item.eligibility||'待补充资格条件')}</p></section></div></div>`;
    document.body.appendChild(layer);layer.addEventListener('click',event=>{if(event.target===layer||event.target.closest('[data-close]'))layer.remove();});
  }
  function showCampaignVersionDetail(version, campaignName){
    const layer=document.createElement('div'); layer.className='production-modal';
    const snapshot=tenantData.audienceSnapshots.find(item=>item.id===version.audience_snapshot_id);
    const packageName=tenantData.audiencePackages.find(item=>item.id===snapshot?.package_id)?.name;
    const audience=snapshot ? `${packageName||'客群快照'} · ${snapshot.version} · ${Number(snapshot.estimated_size).toLocaleString('zh-CN')} 人` : '未绑定客群快照';
    const product=tenantData.productPackages.find(item=>item.id===version.product_package_id)?.name || '未绑定产品包';
    layer.innerHTML=`<div class="production-modal-card campaign-detail-card"><div class="production-modal-head"><div><b>${escapeHtml(campaignName)} · ${escapeHtml(version.version)}</b><small>${escapeHtml(version.external_id)} · 版本详情</small></div><button class="btn" data-close>关闭</button></div><div class="production-modal-body"><div class="campaign-detail-summary"><span><b>版本状态</b>${escapeHtml(version.status)}</span><span><b>创建时间</b>${businessTime(version.created_at)}</span><span><b>客群</b>${escapeHtml(audience)}</span><span><b>产品</b>${escapeHtml(product)}</span></div><div class="campaign-detail-grid"><section><h3>版本配置</h3><dl><dt>预算</dt><dd>¥${Number(version.budget_yuan||0).toLocaleString('zh-CN')}</dd><dt>内容资产</dt><dd>${(version.content_asset_ids||[]).length} 个</dd><dt>执行渠道</dt><dd>${escapeHtml((version.channels||[]).join('、')||'未配置')}</dd></dl></section><section><h3>可追溯信息</h3><dl><dt>版本编号</dt><dd>${escapeHtml(version.external_id)}</dd><dt>关联客群快照</dt><dd>${escapeHtml(audience)}</dd><dt>关联产品包</dt><dd>${escapeHtml(product)}</dd></dl></section></div></div></div>`;
    document.body.appendChild(layer); layer.addEventListener('click',event=>{if(event.target===layer||event.target.closest('[data-close]'))layer.remove();}); if(window.lucide)lucide.createIcons();
  }
  function showCampaignVersionCompare(left,right,campaignName){
    const field=(label,a,b)=>`<tr><th>${label}</th><td>${escapeHtml(String(a??'未配置'))}</td><td>${escapeHtml(String(b??'未配置'))}</td></tr>`;
    const layer=document.createElement('div'); layer.className='production-modal';
    layer.innerHTML=`<div class="production-modal-card campaign-detail-card"><div class="production-modal-head"><div><b>${escapeHtml(campaignName)} · 版本对比</b><small>差异检查 · ${escapeHtml(left.version)} 对比 ${escapeHtml(right.version)}</small></div><button class="btn" data-close>关闭</button></div><div class="production-modal-body"><table class="table"><tr><th>配置项</th><th>${escapeHtml(left.version)}</th><th>${escapeHtml(right.version)}</th></tr>${field('状态',left.status,right.status)}${field('预算',`¥${Number(left.budget_yuan||0).toLocaleString('zh-CN')}`,`¥${Number(right.budget_yuan||0).toLocaleString('zh-CN')}`)}${field('客群快照',left.audience_snapshot_id||'未配置',right.audience_snapshot_id||'未配置')}${field('产品包',left.product_package_id||'未配置',right.product_package_id||'未配置')}${field('内容资产数量',(left.content_asset_ids||[]).length,(right.content_asset_ids||[]).length)}${field('渠道',(left.channels||[]).join('、'),(right.channels||[]).join('、'))}</table></div></div>`;
    document.body.appendChild(layer); bindProductionModal(layer);
  }
  async function showCampaignEditor(item){
    const creating=!item.id;
    let versions=[];
    if(!creating){try { versions = await request(`/api/campaigns/${encodeURIComponent(item.id)}/versions`); } catch (cause) { toast(cause.message || '活动版本加载失败'); return; }}
    const latest = versions[0] || {};
    const productOptions = (tenantData.productPackages || []).map(value => ({ value: value.id, label: `${value.name} · ${value.version || 'V1'}` }));
    const snapshotOptions = (tenantData.audienceSnapshots || []).map(value => ({ value: value.id, label: `${value.external_id || `快照 #${value.id}`} · ${Number(value.estimated_size || 0).toLocaleString('zh-CN')} 人` }));
    const contentOptions = (tenantData.contentAssets || []).map(value => ({ value: value.id, label: `${value.name} · ${value.channel} · ${value.version || 'V1'}` }));
    const currentProductId = latest.product_package_id ?? '';
    const currentSnapshotId = latest.audience_snapshot_id ?? '';
    const currentContentIds = latest.content_asset_ids || [];
    openBusinessEditor({
      title: creating?'新建营销活动':'编辑营销活动', subtitle: creating?'配置并保存 V1 草稿；提交审批后才能执行':`${item.id} · 活动主数据与当前版本配置`, item: {
        ...item,
        audience_snapshot_id: currentSnapshotId,
        product_package_id: currentProductId,
        content_asset_ids: currentContentIds,
        channels: latest.channels || item.channels || [],
        budget_yuan: latest.budget_yuan ?? item.budget_yuan,
      }, width: 'campaign-editor-card', saveLabel: creating ? '保存草稿' : '保存修改',
      fields: [
        { name: 'name', label: '活动名称', type: 'text' },
        { name: 'stage', label: '当前节点', type: 'select', options: ({'机会':['机会','创建'],'创建':['创建','内容','审批'],'内容':['内容','审批','创建'],'审批':['审批','内容'],'执行':['执行','复盘'],'复盘':['复盘'],'归档':['归档']})[item.stage] || [item.stage] },
        { name: 'audience_size', label: '预计客群人数', type: 'number', min: 0 },
        { name: 'budget_yuan', label: '活动预算（元）', type: 'number', min: 0 },
        { name: 'roi_target', label: '目标 ROI', type: 'number', min: 0, step: 0.1 },
        { name: 'channels', label: '执行渠道', type: 'multiselect', options: channelOptions.map(([value, label]) => ({value, label})), help: '选择本次活动的渠道；演示执行仅产生虚构回执。' },
        { name: 'audience_snapshot_id', label: '客群快照', type: 'select', required: false, options: [{ value: '', label: '暂不绑定' }, ...snapshotOptions] },
        { name: 'product_package_id', label: '活动产品包', type: 'select', required: false, options: [{ value: '', label: '暂不绑定' }, ...productOptions] },
        { name: 'content_asset_ids', label: '内容资产', type: 'multiselect', required: false, options: contentOptions, help: '可多选短信、App 卡片、微信图文等已生成内容。' },
      ],
      save: async values => {
        await request(creating?'/api/campaigns':`/api/campaigns/${encodeURIComponent(item.id)}`, { method: creating?'POST':'PUT', body: JSON.stringify({
          name: String(values.name || '').trim(), stage: values.stage, audience_size: values.audience_size,
          budget_yuan: values.budget_yuan, roi_target: values.roi_target,
          channels: values.channels || [],
          audience_snapshot_id: values.audience_snapshot_id ? Number(values.audience_snapshot_id) : null,
          product_package_id: values.product_package_id ? Number(values.product_package_id) : null,
          content_asset_ids: values.content_asset_ids || [],
        }) });
        toast(creating?'活动与 V1 配置已保存为草稿':'活动完整配置已更新'); await refreshAfterBusinessSave();activate('campaigns');
      }
    });
  }

  function showChannelFeedbackEditor(item) {
    openBusinessEditor({
      title: '编辑渠道回执', subtitle: `${item.external_id || item.channel} · 更新执行结果`, item,
      fields: [
        { name: 'sent_count', label: '已发送任务数', type: 'number', min: 0, max: item.target_count },
        { name: 'delivered_count', label: '已送达任务数', type: 'number', min: 0 },
        { name: 'clicked_count', label: '点击任务数', type: 'number', min: 0 },
        { name: 'converted_count', label: '转化任务数', type: 'number', min: 0 },
        { name: 'failed_count', label: '失败任务数', type: 'number', min: 0 },
        { name: 'status', label: '任务状态', type: 'select', options: ['待执行', '执行中', '已完成', '已暂停', '失败'] },
      ],
      save: async values => {
        await request(`/api/channel-tasks/${item.id}/feedback`, { method: 'POST', body: JSON.stringify(values) });
        toast(`${item.channel} 渠道回执已更新`); await refreshAfterBusinessSave();
      }
    });
  }
  async function showCampaignDetail(item){
    if(!item)return;
    let layer=q('#campaignDetailLayer');
    if(!layer){layer=document.createElement('div');layer.id='campaignDetailLayer';layer.className='production-modal';document.body.appendChild(layer);}
    layer.innerHTML='<div class="production-modal-card campaign-detail-card"><div class="production-modal-head"><div><b>'+escapeHtml(item.name)+'</b><small>'+escapeHtml(item.id)+' · 活动详情与版本</small></div><button class="btn" data-campaign-detail-close>关闭</button></div><div class="production-modal-body"><div class="campaign-detail-summary"><span><b>当前节点</b>'+escapeHtml(item.stage)+'</span><span><b>当前版本</b>'+escapeHtml(item.version)+'</span><span><b>负责人</b>'+escapeHtml(item.owner)+'</span><span><b>状态</b>'+escapeHtml(item.status)+'</span></div><div class="campaign-detail-grid"><section><h3>活动配置</h3><dl><dt>活动目标</dt><dd>围绕航线、客群和产品包完成精准触达</dd><dt>关联客群</dt><dd>'+Number(item.audience_size||0).toLocaleString('zh-CN')+' 人</dd><dt>关联产品</dt><dd>'+escapeHtml(item.product_package||'未绑定产品包')+'</dd><dt>活动预算</dt><dd>¥'+Number(item.budget_yuan||0).toLocaleString('zh-CN')+'</dd><dt>目标 ROI</dt><dd>'+Number(item.roi_target||0).toFixed(1)+'</dd></dl></section><section><h3>版本记录</h3><div class="campaign-version-list" data-version-list><div class="empty-action">正在加载真实版本记录…</div></div></section></div></div></div>';
    layer.hidden=false;
    bindProductionModal(layer,{closeSelector:'[data-campaign-detail-close]'});
    try{
      const versions=await request('/api/campaigns/'+encodeURIComponent(item.id)+'/versions');
      const list=q('[data-version-list]',layer);
      if(list)list.innerHTML=versions.length?versions.map((version,index)=>`<div class="${index===0?'current':''}"><b>${escapeHtml(version.version)}</b><span>${businessTime(version.created_at)} · ${escapeHtml(version.status)}</span><small>客群 ${(version.audience_snapshot_id||'未绑定')} · 产品 ${(version.product_package_id||'未绑定')} · ${escapeHtml((version.channels||[]).join('、')||'未配置渠道')}</small><button class="btn" data-campaign-version-view="${version.id}">查看</button>${canWrite()&&['草稿','已退回'].includes(version.status)?`<button class="btn primary" data-version-submit="${version.id}">提交审批</button>`:''}${versions.length>1?`<button class="btn" data-campaign-version-compare="${version.id}">对比当前</button>`:''}</div>`).join(''):'<div class="empty-action">暂无版本记录</div>';
      qa('[data-version-submit]',layer).forEach(button=>button.addEventListener('click',async()=>{
        button.disabled=true;
        try{await request(`/api/campaigns/${encodeURIComponent(item.id)}/versions/${button.dataset.versionSubmit}/approval`,{method:'POST'});layer.remove();await loadTenantData();activate('approvals');toast('活动版本已提交审批');}
        catch(cause){toast(cause.message||'提交审批失败');button.disabled=false;}
      }));
      qa('[data-campaign-version-view]',layer).forEach(button=>button.addEventListener('click',()=>{const version=versions.find(value=>String(value.id)===String(button.dataset.campaignVersionView));if(version)showCampaignVersionDetail(version,item.name);}));
      qa('[data-campaign-version-compare]',layer).forEach(button=>button.addEventListener('click',()=>{const version=versions.find(value=>String(value.id)===String(button.dataset.campaignVersionCompare));const current=versions[0];if(version&&current&&version.id!==current.id)showCampaignVersionCompare(version,current,item.name);else toast('当前只有一个可比较的版本');}));
    }catch(cause){const list=q('[data-version-list]',layer);if(list)list.innerHTML='<div class="empty-action">版本记录加载失败：'+escapeHtml(cause.message||'请稍后重试')+'</div>';}
  }

  function renderOntologySchema() {
    const host=q('#ontologySchema'); if(!host) return;
    const types=[
      ['opportunity','\u8425\u9500\u673a\u4f1a','\u5e02\u573a\u3001\u822a\u7ebf\u4e0e\u7ecf\u8425\u4fe1\u53f7\u5f62\u6210\u7684\u53ef\u8fd0\u8425\u673a\u4f1a'],
      ['audience','\u5ba2\u7fa4\u5305','\u7531\u753b\u50cf\u6807\u7b7e\u7ec4\u5408\u6216 AI \u5708\u9009\u5f62\u6210\u7684\u53ef\u89e6\u8fbe\u5ba2\u7fa4'],
      ['product','\u6d3b\u52a8\u4ea7\u54c1\u5305','\u673a\u7968\u3001\u5361\u5238\u3001\u8f85\u8425\u670d\u52a1\u4e0e\u4f1a\u5458\u6743\u76ca\u7684\u8425\u9500\u7ec4\u5408'],
      ['content','\u5185\u5bb9\u8d44\u4ea7','\u9762\u5411\u4e0d\u540c\u5ba2\u7fa4\u4e0e\u6e20\u9053\u7684\u8425\u9500\u5185\u5bb9\u7248\u672c'],
      ['campaign','\u8425\u9500\u6d3b\u52a8','\u8d2f\u7a7f\u673a\u4f1a\u3001\u5ba2\u7fa4\u3001\u4ea7\u54c1\u3001\u5ba1\u6279\u4e0e\u6267\u884c\u7684\u4e1a\u52a1\u4e3b\u7ebf'],
      ['approval','\u5ba1\u6279\u4efb\u52a1','\u9884\u7b97\u3001\u4ea7\u54c1\u3001\u5408\u89c4\u4e0e\u53d1\u5e03\u7684\u4eba\u5de5\u786e\u8ba4\u8282\u70b9'],
      ['result','\u8425\u9500\u7ed3\u679c','\u89e6\u8fbe\u3001\u70b9\u51fb\u3001\u51fa\u7968\u3001\u9886\u5238\u3001\u6838\u9500\u4e0e\u8f85\u8425\u8d2d\u4e70\u7ed3\u679c']
    ];
    const relations=['\u673a\u4f1a \u2192 \u8bc6\u522b\u5ba2\u7fa4','\u5ba2\u7fa4\u5305 \u2192 \u9002\u914d\u4ea7\u54c1\u5305','\u4ea7\u54c1\u5305 \u2192 \u652f\u6491\u6d3b\u52a8','\u6d3b\u52a8 \u2192 \u751f\u6210\u5185\u5bb9','\u6d3b\u52a8 \u2192 \u53d1\u8d77\u5ba1\u6279','\u5ba1\u6279 \u2192 \u5141\u8bb8\u6267\u884c','\u6d3b\u52a8 \u2192 \u4ea7\u751f\u7ed3\u679c','\u7ed3\u679c \u2192 \u53cd\u54fa\u673a\u4f1a'];
    host.innerHTML='<div class="ontology-schema-summary"><b>\u672c\u4f53\u7ed3\u6784</b><span>\u5b9a\u4e49\u4e1a\u52a1\u5bf9\u8c61\u3001\u5c5e\u6027\u4e0e\u5173\u7cfb\uff0c\u4e0d\u5c55\u793a\u5177\u4f53\u5b9e\u4f8b</span><em>'+types.length+' \u7c7b\u5bf9\u8c61 \u00b7 '+relations.length+' \u6761\u6838\u5fc3\u5173\u7cfb</em></div><div class="ontology-schema-grid">'+types.map(item=>'<button type="button" class="ontology-type-card '+item[0]+'" data-schema-type="'+item[0]+'"><strong>'+item[1]+'</strong><span>'+item[2]+'</span><small>\u70b9\u51fb\u67e5\u770b\u7c7b\u578b\u5b9a\u4e49</small></button>').join('')+'</div><div class="ontology-relation-strip">'+relations.map((item,index)=>'<span><i>'+String(index+1).padStart(2,'0')+'</i>'+item+'</span>').join('')+'</div>';
    qa('[data-schema-type]').forEach(button=>button.addEventListener('click',()=>{const item=types.find(value=>value[0]===button.dataset.schemaType);const detail=q('#entityDetail');if(item&&detail)detail.innerHTML='<div class="entity-title"><b>'+item[1]+'</b><span>\u672c\u4f53\u7c7b\u578b\u5b9a\u4e49</span></div><dl><dt>\u4e1a\u52a1\u5b9a\u4f4d</dt><dd>'+item[2]+'</dd><dt>\u6570\u636e\u6765\u6e90</dt><dd>\u672c\u4f53\u6a21\u578b\u914d\u7f6e\u4e0e\u79df\u6237\u6570\u636e\u52a8\u6001\u66f4\u65b0</dd></dl><div class="ai-result"><b>\u5173\u7cfb\u4f7f\u7528</b><p>\u53ef\u4e0e\u5176\u4ed6\u8425\u9500\u4e1a\u52a1\u5bf9\u8c61\u5efa\u7acb\u53ef\u8ffd\u6eaf\u5173\u8054</p></div>'; }));
  }
  async function renderOntologySchemaGraph(){
    const host=q('#ontologySchema'); if(!host)return;
    let model; try{model=await request('/api/ontology/semantic-model');}catch{model={object_types:[],relation_types:[]};}
    if(window.ceairSchemaSimulation)window.ceairSchemaSimulation.stop();
    const types=model.object_types||[], relations=model.relation_types||[];
    const W=220,H=116,cols=5,gx=258,gy=150,width=Math.max(1320,cols*gx+20),height=Math.max(760,Math.ceil(types.length/cols)*gy+36);
    const positions=new Map(types.map((item,index)=>[item.id,{x:18+(index%cols)*gx,y:18+Math.floor(index/cols)*gy}]));
    const point=id=>positions.get(id)||null;
    const colors={data:'#5387b8',aviation:'#4c91b8',customer:'#42a184',product:'#c79432',strategy:'#7c70bd',marketing:'#4589c7',governance:'#bd7853',execution:'#4b9a9a',measurement:'#6b7fa9',agent:'#b25e9b',knowledge:'#6e8f78',semantic:'#7e8795'};
    let edges='',nodes='';
    relations.forEach(rel=>{const from=(rel.from_types||[])[0],to=(rel.to_types||[])[0],a=point(from),b=point(to);if(!a||!b)return;const label=escapeHtml(rel.name||rel.id||'关系');edges+='<g class="ontology-schema-edge" data-from="'+escapeHtml(from)+'" data-to="'+escapeHtml(to)+'"><line class="ontology-edge" x1="'+(a.x+W/2)+'" y1="'+(a.y+H/2)+'" x2="'+(b.x+W/2)+'" y2="'+(b.y+H/2)+'" marker-end="url(#ontology-arrow)"></line><text class="ontology-edge-label" x="'+((a.x+b.x+W)/2)+'" y="'+((a.y+b.y+H)/2-6)+'">'+label+'</text></g>';});
    const attributes={MarketSignal:['signal_type','topic','occurred_at','source'],Route:['route_code','origin','destination','market_scope'],Flight:['flight_no','flight_date','route_code','operation_status'],Fare:['fare_basis','price','refund_rule','change_rule'],Opportunity:['opportunity_type','route_id','target_need','score'],CustomerAggregate:['audience_type','member_level','travel_frequency','population'],AudienceSnapshot:['snapshot_code','selection_logic','population','frozen_at'],Product:['product_code','product_type','price','eligibility'],ProductPackage:['package_code','version','components','approval_status'],StrategyPlan:['plan_code','objective_id','audience_id','budget'],ContentAsset:['content_id','channel','title','version'],Campaign:['campaign_id','name','objective','budget'],CampaignVersion:['version','audience_snapshot_id','product_package_id','channels'],ApprovalTask:['approval_type','approver_role','decision','decided_at'],ExecutionBatch:['batch_code','channel','target_count','status'],Channel:['channel_code','channel_type','provider','status'],Feedback:['delivered_count','clicked_count','converted_count','complaint_count'],AttributionResult:['attribution_model','incremental_revenue','roi','confidence'],Review:['review_period','conclusion','next_action'],Recommendation:['recommendation_type','reasoning','confidence','status'],BusinessRule:['rule_type','expression','priority','status'],Evidence:['source_type','source_ref','excerpt','confidence'],KnowledgeDocument:['document_id','title','source_name','version'],KnowledgeChunk:['document_id','page_no','paragraph_no','content_hash'],KnowledgeClaim:['claim_type','subject_id','predicate','object_id']};
    types.forEach(item=>{const p=point(item.id),stroke=colors[item.module]||'#718b9c',list=item.attributes||attributes[item.id]||['id','name','source','status'];nodes+='<g class="ontology-schema-node" data-schema-type="'+escapeHtml(item.id)+'" transform="translate('+p.x+','+p.y+')" tabindex="0"><rect width="'+W+'" height="'+H+'" rx="7" fill="#fff" stroke="'+stroke+'"></rect><rect width="'+W+'" height="25" rx="7" fill="'+stroke+'" opacity=".13"></rect><text class="ontology-node-module" x="11" y="17" fill="'+stroke+'">'+escapeHtml(item.module||'business')+'</text><text class="ontology-node-title" x="11" y="46">'+escapeHtml(item.name||item.id)+'</text><text class="ontology-node-id" x="11" y="63">'+escapeHtml(item.id)+'</text>';list.slice(0,4).forEach((value,index)=>{nodes+='<text class="ontology-node-attr" x="11" y="'+(81+index*12)+'">· '+escapeHtml(value)+'</text>';});nodes+='</g>';});
    let relationList='<b>关系定义</b>';relations.forEach((rel,index)=>{relationList+='<span><i>'+String(index+1).padStart(2,'0')+'</i>'+escapeHtml((rel.from_types||[]).join(' / '))+' → '+escapeHtml(rel.name||rel.id)+' → '+escapeHtml((rel.to_types||[]).join(' / '))+'</span>';});
    host.innerHTML='<div class="ontology-schema-summary"><b>本体结构图谱</b><span>类节点展示核心属性，连线展示语义关系；点击节点查看完整定义，关系清单保留全部多类型约束</span><em>'+types.length+' 类对象 · '+relations.length+' 条关系</em></div><div class="ontology-schema-viewport"><svg class="ontology-schema-canvas" width="'+width+'" height="'+height+'" viewBox="0 0 '+width+' '+height+'"><defs><marker id="ontology-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#9bb5c4"></path></marker></defs><g class="ontology-edges">'+edges+'</g><g class="ontology-nodes">'+nodes+'</g></svg></div><div class="ontology-relation-strip">'+relationList+'</div>';
    const detailFor=function(item){const list=item.attributes||attributes[item.id]||['id','name','source','status'],out=relations.filter(rel=>(rel.from_types||[]).includes(item.id)),input=relations.filter(rel=>(rel.to_types||[]).includes(item.id)),detail=q('#entityDetail');if(!detail)return;detail.innerHTML='<div class="entity-title"><b>'+escapeHtml(item.name||item.id)+'</b><span>本体类 · '+escapeHtml(item.id)+'</span></div><dl><dt>业务定义</dt><dd>'+escapeHtml(item.description||'暂无业务定义')+'</dd><dt>核心属性</dt><dd>'+list.map(value=>'<code>'+escapeHtml(value)+'</code>').join(' ')+'</dd></dl><div class="ai-result"><b>关系使用</b><p>出边 '+out.length+' 条 · 入边 '+input.length+' 条</p><p>'+escapeHtml(out.slice(0,6).map(rel=>(item.name||item.id)+' —'+(rel.name||rel.id)+'→ '+(rel.to_types||[]).join('/')).join('；')||'暂无出边关系')+'</p></div>';qa('.ontology-schema-node').forEach(node=>node.classList.toggle('selected',node.dataset.schemaType===item.id));};
    const updateEdges=()=>qa('.ontology-schema-edge').forEach(edge=>{const a=point(edge.dataset.from),b=point(edge.dataset.to);if(!a||!b)return;const line=edge.querySelector('line'),label=edge.querySelector('text');line.setAttribute('x1',a.x+W/2);line.setAttribute('y1',a.y+H/2);line.setAttribute('x2',b.x+W/2);line.setAttribute('y2',b.y+H/2);label.setAttribute('x',(a.x+b.x+W)/2);label.setAttribute('y',(a.y+b.y+H)/2-6);});
    qa('.ontology-schema-node').forEach(element=>{const item=types.find(value=>value.id===element.dataset.schemaType);element.addEventListener('click',()=>item&&detailFor(item));element.addEventListener('keydown',event=>{if(item&&(event.key==='Enter'||event.key===' ')){event.preventDefault();detailFor(item);}});let moving=false;element.addEventListener('pointerdown',event=>{moving=true;element.setPointerCapture(event.pointerId);});element.addEventListener('pointermove',event=>{if(moving){const p=point(item.id);p.x=Math.max(0,p.x+event.movementX);p.y=Math.max(0,p.y+event.movementY);element.setAttribute('transform','translate('+p.x+','+p.y+')');updateEdges();}});element.addEventListener('pointerup',()=>{moving=false;});element.addEventListener('pointercancel',()=>{moving=false;});});
    if(types[0])detailFor(types[0]);
  }
  async function renderOntologySchemaGraphV2(){
    const host=q('#ontologySchema'); if(!host)return;
    let model; try{model=await request('/api/ontology/semantic-model');}catch{model={object_types:[],relation_types:[]};}
    if(window.ceairSchemaSimulation)window.ceairSchemaSimulation.stop();
    const types=model.object_types||[], relations=model.relation_types||[];
    if(!types.length){host.innerHTML='<div class="ontology-map-empty"><i data-lucide="network"></i><b>暂无本体结构</b><span>完成数据处理或配置语义模型后，这里会展示业务对象与关系。</span></div>';if(window.lucide)lucide.createIcons();return;}
    const moduleLabels={data:'数据来源',aviation:'航空业务',customer:'客户与客群',product:'产品与权益',strategy:'策略规划',marketing:'营销活动',governance:'治理审批',execution:'执行触达',measurement:'效果度量',agent:'智能体',knowledge:'知识底座',semantic:'语义配置'};
    const colors={data:'#5b8db8',aviation:'#3d91b7',customer:'#43a584',product:'#c59435',strategy:'#806dc0',marketing:'#438bc5',governance:'#bd7853',execution:'#4d9e9c',measurement:'#687fac',agent:'#b15e9b',knowledge:'#6c9078',semantic:'#7e8795'};
    const modules=[...new Set(types.map(item=>item.module||'semantic'))];
    const typeMap=new Map(types.map(item=>[item.id,item]));
    const links=[];relations.forEach(rel=>(rel.from_types||[]).forEach(from=>(rel.to_types||[]).forEach(to=>{if(typeMap.has(from)&&typeMap.has(to))links.push({source:from,target:to,label:rel.name||rel.id});})));
    host.innerHTML='<div class="ontology-map-summary"><div><b>本体语义拓扑</b><span></span></div><strong>'+types.length+'<small> 类对象</small><i>·</i>'+relations.length+'<small> 条关系</small></strong></div><div class="ontology-map-toolbar"><label class="ontology-map-search"><i data-lucide="search"></i><input data-ontology-search placeholder="搜索对象类、业务域或属性"></label><select data-ontology-module><option value="all">全部业务域</option>'+modules.map(item=>'<option value="'+escapeHtml(item)+'">'+escapeHtml(moduleLabels[item]||item)+'</option>').join('')+'</select><button type="button" class="btn" data-ontology-reset><i data-lucide="scan-search"></i>重置视图</button><span class="ontology-map-hint">拖动节点 · 滚轮缩放 · 点击聚焦</span></div><div class="ontology-map-legend">'+modules.map(item=>'<span><i style="background:'+colors[item]+'"></i>'+escapeHtml(moduleLabels[item]||item)+'</span>').join('')+'</div><div class="ontology-map-viewport"><svg class="ontology-map-canvas" viewBox="0 0 1240 690" role="img" aria-label="本体语义拓扑图"><defs><marker id="ontology-map-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#9bb6c6"></path></marker></defs><g class="ontology-map-root"><g class="ontology-map-edges"></g><g class="ontology-map-edge-labels"></g><g class="ontology-map-nodes"></g></g></svg></div>';
    if(window.lucide)lucide.createIcons();
    const width=1240,height=690,svg=d3.select('.ontology-map-canvas',host),root=svg.select('.ontology-map-root'),edgeLayer=root.select('.ontology-map-edges'),labelLayer=root.select('.ontology-map-edge-labels'),nodeLayer=root.select('.ontology-map-nodes');
    const nodes=types.map(item=>({...item,title:item.name||item.id,module:item.module||'semantic',attributes:item.attributes||[]}));
    const nodeById=new Map(nodes.map(item=>[item.id,item]));
    const simLinks=links.map(item=>({...item,source:nodeById.get(item.source),target:nodeById.get(item.target)}));
    const edge=edgeLayer.selectAll('path').data(simLinks).join('path').attr('class','ontology-map-edge').attr('marker-end','url(#ontology-map-arrow)');
    const edgeLabel=labelLayer.selectAll('text').data(simLinks).join('text').attr('class','ontology-map-edge-label').text(item=>item.label);
    const node=nodeLayer.selectAll('g').data(nodes,d=>d.id).join('g').attr('class','ontology-map-node').attr('data-schema-type',d=>d.id).attr('tabindex',0);
    node.append('rect').attr('class','ontology-map-card').attr('width',186).attr('height',92).attr('rx',10).attr('stroke',d=>colors[d.module]||colors.semantic);
    node.append('rect').attr('class','ontology-map-card-top').attr('width',186).attr('height',7).attr('rx',6).attr('fill',d=>colors[d.module]||colors.semantic);
    node.append('text').attr('class','ontology-map-module').attr('x',12).attr('y',27).text(d=>moduleLabels[d.module]||d.module);
    node.append('text').attr('class','ontology-map-title').attr('x',12).attr('y',49).text(d=>String(d.title).slice(0,13));
    node.append('text').attr('class','ontology-map-id').attr('x',12).attr('y',66).text(d=>d.id);
    node.append('text').attr('class','ontology-map-attrs').attr('x',12).attr('y',83).text(d=>(d.attributes||[]).slice(0,3).join(' · ')||'核心属性待补充');
    const zoom=d3.zoom().scaleExtent([.45,2.2]).on('zoom',event=>root.attr('transform',event.transform));svg.call(zoom);
    const updateEdges=()=>{edge.attr('d',item=>`M${item.source.x},${item.source.y} L${item.target.x},${item.target.y}`);edgeLabel.attr('x',item=>(item.source.x+item.target.x)/2).attr('y',item=>(item.source.y+item.target.y)/2-5);};
    const connected=new Map(nodes.map(item=>[item.id,new Set()]));links.forEach(item=>{connected.get(item.source)?.add(item.target);connected.get(item.target)?.add(item.source);});
    const showDetail=item=>{const out=relations.filter(rel=>(rel.from_types||[]).includes(item.id)),input=relations.filter(rel=>(rel.to_types||[]).includes(item.id)),detail=q('#entityDetail');if(!detail)return;detail.innerHTML='<div class="entity-title"><b>'+escapeHtml(item.title)+'</b><span>本体类 · '+escapeHtml(item.id)+'</span></div><dl><dt>业务域</dt><dd>'+escapeHtml(moduleLabels[item.module]||item.module)+'</dd><dt>业务定义</dt><dd>'+escapeHtml(item.description||'暂无业务定义')+'</dd><dt>核心属性</dt><dd>'+((item.attributes||[]).map(value=>'<code>'+escapeHtml(value)+'</code>').join(' ')||'暂无属性定义')+'</dd></dl><div class="ai-result"><b>关系使用</b><p>出边 '+out.length+' 条 · 入边 '+input.length+' 条</p><p>'+escapeHtml(out.slice(0,5).map(rel=>(item.title)+' —'+(rel.name||rel.id)+'→ '+(rel.to_types||[]).join('/')).join('；')||'暂无出边关系')+'</p></div>';node.classed('is-selected',value=>value.id===item.id).classed('is-neighbor',value=>value.id!==item.id&&(connected.get(item.id)?.has(value.id)));};
    const applyFilter=()=>{const query=(q('[data-ontology-search]',host)?.value||'').trim().toLowerCase(),module=q('[data-ontology-module]',host)?.value||'all';const visible=new Set(nodes.filter(item=>{const hay=[item.id,item.title,item.description,item.module,...(item.attributes||[])].join(' ').toLowerCase();return (!query||hay.includes(query))&&(module==='all'||item.module===module);}).map(item=>item.id));node.classed('is-muted',item=>!visible.has(item.id));edge.classed('is-hidden',item=>!visible.has(item.source.id)||!visible.has(item.target.id));edgeLabel.classed('is-hidden',item=>!visible.has(item.source.id)||!visible.has(item.target.id));};
    node.on('click',(event,item)=>{event.stopPropagation();showDetail(item);}).on('keydown',(event,item)=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();showDetail(item);}}).call(d3.drag().on('start',(event,item)=>{if(!event.active)simulation.alphaTarget(.25).restart();item.fx=item.x;item.fy=item.y;}).on('drag',(event,item)=>{item.fx=event.x;item.fy=event.y;updateEdges();}).on('end',(event,item)=>{if(!event.active)simulation.alphaTarget(0);item.fx=null;item.fy=null;}));
    const simulation=window.ceairSchemaSimulation=d3.forceSimulation(nodes).force('link',d3.forceLink(simLinks).id(item=>item.id).distance(150).strength(.55)).force('charge',d3.forceManyBody().strength(-430)).force('collide',d3.forceCollide().radius(112)).force('center',d3.forceCenter(width/2,height/2)).force('x',d3.forceX(width/2).strength(.045)).force('y',d3.forceY(height/2).strength(.045)).on('tick',()=>{node.attr('transform',item=>`translate(${item.x-93},${item.y-46})`);updateEdges();});
    q('[data-ontology-search]',host)?.addEventListener('input',applyFilter);q('[data-ontology-module]',host)?.addEventListener('change',applyFilter);q('[data-ontology-reset]',host)?.addEventListener('click',()=>{q('[data-ontology-search]',host).value='';q('[data-ontology-module]',host).value='all';applyFilter();svg.transition().duration(350).call(zoom.transform,d3.zoomIdentity);node.classed('is-selected',false).classed('is-neighbor',false);});
    simulation.stop();for(let tick=0;tick<150;tick++)simulation.tick();updateEdges();node.attr('transform',item=>`translate(${item.x-93},${item.y-46})`);
    const minX=Math.min(...nodes.map(n=>n.x-95)),maxX=Math.max(...nodes.map(n=>n.x+95)),minY=Math.min(...nodes.map(n=>n.y-48)),maxY=Math.max(...nodes.map(n=>n.y+48));const scale=Math.min(1,(width-40)/(maxX-minX),(height-40)/(maxY-minY));const fit=d3.zoomIdentity.translate((width-scale*(maxX+minX))/2,(height-scale*(maxY+minY))/2).scale(scale);svg.call(zoom.transform,fit);
    if(nodes[0])showDetail(nodes[0]);applyFilter();
  }

  function setupKnowledgeViews(){
    const canvas=q('#graphCanvas'); if(!canvas) return; const body=canvas.closest('.panel-body'); if(!body||q('#knowledgeViewTabs',body)) return;
    const tabs=document.createElement('div'); tabs.id='knowledgeViewTabs'; tabs.className='knowledge-view-tabs'; tabs.innerHTML='<button type="button" class="knowledge-view-tab active" data-knowledge-view="schema">\u672c\u4f53\u7ed3\u6784</button><button type="button" class="knowledge-view-tab" data-knowledge-view="instances">\u672c\u4f53\u5b9e\u4f8b</button>'; body.prepend(tabs);
    const schema=document.createElement('div'); schema.id='ontologySchema'; schema.className='ontology-schema-view'; body.insertBefore(schema,canvas);
    const toolbar=body.querySelector('.graph-toolbar'); if(toolbar) { toolbar.dataset.instanceToolbar='true'; toolbar.hidden=true; } canvas.hidden=true; schema.hidden=false;
    qa('[data-knowledge-view]').forEach(button=>button.addEventListener('click',()=>{const mode=button.dataset.knowledgeView;qa('[data-knowledge-view]').forEach(item=>item.classList.toggle('active',item===button));schema.hidden=mode!=='schema';canvas.hidden=mode!=='instances';const bar=q('[data-instance-toolbar]');if(bar)bar.hidden=mode!=='instances';if(mode==='instances')renderDynamicGraph();else renderOntologySchemaGraphV2();})); renderOntologySchemaGraphV2();
  }

  function renderDynamicGraph() {
    setupKnowledgeViews();
    const canvas=q('#graphCanvas'); if (!canvas || canvas.hidden || !window.d3) return; canvas.innerHTML='';
    let source=tenantData.graph; if (!source.nodes.length) { canvas.innerHTML='<div class="graph-empty">当前租户暂无营销知识数据，请先在数据接入中投递业务文件。</div>'; return; }
    let picker=q('[data-graph-case]');
    if(!picker){picker=document.createElement('select');picker.dataset.graphCase='true';picker.setAttribute('aria-label','选择图谱活动');q('[data-instance-toolbar]')?.append(picker);picker.onchange=()=>{window.ceairSetChainCase?.(picker.value);renderDynamicGraph();};}
    const selected=picker.value||(tenantData.demo?.enabled?'ACT-2026-0921':tenantData.campaigns[0]?.id)||'';
    picker.innerHTML='<option value="all">全部本体对象</option>'+tenantData.campaigns.map(c=>'<option value="'+escapeHtml(c.id)+'">'+escapeHtml(c.name)+'</option>').join('');picker.value=selected;
    if(selected!=='all'){
      const ids=new Set(source.nodes.filter(n=>n.id===selected||n.attributes?.campaign_id===selected).map(n=>n.id));
      for(let pass=0;pass<3;pass++)source.edges.forEach(e=>{const target=source.nodes.find(n=>n.id===e.target);if(ids.has(e.source)&&target&&(!target.attributes?.campaign_id||target.attributes.campaign_id===selected)&&!String(e.target).startsWith('ACT-'))ids.add(e.target);});
      source={nodes:source.nodes.filter(n=>ids.has(n.id)),edges:source.edges.filter(e=>ids.has(e.source)&&ids.has(e.target))};
    }
    const search=q('#graphSearch'),typeSelect=q('#graphType');
    const selectedType=typeSelect?.value||'all';
    if(typeSelect){const names={Campaign:'活动',CampaignVersion:'活动版本',Opportunity:'机会',AudienceSnapshot:'冻结客群',ProductPackage:'产品包',ContentAsset:'内容',AgentRun:'智能体',Evidence:'证据',ExecutionBatch:'执行批次',Feedback:'反馈',Review:'复盘'};typeSelect.innerHTML='<option value="all">全部对象类型</option>'+[...new Set(tenantData.graph.nodes.map(n=>n.type))].map(t=>'<option value="'+escapeHtml(t)+'">'+escapeHtml(window.ceairOntologyLabels[t]||names[t]||t)+'</option>').join('');typeSelect.value=selectedType;typeSelect.onchange=()=>renderDynamicGraph();}
    if(search)search.oninput=()=>renderDynamicGraph();
    const term=(search?.value||'').trim().toLowerCase();
    if(term||selectedType!=='all'){
      const matches=new Set(source.nodes.filter(n=>(!term||[n.label,n.id,JSON.stringify(n.attributes)].join(' ').toLowerCase().includes(term))&&(selectedType==='all'||n.type===selectedType)).map(n=>n.id));
      source={nodes:source.nodes.filter(n=>matches.has(n.id)),edges:source.edges.filter(e=>matches.has(e.source)&&matches.has(e.target))};
    }
    qa('[data-graph-filter]').forEach(button=>{button.onclick=()=>{if(search)search.value='';if(typeSelect)typeSelect.value='all';picker.value=button.dataset.graphFilter==='all'?'all':(tenantData.demo?.enabled?'ACT-2026-0921':tenantData.campaigns[0]?.id||'all');renderDynamicGraph();};});
    if(!source.nodes.length){canvas.innerHTML='<div class="graph-empty">没有符合筛选条件的本体对象</div>';return;}
    if(window.ceairGraphSimulation)window.ceairGraphSimulation.stop();
    const box=canvas.getBoundingClientRect(), width=box.width||900, height=box.height||500;
    const typeLabels={opportunity:'营销机会',audience:'客群',customer:'客户',product:'产品包',product_package:'产品包',content:'内容',campaign:'营销活动',channel:'渠道',flight:'航班',flight_segment:'航段',airport:'机场',route:'航线',fare:'运价',cabin:'舱位',result:'营销结果',entity:'业务对象',audiencesnapshot:'冻结客群',customeraggregate:'聚合客群',productpackage:'产品包',contentasset:'内容资产',campaignversion:'活动版本',approvaltask:'审批任务',executionbatch:'执行批次',feedback:'渠道反馈',review:'效果复盘',agentRun:'智能体运行',agentrun:'智能体运行',evidence:'证据',marketsignal:'市场信号',knowledgedocument:'来源文档',knowledgechunk:'知识片段',strategyplan:'策略计划',touchpointplan:'触点计划',humandecision:'人工决策',valueproposition:'价值主张',customerneed:'旅客需求',recommendation:'机会建议'};
    const nodes=source.nodes.map(item=>({...item,title:displayText(item.label,'未命名对象'),type:String(item.type||'entity').toLowerCase(),typeLabel:typeLabels[String(item.type||'entity').toLowerCase()]||'业务对象',w:172,h:60}));
    const byId=new Map(nodes.map(item=>[item.id,item])); const links=source.edges.filter(item=>byId.has(item.source)&&byId.has(item.target)).map(item=>({...item,source:byId.get(item.source),target:byId.get(item.target),label:displayText(({has_campaign_version:'包含版本',targets_audience:'面向客群',uses_product_package:'使用产品包',generates_content:'生成内容',requires_approval:'需要审批',confirmed_by_human:'人工确认',executes:'产生执行',uses_channel:'使用渠道',produces_feedback:'产生反馈',reviewed_by:'效果复盘',supports_campaign:'支撑活动',has_evidence:'具有证据',derived_from:'来源于',contains_chunk:'包含片段',has_strategy_plan:'策略方案',uses_touchpoint_plan:'触点计划',produces_object:'形成对象',evidence_for:'提供证据',addresses_opportunity:'响应机会'})[item.relation]||item.relation,'关联')})); const neighbors=new Map(nodes.map(item=>[item.id,new Set()])); links.forEach(item=>{neighbors.get(item.source.id)?.add(item.target.id);neighbors.get(item.target.id)?.add(item.source.id);});
    const svg=d3.select(canvas).append('svg').attr('width',width).attr('height',height), defs=svg.append('defs');
    defs.append('marker').attr('id','production-arrow').attr('viewBox','0 0 8 8').attr('refX',7).attr('refY',4).attr('markerWidth',6).attr('markerHeight',6).attr('orient','auto').append('path').attr('d','M0,0 L8,4 L0,8 z').attr('fill','#93b2c4');
    const root=svg.append('g'),zoom=d3.zoom().scaleExtent([.08,2]).on('zoom',event=>root.attr('transform',event.transform));svg.call(zoom);
    const edge=root.append('g').selectAll('path').data(links).join('path').attr('class','graph-edge').attr('marker-end','url(#production-arrow)');
    const labels=root.append('g').selectAll('text').data(links).join('text').attr('class','edge-label').text(item=>item.label);
    const node=root.append('g').selectAll('g').data(nodes).join('g').attr('class',item=>`graph-node dynamic ${item.type}`).call(d3.drag().on('start',(event,item)=>{if(!event.active)simulation.alphaTarget(.25).restart();item.fx=item.x;item.fy=item.y}).on('drag',(event,item)=>{item.fx=event.x;item.fy=event.y}).on('end',(event,item)=>{if(!event.active)simulation.alphaTarget(0);item.fx=null;item.fy=null}));
    node.append('rect').attr('x',item=>-item.w/2).attr('y',item=>-item.h/2).attr('width',item=>item.w).attr('height',item=>item.h).attr('rx',4);
    node.append('text').attr('class','title').attr('x',item=>-item.w/2+10).attr('y',-5).text(item=>item.title.slice(0,16)); node.append('text').attr('class','type').attr('x',item=>-item.w/2+10).attr('y',17).text(item=>item.typeLabel);
    node.on('click',(event,item)=>{event.stopPropagation();const near=neighbors.get(item.id)||new Set();node.classed('is-selected',value=>value.id===item.id).classed('is-neighbor',value=>near.has(value.id)).classed('is-muted',value=>value.id!==item.id&&!near.has(value.id));edge.classed('is-muted',value=>value.source.id!==item.id&&value.target.id!==item.id);labels.classed('is-muted',value=>value.source.id!==item.id&&value.target.id!==item.id);q('#entityDetail').innerHTML=`<div class="entity-title">
<b>${escapeHtml(item.title)}</b>
<span>${escapeHtml(item.typeLabel)}</span>
</div>
<dl>
<dt>对象 ID</dt>
<dd>${escapeHtml(item.id)}</dd>
<dt>数据来源</dt>
<dd>${escapeHtml(displayText(item.source,'未知来源'))}</dd>
<dt>置信度</dt>
<dd>${item.attributes?.confidence_status==='未评估'?'未评估':Math.round((item.confidence||0)*100)+'%'}</dd>
</dl>
<div class="ai-result">
<b>对象属性（入库记录）</b>
<p>${escapeHtml(Object.entries(item.attributes||{}).slice(0,6).map(([key,value])=>`${key}：${typeof value==='object'?JSON.stringify(value):value}`).join('；')||'暂无扩展属性')}</p>
</div>`;});
    const simulation=window.ceairGraphSimulation=d3.forceSimulation(nodes).force('link',d3.forceLink(links).id(item=>item.id).distance(145).strength(.7)).force('charge',d3.forceManyBody().strength(-420)).force('collide',d3.forceCollide().radius(90)).force('center',d3.forceCenter(width/2,height/2)).on('tick',()=>{edge.attr('d',item=>`M${item.source.x},${item.source.y} L${item.target.x},${item.target.y}`);labels.attr('x',item=>(item.source.x+item.target.x)/2).attr('y',item=>(item.source.y+item.target.y)/2-5);node.attr('transform',item=>`translate(${item.x},${item.y})`)});
    simulation.stop();for(let tick=0;tick<160;tick++)simulation.tick();
    const bounds={minX:Math.min(...nodes.map(n=>n.x-90)),maxX:Math.max(...nodes.map(n=>n.x+90)),minY:Math.min(...nodes.map(n=>n.y-35)),maxY:Math.max(...nodes.map(n=>n.y+35))};
    const scale=Math.min(.95,(width-30)/(bounds.maxX-bounds.minX),(height-30)/(bounds.maxY-bounds.minY));
    svg.call(zoom.transform,d3.zoomIdentity.translate((width-scale*(bounds.maxX+bounds.minX))/2,(height-scale*(bounds.maxY+bounds.minY))/2).scale(scale));simulation.alpha(.03).restart();
    node.filter((_,index)=>index===0).dispatch('click');
  }

  const pipelineStages={queued:['\u7b49\u5f85\u5904\u7406',6],received:['\u6587\u4ef6\u68c0\u67e5',16],extracting:['\u5185\u5bb9\u89e3\u6790',32],extracted:['\u6e05\u6d17\u5207\u5206',48],classifying:['AI \u8bed\u4e49\u62bd\u53d6',65],classified:['\u4e1a\u52a1\u6821\u9a8c',78],persisting:['\u77e5\u8bc6\u5165\u5e93',90],'ontology-updated':['\u5904\u7406\u5b8c\u6210',100],failed:['\u5904\u7406\u5931\u8d25',100]};
  const pipelineStatusText={queued:'\u6392\u961f\u4e2d',running:'\u5904\u7406\u4e2d',completed:'\u5df2\u5b8c\u6210',failed:'\u5931\u8d25'};
  const formatBytes=value=>value>=1048576?(value/1048576).toFixed(1)+' MB':Math.max(1,Math.round(value/1024))+' KB';
  function stageInfo(item){const value=pipelineStages[item.current_stage]||[item.current_stage||'\u5904\u7406\u4e2d',item.status==='completed'?100:12];return {label:value[0],progress:value[1]};}
  function renderImports() {
    const table=q('#importTable'); if(!table)return;
    const pipelines=tenantData.pipelines||[];
    const syncs=(tenantData.imports||[]).filter(item=>['audience','product'].includes(item.dataset_type));
    q('#importCount').textContent=(pipelines.length+syncs.length)+' 个批次';
    const rows=[
      ...pipelines.map(item=>({id:item.id,name:item.file_name,format:item.file_format,status:item.status,time:item.completed_at||item.created_at,result:'业务对象 '+item.accepted_entities+' · 关系 '+item.accepted_relations+(item.rejected_items?' · 待复核 '+item.rejected_items:''),error:item.error_message})),
      ...syncs.map(item=>({id:item.id,name:item.file_name,format:item.file_format,status:item.status,time:item.completed_at||item.created_at,result:(item.dataset_type==='audience'?'聚合客群':'产品包')+' · 接收 '+item.accepted_rows+' / '+item.total_rows+' 条',error:item.rejected_rows?'待复核 '+item.rejected_rows+' 条':''}))
    ].sort((a,b)=>String(b.time||'').localeCompare(String(a.time||'')));
    table.innerHTML='<tr><th>文件 / 来源</th><th>格式</th><th>处理结果</th><th>状态</th><th>完成时间（北京时间）</th></tr>'+(rows.length?rows.map(item=>'<tr><td><strong>'+escapeHtml(item.name)+'</strong><small>'+escapeHtml(item.id)+'</small></td><td>'+escapeHtml(String(item.format||'').toUpperCase())+'</td><td>'+escapeHtml(item.result)+'</td><td><span class="status '+(item.status==='failed'?'warn':'good')+'">'+escapeHtml(pipelineStatusText[item.status]||item.status)+'</span>'+(item.error?'<small class="pipeline-error">'+escapeHtml(item.error)+'</small>':'')+'</td><td>'+escapeHtml(businessTime(item.time))+'</td></tr>').join(''):'<tr><td colspan="5" class="table-empty">暂无处理记录。可投递文件，或在客群与产品页同步标准 JSON。</td></tr>');
  }
  function renderPipelineQueue(){const queue=q('#pipelineQueue');if(!queue)return;const active=(tenantData.pipelines||[]).filter(item=>['queued','running'].includes(item.status));const local=[...pipelineFiles.values()].filter(item=>!item.job||['uploading','failed'].includes(item.status));const merged=[...local,...active.filter(item=>!local.some(localItem=>localItem.job&&localItem.job.id===item.id))];q('#pipelineQueueCount').textContent=merged.length+' \u4e2a\u4efb\u52a1';if(!merged.length){queue.innerHTML='<div class="pipeline-empty"><i data-lucide="inbox"></i><b>\u6682\u65e0\u5904\u7406\u4efb\u52a1</b><span>\u62d6\u5165\u6587\u4ef6\u540e\u5c06\u5728\u8fd9\u91cc\u663e\u793a\u8fdb\u5ea6</span></div>';}else{queue.innerHTML=merged.map(item=>{const job=item.job||item;const info=item.status==='uploading'?{label:'\u6b63\u5728\u4e0a\u4f20',progress:item.progress||8}:stageInfo(job);const failed=item.status==='failed'||job.status==='failed';return '<article class="pipeline-task '+(failed?'is-failed':'')+'"><div class="pipeline-file-icon"><i data-lucide="file-text"></i></div><div class="pipeline-task-main"><div class="pipeline-task-title"><b>'+escapeHtml(item.file?item.file.name:job.file_name)+'</b><span>'+(item.file?formatBytes(item.file.size):escapeHtml((job.file_format||'').toUpperCase()))+'</span></div><div class="pipeline-progress"><i style="width:'+info.progress+'%"></i></div><div class="pipeline-task-meta"><span>'+(failed?'\u5904\u7406\u5931\u8d25':info.label)+'</span><small>'+(failed?escapeHtml(item.error||job.error_message||'\u8bf7\u68c0\u67e5\u6587\u4ef6\u540e\u91cd\u8bd5'):info.progress+'% \u00b7 \u7cfb\u7edf\u6b63\u5728\u81ea\u52a8\u5904\u7406')+'</small></div></div>'+(failed&&item.file?'<button class="btn" data-pipeline-retry="'+item.localId+'"><i data-lucide="rotate-ccw"></i>\u91cd\u8bd5</button>':'')+'</article>';}).join('');}if(window.lucide)lucide.createIcons();}
  async function refreshPipelines(){tenantData.pipelines=await request('/api/data-pipelines');for(const [localId,entry] of pipelineFiles){if(!entry.job)continue;const latest=tenantData.pipelines.find(item=>item.id===entry.job.id);if(!latest)continue;entry.job=latest;if(latest.status==='failed'){entry.status='failed';entry.error=latest.error_message;}else if(latest.status==='completed'){pipelineFiles.delete(localId);}}renderPipelineQueue();renderImports();const hasActive=tenantData.pipelines.some(item=>['queued','running'].includes(item.status));clearTimeout(pipelinePollTimer);if(hasActive)pipelinePollTimer=setTimeout(()=>refreshPipelines().catch(()=>{}),1500);}
  async function uploadPipelineFile(entry){entry.status='uploading';entry.progress=8;renderPipelineQueue();const form=new FormData();form.append('file',entry.file);try{const result=await request('/api/data-pipelines',{method:'POST',body:form},true);entry.job=result.job;entry.status='queued';entry.progress=10;await refreshPipelines();}catch(cause){entry.status='failed';entry.error=cause.message||'\u4e0a\u4f20\u5931\u8d25';renderPipelineQueue();}}
  function queuePipelineFiles(files){if(!canWrite()){toast('当前角色只有只读权限，不能上传数据');return;}const allowed=/\.(txt|md|json|csv|pdf|png|jpe?g|docx?|pptx?|xlsx?|html)$/i;[...files].forEach(file=>{const localId=Date.now()+'-'+Math.random().toString(16).slice(2);if(!allowed.test(file.name)){toast('\u4e0d\u652f\u6301\u6587\u4ef6\uff1a'+file.name);return;}if(file.size>20*1024*1024){toast('\u6587\u4ef6\u8d85\u8fc7 20MB\uff1a'+file.name);return;}const entry={localId,file,status:'queued',progress:0};pipelineFiles.set(localId,entry);uploadPipelineFile(entry);});}

  function renderMineru() {
    const panel=q('.mineru-panel'); if(!panel) return;
    panel.hidden=!isTenantAdmin();
    const config=tenantData.mineru; if(!config) return;
    q('#mineruState').textContent=config.api_key_configured?(config.enabled?'已启用':'已停用'):'未配置密钥';
  }
  function renderModels() { if(q('#providerSettings')) getProviderSettings().render(); }

  async function loadPlatform() { if(!session.is_platform_admin) return; const [tenants,users]=await Promise.all([request('/api/platform/tenants'),request('/api/platform/users')]); q('#tenantCount').textContent=`${tenants.length} 个`; q('#userCount').textContent=`${users.length} 人`; q('#tenantTable').innerHTML=`<tr>
<th>编码</th>
<th>租户名称</th>
<th>角色</th>
</tr>${tenants.length ? tenants.map(item=>`<tr>
<td>${escapeHtml(item.code)}</td>
<td>
<strong>${escapeHtml(item.name)}</strong>
</td>
<td>${escapeHtml(roleLabels[item.role] || item.role)}</td>
</tr>`).join('') : '<tr><td colspan="3"><div class="empty-action"><b>暂无运营租户</b><span>请先创建营销运营组织，再配置成员与数据权限。</span></div></td></tr>'}`; q('#userTable').innerHTML=`<tr>
<th>姓名</th>
<th>用户名</th>
<th>租户授权</th>
<th>平台权限</th>
</tr>${users.length ? users.map(item=>`<tr>
<td>
<strong>${escapeHtml(item.display_name===['内置','演示模型'].join('')?'内置测试模型':item.display_name)}</strong>
</td>
<td>${escapeHtml(item.username)}</td>
<td>${item.memberships.map(m=>`${escapeHtml(m.name)}（${escapeHtml(roleLabels[m.role] || m.role)}）`).join('、')}</td>
<td>${item.is_platform_admin?'平台管理员':'普通用户'}</td>
</tr>`).join('') : '<tr><td colspan="4"><div class="empty-action"><b>暂无用户授权</b><span>创建用户后，可在这里配置租户、角色与数据范围。</span></div></td></tr>'}`; }

  function bindProductionActions() {
    bindWorkbenchControls();
    document.addEventListener('click',event=>{
      if(!event.target.closest('[data-action="createCampaign"]'))return;
      event.preventDefault();event.stopImmediatePropagation();
      if(canWrite())showCampaignEditor({name:'',stage:'创建',audience_size:0,budget_yuan:0,roi_target:0});
    },true);
    document.addEventListener('click', async event => {
      const subviewButton=event.target.closest?.('[data-business-subview]');
      if(subviewButton){const view=subviewButton.closest('.view');if(view?.id==='audiences'&&subviewButton.dataset.businessSubview==='selection'){showAudienceSelectionModal();return;}if(view)activateBusinessSubview(view.id,subviewButton.dataset.businessSubview);return;}
      const openCampaign=event.target.closest?.('[data-open-campaign]');
      if(openCampaign){const item=(tenantData.campaigns||[]).find(value=>value.name===openCampaign.dataset.openCampaign);if(item){showCampaignDetail(item);toast('已打开活动详情：'+item.name);}return;}
      const button=event.target.closest('button'); if(!button) return;
      if(button.dataset.action==='approvalHistory'){activateBusinessSubview('approvals','history');return;}
      if(button.dataset.action==='exportCampaign'){downloadBusinessJson('活动清单',{workspace:activeTenant().name,campaigns:tenantData.campaigns});return;}
      if(button.dataset.action==='exportReview'){downloadBusinessJson('活动复盘',{workspace:activeTenant().name,exported_at:new Date().toISOString(),note:'渠道联调为虚构回执；收入与ROI等待交易归因',summary:tenantData.effectSummary});return;}
      if(button.dataset.action==='traceLifecycle'){activate('graph');activateBusinessSubview('graph','instances');return;}
      if(button.matches('[aria-label="查看通知"]')){showNotifications();return;}
      const decisionModal=q('#decisionModal');
      if(button.dataset.productionApprovalAction){
        const approval=(tenantData.approvals||[]).find(item=>String(item.id)===String(selectedProductionApprovalId));
        if(!approval||!approvalIsPending(approval)){toast('\u8be5\u5ba1\u6279\u4efb\u52a1\u5df2\u5904\u7406\uff0c\u8bf7\u5237\u65b0\u5217\u8868');return;}
        if(decisionModal){decisionModal.dataset.productionApprovalId=String(approval.id);decisionModal.dataset.productionDecision=button.dataset.productionApprovalAction;const title=displayText(approvalCampaign(approval)?.name,approval.campaign_id);q('#decisionSubtitle')?.replaceChildren(document.createTextNode(title));const comment=q('#decisionComment');if(comment)comment.value=button.dataset.productionApprovalAction==='approve'?'\u914d\u7f6e\u5df2\u6838\u9a8c\uff0c\u540c\u610f\u8fdb\u5165\u6267\u884c\u9636\u6bb5\u3002':'\u8bf7\u8865\u5145\u6d3b\u52a8\u6750\u6599\u540e\u91cd\u65b0\u63d0\u4ea4\u5ba1\u6279\u3002';openLayer('decisionModal');}
        return;
      }
      if(button.dataset.decision && decisionModal?.dataset.productionApprovalId){decisionModal.dataset.productionDecision=button.dataset.decision;return;}
      if(button.id==='confirmDecision' && decisionModal?.dataset.productionApprovalId){const decision=decisionModal.dataset.productionDecision||'approve';const comment=q('#decisionComment')?.value||'';await decideProductionApproval(decision,comment);return;}
      if(button.dataset.insightSourceEdit){const item=(tenantData.opportunitySources||[]).find(value=>String(value.id)===String(button.dataset.insightSourceEdit));const form=q('#opportunitySourceForm');if(item&&form){for(const key of ['source_id','name','source_url','source_type','schedule','focus']){const field=form.elements[key];if(field)field.value=key==='source_id'?item.id:(item[key]||'');}form.scrollIntoView({behavior:'smooth',block:'center'});}return;}
      if(button.dataset.insightSourceDelete){if(!canWrite()||!window.confirm('确认删除这个洞察来源？历史任务不会被删除。'))return;try{await request('/api/opportunity-insight/sources/'+button.dataset.insightSourceDelete,{method:'DELETE'});toast('洞察来源已删除');await loadTenantData();}catch(cause){toast(cause.message||'来源删除失败');}return;}
      if(button.dataset.insightRunView){try{const detail=await request('/api/opportunity-insight/runs/'+button.dataset.insightRunView);showInsightRunDetail(detail);}catch(cause){toast(cause.message||'洞察任务加载失败');}return;}
      if(button.dataset.action==='resetOpportunitySource'){const form=q('#opportunitySourceForm');if(form){form.reset();form.elements.source_id.value='';}return;}
      if(button.dataset.action==='runOpportunityInsight'){if(!canWrite())return;button.disabled=true;try{const sourceIds=qa('[data-insight-source]:checked').map(input=>Number(input.value));const prompt=(q('#opportunityInsightPrompt')?.value||'').trim();const result=await request('/api/opportunity-insight/runs',{method:'POST',body:JSON.stringify({prompt,source_ids:sourceIds,operator:session?.display_name||''})});toast('商机洞察已启动：'+result.id);await loadTenantData();}catch(cause){toast(cause.message||'商机洞察启动失败');}finally{button.disabled=false;}return;}
       if(button.dataset.productionCampaignView){const item=(tenantData.campaigns||[]).find(value=>value.id===button.dataset.productionCampaignView);if(item){showCampaignDetail(item);toast('已打开活动详情：'+item.name);}return;}
       if(button.dataset.productionCampaignArchive){const item=(tenantData.campaigns||[]).find(value=>value.id===button.dataset.productionCampaignArchive);if(!item||!canWrite()||!window.confirm('确认归档活动“'+item.name+'”？归档后将停止继续编辑，并保留执行与审批留痕。'))return;try{await request('/api/campaigns/'+encodeURIComponent(item.id)+'/archive',{method:'POST'});toast('活动“'+item.name+'”已归档，现在可以按审计要求删除');await loadTenantData();}catch(cause){toast(cause.message||'活动归档失败');}return;}
       if(button.dataset.productionCampaignDelete){const item=(tenantData.campaigns||[]).find(value=>value.id===button.dataset.productionCampaignDelete);if(!item||!canWrite())return;const prompt=item.status==='已归档'?'确认删除已归档活动“'+item.name+'”？相关版本、审批、执行记录将一并删除。':'确认删除草稿活动“'+item.name+'”？删除后不可恢复。';if(!window.confirm(prompt))return;try{await request('/api/campaigns/'+encodeURIComponent(item.id),{method:'DELETE'});toast('活动“'+item.name+'”已删除');await loadTenantData();}catch(cause){toast(cause.message||'活动删除失败');}return;}
       if(button.dataset.productionCampaignEdit){const item=(tenantData.campaigns||[]).find(value=>value.id===button.dataset.productionCampaignEdit);if(!item||!canWrite())return;await showCampaignEditor(item);return;}
       if(button.dataset.productView){const item=(tenantData.productPackages||[]).find(value=>String(value.id)===String(button.dataset.productView));if(item)showProductDetail(item);return;}
       if(button.dataset.productCatalogView){const item=(tenantData.productCatalog?.products||[]).find(value=>String(value.code)===String(button.dataset.productCatalogView));if(item)showBaseProductDetail(item);return;}
       if(button.dataset.audienceDimension){const item=(tenantData.personaDimensions||[]).find(value=>String(value.id)===String(button.dataset.audienceDimension));if(item)showAudienceDimensionDetail(item);return;}
       if(button.dataset.audiencePersona){const item=(tenantData.personaSegments||[]).find(value=>String(value.id)===String(button.dataset.audiencePersona));if(item)showPersonaDetail(item);return;}
       if(button.dataset.productEdit){const item=(tenantData.productPackages||[]).find(value=>String(value.id)===String(button.dataset.productEdit));if(!item||!canWrite())return;showProductEditor(item);return;}
       if(button.dataset.productDelete){const item=(tenantData.productPackages||[]).find(value=>String(value.id)===String(button.dataset.productDelete));if(!item||!canWrite()||!window.confirm('确认删除产品包“'+item.name+'”？删除后不可恢复。'))return;try{await request(`/api/product-packages/${item.id}`,{method:'DELETE'});toast('产品包“'+item.name+'”已删除');await loadTenantData();}catch(cause){toast(cause.message||'产品包删除失败');}return;}      if(button.dataset.action==='newProduct'){
        if(!canWrite())return;
         showProductEditor({name:'',product_type:'机票组合',description:'',eligibility:'',version:'V1',status:'草稿',valid_from:null,valid_to:null});return;
      }
      if(button.dataset.audienceEdit){const item=(tenantData.audiencePackages||[]).find(value=>String(value.id)===String(button.dataset.audienceEdit));if(!item||!canWrite()||button.disabled)return;showAudiencePackageEditor(item);return;}
      if(button.dataset.audienceTagEdit){const item=(tenantData.audienceTags||[]).find(value=>String(value.id)===String(button.dataset.audienceTagEdit));if(!item||!canWrite())return;showAudienceTagEditor(item);return;}
      if(button.dataset.audienceSnapshot){if(!canWrite()||button.disabled)return;try{const result=await request(`/api/audience-packages/${button.dataset.audienceSnapshot}/snapshots`,{method:'POST'});toast('客群快照 '+result.version+' 已冻结，可用于活动执行');await loadTenantData();}catch(cause){toast(cause.message||'客群快照生成失败');}return;}      if(button.dataset.contentView){const item=(tenantData.contentAssets||[]).find(value=>String(value.id)===String(button.dataset.contentView));if(item){selectedContentAssetId=String(item.id);selectedPreviewChannel=item.channel||'App';renderContents();showContentDetail(item);}return;}
      if(button.dataset.contentReview){const item=tenantData.contentAssets.find(a=>String(a.id)===button.dataset.contentReview);if(item)openBusinessEditor({title:'内容事实与渠道审核',item:{decision:'approve',comment:''},fields:[{name:'decision',label:'审核决定',type:'select',options:[{value:'approve',label:'核验后通过'},{value:'reject',label:'退回草稿'}]},{name:'comment',label:'审核说明',type:'textarea'}],save:async values=>{await request('/api/content-assets/'+item.id+'/review',{method:'POST',body:JSON.stringify(values)});await loadTenantData();}});return;}
      if(button.dataset.contentVisual){const item=tenantData.contentAssets.find(a=>String(a.id)===button.dataset.contentVisual);if(item)window.ceairOpenVisual(item);return;}
      if(button.dataset.contentEdit){const item=(tenantData.contentAssets||[]).find(value=>String(value.id)===String(button.dataset.contentEdit));if(!item||!canWrite())return;showContentEditor(item);return;}
       if(button.dataset.channelFeedback){const item=(tenantData.channelTasks||[]).find(value=>String(value.id)===String(button.dataset.channelFeedback));if(!item||!canWrite())return;showChannelFeedbackEditor(item);return;}
      if(button.dataset.contentDelete){const item=(tenantData.contentAssets||[]).find(value=>String(value.id)===String(button.dataset.contentDelete));if(!item||!canWrite()||!window.confirm('确认删除内容“'+item.name+'”？删除后不可恢复。'))return;try{await request(`/api/content-assets/${item.id}`,{method:'DELETE'});toast('内容已删除');await loadTenantData();}catch(cause){toast(cause.message||'内容删除失败');}return;}
      if(button.dataset.action==='refreshExecution'&&button.dataset.batchId){
        if(!canWrite())return;
        button.disabled=true;
        try{const result=await request(`/api/execution-batches/${button.dataset.batchId}/run`,{method:'POST'});toast('执行完成：'+result.external_id);await loadTenantData();}
        catch(cause){toast(cause.message||'批次执行失败');}
        finally{renderExecution();if(window.lucide)lucide.createIcons();}return;
      }
      if(button.dataset.action==='pauseCampaign'&&button.dataset.batchId){try{const result=await request(`/api/execution-batches/${button.dataset.batchId}/status`,{method:'POST',body:JSON.stringify({status:'已暂停'})});toast('执行批次已暂停：'+result.external_id);await loadTenantData();}catch(cause){toast(cause.message||'批次暂停失败');}return;}      if(button.dataset.pipelineRetry){const entry=pipelineFiles.get(button.dataset.pipelineRetry);if(entry){entry.error='';uploadPipelineFile(entry);}return;}
      if(button.dataset.opportunityDelete){
        if(!canWrite()||!window.confirm('删除后该机会及其关联引用将不再出现在当前租户，确定继续吗？')) return;
        try{await request(`/api/opportunities/${encodeURIComponent(button.dataset.opportunityDelete)}`,{method:'DELETE'});toast('机会已删除');await loadTenantData();}catch(cause){toast(cause.message||'机会删除失败');}return;
      }
      if(button.dataset.opportunityEdit){
        const item=(tenantData.opportunities||[]).find(value=>value.id===button.dataset.opportunityEdit);if(!item||!canWrite())return;
        showOpportunityEditor(item);return;
      }
      if(button.dataset.documentDelete){
        if(!canWrite()||!window.confirm('删除文档将同步删除知识切片、本体对象及关系，确定继续吗？'))return;
        try{await request(`/api/knowledge/documents/${button.dataset.documentDelete}`,{method:'DELETE'});toast('文档及关联知识、本体已删除');await loadTenantData();}catch(cause){toast(cause.message||'文档删除失败');}return;
      }
      if(button.dataset.documentEdit){
        const item=(tenantData.documents||[]).find(value=>String(value.id)===String(button.dataset.documentEdit));if(!item||!canWrite())return;
        showKnowledgeDocumentEditor(item);return;
      }
      if(button.dataset.action==='newAudience'){if(!canWrite())return;showAudiencePackageCreator();return;}
      if(button.dataset.action==='viewAudienceSnapshot'){showAudienceSelectionModal();return;}
      if(button.dataset.contentActions){
        const item=(tenantData.contentAssets||[]).find(value=>String(value.id)===button.dataset.contentActions);if(!item)return;
        const layer=document.createElement('div');layer.className='production-modal';
        layer.innerHTML=`<div class="production-modal-card content-actions-card"><div class="production-modal-head"><b>${escapeHtml(item.name)}</b><button class="btn" type="button" data-close>关闭</button></div><div class="production-modal-body content-secondary-actions"><button class="btn" type="button" data-content-visual="${item.id}">视觉</button>${["草稿","待审核"].includes(item.status)&&["admin","manager"].includes(activeTenant()?.role)?`<button class="btn" data-content-review="${item.id}">审核</button>`:""}<button class="btn" data-content-edit="${item.id}">编辑</button><button class="btn danger" type="button" data-content-delete="${item.id}">删除</button></div></div>`;
        document.body.append(layer);bindProductionModal(layer);
        layer.addEventListener('click',event=>{if(event.target.closest('[data-content-visual],[data-content-review],[data-content-edit],[data-content-delete]'))layer.__closeProductionModal();});return;
      }
      if(button.dataset.action==='newContent'){if(!canWrite())return;showContentEditor({name:'',campaign_id:contentGenerationContext.campaign_id||null,channel:'App',version:'V1',status:'草稿',generated_by:'manual',title:'',body:''});return;}
      if(button.dataset.action==='refreshAudienceCatalog'){if(!canWrite())return;button.disabled=true;try{await loadTenantData();toast('\u753b\u50cf\u76ee\u5f55\u5df2\u540c\u6b65\uff1a'+(tenantData.personaDimensions||[]).length+'\u4e2a\u753b\u50cf\u7ef4\u5ea6');}catch(cause){toast(cause.message||'\u753b\u50cf\u540c\u6b65\u5931\u8d25');}finally{button.disabled=false;}return;}
       if(button.dataset.action==='newProvider'){if(!isTenantAdmin())return;showProviderCreateEditor();return;}
       if(button.dataset.action==='editMineru'){if(!isTenantAdmin())return;showMineruEditor();return;}
       if(button.dataset.action==='newTenant'){if(!session?.is_platform_admin)return;showTenantCreateEditor();return;}
       const agentMap={scanOpportunity:'opportunity-insight',naturalAudience:'audience-insight',calculateAudience:'audience-insight',useProduct:'product-match',aiOrchestrate:'activity-orchestration',generateReview:'effect-analysis'};
       if(button.dataset.action==='generateContent'){await generateContentFromContext(button);return;}
       const domain=agentMap[button.dataset.action];
       if(domain){showDomainRequest(domain);return;}
    });
    document.addEventListener('submit',async event=>{if(event.target?.id!=='opportunitySourceForm')return;event.preventDefault();if(!canWrite())return;const form=event.target;const values=Object.fromEntries(new FormData(form));values.max_pages=5;values.enabled=true;const sourceId=values.source_id;delete values.source_id;try{await request(sourceId?'/api/opportunity-insight/sources/'+sourceId:'/api/opportunity-insight/sources',{method:sourceId?'PUT':'POST',body:JSON.stringify(values)});form.reset();form.elements.source_id.value='';toast(sourceId?'洞察来源已更新':'洞察来源已新增');await loadTenantData();}catch(cause){toast(cause.message||'来源保存失败');}});
    const dropzone=q('#pipelineDropzone'),fileInput=q('#pipelineFiles');
    dropzone.addEventListener('click',()=>fileInput.click());
    dropzone.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();fileInput.click();}});
    fileInput.addEventListener('change',()=>{queuePipelineFiles(fileInput.files);fileInput.value='';});
    ['dragenter','dragover'].forEach(name=>dropzone.addEventListener(name,event=>{event.preventDefault();dropzone.classList.add('is-dragging');}));
    ['dragleave','drop'].forEach(name=>dropzone.addEventListener(name,event=>{event.preventDefault();dropzone.classList.remove('is-dragging');}));
    dropzone.addEventListener('drop',event=>queuePipelineFiles(event.dataTransfer.files));
    q('#refreshPipelines')?.addEventListener('click',()=>refreshPipelines().then(()=>toast('\u5904\u7406\u72b6\u6001\u5df2\u5237\u65b0')).catch(cause=>toast(cause.message)));
    q('#syncNdcFlight')?.addEventListener('click',async()=>{if(!canWrite())return;const button=q('#syncNdcFlight');button.disabled=true;try{const result=await request('/api/ndc/sync-flight-products',{method:'POST',body:JSON.stringify({origin:'SHA',destination:'SYX',departure_date:'2026-09-14',sales_channel:'10000'})});toast('NDC24.1航班产品已进入流水线：'+result.job.id);await loadTenantData();showAgentTrace({summary:'NDC24.1模拟航班产品已完成标准化，等待人工确认',events:result.stages||[]});}catch(cause){toast(cause.message||'NDC航班同步失败');}finally{button.disabled=false;}});
    q('#tenantForm')?.addEventListener('submit',async event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.currentTarget));values.code=String(values.code).toUpperCase();await request('/api/platform/tenants',{method:'POST',body:JSON.stringify(values)});event.currentTarget.reset();toast('租户已创建');await loadPlatform();});
  }

function mountMarketingAssistantV2(){
    if(q('#marketingAssistant')) q('#marketingAssistant').remove();
    const root=document.createElement('div');
    root.id='marketingAssistant';
    root.innerHTML=`<button class="assistant-fab" title="打开东东" aria-label="打开东东"><img class="assistant-fab-mark" src="./brand/dongdong-robot.svg" alt=""><span>东东</span></button>
      <section class="assistant-panel" hidden aria-label="东东对话框">
        <header class="assistant-drag-handle">
          <div class="assistant-title"><div><b>东东</b><button class="assistant-history-button" type="button" data-assistant-history>历史</button></div></div>
          <div class="assistant-header-actions">
            <span class="assistant-live" role="status"><i></i><span>就绪</span></span>
            <button type="button" class="icon-btn" data-assistant-collapse aria-label="折叠对话框" title="折叠"><i data-lucide="minus"></i></button>
            <button type="button" class="icon-btn" data-assistant-close aria-label="关闭对话框" title="关闭"><i data-lucide="x"></i></button>
          </div>
        </header>
        <div class="assistant-messages"></div>
        <form><textarea name="message" rows="1" aria-label="营销任务" placeholder="输入营销任务" autocomplete="off" maxlength="12000"></textarea><button class="btn" type="button" data-assistant-stop hidden>停止等待</button><button class="btn primary" type="submit"><i data-lucide="arrow-up"></i><span>发送</span></button></form>
      </section>`;
    document.body.appendChild(root);
    const fab=q('.assistant-fab',root),panel=q('.assistant-panel',root),header=q('.assistant-drag-handle',root),messages=q('.assistant-messages',root),form=q('form',root),input=q('textarea',root),collapseButton=q('[data-assistant-collapse]',root);
    const traceLabel={'harness/context-loaded':'加载业务上下文','harness/model-started':'分析任务','harness/model-finished':'整理结果','harness/tool-started':'调用业务能力','harness/tool-failed':'工具返回错误','agent/plan':'执行计划'};
    const stateKey='ceair-marketing-assistant-layout-v2';
    const readLayout=()=>{try{return JSON.parse(localStorage.getItem(stateKey)||'{}')}catch{return {}}};
    const saveLayout=()=>{if(panel.classList.contains('is-docked'))return;const panelRect=panel.getBoundingClientRect(),fabRect=fab.getBoundingClientRect();localStorage.setItem(stateKey,JSON.stringify({panel:{left:panelRect.left,top:panelRect.top,width:panelRect.width,height:panelRect.height},fab:{left:fabRect.left,top:fabRect.top},collapsed:panel.classList.contains('is-collapsed')}));};
    const clamp=(value,min,max)=>Math.min(Math.max(value,min),Math.max(min,max));
    const positionElement=(element,left,top)=>{const rect=element.getBoundingClientRect();element.style.right='auto';element.style.bottom='auto';element.style.left=clamp(left,8,window.innerWidth-rect.width-8)+'px';element.style.top=clamp(top,8,window.innerHeight-rect.height-8)+'px';};
    const restoreLayout=()=>{const state=readLayout();if(state.panel){panel.style.width=clamp(Number(state.panel.width)||410,340,Math.max(340,window.innerWidth-16))+'px';panel.style.height=clamp(Number(state.panel.height)||640,360,Math.max(360,window.innerHeight-16))+'px';positionElement(panel,Number(state.panel.left)||24,Number(state.panel.top)||24);}if(state.fab)positionElement(fab,Number(state.fab.left)||window.innerWidth-160,Number(state.fab.top)||window.innerHeight-72);if(state.collapsed)panel.classList.add('is-collapsed');};
    let suppressFabClick=false;
    const makeDraggable=(handle,target,isFab=false)=>{
      handle.addEventListener('pointerdown',event=>{if(event.button!==0||event.target.closest('button')&&!isFab)return;const rect=target.getBoundingClientRect(),originX=event.clientX,originY=event.clientY;let moved=false;target.style.right='auto';target.style.bottom='auto';target.style.left=rect.left+'px';target.style.top=rect.top+'px';handle.setPointerCapture(event.pointerId);target.classList.add('is-dragging');
        const move=moveEvent=>{const dx=moveEvent.clientX-originX,dy=moveEvent.clientY-originY;if(Math.abs(dx)+Math.abs(dy)>5)moved=true;positionElement(target,rect.left+dx,rect.top+dy);};
        const end=()=>{handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',end);handle.removeEventListener('pointercancel',end);target.classList.remove('is-dragging');if(isFab&&moved)suppressFabClick=true;saveLayout();};
        handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',end);handle.addEventListener('pointercancel',end);
      });
    };
    const setCollapsed=collapsed=>{panel.classList.toggle('is-collapsed',collapsed);collapseButton.innerHTML='<i data-lucide="'+(collapsed?'chevron-up':'minus')+'"></i>';collapseButton.setAttribute('aria-label',collapsed?'展开对话框':'折叠对话框');collapseButton.title=collapsed?'展开':'折叠';if(window.lucide)lucide.createIcons();saveLayout();};
    const conversation=[];
    let workspace;
    const submitButton=q('[type=submit]',form),stopButton=q('[data-assistant-stop]',form),live=q('.assistant-live',root);
    let currentRequest,conversationId='';
    const setLive=(text,error=false)=>{q('span',live).textContent=text;live.classList.toggle('is-error',error);const toolbar=q('[data-chat-status]',panel);if(toolbar){toolbar.textContent=text;toolbar.classList.toggle('is-error',error);}const home=q('.dongdong-live');if(home){home.innerHTML='<i></i>'+escapeHtml(text);home.classList.toggle('is-error',error);}};
    stopButton.addEventListener('click',()=>currentRequest?.abort());
    const send=async (message,retryWrap=null)=>{
      message=String(message||'').trim();
      if(!message||form.dataset.busy)return;
      if(!canWrite()){setLive('无对话权限',true);return;}
      const requestTenantId=activeTenant()?.id;
      form.dataset.busy='1';input.disabled=true;submitButton.disabled=true;stopButton.hidden=false;setLive('处理中');
      currentRequest=new AbortController();
      workspace.setTitle(message);
      panel.classList.add('has-conversation');
      q('.assistant-welcome',panel)?.remove();
      if(!retryWrap)messages.insertAdjacentHTML('beforeend','<div class="assistant-message user"><div>'+escapeHtml(message)+'</div></div>');
      const wrap=retryWrap||document.createElement('div');wrap.className='assistant-message assistant live-message';wrap.innerHTML='<div class="assistant-live-body"><div class="assistant-streaming"><span></span><span></span><span></span><b>正在读取业务数据</b></div><div class="assistant-answer is-streaming" aria-live="polite"></div><div class="assistant-ui-output"></div></div>';if(!retryWrap)messages.appendChild(wrap);
      const answer=q('.assistant-answer',wrap),streaming=q('.assistant-streaming',wrap),process=window.createAssistantProcess(q('.assistant-live-body',wrap)),ui=workspace.renderer(q('.assistant-ui-output',wrap));messages.scrollTop=messages.scrollHeight;
      const acceptUI=message=>{try{ui.accept(message);}catch{if(!q('.assistant-ui-error',wrap)){const error=document.createElement('div');error.className='assistant-ui-error';error.setAttribute('role','alert');error.textContent='结果界面暂时无法显示，请查看文字答复。';q('.assistant-ui-output',wrap).append(error);}}};
      let finalAnswer='';
      try{
        const result=await window.CeairAgentStream.chat(`${mount}/api/agent-chat/stream`,{
          signal:currentRequest.signal,
          headers:{'Content-Type':'application/json',Authorization:`Bearer ${session?.access_token||''}`,'X-Tenant-ID':String(requestTenantId||'')},
          payload:{message,conversation_id:conversationId,domain_id:'marketing-copilot',history:conversation.slice(-12)},
          onEvent:(event,value)=>{
            if(event==='trace'){process.add(value);if(value.event==='harness/model-started'){finalAnswer='';answer.textContent='';}const status=q('.assistant-streaming b',wrap);if(status)status.textContent=traceLabel[value.event]||'正在处理';}
            if(event==='a2ui')acceptUI(value);
            if(event==='conversation'&&value.conversation_id){conversationId=value.conversation_id;}
            if(event==='token'){finalAnswer+=value.text||'';answer.textContent=finalAnswer;messages.scrollTop=messages.scrollHeight;}
          }
        });
        finalAnswer=result.answer||finalAnswer;
        if(!finalAnswer)throw new Error('后台未返回答复，请重试。');
        answer.textContent=finalAnswer;conversationId=result.conversation_id||conversationId;
        workspace.formatAnswer(answer,finalAnswer);
        conversation.push({role:'user',content:message},{role:'assistant',content:finalAnswer});
        process.finish();setLive('就绪');
        if(result.a2ui?.length){try{ui.restore(result.a2ui);}catch{if(!q('.assistant-ui-error',wrap))q('.assistant-ui-output',wrap).insertAdjacentHTML('beforeend','<div class="assistant-ui-error" role="alert">结果界面暂时无法显示，请查看文字答复。</div>');}}
        else{if(result.widgets?.length) workspace.widgets(result.widgets, answer);if(result.tasks?.length) result.tasks.forEach(task=>workspace.task(task, answer));}
        if(result.sources?.length){
          const sourcesButton=document.createElement('button');sourcesButton.type='button';sourcesButton.className='btn assistant-sources';sourcesButton.textContent='业务依据（'+result.sources.length+'）';
          sourcesButton.onclick=()=>{const layer=document.createElement('div');layer.className='production-modal';layer.innerHTML='<div class="production-modal-card"><div class="production-modal-head"><b>业务依据</b><button class="btn" type="button" data-close>关闭</button></div><div class="production-modal-body">'+result.sources.map(source=>'<article class="assistant-source-item"><b>'+escapeHtml(source.title||source.id)+'</b><p>'+escapeHtml(source.excerpt||'')+'</p></article>').join('')+'</div></div>';document.body.append(layer);bindProductionModal(layer);};answer.after(sourcesButton);
        }
        if(activeTenant()?.id===requestTenantId){
          await workspace.refresh();
          try{await loadTenantData();}
          catch{answer.insertAdjacentHTML('afterend','<div class="assistant-sync-error" role="alert">答复已完成，业务列表刷新失败。<button type="button" class="btn" data-refresh-business>刷新列表</button></div>');q('[data-refresh-business]',wrap).onclick=async e=>{e.target.disabled=true;try{await loadTenantData();q('.assistant-sync-error',wrap)?.remove();}catch(cause){toast(cause.message);}finally{e.target.disabled=false;}};}
        }
      }catch(err){
        process.finish(true);
        answer.textContent=err.message||'智能体请求失败，请重试。';answer.setAttribute('role','alert');wrap.classList.add('has-error');setLive(err.code==='cancelled'?'就绪':'回复失败',err.code!=='cancelled');
        if(err.status!==401&&err.code!=='cancelled'){
          const retry=document.createElement('button');retry.type='button';retry.className='btn assistant-retry';retry.textContent='重试';retry.onclick=()=>send(message,wrap);answer.after(retry);
        }
        if(err.status===401)logout();
        else await workspace.refresh();
      }
      finally{streaming?.remove();answer.classList.remove('is-streaming');form.dataset.busy='';input.disabled=false;submitButton.disabled=false;stopButton.hidden=true;currentRequest=null;if(!panel.hidden)input.focus();messages.scrollTop=messages.scrollHeight;}
    };
    workspace=window.createAssistantWorkspace(panel,{request,escapeHtml,bindModal:bindProductionModal,toast,navigate:page=>window.activate?.(page),busy:()=>!!form.dataset.busy,focus:()=>input.focus(),conversationId:()=>conversationId,setConversation:(id,history)=>{conversationId=id;conversation.splice(0,conversation.length,...history);setLive('就绪');},refreshBusiness:loadTenantData});
    fab.addEventListener('click',()=>{if(suppressFabClick){suppressFabClick=false;return;}panel.hidden=!panel.hidden;if(!panel.hidden){restoreLayout();setCollapsed(false);input.focus();}});
    q('[data-assistant-history]',root).addEventListener('click',()=>workspace.show());
    q('[data-assistant-close]',root).addEventListener('click',()=>{panel.hidden=true;saveLayout();});
    collapseButton.addEventListener('click',()=>setCollapsed(!panel.classList.contains('is-collapsed')));
    qa('[data-assistant-suggest]',root).forEach(button=>button.addEventListener('click',()=>send(button.dataset.assistantSuggest)));
    submitButton.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();form.requestSubmit();});
    form.addEventListener('submit',event=>{event.preventDefault();const value=input.value.trim();if(!value)return;input.value='';input.style.height='auto';send(value);});
    input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();form.requestSubmit();}});
    input.addEventListener('input',()=>{input.style.height='auto';input.style.height=Math.min(input.scrollHeight,104)+'px';});
    makeDraggable(fab,fab,true);makeDraggable(header,panel,false);
    if(window.ResizeObserver)new ResizeObserver(()=>{if(!panel.hidden&&!panel.classList.contains('is-dragging'))saveLayout();}).observe(panel);
    window.addEventListener('resize',()=>{const panelRect=panel.getBoundingClientRect(),fabRect=fab.getBoundingClientRect();positionElement(panel,panelRect.left,panelRect.top);positionElement(fab,fabRect.left,fabRect.top);});
    restoreLayout();if(window.lucide)lucide.createIcons();
    const dockHost=q('#dongdongDock');
    const setDocked=view=>{
      const target=view==='smartspace'?q('#smartSpaceDock'):view==='dongdong'?dockHost:null;
      if(target){
        const placeholder=target.querySelector('.dongdong-chat-placeholder');if(placeholder)placeholder.remove();
        target.appendChild(panel);panel.classList.add('is-docked');panel.hidden=false;
        panel.classList.remove('is-collapsed');
        panel.classList.toggle('is-home-docked',view==='dongdong');
        input.placeholder=view==='smartspace'?'输入任务，或查询业务数据':(dongdongModes[q('.dongdong-tabs .active')?.dataset.dongdongMode]?.placeholder||'输入营销任务');
      }else{
        /* docked 分支会强制 hidden=false，离开首页时必须收回，否则面板盖住内页内容 */
        root.appendChild(panel);panel.classList.remove('is-docked','is-home-docked');panel.hidden=true;restoreLayout();
      }
    };
    window.dockDongdong=view=>setDocked(view);
    window.dongdongAsk=send;
    setDocked(q('#smartspace.active')?'smartspace':'dongdong');
  }

  function renderDongdongCapabilities(){
    const host=q('#dongdongCapabilityGrid');if(!host)return;
    const domains=tenantData.domains||[];
    const note=q('#dongdongCapabilityCount');
    if(note)note.textContent=domains.length?`${domains.length} 个智能域`:'智能域按租户启用';
    if(!domains.length){host.innerHTML='<div class="dongdong-cap-empty">'+(tenantDataReady?'当前租户尚未启用智能域，请先在模型配置中接入大模型服务':'正在加载智能域')+'</div>';return;}
    host.innerHTML=domains.map(item=>`<div class="dongdong-cap"><b>${escapeHtml(displayText(item.name,'智能域'))}</b></div>`).join('');
  }
  const dongdongModes={
    opportunity:{placeholder:'想发现什么机会？例如：三亚航线国庆前的预售窗口',chips:[
      {icon:'radar',label:'高价值机会清单',prompt:'当前有哪些高价值营销机会？按预期收入排序'},
      {icon:'trending-up',label:'航线搜索趋势',prompt:'对比京沪快线与沪蓉航线近两周的搜索与出票趋势'},
      {icon:'plane-takeoff',label:'中转辅营缺口',prompt:'哪些国际中转航段存在未开发的辅营机会？'}]},
    audience:{placeholder:'描述目标客群，东东会转成画像条件并评估规模',chips:[
      {icon:'users-round',label:'三亚高意向未购',prompt:'圈选三亚航线近14天搜索过但未出票的客群，并评估可触达规模'},
      {icon:'user-round-search',label:'相似人群扩展',prompt:'找出与家庭出游客群相似的扩展人群，并说明扩展依据'},
      {icon:'shield-check',label:'营销疲劳排查',prompt:'统计近30天被触达超过两次的客户，给出保护建议'}]},
    persona:{placeholder:'想了解哪类旅客？东东按画像维度解释口径与规模',chips:[
      {icon:'users-round',label:'画像维度总览',prompt:'当前同步了哪些旅客画像维度？分别说明口径和数据来源'},
      {icon:'badge-check',label:'会员等级分布',prompt:'按会员等级统计旅客规模与近30天出行频次分布'},
      {icon:'route',label:'航线偏好画像',prompt:'分析常飞京沪快线的商务旅客画像特征与辅营偏好'}]},
    content:{placeholder:'说明活动与渠道，东东按产品事实生成可审核内容',chips:[
      {icon:'file-pen-line',label:'双渠道内容',prompt:'为上海—三亚国庆早鸟活动生成 App 与短信两版内容'},
      {icon:'message-square-text',label:'公众号改写',prompt:'把已通过审核的短信文案改写成微信公众号版本'},
      {icon:'badge-check',label:'事实与敏感词',prompt:'检查现有内容里的敏感词与产品事实偏差'}]}
  };

  function renderDongdongChips(mode){
    const host=q('#dongdongQuick');if(!host)return;
    const config=dongdongModes[mode]||dongdongModes.opportunity;
    host.innerHTML=config.chips.map(chip=>`<button class="dongdong-chip" type="button" data-dongdong-ask="${escapeHtml(chip.prompt)}"><i data-lucide="${chip.icon}"></i>${escapeHtml(chip.label)}</button>`).join('');
    const input=q('#dongdongDock textarea[name=message]');if(input)input.placeholder=config.placeholder;
    if(window.lucide)lucide.createIcons();
  }
  let dongdongChipsBound=false;
  function bindDongdongChips(){
    if(dongdongChipsBound)return;dongdongChipsBound=true;
    q('#dongdongQuick')?.addEventListener('click',event=>{
      const button=event.target.closest('[data-dongdong-ask]');if(!button)return;
      activate('dongdong');
      if(window.dongdongAsk)window.dongdongAsk(button.dataset.dongdongAsk);
      else toast('东东正在准备，请稍候再试');
    });
    qa('.dongdong-tabs button[data-dongdong-mode]').forEach(tab=>tab.addEventListener('click',()=>{
      qa('.dongdong-tabs button[data-dongdong-mode]').forEach(item=>{item.classList.toggle('active',item===tab);item.setAttribute('aria-selected',String(item===tab));});
      renderDongdongChips(tab.dataset.dongdongMode);
    }));
  }
  function mountDongdongHero(){
    qa('.dongdong-band[data-hero-src]').forEach(band=>{
      if(band.dataset.heroState)return;band.dataset.heroState='loading';
      const source=band.dataset.heroSrc;
      if(!source){band.dataset.heroState='empty';return;}
      const loader=new Image();
      loader.onload=()=>{document.body.style.setProperty('--dd-hero',`url("${source}")`);document.body.classList.add('dongdong-hero-ready');band.dataset.heroState='loaded';};
      loader.onerror=()=>{band.dataset.heroState='failed';};
      loader.src=source;
    });
  }

  function downloadBusinessJson(name,payload){
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json;charset=utf-8'}));
    const link=document.createElement('a');link.href=url;link.download=name+'-'+new Date().toISOString().slice(0,10)+'.json';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function showNotifications(){
    const pending=(tenantData.approvals||[]).filter(approvalIsPending);
    const failed=(tenantData.runs||[]).filter(item=>item.status==='failed');
    const layer=document.createElement('div');layer.className='production-modal';
    layer.innerHTML='<div class="production-modal-card"><div class="production-modal-head"><b>工作区通知</b><button class="icon-btn" data-close title="关闭"><i data-lucide="x"></i></button></div><div class="production-modal-body"><p>待审批 '+pending.length+' 项 · 智能域失败 '+failed.length+' 项</p>'+pending.map(item=>'<p>'+escapeHtml(item.external_id)+' · '+escapeHtml(item.status)+'</p>').join('')+failed.map(item=>'<p>'+escapeHtml(item.summary)+'</p>').join('')+(!pending.length&&!failed.length?'<div class="empty-action">当前无待处理通知</div>':'')+'</div></div>';
    document.body.appendChild(layer);bindProductionModal(layer);if(window.lucide)lucide.createIcons();
  }
  function renderPermissions(){
    const view=q('#permissions');if(!view)return;
    const description=q('.page-head p',view);if(description)description.textContent='当前账号授权、租户数据范围与业务处理记录';
    q('[data-action="addRole"]',view).hidden=true;
    const role=activeTenant()?.role;
    const rules=[['查看业务数据',true],['创建与编辑业务对象',canWrite()],['审批与渠道联调',canWrite()],['同步数据与配置模型',isTenantAdmin()],['管理平台租户与用户',Boolean(session.is_platform_admin)]];
    const records=[
      ...(tenantData.approvals||[]).map(item=>({time:item.decided_at||item.updated_at,label:'审批 '+item.external_id,status:item.status})),
      ...(tenantData.imports||[]).map(item=>({time:item.completed_at||item.created_at,label:'导入 '+item.file_name,status:item.status})),
      ...(tenantData.runs||[]).map(item=>({time:item.created_at,label:(domainLabels[item.domain_id]||item.domain_id)+' '+item.id,status:item.status}))
    ].sort((a,b)=>new Date(b.time)-new Date(a.time)).slice(0,20);
    q('.permission-layout',view).innerHTML='<div class="panel" data-subview-panel="roles"><div class="panel-head"><h2>当前账号授权</h2></div><div class="panel-body"><p>'+escapeHtml(session.display_name)+' · '+escapeHtml(activeTenant().name)+' · '+escapeHtml(roleLabels[role]||role)+'</p><table class="table"><tr><th>操作范围</th><th>权限</th></tr>'+rules.map(([name,allowed])=>'<tr><td>'+name+'</td><td>'+ (allowed?'允许':'只读 / 无权限')+'</td></tr>').join('')+'</table><p>当前工作区仅展示聚合画像；账号角色由“租户与用户”维护。</p></div></div><div class="panel" data-subview-panel="audit"><div class="panel-head"><h2>业务处理记录</h2><span>当前租户 · 最近20条</span></div><div class="panel-body"><table class="table"><tr><th>对象与操作</th><th>状态</th><th>时间</th></tr>'+records.map(item=>'<tr><td>'+escapeHtml(item.label)+'</td><td>'+escapeHtml(item.status)+'</td><td>'+escapeHtml(item.time?businessTime(item.time):'待处理')+'</td></tr>').join('')+'</table></div></div>';
  }
  function applyWorkbenchFilters(){
    ['opportunities','audiences','products','contents','campaigns'].forEach(viewId=>{
      const view=q('#'+viewId),toolbar=q(':scope > .toolbar-strip',view);if(!toolbar)return;
      const query=(q('input',toolbar)?.value||'').trim().toLowerCase();
      const selects=qa('select',toolbar),status=selects[1]?.value||'';
      const type=selects[0]?.hidden?'':selects[0]?.value||'';
      const filterType=type&&!type.startsWith('全部');
      const filterStatus=!status.startsWith('全部')&&status!=='当前版本';
      qa('table tr',view).forEach(row=>{
        if(!q('td',row))return;
        const text=row.textContent.toLowerCase();
        const matchesStatus=!filterStatus||(q('.status',row)?.textContent||'').includes(status);
        row.hidden=Boolean((query&&!text.includes(query))||!matchesStatus||(filterType&&!text.includes(type.toLowerCase())));
      });
      if(viewId==='products')qa('.catalog-card',view).forEach(card=>card.hidden=Boolean(query&&!card.textContent.toLowerCase().includes(query)));
      let hint=q('[data-filter-count]',toolbar);if(!hint){hint=document.createElement('span');hint.dataset.filterCount='true';hint.className='toolbar-note';toolbar.appendChild(hint);}
      hint.textContent=query||filterStatus||filterType?qa('table tr',view).filter(row=>q('td',row)&&!row.hidden).length+' 条匹配':'';
    });
  }
  function bindWorkbenchControls(){
    q('.crumb-home')?.addEventListener('click',event=>{event.preventDefault();activate('dongdong');});
    q('#execution .toolbar-strip')?.addEventListener('change',event=>{
      const selects=qa('#execution .toolbar-strip select');
      if(event.target===selects[0]){selectedExecutionCampaignId=event.target.value;selectedExecutionBatchId='';selectedExecutionChannel='';}
      if(event.target===selects[1])selectedExecutionChannel=event.target.value;
      if(event.target===selects[2])selectedExecutionBatchId=event.target.value;
      renderExecution();if(window.lucide)lucide.createIcons();
    });
    q('#feedback .toolbar-strip')?.addEventListener('change',async event=>{
      if(event.target!==q('#feedback .toolbar-strip select'))return;
      selectedEffectCampaignId=event.target.value;tenantData.effectSummary={};
      try{await loadEffectSummary();renderFeedback();}catch(cause){renderFeedback();toast(cause.message||'复盘加载失败');}
    });
    ['opportunities','audiences','products','contents','campaigns'].forEach(viewId=>{
      const toolbar=q('#'+viewId+' > .toolbar-strip');if(!toolbar)return;
      q('input',toolbar)?.addEventListener('input',applyWorkbenchFilters);
      toolbar.addEventListener('change',applyWorkbenchFilters);
      const selects=qa('select',toolbar);
      if(['opportunities','audiences'].includes(viewId)&&selects[0])selects[0].hidden=true;
      if(viewId==='campaigns'&&selects[1])selects[1].hidden=true;
      q('.toolbar-note',toolbar)?.remove();
      q('.btn',toolbar)?.addEventListener('click',applyWorkbenchFilters);
    });
    q('#execution .toolbar-strip .btn')?.addEventListener('click',async()=>{await loadTenantData();});
    q('#feedback .toolbar-strip .btn')?.addEventListener('click',async()=>{try{await loadEffectSummary();renderFeedback();}catch(cause){toast(cause.message);}});
  }
  async function loadEffectSummary(){
    const campaign=tenantData.campaigns.find(item=>item.id===selectedEffectCampaignId)
      ||tenantData.campaigns.find(item=>tenantData.executionBatches.some(batch=>batch.campaign_id===item.id))
      ||tenantData.campaigns[0];
    selectedEffectCampaignId=campaign?.id||'';
    const requestId=++effectRequestId;
    const summary=campaign?await request(`/api/campaigns/${encodeURIComponent(campaign.id)}/effect-summary`):{};
    if(requestId===effectRequestId)tenantData.effectSummary=summary;
  }
  async function loadTenantData(){
    updateIdentity();
    const paths=['/api/campaigns','/api/graph','/api/imports','/api/data-pipelines','/api/model-providers','/api/agent-domains','/api/agent-runs','/api/opportunities','/api/opportunity-insight/sources','/api/opportunity-insight/runs','/api/audience-tags','/api/audience-packages','/api/persona-dimensions','/api/persona-segments','/api/product-packages','/api/product-catalog','/api/content-assets','/api/audience-snapshots','/api/approvals','/api/execution-batches','/api/channel-tasks','/api/knowledge/documents'];
    paths.push('/api/competition/demo');
    const [campaigns,graph,imports,pipelines,providers,domains,runs,opportunities,opportunitySources,opportunityRuns,audienceTags,audiencePackages,personaDimensions,personaSegments,productPackages,productCatalog,contentAssets,audienceSnapshots,approvals,executionBatches,channelTasks,documents,demo]=await Promise.all(paths.map(path=>request(path)));
    let mineru=null;
    if(isTenantAdmin()){try{mineru=await request('/api/integrations/mineru');}catch{mineru=null;}}
    tenantData={campaigns,graph,imports,pipelines,providers,domains,runs,opportunities,opportunitySources,opportunityRuns,audienceTags,audiencePackages,personaDimensions,personaSegments,productPackages,productCatalog,contentAssets,audienceSnapshots,approvals,executionBatches,channelTasks,documents,effectSummary:{},mineru,demo};
    tenantDataReady=true;
    await loadEffectSummary();
    renderOpportunities();renderOpportunityInsightPanel();renderAudienceStructure();renderKnowledgeDocuments();renderCampaigns();renderDashboard();renderDongdongCapabilities();renderProducts();renderContents();renderApprovals();renderExecution();renderFeedback();renderDynamicGraph();renderPipelineQueue();renderImports();renderModels();renderMineru();renderPermissions();applyBusinessSubviewLayouts();applyWorkbenchFilters();
    window.ceairCompetition?.render({demo,data:tenantData,request,showRun:showAgentTrace,runDomain:showDomainRequest});
    if (q('#demoOntologyChain')) q('#demoOntologyChain').hidden=!demo.enabled || (businessSubviewState.get('graph')||'schema')!=='instances';
    const hasActive=pipelines.some(item=>['queued','running'].includes(item.status));
    clearTimeout(pipelinePollTimer);if(hasActive)pipelinePollTimer=setTimeout(()=>refreshPipelines().catch(()=>{}),1500);
    const hasInsight=opportunityRuns.some(item=>['queued','running'].includes(item.status));
    clearTimeout(opportunityPollTimer);if(hasInsight)opportunityPollTimer=setTimeout(()=>loadTenantData().catch(()=>{}),1500);
  }

  /* ── 向导提交载荷 ──────────────────────────────────────────────────────
     第 2/3 步是静态卡片，没有可绑定的表单字段，因此这里按卡片标题回查后端对象。
     回查不到就明确留空，并把缺少的部分回传给提示，不再默认取列表第一项冒充已绑定。 */
  const wizardSqueeze = value => String(value || '').replace(/\s+/g, '');
  function wizardSelectedTitles(rootSelector) {
    return qa(rootSelector).map(el => (el.querySelector('b')?.textContent || '').trim()).filter(Boolean);
  }
  function wizardMatch(items, titles) {
    return (items || []).find(item => {
      const name = wizardSqueeze(item.name);
      if (!name) return false;
      return titles.some(title => { const value = wizardSqueeze(title); return value.includes(name) || name.includes(value); });
    }) || null;
  }
  function wizardChannels() {
    const channels = qa('#campaignModal input[type=\"checkbox\"]:checked')
      .map(input => input.closest('label')?.querySelector('span')?.textContent?.trim()).filter(Boolean);
    return channels.length ? channels : ['App'];
  }
  function collectCampaignBindings() {
    const titles = wizardSelectedTitles('#campaignModal .selection-box.selected');
    const packages = tenantData.audiencePackages || [];
    const snapshots = tenantData.audienceSnapshots || [];
    const audiencePackage = wizardMatch(packages, titles);
    const product = wizardMatch(tenantData.productPackages || [], titles);
    const snapshot = audiencePackage
      ? (snapshots.filter(item => item.package_id === audiencePackage.id).sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))[0] || null)
      : null;
    const contentTitles = wizardSelectedTitles('#campaignModal .content-option.selected');
    const contentIds = (tenantData.contentAssets || []).filter(item => wizardSqueeze(item.name) && contentTitles.some(title => {
      const value = wizardSqueeze(title); const name = wizardSqueeze(item.name);
      return value.includes(name) || name.includes(value);
    })).map(item => item.id);
    const missing = [];
    if (!snapshot) missing.push('客群快照');
    if (!product) missing.push('产品包');
    if (!contentIds.length) missing.push('内容资产');
    return {
      snapshot,
      product,
      contentIds,
      missing,
      audienceSize: snapshot?.estimated_size || 0,
      budget: Number(document.querySelector('#campaignBudget')?.value || 0) || 0,
      roiTarget: Number(document.querySelector('#campaignRoi')?.value || 0) || 0,
    };
  }
  function campaignPayload(name) {
    const binding = collectCampaignBindings();
    return {
      payload: {
        name,
        stage: '创建',
        audience_snapshot_id: binding.snapshot?.id || null,
        product_package_id: binding.product?.id || null,
        audience_size: binding.audienceSize,
        product_package: binding.product?.name || '',
        budget_yuan: binding.budget,
        roi_target: binding.roiTarget,
        channels: wizardChannels(),
        content_asset_ids: binding.contentIds,
      },
      binding,
    };
  }
  window.saveProductionCampaignDraft = async function(name) {
    const { payload, binding } = campaignPayload(name);
    const campaign = await request('/api/campaigns', {method:'POST', body: JSON.stringify(payload)});
    await loadTenantData();
    return Object.assign({}, campaign, { missingBindings: binding.missing });
  };
  window.createProductionCampaign = async function(name) {
    const { payload, binding } = campaignPayload(name);
    const campaign = await request('/api/campaigns', {method:'POST', body: JSON.stringify(payload)});
    const versions = await request(`/api/campaigns/${encodeURIComponent(campaign.id)}/versions`);
    const version = versions[0];
    if (version) await request(`/api/campaigns/${encodeURIComponent(campaign.id)}/versions/${version.id}/approval`, {method:'POST'});
    await loadTenantData();
    return Object.assign({}, campaign, { missingBindings: binding.missing });
  };
  /* ── 全域检索 ────────────────────────────────────────────────────────────
     只接 /api/knowledge/search 会让本页在知识文档为空的库上永久空白，
     因此同时索引已在内存里的业务对象；知识片段一旦有数据就自动多出一类结果。 */
  const searchSources = {
    knowledge:   { label: '知识片段', view: 'graph' },
    document:    { label: '知识文档', view: 'graph' },
    dimension:   { label: '画像字段', view: 'audiences' },
    campaign:    { label: '营销活动', view: 'campaigns' },
    opportunity: { label: '机会', view: 'opportunities' },
    audience:    { label: '客群包', view: 'audiences' },
    product:     { label: '产品包', view: 'products' },
    content:     { label: '内容资产', view: 'contents' },
    domain:      { label: '智能域', view: 'dongdong' },
    provider:    { label: '模型服务', view: 'models' }
  };
  const searchState = { query: '', type: '', knowledge: [], knowledgeFor: '' };

  const searchTag = (...values) => values.flat().map(value => String(value ?? '').replace(/^[一二三四五六七八九十]+\s*[、.．]\s*/, '').trim()).filter(Boolean);

  function searchPush(rows, type, title, snippet, tags, jump, rid, linkedObjects) {
    const name = String(title ?? '').trim();
    if (!name) return;
    rows.push({ type, title: name, snippet: String(snippet ?? '').trim(), tags: searchTag(tags), jump: String(jump ?? ''), rid: rid ?? '', linkedObjects: linkedObjects || [] });
  }

  function buildSearchCorpus() {
    const rows = [];
    (tenantData.documents || []).forEach(item => searchPush(rows, 'document', item.title, searchTag(item.source_name, item.classification).join(' · '), [item.source_type, item.status, `${item.chunk_count || 0} 个片段`, `${item.entity_count || 0} 个实体`], item.id, item.id));
    (tenantData.personaDimensions || []).forEach(item => searchPush(rows, 'dimension', item.field_name, searchTag(item.field_code, item.applicable_personas).join(' · '), [item.module_name, item.data_type, item.update_frequency, item.required_mode], item.module_key, item.id));
    (tenantData.campaigns || []).forEach(item => searchPush(rows, 'campaign', item.name, `编号 ${item.id} · 负责人 ${item.owner || '未指定'}`, [item.stage, item.status, item.product_package, item.version], item.id, item.id));
    (tenantData.opportunities || []).forEach(item => searchPush(rows, 'opportunity', item.name, searchTag(item.route, item.signal_summary).join(' · '), [item.market_scope, item.status, item.score ? `评分 ${item.score}` : '', item.owner], item.id, item.id));
    (tenantData.audiencePackages || []).forEach(item => searchPush(rows, 'audience', item.name, `圈选方式：${item.selection_mode === 'ai-selection' ? 'AI 圈选' : '标签组合'}`, [item.status, `${item.estimated_size || 0} 人`], item.id, item.id));
    (tenantData.productPackages || []).forEach(item => searchPush(rows, 'product', item.name, item.description, [item.product_type, item.status, item.version], item.id, item.id));
    (tenantData.contentAssets || []).forEach(item => searchPush(rows, 'content', item.title || item.name, item.body, [item.channel, item.status, item.version, item.campaign_id], item.id, item.id));
    (tenantData.domains || []).forEach(item => searchPush(rows, 'domain', item.name, item.responsibility, [item.module, item.status], '', item.id));
    (tenantData.providers || []).forEach(item => searchPush(rows, 'provider', item.display_name || item.model_name, item.base_url ? `端点 ${item.base_url}` : '', [item.provider_type, item.model_name, item.is_default ? '默认' : '', item.enabled ? '已启用' : '已停用'], item.id, item.id));
    ((tenantData.productCatalog && tenantData.productCatalog.products) || []).forEach(item => searchPush(rows, 'product', item.name || item.title, item.description, [item.category, item.code], '', item.code || item.id));
    return rows;
  }

  /* 关联业务对象：走各记录上真实存在的外键与本体边，不凭空拼关系 */
  const searchLinkKey = (type, id) => (id == null || id === '' ? '' : `${type}|${id}`);

  function buildSearchNodes() {
    const nodes = new Map();
    const put = (type, id, label, view) => { const key = searchLinkKey(type, id); if (key && label) nodes.set(key, { type, label: String(label), view }); };
    (tenantData.campaigns || []).forEach(item => put('campaign', item.id, item.name, 'campaigns'));
    (tenantData.opportunities || []).forEach(item => put('opportunity', item.id, item.name, 'opportunities'));
    (tenantData.audiencePackages || []).forEach(item => put('audience', item.id, item.name, 'audiences'));
    (tenantData.productPackages || []).forEach(item => put('product', item.id, item.name, 'products'));
    (tenantData.contentAssets || []).forEach(item => put('content', item.id, item.title || item.name, 'contents'));
    (tenantData.executionBatches || []).forEach(item => put('batch', item.id, `执行批次 ${item.external_id || item.id}`, 'execution'));
    (tenantData.channelTasks || []).forEach(item => put('channel', item.id, `${item.channel} 渠道任务 · ${item.status || ''}`.trim(), 'execution'));
    (tenantData.approvals || []).forEach(item => put('approval', item.id, `${item.approver_role || '审批'} · ${item.status || ''}`.trim(), 'approvals'));
    (tenantData.audienceSnapshots || []).forEach(item => put('snapshot', item.id, `客群快照 ${item.version || item.id}`, 'audiences'));
    (tenantData.audienceTags || []).forEach(item => put('tag', item.id, item.name || item.code, 'audiences'));
    (tenantData.documents || []).forEach(item => put('document', item.id, item.title, 'graph'));
    ((tenantData.graph && tenantData.graph.nodes) || []).forEach(item => put('onto', item.id, `${item.label}${item.type ? ` · ${item.type}` : ''}`, 'graph'));
    return nodes;
  }

  function buildSearchRelationPairs() {
    const pairs = [];
    const push = (a, b, rel) => { if (a && b) pairs.push([a, b, rel]); };
    (tenantData.contentAssets || []).forEach(item => {
      push(searchLinkKey('content', item.id), searchLinkKey('campaign', item.campaign_id), '产出内容');
      push(searchLinkKey('content', item.id), searchLinkKey('audience', item.audience_package_id), '面向客群包');
      push(searchLinkKey('content', item.id), searchLinkKey('product', item.product_package_id), '绑定产品包');
    });
    (tenantData.executionBatches || []).forEach(item => push(searchLinkKey('batch', item.id), searchLinkKey('campaign', item.campaign_id), '执行批次'));
    (tenantData.channelTasks || []).forEach(item => push(searchLinkKey('channel', item.id), searchLinkKey('campaign', item.campaign_id), '渠道任务'));
    (tenantData.approvals || []).forEach(item => push(searchLinkKey('approval', item.id), searchLinkKey('campaign', item.campaign_id), '审批任务'));
    (tenantData.audienceSnapshots || []).forEach(item => {
      push(searchLinkKey('snapshot', item.id), searchLinkKey('audience', item.package_id), '客群快照');
      (item.tag_ids || []).forEach(tagId => push(searchLinkKey('snapshot', item.id), searchLinkKey('tag', tagId), '使用标签'));
    });
    ((tenantData.graph && tenantData.graph.edges) || []).forEach(edge => {
      if (edge.source && edge.target) push(searchLinkKey('onto', edge.source), searchLinkKey('onto', edge.target), edge.relation || '关联');
    });
    return pairs;
  }

  function searchRelationsFor(row, nodes, pairs) {
    const key = searchLinkKey(row.type, row.rid);
    const out = [];
    const add = (rel, label, view) => {
      const name = String(label || '').trim();
      if (!name) return;
      if (name === row.title) return;
      if (out.some(item => item.label === name && item.rel === rel)) return;
      out.push({ rel, label: name, view: view || '' });
    };
    if (key) pairs.forEach(([a, b, rel]) => {
      if (a !== key && b !== key) return;
      const node = nodes.get(a === key ? b : a);
      if (node) add(rel, node.label, node.view);
    });
    (row.linkedObjects || []).forEach(obj => {
      if (!obj || typeof obj !== 'object') return;
      add(obj.relation || obj.type || '关联', obj.name || obj.label || obj.title || obj.id, 'graph');
    });
    return out.slice(0, 8);
  }

  function scoreSearchRow(row, query) {
    if (!query) return 0;
    const needle = query.toLowerCase();
    const title = row.title.toLowerCase();
    if (title === needle) return 100;
    if (title.startsWith(needle)) return 80;
    if (title.includes(needle)) return 60;
    if (row.tags.some(tag => tag.toLowerCase().includes(needle))) return 30;
    if (row.snippet.toLowerCase().includes(needle)) return 20;
    return 0;
  }

  function searchRowFromKnowledge(item) {
    const content = String(item.content || '').replace(/\s+/g, ' ').trim();
    return {
      type: 'knowledge',
      title: String(item.title || '未命名知识片段').trim(),
      snippet: content.length > 240 ? `${content.slice(0, 240)}…` : content,
      tags: searchTag(item.document_id && `文档 ${item.document_id}`, item.metadata && item.metadata.module, item.linked_objects && item.linked_objects.length && `关联 ${item.linked_objects.length} 个对象`),
      jump: String(item.document_id || '')
    };
  }

  async function fetchSearchKnowledge(query) {
    if (searchState.knowledgeFor === query) return searchState.knowledge;
    searchState.knowledgeFor = query;
    try {
      const rows = await request(`/api/knowledge/search?q=${encodeURIComponent(query)}&limit=30`);
      searchState.knowledge = Array.isArray(rows) ? rows.map(searchRowFromKnowledge) : [];
    } catch (cause) {
      console.error('知识片段检索失败', cause);
      searchState.knowledge = [];
    }
    return searchState.knowledge;
  }

  function highlightSearch(text, query) {
    const safe = escapeHtml(text);
    const needle = query ? escapeHtml(query) : '';
    if (!needle) return safe;
    const at = safe.toLowerCase().indexOf(needle.toLowerCase());
    if (at < 0) return safe;
    return `${safe.slice(0, at)}<mark>${safe.slice(at, at + needle.length)}</mark>${safe.slice(at + needle.length)}`;
  }

  /* 建议词要能真的搜到东西：取画像字段的一级模块名与智能域名，
     而不是标签词频——词频会吐出 enum / 月度 这种数据类型黑话和带序号的脏名。 */
  function searchHotTerms(corpus) {
    const terms = [];
    const add = value => {
      const term = String(value || '').replace(/^[一二三四五六七八九十]+\s*[、.．]\s*/, '').trim();
      if (term.length >= 2 && term.length <= 10 && !terms.includes(term)) terms.push(term);
    };
    (tenantData.personaDimensions || []).forEach(item => add(item.module_name));
    (tenantData.domains || []).forEach(item => add(item.name));
    (tenantData.campaigns || []).forEach(item => add(item.name));
    if (terms.length < 6) corpus.forEach(row => { if (terms.length < 6 && ['机会', '客群包', '活动产品包', '内容资产'].includes(searchSources[row.type]?.label)) add(row.title); });
    return terms.slice(0, 6);
  }

  function renderSearchSuggest(corpus, query) {
    const host = q('#searchSuggest'); if (!host) return;
    const terms = searchHotTerms(corpus);
    host.innerHTML = terms.length ? `<span class="search-suggest-label">热门检索</span>${terms.map(term => `<button type="button" class="search-pill${term === query ? ' is-active' : ''}" data-search-term="${escapeHtml(term)}">${escapeHtml(term)}</button>`).join('')}` : '';
  }

  function renderSearchFacets(pool, corpus, query) {
    const host = q('#searchFacets'); if (!host) return;
    /* 无查询时"结果范围"和"已接入索引"是同一批数字，只留一个 */
    if (!query) {
      const coverage = new Map();
      corpus.forEach(row => coverage.set(row.type, (coverage.get(row.type) || 0) + 1));
      const order = Object.keys(searchSources).filter(type => coverage.get(type));
      host.innerHTML = `<div class="v-rail__group"><p class="v-rail__title">已接入索引</p>${order.map(type => `<div class="search-coverage"><span>${escapeHtml(searchSources[type].label)}</span><b>${coverage.get(type)}</b></div>`).join('')}<p class="v-rail__note">共 ${corpus.length} 条业务对象，知识片段检索在输入后并入结果。</p></div>`;
      return;
    }
    const counts = new Map();
    pool.forEach(row => counts.set(row.type, (counts.get(row.type) || 0) + 1));
    const order = Object.keys(searchSources).filter(type => counts.get(type));
    host.innerHTML = `<div class="v-rail__group"><p class="v-rail__title">结果范围</p><button type="button" class="v-facet${searchState.type === '' ? ' is-active' : ''}" data-search-type=""><span>全部</span><b>${pool.length}</b></button>${order.map(type => `<button type="button" class="v-facet${searchState.type === type ? ' is-active' : ''}" data-search-type="${type}"><span>${escapeHtml(searchSources[type].label)}</span><b>${counts.get(type)}</b></button>`).join('')}</div>`;
  }

  function searchCardHTML(row, query, nodes, pairs, compact) {
    const source = searchSources[row.type] || { label: row.type, view: '' };
    const relations = searchRelationsFor(row, nodes, pairs);
    const target = source.label === '知识片段' || source.label === '知识文档' ? '知识中心' : source.label;
    return `<article class="search-card${compact ? ' is-compact' : ''}">
      <div class="search-card-head"><span class="search-card-type">${escapeHtml(source.label)}</span><h3>${highlightSearch(row.title, query)}</h3></div>
      ${row.snippet ? `<p class="search-card-snippet">${highlightSearch(row.snippet, query)}</p>` : ''}
      ${row.tags.length ? `<div class="search-card-tags">${row.tags.map(tag => `<span class="v-chip">${escapeHtml(tag)}</span>`).join('')}</div>` : ''}
      ${relations.length ? `<div class="search-card-relations"><p class="search-card-relations-title">关联业务对象</p>${relations.map(rel => `<button type="button" class="search-relation"${rel.view ? ` data-search-jump="${rel.view}"` : ' disabled'}><span>${escapeHtml(rel.rel)}</span><b>${escapeHtml(rel.label)}</b></button>`).join('')}</div>` : ''}
      ${source.view ? `<button type="button" class="search-card-jump" data-search-jump="${source.view}">前往${escapeHtml(target)}<i data-lucide="arrow-right"></i></button>` : ''}
    </article>`;
  }

  function renderSearchList(rows, query, nodes, pairs) {
    const host = q('#searchResults'); if (!host) return;
    if (!query) {
      host.innerHTML = '<div class="empty-state"><i data-lucide="scan-search"></i><b>先告诉我要找什么</b><span>可检索文档标题与正文片段，或活动、客群、画像字段的名称与编号</span></div>';
      return;
    }
    if (!rows.length) {
      host.innerHTML = `<div class="empty-state"><i data-lucide="search-x"></i><b>没有命中「${escapeHtml(query)}」</b><span>换个说法，或试试上方热门检索词</span></div>`;
      return;
    }
    host.innerHTML = `<div class="search-cards">${rows.slice(0, 40).map(row => searchCardHTML(row, query, nodes, pairs, false)).join('')}</div>`;
  }

  function renderSearchHint(query, merged, corpus) {
    const hint = q('#searchResultHint'); if (!hint) return;
    if (!query) { hint.textContent = `索引 ${corpus.length} 条业务对象`; return; }
    if (searchState.knowledgeFor !== query) { hint.textContent = `检索「${query}」中…`; return; }
    hint.textContent = merged.length ? `${merged.length} 条命中 · 关键词「${query}」` : `「${query}」暂无命中`;
  }

  function renderSearch() {
    const view = q('#search'); if (!view) return;
    const query = searchState.query;
    const corpus = buildSearchCorpus();
    const nodes = buildSearchNodes();
    const pairs = buildSearchRelationPairs();
    const local = query ? corpus.map(row => ({ ...row, score: scoreSearchRow(row, query) })).filter(row => row.score > 0) : [];
    const knowledge = query ? searchState.knowledge.map(row => ({ ...row, score: scoreSearchRow(row, query) || 45 })) : [];
    const merged = [...knowledge, ...local].sort((a, b) => b.score - a.score || a.title.localeCompare(b.title, 'zh-CN'));
    const pool = query ? merged : corpus;
    const visible = searchState.type ? pool.filter(row => row.type === searchState.type) : pool;
    renderSearchSuggest(corpus, query);
    renderSearchFacets(pool, corpus, query);
    renderSearchList(visible, query, nodes, pairs);
    renderSearchHint(query, merged, corpus);
    if (window.lucide) lucide.createIcons();
  }

  async function runSearch(rawQuery) {
    const query = String(rawQuery || '').trim();
    searchState.query = query;
    searchState.type = '';
    searchState.knowledge = [];
    searchState.knowledgeFor = '';
    renderSearch();
    if (!query) return;
    await fetchSearchKnowledge(query);
    if (searchState.query === query) renderSearch();
  }

  function mountSearchModule() {
    const view = q('#search'); if (!view || view.dataset.searchMounted === 'true') return;
    view.dataset.searchMounted = 'true';
    const input = q('#searchInput', view);
    q('#searchForm', view).addEventListener('submit', event => { event.preventDefault(); runSearch(input.value); });
    input.addEventListener('input', () => { if (!input.value.trim() && searchState.query) runSearch(''); });
    q('#searchSuggest', view).addEventListener('click', event => {
      const chip = event.target.closest('[data-search-term]'); if (!chip) return;
      input.value = chip.dataset.searchTerm; runSearch(chip.dataset.searchTerm);
    });
    q('#searchFacets', view).addEventListener('click', event => {
      const button = event.target.closest('[data-search-type]'); if (!button) return;
      const next = button.dataset.searchType;
      searchState.type = searchState.type === next ? '' : next;
      renderSearch();
    });
    q('#searchResults', view).addEventListener('click', event => {
      const jump = event.target.closest('[data-search-jump]'); if (!jump) return;
      if (typeof activate === 'function') activate(jump.dataset.searchJump);
    });
    /* 顶栏搜索框是纯展示 div，改成 button 会挪 topbar 高度、进而挪 --dd-head-h 撕开首页 hero，
       所以只加行为与语义，不动盒模型。
       首页点击进独立检索页；其余页面点击弹出全局业务对象检索浮层。 */
    const globalSearch = q('.global-search');
    if (globalSearch && globalSearch.dataset.searchBound !== 'true') {
      globalSearch.dataset.searchBound = 'true';
      globalSearch.setAttribute('role', 'button');
      globalSearch.setAttribute('tabindex', '0');
      globalSearch.title = '全局业务对象检索';
      const open = () => {
        if (document.body.classList.contains('dongdong-mode')) { openGlobalSearch(); return; }
        openGlobalSearch();
      };
      globalSearch.addEventListener('click', open);
      globalSearch.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); } });
    }
    renderSearch();
  }

  /* ── 全局业务对象检索浮层 ──────────────────────────────────────────────
     原先 v31/v32 的这个入口返回写死的假结果，这里保留交互、接到真实索引上。 */
  const overlayState = { query: '', knowledgeFor: '', knowledge: '', knowledgeRows: [], timer: null, lastFocus: null };

  function ensureGlobalSearchOverlay() {
    let host = q('#globalSearchOverlay');
    if (host) return host;
    host = document.createElement('div');
    host.id = 'globalSearchOverlay';
    host.className = 'gs-overlay';
    host.setAttribute('role', 'dialog');
    host.setAttribute('aria-modal', 'true');
    host.setAttribute('aria-label', '全局业务对象检索');
    host.hidden = true;
    host.innerHTML = `<div class="gs-backdrop" data-gs-close></div><div class="gs-panel"><p class="gs-title">全局业务对象检索</p><div class="gs-head"><i data-lucide="search" class="gs-head-icon" aria-hidden="true"></i><input id="gsInput" type="search" placeholder="检索机会、客群、产品包、活动、内容与知识片段" aria-label="全局检索关键词" autocomplete="off"><button type="button" class="gs-close" data-gs-close aria-label="关闭全局检索"><i data-lucide="x"></i></button></div><div class="gs-suggest" id="gsSuggest"></div><div class="gs-results" id="gsResults"></div><div class="gs-foot"><span id="gsHint"></span><button type="button" class="gs-more" data-gs-more>在检索页查看全部结果<i data-lucide="arrow-right"></i></button></div></div>`;
    const intro = document.createElement('div');
    intro.className = 'gs-workbench-intro';
    intro.hidden = true;
    intro.innerHTML = '<div class="gs-eyebrow"><span></span>业务搜索</div><h2>全局业务对象检索</h2>';
    q('.gs-panel', host).prepend(intro);
    document.body.appendChild(host);

    const input = q('#gsInput', host);
    input.addEventListener('input', () => {
      overlayState.query = input.value.trim();
      renderGlobalSearchOverlay();
      clearTimeout(overlayState.timer);
      if (!overlayState.query) return;
      overlayState.timer = setTimeout(async () => {
        await fetchOverlayKnowledge(overlayState.query);
        if (overlayState.query === input.value.trim()) renderGlobalSearchOverlay();
      }, 220);
    });
    input.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); closeGlobalSearch(); } });
    host.addEventListener('click', event => {
      if (event.target.closest('[data-gs-close]')) { closeGlobalSearch(); return; }
      const term = event.target.closest('[data-gs-term]');
      if (term) { input.value = term.dataset.gsTerm; overlayState.query = term.dataset.gsTerm; renderGlobalSearchOverlay(); fetchOverlayKnowledge(overlayState.query).then(() => { if (q('#gsInput', host) === document.activeElement || !host.hidden) renderGlobalSearchOverlay(); }); return; }
      const jump = event.target.closest('[data-search-jump]');
      if (jump) { closeGlobalSearch(); if (typeof activate === 'function') activate(jump.dataset.searchJump); return; }
      if (event.target.closest('[data-gs-more]')) { const query = overlayState.query; closeGlobalSearch(); if (typeof activate === 'function') activate('search'); const pageInput = q('#searchInput'); if (pageInput && query) { pageInput.value = query; runSearch(query); } else if (pageInput) pageInput.focus(); }
    });
    return host;
  }

  async function fetchOverlayKnowledge(query) {
    if (overlayState.knowledgeFor === query) return overlayState.knowledgeRows;
    overlayState.knowledgeFor = query;
    try {
      const rows = await request(`/api/knowledge/search?q=${encodeURIComponent(query)}&limit=12`);
      overlayState.knowledgeRows = Array.isArray(rows) ? rows.map(searchRowFromKnowledge) : [];
    } catch (cause) {
      console.error('全局检索知识片段失败', cause);
      overlayState.knowledgeRows = [];
    }
    return overlayState.knowledgeRows;
  }

  function renderGlobalSearchOverlay() {
    const host = q('#globalSearchOverlay'); if (!host || host.hidden) return;
    const query = overlayState.query;
    const corpus = buildSearchCorpus();
    const nodes = buildSearchNodes(), pairs = buildSearchRelationPairs();
    const suggest = q('#gsSuggest', host), list = q('#gsResults', host), hint = q('#gsHint', host);
    const terms = searchHotTerms(corpus);
    suggest.innerHTML = query ? '' : `<span class="gs-suggest-label">热门检索</span>${terms.map(term => `<button type="button" class="gs-pill" data-gs-term="${escapeHtml(term)}">${escapeHtml(term)}</button>`).join('')}`;
    if (!query) {
      list.innerHTML = `<div class="gs-empty"><i data-lucide="scan-search"></i><p>输入对象名称、编号或关键词</p><span>覆盖活动、机会、客群、产品包、内容资产、画像字段与知识片段</span></div>`;
      hint.textContent = `索引 ${corpus.length} 条业务对象`;
      if (window.lucide) lucide.createIcons();
      return;
    }
    const local = corpus.map(row => ({ ...row, score: scoreSearchRow(row, query) })).filter(row => row.score > 0);
    const knowledge = (overlayState.knowledgeFor === query ? overlayState.knowledgeRows : []).map(row => ({ ...row, score: scoreSearchRow(row, query) || 45 }));
    const rows = [...knowledge, ...local].sort((a, b) => b.score - a.score || a.title.localeCompare(b.title, 'zh-CN')).slice(0, 12);
    hint.textContent = overlayState.knowledgeFor === query ? `${rows.length} 条命中` : `检索「${query}」中…`;
    if (!rows.length) {
      list.innerHTML = `<div class="gs-empty"><i data-lucide="search-x"></i><p>没有命中「${escapeHtml(query)}」</p><span>换个说法，或点下方进入检索页精确筛选</span></div>`;
      if (window.lucide) lucide.createIcons();
      return;
    }
    list.innerHTML = rows.map(row => searchCardHTML(row, query, nodes, pairs, true)).join('');
    if (window.lucide) lucide.createIcons();
  }

  function openGlobalSearch() {
    const host = ensureGlobalSearchOverlay();
    const isInner = !q('#dongdong.active');
    host.classList.toggle('is-workbench-search', isInner);
    q('.gs-workbench-intro', host).hidden = !isInner;
    q('.gs-title', host).hidden = isInner;
    q('#gsInput', host).placeholder = isInner ? '搜索名称、编号或关键词…' : '检索机会、客群、产品包、活动、内容与知识片段';
    overlayState.lastFocus = document.activeElement;
    host.hidden = false;
    document.body.classList.add('layer-open');
    renderGlobalSearchOverlay();
    const input = q('#gsInput', host);
    if (input) { input.value = overlayState.query; input.focus(); input.select(); }
  }

  function closeGlobalSearch() {
    const host = q('#globalSearchOverlay'); if (!host || host.hidden) return;
    host.hidden = true;
    document.body.classList.remove('layer-open');
    clearTimeout(overlayState.timer);
    if (overlayState.lastFocus && overlayState.lastFocus.focus) overlayState.lastFocus.focus();
  }

  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeGlobalSearch(); });

  async function initializeSession(){if(typeof syncDongdongChrome==='function')syncDongdongChrome();resetDashboard();
    try{mountMarketingAssistantV2();setTimeout(()=>{if(!q('#marketingAssistant')){try{mountMarketingAssistantV2();}catch(cause){console.error('assistant remount failed',cause);}}},0);}catch(cause){console.error('营销助手挂载失败',cause);}
    try{bindDongdongChips();renderDongdongChips('opportunity');mountDongdongHero();renderDongdongCapabilities();}catch(cause){console.error('东东首页挂载失败',cause);}
    try{injectNavigation();}catch(cause){console.error('导航扩展失败',cause);}
    try{bindProductionActions();}catch(cause){console.error('生产功能绑定失败',cause);}
    try{await loadTenantData();}catch(cause){console.error('租户数据加载失败',cause);const capabilities=q('#dongdongCapabilityGrid');if(capabilities)capabilities.innerHTML='<div class="dongdong-cap-empty">业务数据加载失败，请检查本地 API 后刷新页面</div>';toast(cause.message||'租户数据加载失败，请稍后重试');}
    try{mountSearchModule();}catch(cause){console.error('检索模块挂载失败',cause);}
    if(window.lucide)lucide.createIcons();
  }
  function boot(){try{session=JSON.parse(localStorage.getItem(sessionKey)||'null');}catch{session=null;}if(!session)return createLogin();const savedTenant=Number(localStorage.getItem(tenantKey));tenantId=session.tenants?.some(item=>item.id===savedTenant)?savedTenant:(session.tenants?.[0]?.id||null);q('.app').style.visibility='visible';initializeSession().catch(cause=>{console.error(cause);toast(cause.message||'租户数据加载失败，请稍后重试');});}
  bindProductionApprovalCapture();
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
