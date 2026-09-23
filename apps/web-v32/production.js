(function () {
  'use strict';
  const mount = location.pathname.startsWith('/ceair-marketing') ? '/ceair-marketing' : '';
  const sessionKey = 'ceair-production-session';
  const tenantKey = 'ceair-production-tenant';
  let session = null;
  let tenantId = null;
  let tenantData = { campaigns: [], graph: { nodes: [], edges: [] }, imports: [], pipelines: [], providers: [], domains: [], runs: [], opportunitySources: [], opportunityRuns: [], mineru: null, opportunities: [], audienceTags: [], audiencePackages: [], personaDimensions: [], personaSegments: [], productPackages: [], productCatalog: {products: []}, contentAssets: [], audienceSnapshots: [], approvals: [], executionBatches: [], documents: [] };
  const pipelineFiles = new Map();
  const roleLabels = { admin: '租户管理员', manager: '营销经理', analyst: '营销分析师', viewer: '只读用户' };
  let pipelinePollTimer = null;
  let opportunityPollTimer = null;
  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const displayText = (value, fallback) => /^\?+$/.test(String(value ?? '').trim()) ? fallback : String(value ?? fallback);
  const statusClass = value => /待|草稿|暂停|失败|停用|未配置/.test(String(value || '')) ? 'warn' : 'good';

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

  function openBusinessEditor({ title, subtitle, item, fields, save, width = 'business-editor-card' }) {
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
        <div class="business-editor-foot"><span>带 <em>*</em> 为必填项</span><div><button type="button" class="btn" data-close>取消</button><button type="submit" class="btn primary">保存修改</button></div></div>
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
      });
      if (invalidJson) return;
      saving = true; button.disabled = true; button.textContent = '正在保存...';
      try { await save(values); saving = false; close(); } catch (cause) { error.textContent = cause.message || '保存失败'; error.hidden = false; error.scrollIntoView({block:'nearest'}); } finally { saving = false; button.disabled = false; button.textContent = '保存修改'; }
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
    openBusinessEditor({
      title: '编辑营销内容', subtitle: item.external_id || '内容资产', item,
      fields: [
        { name: 'name', label: '内容资产名称', type: 'text' },
        { name: 'campaign_id', label: '关联活动', type: 'select', required: false, options: [{value:'',label:'未关联活动'}, ...(tenantData.campaigns || []).map(campaign => ({value:campaign.id,label:`${campaign.name} · ${campaign.id}`}))] },
        { name: 'channel', label: '触达渠道', type: 'select', options: [{value:'App',label:'东航 App'}, '东航App', '短信', '微信', '邮件', '小程序', '官网', '客服外呼', '企业渠道'] },
        { name: 'version', label: '内容版本', type: 'text' },
        { name: 'status', label: '内容状态', type: 'select', options: ['草稿', '待审核', '停用'], help: '已审核内容变更后需重新审核。' },
        { name: 'generated_by', label: '生成来源', type: 'text', required: false, readOnly: true, displayValue: ({manual:'人工创建','content-generation':'内容生成智能域',template:'模板生成'})[item.generated_by] },
        { name: 'title', label: '展示标题', type: 'text', required: false },
        { name: 'body', label: '内容正文', type: 'textarea', rows: 8, required: false, placeholder: '填写短信、App 卡片、微信图文或客服话术的完整内容' },
      ],
      save: async values => { values.campaign_id = String(values.campaign_id || '').trim() || null; const result = await request(`/api/content-assets/${item.id}`, { method: 'PUT', body: JSON.stringify({...values, generated_by: item.generated_by}) }); toast(result.status !== values.status ? '营销内容已更新，状态已退回草稿，请重新审核' : '营销内容已完整更新'); await refreshAfterBusinessSave(); }
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

  function showAudiencePackageEditor(item) {
    const tagOptions = (tenantData.audienceTags || []).filter(tag => tag.enabled || (item.tag_ids || []).includes(tag.id)).map(tag => ({ value: tag.id, label: `${tag.name} · ${tag.enabled ? (tag.category || '画像标签') : '已停用'}` }));
    openBusinessEditor({
      title: '编辑客群包', subtitle: `${item.external_id || '客群包'} · 画像组合与圈选条件`, item,
      fields: [
        { name: 'name', label: '客群包名称', type: 'text' },
        { name: 'selection_mode', label: '圈选方式', type: 'select', options: [{ value: 'tag-combination', label: '画像标签组合' }, { value: 'ai-selection', label: 'AI 智能圈选' }] },
        { name: 'estimated_size', label: '预计客群规模', type: 'number', min: 0 },
        { name: 'status', label: '客群包状态', type: 'select', options: ['草稿', '可用', '停用'] },
        { name: 'tag_ids', label: '关联画像标签', type: 'multiselect', required: false, options: tagOptions, help: '可多选底层画像标签；历史快照不会被修改。' },
        { name: 'expression', label: 'AI 圈选条件（JSON）', type: 'textarea', rows: 6, required: false, parseJson: true, placeholder: '{"route":"SHA-SYX","travel_intent":"high"}', help: '用于保存自然语言圈选后的结构化条件。' },
      ],
      save: async values => { await request(`/api/audience-packages/${item.id}`, { method: 'PUT', body: JSON.stringify(values) }); toast(`客群包“${values.name}”已更新`); await refreshAfterBusinessSave(); }
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

  function showProviderEditor(item) {
    openBusinessEditor({
      title: '编辑模型服务', subtitle: `${item.display_name} · API Key 留空表示保持原配置`, item,
      fields: [
        { name: 'display_name', label: '配置名称', type: 'text' },
        { name: 'provider_type', label: '服务类型', type: 'select', options: [{ value: 'openai-compatible', label: 'OpenAI Compatible' }, { value: 'mock', label: 'Mock' }] },
        { name: 'base_url', label: '服务地址', type: 'url', required: false, placeholder: 'https://.../v1' },
        { name: 'model_name', label: '默认模型名称', type: 'text' },
        { name: 'api_key', label: 'API Key', type: 'password', required: false, placeholder: '留空表示保持当前 Key' },
        { name: 'timeout_seconds', label: '超时（秒）', type: 'number', min: 5, max: 300 },
        { name: 'temperature', label: 'Temperature', type: 'number', min: 0, max: 2, step: 0.1 },
        { name: 'max_tokens', label: '最大输出 Token', type: 'number', min: 128, max: 32768 },
        { name: 'enabled', label: '启用模型服务', type: 'checkbox' },
        { name: 'is_default', label: '设为默认模型', type: 'checkbox' },
      ],
      save: async values => { if (!values.api_key) delete values.api_key; await request(`/api/model-providers/${item.id}`, { method: 'PUT', body: JSON.stringify(values) }); toast('模型服务配置已更新'); await refreshAfterBusinessSave(); renderModels(); }
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
<div class="page-head"><div><h1>\u6570\u636e\u63a5\u5165</h1><p>\u6295\u9012\u6587\u6863\u3001\u8868\u683c\u548c\u7ed3\u6784\u5316\u6570\u636e\uff0c\u7cfb\u7edf\u81ea\u52a8\u89e3\u6790\u5e76\u66f4\u65b0\u77e5\u8bc6\u5e95\u5ea7</p></div><div class="page-actions"><button class="btn" id="syncNdcFlight"><i data-lucide="plane-takeoff"></i>同步 NDC24.1 模拟航班</button><button class="btn" id="refreshPipelines"><i data-lucide="refresh-cw"></i>\u5237\u65b0\u72b6\u6001</button></div></div>
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
    session.tenants = (session.tenants || []).filter(item => item.code !== 'CEA-ECOM' && !String(item.name || '').includes('电商运营中心'));
    if (!session.tenants.some(item => item.id === tenantId)) tenantId = session.tenants[0]?.id;
    const tenant = activeTenant(); const user = q('.user');
    q('b', user).textContent = tenant?.name || '未选择租户';
    q('span', user).textContent = `${session.display_name} · 当前角色：${roleLabels[tenant?.role] || tenant?.role || '未授权'}`;
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

  const cleanText = (value, fallback = '') => { const text = String(value ?? ''); return !text.trim() || (text.match(/\?/g)||[]).length > Math.max(2, text.length * .35) || text.includes('?') ? fallback : text; };
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
    panel.innerHTML=`<div class="panel-head"><div><h2>商机洞察智能体</h2><span>按业务人员配置的网站与关注点，采用 wigolo 风格的规划、取证、并行洞察和商机合并流程</span></div><span class="insight-badge"><i data-lucide="sparkles"></i> AgentScope · 多智能体</span></div><div class="panel-body"><div class="insight-console-grid"><section class="insight-source-config"><div class="section-kicker">01 · 洞察来源</div><div class="insight-source-list">${sourceRows||'<div class="empty-action">暂无来源，请先新增一个网站或人工信号来源</div>'}</div><form id="opportunitySourceForm" class="insight-source-form"><input type="hidden" name="source_id"><input name="name" placeholder="来源名称，例如：三亚文旅官方动态" required><input name="source_url" placeholder="网站地址，可留空使用人工描述"><select name="source_type"><option value="web">网站</option><option value="api">接口</option><option value="manual">人工信号</option><option value="social">社媒</option></select><input name="schedule" value="manual" placeholder="采集方式，例如 manual / daily"><textarea name="focus" placeholder="希望重点关注什么：航线需求、节假日热度、产品机会、竞品变化等"></textarea><div class="insight-form-actions"><button type="submit" class="btn primary" data-action="saveOpportunitySource">保存来源</button><button type="button" class="btn" data-action="resetOpportunitySource">清空</button></div></form></section><section class="insight-run-config"><div class="section-kicker">02 · 业务洞察要求</div><textarea id="opportunityInsightPrompt" class="insight-prompt" placeholder="例如：围绕国庆前上海—三亚航线，关注客座率、价格、目的地热度、家庭客群和行李/选座辅营机会">围绕东航重点航线和近期市场热点，识别可落地的营销商机，并说明证据、适配客群和可引用产品。</textarea><div class="insight-run-actions"><button class="btn primary" data-action="runOpportunityInsight"><i data-lucide="play"></i>开始多智能体洞察</button><span>选择来源后启动，任务会持续记录每一步进度</span></div><div class="insight-agent-lane"><span>市场信号</span><i>＋</i><span>航线经营</span><i>＋</i><span>产品商业化</span><b>→ 商机候选</b></div></section></div><div class="insight-history"><div class="section-kicker">03 · 洞察历史与溯源</div><table class="table compact-table"><tr><th>任务</th><th>当前阶段</th><th>状态</th><th>步骤</th><th>操作</th></tr>${runRows||'<tr><td colspan="5" class="muted">暂无洞察任务</td></tr>'}</table></div></div>`;
    if(window.lucide)lucide.createIcons();
  }
  function renderAudienceStructure(){
    const panel=q('#audiences .grid2 .panel:first-child .panel-body'); if(!panel)return;
    const packages=tenantData.audiencePackages||[], tags=tenantData.audienceTags||[], snapshots=tenantData.audienceSnapshots||[];
    const segments=tenantData.personaSegments||[];
    const personaCards=segments.map(item=>`<div class="catalog-card persona-card">
      <div class="catalog-card-top"><span class="catalog-icon"><i data-lucide="user-round"></i></span><span class="status good">\u53ef\u7528\u4e8e\u5708\u9009</span></div>
      <strong title="${escapeHtml(displayText(item.segment_name,'\u672a\u547d\u540d\u753b\u50cf'))}">${escapeHtml(displayText(item.segment_name,'\u672a\u547d\u540d\u753b\u50cf'))}</strong>
      <small>${escapeHtml(displayText(item.primary_persona_name,'\u5ba2\u6237\u753b\u50cf'))} \u00b7 ${escapeHtml(displayText(item.segment_code,'\u753b\u50cf\u7f16\u7801'))} \u00b7 ${escapeHtml(displayText(item.belongs_to,'ToC'))}</small>
      <p class="persona-card-rule">${escapeHtml(displayText((item.recommended_products||[])[0],'\u53ef\u4e0e\u4ea7\u54c1\u5305\u7ec4\u5408'))}</p>
      <div class="catalog-card-meta"><span>${item.rules?.length||0} \u6761\u753b\u50cf\u6761\u4ef6</span><button class="btn" data-audience-persona="${escapeHtml(item.id)}">\u67e5\u770b\u753b\u50cf</button></div>
    </div>`).join('');
    const packageRows=packages.map(item=>{const protectedPackage=['已冻结','已使用','执行中','已归档'].includes(item.status);return `<tr><td><strong>${escapeHtml(displayText(item.name,'未命名客群包'))}</strong><small>${escapeHtml(item.external_id||'')}</small></td><td>${Number(item.estimated_size||0).toLocaleString('zh-CN')} 人</td><td>${escapeHtml(item.selection_mode==='ai-selection'?'AI圈选':'画像组合')}</td><td>${escapeHtml(item.version||'V1')}</td><td><span class="status ${statusClass(item.status)}">${escapeHtml(item.status||'可用')}</span></td><td class="production-actions"><button class="btn" data-audience-edit="${item.id}"${protectedPackage?' disabled title="已冻结或已投入执行的客群包不可直接编辑"':''}>编辑</button><button class="btn" data-audience-snapshot="${item.id}"${protectedPackage?' disabled':''}>冻结快照</button></td></tr>`;}).join('');
    panel.innerHTML=`<div class="catalog-summary"><div><b>客户画像</b><span>底层画像目录，可作为客群组合条件</span></div><div class="catalog-summary-stats"><strong>${segments.length}</strong><small>个可复用画像</small><button class="btn" data-action="refreshAudienceCatalog"><i data-lucide="refresh-cw"></i>同步画像</button></div></div>
      <div class="catalog-grid">${personaCards||'<div class="empty-action">暂无客户画像，可先同步画像平台数据</div>'}</div>
      <div class="catalog-section-head"><div><b>客群包</b><span>由多个画像、标签或 AI 圈选条件组合形成，可被营销活动直接引用</span></div><span class="catalog-count">${packages.length} 个</span></div>
      <table class="table compact-table"><tr><th>客群包</th><th>规模</th><th>组合方式</th><th>版本</th><th>状态</th><th>操作</th></tr>${packageRows||'<tr><td colspan="6" class="muted">暂无客群包，请通过新建客群完成画像组合</td></tr>'}</table>
      <details class="audience-tag-details"><summary>画像标签维护 · ${tags.length} 个</summary>
      <div class="audience-tag-list">${tags.map(tag => `<div class="audience-tag-item"><div><strong>${escapeHtml(displayText(tag.name, '未命名标签'))}</strong><small>${escapeHtml(displayText(tag.code, 'TAG'))} · ${escapeHtml(displayText(tag.category, '基础属性'))} · ${escapeHtml(displayText(tag.source, '画像平台'))}</small></div><span class="status ${tag.enabled === false ? 'warn' : 'good'}">${tag.enabled === false ? '停用' : '启用'}</span><button class="btn" data-audience-tag-edit="${tag.id}">编辑</button></div>`).join('') || '<div class="empty-action">暂无画像标签，请先同步用户画像平台</div>'}</div>
      </details><div class="catalog-foot"><span>可复用标签 ${tags.length} 个 · 已冻结快照 ${snapshots.length} 个</span><span>客群包是活动执行时的正式客群对象</span></div>`;
    if(window.lucide)lucide.createIcons();
  }  function renderKnowledgeDocuments(){
    const host=q('#graph .graph-layout'); if(!host)return; let panel=q('#knowledgeDocuments'); if(!panel){panel=document.createElement('div');panel.id='knowledgeDocuments';panel.className='panel knowledge-documents';host.appendChild(panel);} const docs=tenantData.documents||[];
    panel.innerHTML='<div class="panel-head"><h2>\u77e5\u8bc6\u6587\u6863</h2><span>'+docs.length+' \u4e2a\u6587\u6863 · \u5220\u9664\u5c06\u540c\u6b65\u6e05\u7406\u672c\u4f53\u5bf9\u8c61</span></div><div class="panel-body">'+(docs.length?'<table class="table"><tr><th>\u6587\u6863</th><th>\u6765\u6e90</th><th>\u5207\u7247</th><th>\u672c\u4f53\u5bf9\u8c61</th><th>\u7248\u672c</th><th>\u64cd\u4f5c</th></tr>'+docs.map(d=>'<tr><td><strong>'+escapeHtml(cleanText(d.title,'\u672a\u547d\u540d\u6587\u6863'))+'</strong><small>'+escapeHtml(d.external_id)+'</small></td><td>'+escapeHtml(cleanText(d.source_name,d.source_type))+'</td><td>'+d.chunk_count+'</td><td>'+d.entity_count+'</td><td>V'+d.version+'</td><td class="production-actions"><button class="btn" data-document-edit="'+d.id+'">\u7f16\u8f91</button><button class="btn danger" data-document-delete="'+d.id+'">\u5220\u9664</button></td></tr>').join('')+'</table>':'<div class="empty-action">\u6682\u65e0\u77e5\u8bc6\u6587\u6863\u3002\u4e0a\u4f20\u6587\u4ef6\u540e\uff0c\u5904\u7406\u7ed3\u679c\u4f1a\u5728\u8fd9\u91cc\u5f62\u6210\u77e5\u8bc6\u4e0e\u672c\u4f53\u3002</div>')+'</div>';
  }
  function showAgentTrace(run){
    const events=run?.events||[]; const html='<div class="agent-trace"><div class="agent-trace-head"><i data-lucide="bot"></i><b>Agent\u6267\u884c\u8fc7\u7a0b</b><span>'+escapeHtml(cleanText(run?.status,'\u5df2\u5b8c\u6210'))+'</span></div><div class="agent-trace-list">'+(events.length?events.map((e,i)=>'<div class="agent-trace-item"><i>'+(i+1)+'</i><div><b>'+escapeHtml(cleanText(e.event_type,'\u5904\u7406\u6b65\u9aa4'))+'</b><small>'+new Date(e.timestamp).toLocaleString('zh-CN')+'</small><p>'+escapeHtml(JSON.stringify(e.payload||{}))+'</p></div></div>').join(''):'<div class="empty-action">\u672a\u8fd4\u56de\u6b65\u9aa4\u4e8b\u4ef6</div>')+'</div><div class="drawer-ai">'+escapeHtml(cleanText(run?.summary,'Agent\u5df2\u5b8c\u6210\u5904\u7406'))+'</div></div>';
    const layer=document.createElement('div');layer.className='production-modal';layer.innerHTML='<div class="production-modal-card"><div class="production-modal-head"><b>\u667a\u80fd\u57df\u8fc7\u7a0b\u8ffd\u8e2a</b><button class="btn" data-close>\u5173\u95ed</button></div><div class="production-modal-body">'+html+'</div></div>';document.body.appendChild(layer);layer.addEventListener('click',e=>{if(e.target===layer||e.target.closest('[data-close]'))layer.remove();});if(window.lucide)lucide.createIcons();
  }
  function campaignActions(item){
    const archived=item.status==='已归档';
    const editable=['草稿','待修改'].includes(item.status);
    const removable=archived || ['草稿','待修改'].includes(item.status);
    return `<button class="btn" data-production-campaign-view="${escapeHtml(item.id)}">查看</button>${editable?`<button class="btn" data-production-campaign-edit="${escapeHtml(item.id)}">编辑</button>`:''}${archived?'<button class="btn danger" data-production-campaign-delete="'+escapeHtml(item.id)+'">删除</button>':removable?'<button class="btn danger" data-production-campaign-delete="'+escapeHtml(item.id)+'">删除</button>':'<button class="btn" data-production-campaign-archive="'+escapeHtml(item.id)+'">归档</button>'}`;
  }
  function renderCampaigns(){
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
<td class="production-actions">${campaignActions(item)}</td>
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
    const lower = q('#campaigns .campaign-lower'); if (lower) lower.hidden = true;
    renderProducts();
  }

  function renderProducts(){
    const table=q('#products .table'); if(!table)return;
    const products=tenantData.productPackages||[];
    const body=table.parentElement;
    let baseCatalog=q('#productCatalog');
    if(!baseCatalog){baseCatalog=document.createElement('div');baseCatalog.id='productCatalog';baseCatalog.className='base-product-catalog';body.insertBefore(baseCatalog,table);}
    const baseProducts=tenantData.productCatalog?.products||[];
    baseCatalog.innerHTML=`<div class="catalog-section-head"><div><b>基础产品目录</b><span>来自产品管理平台的可售产品，是产品包组合和活动匹配的底层对象</span></div><span class="catalog-count">${baseProducts.length} 个</span></div><div class="catalog-grid product-catalog-grid">${baseProducts.map(item=>`<div class="catalog-card product-card"><div class="catalog-card-top"><span class="catalog-icon"><i data-lucide="ticket"></i></span><span class="status good">可引用</span></div><strong>${escapeHtml(displayText(item.name,'未命名产品'))}</strong><small>${escapeHtml(displayText(item.category,'航空产品'))} · ${escapeHtml(displayText(item.code,'产品编码'))}</small><div class="catalog-card-meta"><span>${(item.benefits||[]).length} 项权益</span><button class="btn" data-product-catalog-view="${escapeHtml(item.code)}">查看产品</button></div></div>`).join('')||'<div class="empty-action">暂无基础产品，可从产品管理平台同步</div>'}</div>`;
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

  function renderContents(){
    const table=q('#contents .table'); if(!table)return;
    const assets=tenantData.contentAssets||[];
    const rows=assets.map(item=>`<tr><td><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.title||'')}</small></td><td>${escapeHtml(item.campaign_id||'未关联活动')}</td><td>${escapeHtml(item.channel)}</td><td>${escapeHtml(item.version)}</td><td><span class="status ${statusClass(item.status)}">${escapeHtml(item.status)}</span></td><td class="production-actions"><button class="btn" data-content-view="${item.id}">查看</button><button class="btn" data-content-edit="${item.id}">编辑</button><button class="btn danger" data-content-delete="${item.id}">删除</button></td></tr>`).join('');
    table.innerHTML=`<tr><th>内容名称</th><th>活动</th><th>渠道</th><th>版本</th><th>状态</th><th>操作</th></tr>${rows||'<tr><td colspan="6"><div class="empty-action">暂无内容资产。可以新建内容，或使用 AI 生成多渠道版本。</div></td></tr>'}`;
    const latest=assets[0]; if(latest){const hero=q('.phone-hero'),copy=q('.phone-body b'),desc=q('.phone-body p');if(hero)hero.textContent=latest.title||latest.name;if(copy)copy.textContent=latest.body||'暂无正文';if(desc)desc.textContent=`${latest.channel} · ${latest.version} · ${latest.status}`;}
  }

  function renderExecution(){
    const batches=tenantData.executionBatches||[]; const batch=batches[0]; if(!batch)return;
    const section=q('#execution'); if(!section)return;
    const kpis=qa('.kpi b',section); if(kpis[0])kpis[0].textContent=Number(batch.target_size||0).toLocaleString('zh-CN'); if(kpis[1])kpis[1].textContent=Number(batch.delivered_count||0).toLocaleString('zh-CN'); if(kpis[2])kpis[2].textContent=Number(batch.feedback_count||0).toLocaleString('zh-CN'); if(kpis[3])kpis[3].textContent=Number(batch.failed_count||0).toLocaleString('zh-CN'); if(kpis[4])kpis[4].textContent=batch.status;
    const batchText=qa('#execution .toolbar-strip option'); if(batchText[0])batchText[0].textContent=batch.external_id+' · '+batch.status;
    const action=qa('#execution [data-action]'); action.filter(button=>['pauseCampaign','refreshExecution'].includes(button.dataset.action)).forEach(button=>{button.dataset.batchId=batch.id;});
    const tasks=(tenantData.channelTasks||[]).filter(item=>item.batch_id===batch.id);
    const table=q('#execution .table');
    if(table){
      const body=table.tBodies[0]||table.createTBody();
      body.innerHTML=tasks.length?tasks.map(item=>`<tr><td><strong>${escapeHtml(item.channel)}</strong><small class="table-subline">${escapeHtml(item.external_id)}</small></td><td>${Number(item.target_count||0).toLocaleString('zh-CN')}</td><td>${Number(item.delivered_count||0).toLocaleString('zh-CN')}</td><td>${Number(item.failed_count||0).toLocaleString('zh-CN')}</td><td>${item.last_feedback_at?new Date(item.last_feedback_at).toLocaleTimeString('zh-CN'):'待回执'}</td><td><span class="status ${item.status==='失败'?'bad':item.status==='执行中'?'good':'warn'}">${escapeHtml(item.status)}</span> <button class="btn compact" data-channel-feedback="${item.id}">录入回执</button></td></tr>`).join(''):'<tr><td colspan="6" class="table-empty">暂无渠道任务，审批通过后将按活动版本渠道自动生成</td></tr>';
    }
  }
  function renderFeedback(){
    const section=q('#feedback'); if(!section)return;
    const summary=tenantData.effectSummary; if(!summary)return;
    const values=[summary.target_count,summary.delivered_count,summary.clicked_count,summary.converted_count];
    const kpis=qa('.kpi b',section); if(kpis[0])kpis[0].textContent=Number(summary.target_count||0).toLocaleString('zh-CN'); if(kpis[1])kpis[1].textContent=`${Number(summary.click_rate||0).toFixed(1)}%`; if(kpis[2])kpis[2].textContent=`${Number(summary.conversion_rate||0).toFixed(1)}%`; if(kpis[3])kpis[3].textContent=`${Number(summary.delivered_count||0).toLocaleString('zh-CN')}`; if(kpis[4])kpis[4].textContent=summary.batch_count?`${summary.batch_count} 批`:'暂无';
    const metrics=qa('.metric-list .metric b',section); metrics.forEach((item,index)=>{if(values[index]!==undefined)item.textContent=Number(values[index]||0).toLocaleString('zh-CN');});
    const bars=qa('.metric-list .bar i',section); if(bars[0])bars[0].style.width='100%'; if(bars[1])bars[1].style.width=Math.min(100,summary.delivery_rate||0)+'%'; if(bars[2])bars[2].style.width=Math.min(100,summary.click_rate||0)+'%'; if(bars[3])bars[3].style.width=Math.min(100,summary.conversion_rate||0)+'%';
    const box=q('#reviewBox'); if(box && summary.batch_count){box.innerHTML=`<div class="review-summary"><b>真实回执已接入</b><p>已汇总 ${summary.batch_count} 个执行批次，触达率 ${summary.delivery_rate}%、点击率 ${summary.click_rate}%、点击后转化率 ${summary.conversion_rate}%。效果分析智能域可基于这些结果继续生成客群、内容、时机和渠道优化建议。</p><div class="review-tags"><span>送达 ${Number(summary.delivered_count||0).toLocaleString('zh-CN')}</span><span>点击 ${Number(summary.clicked_count||0).toLocaleString('zh-CN')}</span><span>转化 ${Number(summary.converted_count||0).toLocaleString('zh-CN')}</span><span>失败 ${Number(summary.failed_count||0).toLocaleString('zh-CN')}</span></div></div>`;}
  }
  function renderApprovals(){
    const list=q('#approvals .approval-list'); if(!list)return;
    const approvals=tenantData.approvals||[];
    if(!approvals.length){list.innerHTML='<div class="empty-action">暂无待处理审批。活动版本提交审批后会出现在这里。</div>';return;}
    list.innerHTML=approvals.map(item=>`<button class="approval-item ${item.status==='待审批'?'active':''}" data-approval="${item.id}"><span class="approval-icon activity"><i data-lucide="megaphone"></i></span><span><b>${escapeHtml(item.campaign_id)}</b><small>${escapeHtml(item.approver_role)} · ${escapeHtml(item.external_id)}</small></span><em class="pill ${item.status==='待审批'?'red':'blue'}">${escapeHtml(item.status)}</em></button>`).join('');
    if(window.lucide)lucide.createIcons();
  }

  function renderContentChannelPreview(item){
    const channel=String(item.channel||'').toLowerCase();
    const title=escapeHtml(displayText(item.title||item.name,'\u4e1c\u822a\u8425\u9500\u6d3b\u52a8'));
    const body=escapeHtml(displayText(item.body,'\u6682\u65e0\u6b63\u6587')).replace(/\r?\n/g,'<br>');
    const action='<button class="preview-cta">\u7acb\u5373\u67e5\u770b</button>';
    if(channel.includes('\u77ed\u4fe1')) return `<div class="channel-preview sms-preview"><div class="preview-device-bar"><span>China Mobile</span><span>Just now</span></div><div class="preview-sms-bubble"><b>${title}</b><p>${body}</p></div></div>`;
    if(channel.includes('\u5fae\u4fe1')||channel.includes('\u516c\u4f17\u53f7')) return `<div class="channel-preview wechat-preview"><div class="preview-wechat-head"><span class="preview-avatar">\u4e1c</span><b>\u4e2d\u56fd\u4e1c\u65b9\u822a\u7a7a</b><small>\u516c\u4f17\u53f7\u6d88\u606f</small></div><div class="preview-wechat-card"><b>${title}</b><p>${body}</p>${action}</div></div>`;
    if(channel.includes('app')||channel.includes('\u5c0f\u7a0b\u5e8f')) return `<div class="channel-preview app-preview"><div class="preview-app-head"><span>CEAir App</span><small>\u8425\u9500\u6d88\u606f</small></div><div class="preview-app-card"><span class="preview-app-tag">\u4e13\u5c5e\u63a8\u8350</span><h4>${title}</h4><p>${body}</p>${action}</div></div>`;
    if(channel.includes('\u90ae\u4ef6')) return `<div class="channel-preview email-preview"><div class="preview-email-head"><b>\u6536\u4ef6\u7bb1</b><span>\u4e1c\u822a\u8425\u9500\u8fd0\u8425\u4e2d\u5fc3</span></div><article><small>\u4e3b\u9898</small><h4>${title}</h4><p>${body}</p>${action}</article></div>`;
    if(channel.includes('ota')||channel.includes('ndc')||channel.includes('\u5b98\u7f51')) return `<div class="channel-preview offer-preview"><div class="preview-offer-head"><b>\u53ef\u552e\u4ea7\u54c1\u63a8\u8350</b><span>${escapeHtml(item.channel||'\u5b98\u7f51')}</span></div><div class="preview-offer-body"><h4>${title}</h4><p>${body}</p><div class="preview-offer-foot"><span>\u4e1c\u65b9\u822a\u7a7a</span>${action}</div></div></div>`;
    return `<div class="channel-preview generic-preview"><span class="preview-channel-label">${escapeHtml(item.channel||'\u8425\u9500\u6e20\u9053')}</span><h4>${title}</h4><p>${body}</p>${action}</div>`;
  }
  function showContentDetail(item){
    const layer=document.createElement('div');layer.className='production-modal';layer.innerHTML=`<div class="production-modal-card content-detail-card"><div class="production-modal-head"><div><b>${escapeHtml(displayText(item.name,'\u8425\u9500\u5185\u5bb9'))}</b><small>${escapeHtml(displayText(item.channel,'\u8425\u9500\u6e20\u9053'))} \u00b7 ${escapeHtml(displayText(item.version,'V1'))} \u00b7 ${escapeHtml(displayText(item.status,'\u8349\u7a3f'))}</small></div><button class="btn" data-close>\u5173\u95ed</button></div><div class="production-modal-body"><div class="content-preview-layout"><section class="content-preview-stage"><div class="content-preview-stage-head"><div><b>\u6e20\u9053\u9884\u89c8</b><small>\u6309\u5b9e\u9645\u89e6\u8fbe\u6e20\u9053\u6a21\u62df\u5c55\u793a</small></div><span>${escapeHtml(displayText(item.channel,'\u8425\u9500\u6e20\u9053'))}</span></div>${renderContentChannelPreview(item)}</section><section class="content-detail-copy"><div class="campaign-detail-summary"><span><b>\u6d3b\u52a8</b>${escapeHtml(item.campaign_id||'\u672a\u5173\u8054\u6d3b\u52a8')}</span><span><b>\u751f\u6210\u65b9\u5f0f</b>${escapeHtml(item.generated_by||'manual')}</span><span><b>\u7248\u672c</b>${escapeHtml(item.version||'V1')}</span></div><h3>${escapeHtml(item.title||'\u5185\u5bb9\u6b63\u6587')}</h3><p class="content-body-copy">${escapeHtml(item.body||'\u6682\u65e0\u6b63\u6587')}</p></section></div></div></div>`;document.body.appendChild(layer);layer.addEventListener('click',event=>{if(event.target===layer||event.target.closest('[data-close]'))layer.remove();});
  }
  function showPersonaDetail(item){
    const rules=(item.rules||[]).map(rule=>`<li><b>${escapeHtml(displayText(rule.dimension_name,'\u753b\u50cf\u6761\u4ef6'))}</b><span>${escapeHtml(displayText(rule.condition_expression,`${rule.condition_operator||'='} ${rule.condition_value||''}`))}</span><small>\u6765\u6e90\uff1a${escapeHtml(displayText(rule.data_source,'\u753b\u50cf\u63a5\u53e3'))}</small></li>`).join('');
    const layer=document.createElement('div'); layer.className='production-modal';
    layer.innerHTML=`<div class="production-modal-card"><div class="production-modal-head"><div><b>${escapeHtml(displayText(item.segment_name,'\u5ba2\u6237\u753b\u50cf'))}</b><small>${escapeHtml(displayText(item.segment_code,'\u753b\u50cf\u7f16\u7801'))} · ${escapeHtml(displayText(item.primary_persona_name,'\u5ba2\u6237\u753b\u50cf'))}</small></div><button class="btn" data-close>\u5173\u95ed</button></div><div class="production-modal-body"><div class="campaign-detail-summary"><span><b>\u753b\u50cf\u7c7b\u578b</b>${escapeHtml(displayText(item.primary_persona_name,'\u672a\u5206\u7c7b'))}</span><span><b>\u6761\u4ef6\u6570\u91cf</b>${item.rules?.length||0} \u6761</span><span><b>\u53ef\u7ecf\u8425\u72b6\u6001</b>\u53ef\u7528\u4e8e\u5708\u9009</span></div><section><h3>\u753b\u50cf\u7ec4\u5408\u6761\u4ef6</h3><ul class="catalog-detail-list">${rules||'<li><span>\u6682\u65e0\u660e\u7ec6\u6761\u4ef6</span></li>'}</ul></section><section><h3>\u5173\u8054\u8bf4\u660e</h3><p>\u8be5\u753b\u50cf\u53ef\u4e0e\u5176\u4ed6\u753b\u50cf\u548c\u6807\u7b7e\u7ec4\u5408\u751f\u6210\u5ba2\u7fa4\u5305\uff0c\u518d\u7528\u4e8e\u6d3b\u52a8\u5ba2\u7fa4\u5feb\u7167\u548c\u4ea7\u54c1\u5339\u914d\u3002</p></section></div></div>`;
    document.body.appendChild(layer); layer.addEventListener('click',event=>{if(event.target===layer||event.target.closest('[data-close]'))layer.remove();}); if(window.lucide)lucide.createIcons();
  }
  function showBaseProductDetail(item){
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
    const audience=version.audience_snapshot_id ? `客群快照 #${version.audience_snapshot_id}` : '未绑定客群快照';
    const product=version.product_package_id ? `产品包 #${version.product_package_id}` : '未绑定产品包';
    layer.innerHTML=`<div class="production-modal-card campaign-detail-card"><div class="production-modal-head"><div><b>${escapeHtml(campaignName)} · ${escapeHtml(version.version)}</b><small>${escapeHtml(version.external_id)} · 版本详情</small></div><button class="btn" data-close>关闭</button></div><div class="production-modal-body"><div class="campaign-detail-summary"><span><b>版本状态</b>${escapeHtml(version.status)}</span><span><b>创建时间</b>${new Date(version.created_at).toLocaleString('zh-CN')}</span><span><b>客群</b>${escapeHtml(audience)}</span><span><b>产品</b>${escapeHtml(product)}</span></div><div class="campaign-detail-grid"><section><h3>版本配置</h3><dl><dt>预算</dt><dd>¥${Number(version.budget_yuan||0).toLocaleString('zh-CN')}</dd><dt>内容资产</dt><dd>${(version.content_asset_ids||[]).length} 个</dd><dt>执行渠道</dt><dd>${escapeHtml((version.channels||[]).join('、')||'未配置')}</dd></dl></section><section><h3>可追溯信息</h3><dl><dt>版本编号</dt><dd>${escapeHtml(version.external_id)}</dd><dt>关联客群快照</dt><dd>${escapeHtml(audience)}</dd><dt>关联产品包</dt><dd>${escapeHtml(product)}</dd></dl></section></div></div></div>`;
    document.body.appendChild(layer); layer.addEventListener('click',event=>{if(event.target===layer||event.target.closest('[data-close]'))layer.remove();}); if(window.lucide)lucide.createIcons();
  }
  function showCampaignVersionCompare(left,right,campaignName){
    const field=(label,a,b)=>`<tr><th>${label}</th><td>${escapeHtml(String(a??'未配置'))}</td><td>${escapeHtml(String(b??'未配置'))}</td></tr>`;
    const layer=document.createElement('div'); layer.className='production-modal';
    layer.innerHTML=`<div class="production-modal-card campaign-detail-card"><div class="production-modal-head"><div><b>${escapeHtml(campaignName)} · 版本对比</b><small>差异检查 · ${escapeHtml(left.version)} 对比 ${escapeHtml(right.version)}</small></div><button class="btn" data-close>关闭</button></div><div class="production-modal-body"><table class="table"><tr><th>配置项</th><th>${escapeHtml(left.version)}</th><th>${escapeHtml(right.version)}</th></tr>${field('状态',left.status,right.status)}${field('预算',`¥${Number(left.budget_yuan||0).toLocaleString('zh-CN')}`,`¥${Number(right.budget_yuan||0).toLocaleString('zh-CN')}`)}${field('客群快照',left.audience_snapshot_id||'未配置',right.audience_snapshot_id||'未配置')}${field('产品包',left.product_package_id||'未配置',right.product_package_id||'未配置')}${field('内容资产数量',(left.content_asset_ids||[]).length,(right.content_asset_ids||[]).length)}${field('渠道',(left.channels||[]).join('、'),(right.channels||[]).join('、'))}</table></div></div>`;
    document.body.appendChild(layer); layer.addEventListener('click',event=>{if(event.target===layer||event.target.closest('[data-close]'))layer.remove();});
  }
  async function showCampaignEditor(item){
    let versions=[];
    try { versions = await request(`/api/campaigns/${encodeURIComponent(item.id)}/versions`); } catch (cause) { toast(cause.message || '活动版本加载失败'); return; }
    const latest = versions[0] || {};
    const productOptions = (tenantData.productPackages || []).map(value => ({ value: value.id, label: `${value.name} · ${value.version || 'V1'}` }));
    const snapshotOptions = (tenantData.audienceSnapshots || []).map(value => ({ value: value.id, label: `${value.external_id || `快照 #${value.id}`} · ${Number(value.estimated_size || 0).toLocaleString('zh-CN')} 人` }));
    const contentOptions = (tenantData.contentAssets || []).map(value => ({ value: value.id, label: `${value.name} · ${value.channel} · ${value.version || 'V1'}` }));
    const currentProductId = latest.product_package_id ?? '';
    const currentSnapshotId = latest.audience_snapshot_id ?? '';
    const currentContentIds = latest.content_asset_ids || [];
    openBusinessEditor({
      title: '编辑营销活动', subtitle: `${item.id} · 活动主数据与当前版本配置`, item: {
        ...item,
        audience_snapshot_id: currentSnapshotId,
        product_package_id: currentProductId,
        content_asset_ids: currentContentIds,
        channels: (latest.channels || item.channels || []).join('、'),
        budget_yuan: latest.budget_yuan ?? item.budget_yuan,
      }, width: 'campaign-editor-card',
      fields: [
        { name: 'name', label: '活动名称', type: 'text' },
        { name: 'stage', label: '当前节点', type: 'select', options: ({'机会':['机会','创建'],'创建':['创建','内容','审批'],'内容':['内容','审批','创建'],'审批':['审批','内容'],'执行':['执行','复盘'],'复盘':['复盘'],'归档':['归档']})[item.stage] || [item.stage] },
        { name: 'audience_size', label: '预计客群人数', type: 'number', min: 0 },
        { name: 'budget_yuan', label: '活动预算（元）', type: 'number', min: 0 },
        { name: 'roi_target', label: '目标 ROI', type: 'number', min: 0, step: 0.1 },
        { name: 'channels', label: '执行渠道', type: 'text', required: false, placeholder: '东航App、短信、微信、OTA' },
        { name: 'audience_snapshot_id', label: '客群快照', type: 'select', required: false, options: [{ value: '', label: '暂不绑定' }, ...snapshotOptions] },
        { name: 'product_package_id', label: '活动产品包', type: 'select', required: false, options: [{ value: '', label: '暂不绑定' }, ...productOptions] },
        { name: 'content_asset_ids', label: '内容资产', type: 'multiselect', required: false, options: contentOptions, help: '可多选短信、App 卡片、微信图文等已生成内容。' },
      ],
      save: async values => {
        await request(`/api/campaigns/${encodeURIComponent(item.id)}`, { method: 'PUT', body: JSON.stringify({
          name: String(values.name || '').trim(), stage: values.stage, audience_size: values.audience_size,
          budget_yuan: values.budget_yuan, roi_target: values.roi_target,
          channels: String(values.channels || '').split(/[、,，]/).map(value => value.trim()).filter(Boolean),
          audience_snapshot_id: values.audience_snapshot_id ? Number(values.audience_snapshot_id) : null,
          product_package_id: values.product_package_id ? Number(values.product_package_id) : null,
          content_asset_ids: values.content_asset_ids || [],
        }) });
        toast('活动完整配置已更新'); await refreshAfterBusinessSave();
      }
    });
  }

  function showChannelFeedbackEditor(item) {
    openBusinessEditor({
      title: '编辑渠道回执', subtitle: `${item.external_id || item.channel} · 更新执行结果`, item,
      fields: [
        { name: 'sent_count', label: '已发送人数', type: 'number', min: 0, max: item.target_count },
        { name: 'delivered_count', label: '已送达人数', type: 'number', min: 0 },
        { name: 'clicked_count', label: '点击人数', type: 'number', min: 0 },
        { name: 'converted_count', label: '转化人数', type: 'number', min: 0 },
        { name: 'failed_count', label: '失败人数', type: 'number', min: 0 },
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
    layer.onclick=event=>{if(event.target===layer||event.target.closest('[data-campaign-detail-close]'))layer.hidden=true;};
    try{
      const versions=await request('/api/campaigns/'+encodeURIComponent(item.id)+'/versions');
      const list=q('[data-version-list]',layer);
      if(list)list.innerHTML=versions.length?versions.map((version,index)=>`<div class="${index===0?'current':''}"><b>${escapeHtml(version.version)}</b><span>${new Date(version.created_at).toLocaleString('zh-CN')} · ${escapeHtml(version.status)}</span><small>客群 ${(version.audience_snapshot_id||'未绑定')} · 产品 ${(version.product_package_id||'未绑定')} · ${(version.channels||[]).join('、')||'未配置渠道'}</small><button class="btn" data-campaign-version-view="${version.id}">查看</button>${versions.length>1?`<button class="btn" data-campaign-version-compare="${version.id}">对比当前</button>`:''}</div>`).join(''):'<div class="empty-action">暂无版本记录</div>';
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
    const types=model.object_types||[], relations=model.relation_types||[];
    if(!types.length){host.innerHTML='<div class="ontology-map-empty"><i data-lucide="network"></i><b>暂无本体结构</b><span>完成数据处理或配置语义模型后，这里会展示业务对象与关系。</span></div>';if(window.lucide)lucide.createIcons();return;}
    const moduleLabels={data:'数据来源',aviation:'航空业务',customer:'客户与客群',product:'产品与权益',strategy:'策略规划',marketing:'营销活动',governance:'治理审批',execution:'执行触达',measurement:'效果度量',agent:'智能体',knowledge:'知识底座',semantic:'语义配置'};
    const colors={data:'#5b8db8',aviation:'#3d91b7',customer:'#43a584',product:'#c59435',strategy:'#806dc0',marketing:'#438bc5',governance:'#bd7853',execution:'#4d9e9c',measurement:'#687fac',agent:'#b15e9b',knowledge:'#6c9078',semantic:'#7e8795'};
    const modules=[...new Set(types.map(item=>item.module||'semantic'))];
    const typeMap=new Map(types.map(item=>[item.id,item]));
    const links=[];relations.forEach(rel=>(rel.from_types||[]).forEach(from=>(rel.to_types||[]).forEach(to=>{if(typeMap.has(from)&&typeMap.has(to))links.push({source:from,target:to,label:rel.name||rel.id});})));
    host.innerHTML='<div class="ontology-map-summary"><div><b>本体语义拓扑</b><span>按业务域组织对象类，点击任意节点聚焦上下游关系；节点属性与定义在右侧详情面板查看。</span></div><strong>'+types.length+'<small> 类对象</small><i>·</i>'+relations.length+'<small> 条关系</small></strong></div><div class="ontology-map-toolbar"><label class="ontology-map-search"><i data-lucide="search"></i><input data-ontology-search placeholder="搜索对象类、业务域或属性"></label><select data-ontology-module><option value="all">全部业务域</option>'+modules.map(item=>'<option value="'+escapeHtml(item)+'">'+escapeHtml(moduleLabels[item]||item)+'</option>').join('')+'</select><button type="button" class="btn" data-ontology-reset><i data-lucide="scan-search"></i>重置视图</button><span class="ontology-map-hint">拖动节点 · 滚轮缩放 · 点击聚焦</span></div><div class="ontology-map-legend">'+modules.map(item=>'<span><i style="background:'+colors[item]+'"></i>'+escapeHtml(moduleLabels[item]||item)+'</span>').join('')+'</div><div class="ontology-map-viewport"><svg class="ontology-map-canvas" viewBox="0 0 1240 690" role="img" aria-label="本体语义拓扑图"><defs><marker id="ontology-map-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#9bb6c6"></path></marker></defs><g class="ontology-map-root"><g class="ontology-map-edges"></g><g class="ontology-map-edge-labels"></g><g class="ontology-map-nodes"></g></g></svg></div>';
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
    const simulation=d3.forceSimulation(nodes).force('link',d3.forceLink(simLinks).id(item=>item.id).distance(150).strength(.55)).force('charge',d3.forceManyBody().strength(-430)).force('collide',d3.forceCollide().radius(112)).force('center',d3.forceCenter(width/2,height/2)).force('x',d3.forceX(width/2).strength(.045)).force('y',d3.forceY(height/2).strength(.045)).on('tick',()=>{node.attr('transform',item=>`translate(${item.x-93},${item.y-46})`);updateEdges();});
    q('[data-ontology-search]',host)?.addEventListener('input',applyFilter);q('[data-ontology-module]',host)?.addEventListener('change',applyFilter);q('[data-ontology-reset]',host)?.addEventListener('click',()=>{q('[data-ontology-search]',host).value='';q('[data-ontology-module]',host).value='all';applyFilter();svg.transition().duration(350).call(zoom.transform,d3.zoomIdentity);node.classed('is-selected',false).classed('is-neighbor',false);});
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
    const source=tenantData.graph; if (!source.nodes.length) { canvas.innerHTML='<div class="graph-empty">当前租户暂无营销知识数据，请先在数据接入中投递业务文件。</div>'; return; }
    const box=canvas.getBoundingClientRect(), width=box.width||900, height=box.height||500;
    const typeLabels={opportunity:'营销机会',audience:'客群',customer:'客户',product:'产品包',product_package:'产品包',content:'内容',campaign:'营销活动',channel:'渠道',flight:'航班',flight_segment:'航段',airport:'机场',route:'航线',fare:'运价',cabin:'舱位',result:'营销结果',entity:'业务对象'};
    const nodes=source.nodes.map(item=>({...item,title:displayText(item.label,'未命名对象'),type:String(item.type||'entity').toLowerCase(),typeLabel:typeLabels[String(item.type||'entity').toLowerCase()]||'业务对象',w:172,h:60}));
    const byId=new Map(nodes.map(item=>[item.id,item])); const links=source.edges.filter(item=>byId.has(item.source)&&byId.has(item.target)).map(item=>({...item,source:byId.get(item.source),target:byId.get(item.target),label:displayText(item.relation,'关联')})); const neighbors=new Map(nodes.map(item=>[item.id,new Set()])); links.forEach(item=>{neighbors.get(item.source.id)?.add(item.target.id);neighbors.get(item.target.id)?.add(item.source.id);});
    const svg=d3.select(canvas).append('svg').attr('width',width).attr('height',height), defs=svg.append('defs');
    defs.append('marker').attr('id','production-arrow').attr('viewBox','0 0 8 8').attr('refX',7).attr('refY',4).attr('markerWidth',6).attr('markerHeight',6).attr('orient','auto').append('path').attr('d','M0,0 L8,4 L0,8 z').attr('fill','#93b2c4');
    const root=svg.append('g'); svg.call(d3.zoom().scaleExtent([.55,2]).on('zoom',event=>root.attr('transform',event.transform)));
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
<dd>${Math.round((item.confidence||0)*100)}%</dd>
</dl>
<div class="ai-result">
<b>对象属性</b>
<p>${escapeHtml(Object.entries(item.attributes||{}).slice(0,6).map(([key,value])=>`${key}：${typeof value==='object'?JSON.stringify(value):value}`).join('；')||'暂无扩展属性')}</p>
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
  function queuePipelineFiles(files){if(!canWrite()){toast('当前角色只有只读权限，不能上传数据');return;}const allowed=/\.(txt|md|json|csv|pdf|png|jpe?g|docx?|pptx?|xlsx?|html)$/i;[...files].forEach(file=>{const localId=Date.now()+'-'+Math.random().toString(16).slice(2);if(!allowed.test(file.name)){toast('\u4e0d\u652f\u6301\u6587\u4ef6\uff1a'+file.name);return;}if(file.size>20*1024*1024){toast('\u6587\u4ef6\u8d85\u8fc7 20MB\uff1a'+file.name);return;}const entry={localId,file,status:'queued',progress:0};pipelineFiles.set(localId,entry);uploadPipelineFile(entry);});}

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
      q('#modelDetail').innerHTML=`<div class="usage-metrics"><div><span>请求次数</span><b>${value.request_count.toLocaleString()}</b></div><div><span>输入 Token</span><b>${value.prompt_tokens.toLocaleString()}</b></div><div><span>输出 Token</span><b>${value.completion_tokens.toLocaleString()}</b></div><div><span>总 Token</span><b>${value.total_tokens.toLocaleString()}</b></div></div>${value.by_model.length?`<table class="table usage-table"><tr><th>模型</th><th>请求</th><th>总 Token</th></tr>${value.by_model.map(item=>`<tr><td>${escapeHtml(cleanText(item.model_name, '\u6a21\u578b\u6807\u8bc6\u672a\u8fd4\u56de'))}</td><td>${item.request_count}</td><td>${item.total_tokens.toLocaleString()}</td></tr>`).join('')}</table>`:''} `;
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
<td>${escapeHtml(cleanText(item.provider_type, 'OpenAI Compatible'))}</td>
<td>${escapeHtml(cleanText(item.model_name, '未返回模型名称'))}</td>
<td>
<span class="status ${item.enabled?'good':'warn'}">${item.enabled?'启用':'停用'}</span>
</td>
<td>${item.is_default?'是':'否'}</td>
<td>
<div class="production-actions">
<button class="btn" data-provider-edit="${item.id}">编辑</button><button class="btn" data-provider-test="${item.id}">测试</button><button class="btn" data-provider-models="${item.id}">可用模型</button><button class="btn" data-provider-usage="${item.id}">用量</button>${item.is_default?'':`<button class="btn" data-provider-default="${item.id}">设为默认</button>`}</div>
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
<td>${escapeHtml(roleLabels[item.role] || item.role)}</td>
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
<td>${item.memberships.map(m=>`${escapeHtml(m.name)}（${escapeHtml(roleLabels[m.role] || m.role)}）`).join('、')}</td>
<td>${item.is_platform_admin?'平台管理员':'普通用户'}</td>
</tr>`).join('')}`; }

  function bindProductionActions() {
    document.addEventListener('click', async event => {
      const openCampaign=event.target.closest?.('[data-open-campaign]');
      if(openCampaign){const item=(tenantData.campaigns||[]).find(value=>value.name===openCampaign.dataset.openCampaign);if(item){showCampaignDetail(item);toast('已打开活动详情：'+item.name);}return;}
      const button=event.target.closest('button'); if(!button) return;
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
       if(button.dataset.audiencePersona){const item=(tenantData.personaSegments||[]).find(value=>String(value.id)===String(button.dataset.audiencePersona));if(item)showPersonaDetail(item);return;}
       if(button.dataset.productEdit){const item=(tenantData.productPackages||[]).find(value=>String(value.id)===String(button.dataset.productEdit));if(!item||!canWrite())return;showProductEditor(item);return;}
       if(button.dataset.productDelete){const item=(tenantData.productPackages||[]).find(value=>String(value.id)===String(button.dataset.productDelete));if(!item||!canWrite()||!window.confirm('确认删除产品包“'+item.name+'”？删除后不可恢复。'))return;try{await request(`/api/product-packages/${item.id}`,{method:'DELETE'});toast('产品包“'+item.name+'”已删除');await loadTenantData();}catch(cause){toast(cause.message||'产品包删除失败');}return;}      if(button.dataset.action==='newProduct'){
        if(!canWrite())return;
         showProductEditor({name:'',product_type:'机票组合',description:'',eligibility:'',version:'V1',status:'草稿',valid_from:null,valid_to:null});return;
      }
      if(button.dataset.audienceEdit){const item=(tenantData.audiencePackages||[]).find(value=>String(value.id)===String(button.dataset.audienceEdit));if(!item||!canWrite()||button.disabled)return;showAudiencePackageEditor(item);return;}
      if(button.dataset.audienceTagEdit){const item=(tenantData.audienceTags||[]).find(value=>String(value.id)===String(button.dataset.audienceTagEdit));if(!item||!canWrite())return;showAudienceTagEditor(item);return;}
      if(button.dataset.audienceSnapshot){if(!canWrite()||button.disabled)return;try{const result=await request(`/api/audience-packages/${button.dataset.audienceSnapshot}/snapshots`,{method:'POST'});toast('客群快照 '+result.version+' 已冻结，可用于活动执行');await loadTenantData();}catch(cause){toast(cause.message||'客群快照生成失败');}return;}      if(button.dataset.contentView){const item=(tenantData.contentAssets||[]).find(value=>String(value.id)===String(button.dataset.contentView));if(item)showContentDetail(item);return;}
      if(button.dataset.contentEdit){const item=(tenantData.contentAssets||[]).find(value=>String(value.id)===String(button.dataset.contentEdit));if(!item||!canWrite())return;showContentEditor(item);return;}
       if(button.dataset.channelFeedback){const item=(tenantData.channelTasks||[]).find(value=>String(value.id)===String(button.dataset.channelFeedback));if(!item||!canWrite())return;showChannelFeedbackEditor(item);return;}
      if(button.dataset.contentDelete){const item=(tenantData.contentAssets||[]).find(value=>String(value.id)===String(button.dataset.contentDelete));if(!item||!canWrite()||!window.confirm('确认删除内容“'+item.name+'”？删除后不可恢复。'))return;try{await request(`/api/content-assets/${item.id}`,{method:'DELETE'});toast('内容已删除');await loadTenantData();}catch(cause){toast(cause.message||'内容删除失败');}return;}      if(button.dataset.action==='refreshExecution'&&button.dataset.batchId){try{const result=await request(`/api/execution-batches/${button.dataset.batchId}/status`,{method:'POST',body:JSON.stringify({status:'执行中'})});toast('执行批次已启动：'+result.external_id);await loadTenantData();}catch(cause){toast(cause.message||'批次启动失败');}return;}
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
      if(button.dataset.action==='refreshAudienceCatalog'){if(!canWrite())return;button.disabled=true;try{await loadTenantData();toast('\u753b\u50cf\u76ee\u5f55\u5df2\u540c\u6b65\uff1a'+(tenantData.personaDimensions||[]).length+'\u4e2a\u753b\u50cf\u7ef4\u5ea6');}catch(cause){toast(cause.message||'\u753b\u50cf\u540c\u6b65\u5931\u8d25');}finally{button.disabled=false;}return;}
       if(button.dataset.providerEdit){const item=(tenantData.providers||[]).find(value=>Number(value.id)===Number(button.dataset.providerEdit));if(!item||!isTenantAdmin())return;showProviderEditor(item);return;}
       if(button.dataset.providerTest){const result=await request(`/api/model-providers/${button.dataset.providerTest}/test`,{method:'POST'});toast(result.message||'模型连接正常');}
      if(button.dataset.providerModels){await showProviderModels(Number(button.dataset.providerModels));}
      if(button.dataset.providerUsage){await showProviderUsage(Number(button.dataset.providerUsage));}
      if(button.dataset.providerDefault){await request(`/api/model-providers/${button.dataset.providerDefault}/default`,{method:'POST'});toast('默认模型已更新');await loadTenantData();renderModels();}
       const agentMap={scanOpportunity:'opportunity-insight',naturalAudience:'audience-insight',calculateAudience:'audience-insight',useProduct:'product-match',aiOrchestrate:'activity-orchestration',generateContent:'content-generation',generateReview:'effect-analysis'};
       if(button.dataset.action==='generateContent'){if(!canWrite())return;const campaign=tenantData.campaigns?.[0];try{await request('/api/content-assets',{method:'POST',body:JSON.stringify({campaign_id:campaign?.id||null,name:(campaign?.name||'营销活动')+'·AI内容版本',channel:'App',version:'V1',title:'内容已生成',body:'结合目标客群与活动产品包，为您生成了可审核的东航营销内容。',status:'待审核',generated_by:'content-generation'})});toast('内容生成完成：已写入内容资产并进入审核');await loadTenantData();}catch(cause){toast(cause.message||'内容生成失败');}}
      const domain=agentMap[button.dataset.action]; if(domain&&tenantData.campaigns[0]) request('/api/agent-runs',{method:'POST',body:JSON.stringify({campaign_id:tenantData.campaigns[0].id,domain_id:domain,operator:session.display_name})}).then(result=>{toast(result.summary);showAgentTrace(result);}).catch(cause=>toast(cause.message));
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
     q('#opportunitySourceForm')?.addEventListener('submit',async event=>{event.preventDefault();if(!canWrite())return;const form=event.currentTarget;const values=Object.fromEntries(new FormData(form));values.max_pages=5;values.enabled=true;const sourceId=values.source_id;delete values.source_id;try{await request(sourceId?'/api/opportunity-insight/sources/'+sourceId:'/api/opportunity-insight/sources',{method:sourceId?'PUT':'POST',body:JSON.stringify(values)});form.reset();form.elements.source_id.value='';toast(sourceId?'洞察来源已更新':'洞察来源已新增');await loadTenantData();}catch(cause){toast(cause.message||'来源保存失败');}});
     q('#modelForm')?.addEventListener('submit',async event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.currentTarget));values.enabled=true;values.is_default=!!values.is_default;values.timeout_seconds=60;values.temperature=.3;values.max_tokens=2048;await request('/api/model-providers',{method:'POST',body:JSON.stringify(values)});event.currentTarget.reset();toast('模型配置已保存');await loadTenantData();renderModels();});
    q('#mineruForm')?.addEventListener('submit',async event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.currentTarget));await request('/api/integrations/mineru',{method:'PUT',body:JSON.stringify({display_name:'MinerU 文档解析',base_url:values.base_url||'https://mineru.net',api_key:values.api_key||'',enabled:!!values.enabled,config:{model_version:'vlm',enable_table:true,is_ocr:false}})});event.currentTarget.api_key.value='';toast('MinerU 配置已保存');await loadTenantData();});
    q('#tenantForm')?.addEventListener('submit',async event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.currentTarget));values.code=String(values.code).toUpperCase();await request('/api/platform/tenants',{method:'POST',body:JSON.stringify(values)});event.currentTarget.reset();toast('租户已创建');await loadPlatform();});
  }

  function mountMarketingAssistantLegacy(){
    if(q('#marketingAssistant'))return; const root=document.createElement('div');root.id='marketingAssistant';root.innerHTML='<button class="assistant-fab" title="\u003f\u003f\u003f\u003f\u003f\u003f"><i data-lucide="bot"></i><span>\u003f\u003f\u003f\u003f</span></button><section class="assistant-panel" hidden><header><b>\u003f\u003f\u003f\u003f\u003f\u003f</b><button class="icon-btn" data-assistant-close aria-label="\u003f\u003f"><i data-lucide="x"></i></button></header><div class="assistant-messages"><div class="assistant-message assistant">\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f</div></div><form><input name="message" placeholder="\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f" autocomplete="off"><button class="btn primary">\u003f\u003f</button></form></section>';document.body.appendChild(root);const fab=q('.assistant-fab',root),panel=q('.assistant-panel',root),messages=q('.assistant-messages',root);fab.addEventListener('click',()=>{panel.hidden=!panel.hidden;if(!panel.hidden)q('input',root).focus();});q('[data-assistant-close]',root).addEventListener('click',()=>panel.hidden=true);q('form',root).addEventListener('submit',async e=>{e.preventDefault();const input=q('input',root),message=input.value.trim();if(!message)return;messages.insertAdjacentHTML('beforeend','<div class="assistant-message user">'+escapeHtml(message)+'</div>');input.value='';messages.insertAdjacentHTML('beforeend','<div class="assistant-message assistant pending">\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u003f\u002e\u002e\u002e</div>');const pending=messages.lastElementChild;try{const result=await request('/api/agent-chat',{method:'POST',body:JSON.stringify({message,domain_id:'marketing-copilot',history:[]})});pending.classList.remove('pending');pending.innerHTML=escapeHtml(cleanText(result.answer,'\u0041\u0067\u0065\u006e\u0074\u003f\u003f\u003f\u003f\u003f\u003f\u003f'))+(result.trace?.length?'<details><summary>\u003f\u003f\u003f\u003f\u003f\u003f</summary><pre>'+escapeHtml(JSON.stringify(result.trace,null,2))+'</pre></details>':'');}catch(err){pending.classList.remove('pending');pending.textContent='\u003f\u003f\u003f\u003f\u003f'+(err.message||'\u003f\u003f\u003f\u003f\u003f\u003f\u003f');}});if(window.lucide)lucide.createIcons();
  }

function mountMarketingAssistantV2(){
    if(q('#marketingAssistant')) q('#marketingAssistant').remove();
    const root=document.createElement('div');
    root.id='marketingAssistant';
    root.innerHTML=`<button class="assistant-fab" title="打开营销助手" aria-label="打开营销助手"><i data-lucide="bot"></i><span>营销助手</span></button>
      <section class="assistant-panel" hidden aria-label="AI营销助手对话框">
        <header class="assistant-drag-handle">
          <div class="assistant-title"><div><b>AI营销助手</b><small>东航营销业务协同</small></div></div>
          <div class="assistant-header-actions">
            <span class="assistant-live"><i></i>在线</span>
            <button type="button" class="icon-btn" data-assistant-collapse aria-label="折叠对话框" title="折叠"><i data-lucide="minus"></i></button>
            <button type="button" class="icon-btn" data-assistant-close aria-label="关闭对话框" title="关闭"><i data-lucide="x"></i></button>
          </div>
        </header>
        <div class="assistant-messages">
          <div class="assistant-message assistant"><div><b>你好，我是东航 AI 营销助手</b><p>可以查询营销知识与本体关系，分析机会、客群和产品，并协助查看活动执行状态。</p><div class="assistant-suggestions"><button data-assistant-suggest="当前有哪些高价值营销机会？">高价值机会</button><button data-assistant-suggest="查询近期数据处理任务">流水线进度</button></div></div></div>
        </div>
        <form><textarea name="message" rows="1" placeholder="输入营销问题或操作指令" autocomplete="off"></textarea><button class="btn primary" aria-label="发送"><i data-lucide="arrow-up"></i></button></form>
      </section>`;
    document.body.appendChild(root);
    const fab=q('.assistant-fab',root),panel=q('.assistant-panel',root),header=q('.assistant-drag-handle',root),messages=q('.assistant-messages',root),form=q('form',root),input=q('textarea',root),collapseButton=q('[data-assistant-collapse]',root);
    const toolNames={search_marketing_knowledge:'营销知识检索',query_marketing_ontology:'本体关系查询',inspect_campaign:'活动状态查询',list_available_products:'产品包查询',inspect_data_pipeline:'数据处理进度查询',run_marketing_domain:'智能域调用',planner_conclusion:'生成业务结论'};
    const traceLabel={'harness/context-loaded':'加载业务上下文','agent/planning':'规划下一步','agent/decision':'选择业务动作','harness/model-started':'调用大模型','harness/model-finished':'模型输出完成','harness/tool-started':'调用业务能力','harness/tool-finished':'业务能力返回','harness/tool-failed':'业务能力调用失败','harness/json-parsed':'解析执行计划','model/provider-fallback':'切换备用模型'};
    const traceDetail=item=>{
      if(item.event==='agent/planning') return '第 '+(item.step||1)+' 步 · '+(item.summary||'分析问题并选择下一步业务工具');
      if(item.event==='agent/decision'){const action=toolNames[item.action]||item.action||'继续分析';return '第 '+(item.step||1)+' 步 · '+action+(item.reason?' · '+item.reason:'');}
      if(item.event==='harness/context-loaded') return '已载入知识、本体、活动与授权工具上下文';
      if(item.event==='harness/tool-started') return '正在调用：'+(toolNames[item.tool]||item.tool||'业务能力');
      if(item.event==='harness/tool-finished') return '已完成：'+(toolNames[item.tool]||item.tool||'业务能力');
      if(item.event==='harness/tool-failed') return (toolNames[item.tool]||item.tool||'业务能力')+'执行失败，请检查服务状态';
      if(item.event==='harness/model-started') return item.mode==='stream'?'正在流式生成最终答复':'正在生成业务执行计划';
      if(item.event==='harness/model-finished'){const tokens=item.total_tokens?(' · '+item.total_tokens+' tokens'):'';return (item.mode==='stream'?'最终答复生成完成':'执行计划生成完成')+tokens;}
      if(item.event==='harness/json-parsed') return '执行计划已校验，可进入下一步';
      if(item.event==='model/provider-fallback') return '主模型暂不可用，已切换备用模型';
      return '步骤已完成';
    };
    const addTrace=(traceBox,item)=>{
      const label=traceLabel[item.event]||'业务处理';
      traceBox.insertAdjacentHTML('beforeend','<div class="assistant-trace-row"><span class="assistant-trace-dot"></span><div><b>'+escapeHtml(label)+'</b><small>'+new Date(item.timestamp||Date.now()).toLocaleTimeString('zh-CN',{hour12:false})+'</small><p>'+escapeHtml(traceDetail(item))+'</p></div></div>');
      traceBox.scrollTop=traceBox.scrollHeight;
    };
    const stateKey='ceair-marketing-assistant-layout-v2';
    const readLayout=()=>{try{return JSON.parse(localStorage.getItem(stateKey)||'{}')}catch{return {}}};
    const saveLayout=()=>{const panelRect=panel.getBoundingClientRect(),fabRect=fab.getBoundingClientRect();localStorage.setItem(stateKey,JSON.stringify({panel:{left:panelRect.left,top:panelRect.top,width:panelRect.width,height:panelRect.height},fab:{left:fabRect.left,top:fabRect.top},collapsed:panel.classList.contains('is-collapsed')}));};
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
    const send=async message=>{
      if(!message||form.dataset.busy)return;
      form.dataset.busy='1';input.disabled=true;conversation.push({role:'user',content:message});
      messages.insertAdjacentHTML('beforeend','<div class="assistant-message user"><div>'+escapeHtml(message)+'</div></div>');
      const wrap=document.createElement('div');wrap.className='assistant-message assistant live-message';wrap.innerHTML='<div class="assistant-live-body"><div class="assistant-streaming"><span></span><span></span><span></span><b>正在分析业务上下文</b></div><details class="assistant-trace-details" open><summary><b>执行过程</b><span>实时</span></summary><div class="assistant-trace-list"></div></details><p class="assistant-answer is-streaming"></p></div>';messages.appendChild(wrap);
      const traceList=q('.assistant-trace-list',wrap),answer=q('.assistant-answer',wrap),streaming=q('.assistant-streaming',wrap);messages.scrollTop=messages.scrollHeight;
      try{
        const response=await fetch(`${mount}/api/agent-chat/stream`,{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${session?.access_token||''}`,'X-Tenant-ID':String(activeTenant()?.id||'')},body:JSON.stringify({message,domain_id:'marketing-copilot',history:conversation.slice(-12,-1)})});
        if(!response.ok)throw new Error((await response.json().catch(()=>({}))).detail||'智能体连接失败');
        const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',finalAnswer='';
        const handleFrame=frame=>{const lines=frame.split(/\r?\n/),event=(lines.find(line=>line.startsWith('event:'))||'event: message').slice(6).trim(),dataText=lines.filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trim()).join('');if(!dataText)return;const value=JSON.parse(dataText);if(event==='trace'){addTrace(traceList,value);const status=q('.assistant-streaming b',wrap);if(status)status.textContent=value.event==='harness/model-started'&&value.mode==='stream'?'正在生成答复':'正在'+(traceLabel[value.event]||'处理业务步骤');}if(event==='token'){finalAnswer+=value.text||'';answer.textContent=finalAnswer;messages.scrollTop=messages.scrollHeight;}if(event==='complete'){streaming?.remove();answer.classList.remove('is-streaming');conversation.push({role:'assistant',content:finalAnswer||value.answer||''});const summary=q('.assistant-trace-details summary span',wrap);if(summary)summary.textContent='已完成';if(value.sources?.length)answer.insertAdjacentHTML('afterend','<div class="assistant-sources">已引用 '+value.sources.length+' 条业务依据</div>');}if(event==='error'){streaming?.remove();answer.classList.remove('is-streaming');answer.textContent=value.message||'智能体运行失败';}};
        while(true){const part=await reader.read();buffer+=decoder.decode(part.value||new Uint8Array(),{stream:!part.done});const frames=buffer.split(/\r?\n\r?\n/);buffer=frames.pop()||'';frames.forEach(handleFrame);if(part.done)break;}if(buffer.trim())handleFrame(buffer);
      }catch(err){streaming?.remove();answer.classList.remove('is-streaming');answer.textContent='请求失败：'+(err.message||'请稍后重试');}
      finally{form.dataset.busy='';input.disabled=false;input.focus();messages.scrollTop=messages.scrollHeight;}
    };
    fab.addEventListener('click',()=>{if(suppressFabClick){suppressFabClick=false;return;}panel.hidden=!panel.hidden;if(!panel.hidden){restoreLayout();setCollapsed(false);input.focus();}});
    q('[data-assistant-close]',root).addEventListener('click',()=>{panel.hidden=true;saveLayout();});
    collapseButton.addEventListener('click',()=>setCollapsed(!panel.classList.contains('is-collapsed')));
    qa('[data-assistant-suggest]',root).forEach(button=>button.addEventListener('click',()=>send(button.dataset.assistantSuggest)));
    form.addEventListener('submit',event=>{event.preventDefault();const value=input.value.trim();if(!value)return;input.value='';input.style.height='auto';send(value);});
    input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();form.requestSubmit();}});
    input.addEventListener('input',()=>{input.style.height='auto';input.style.height=Math.min(input.scrollHeight,104)+'px';});
    makeDraggable(fab,fab,true);makeDraggable(header,panel,false);
    if(window.ResizeObserver)new ResizeObserver(()=>{if(!panel.hidden&&!panel.classList.contains('is-dragging'))saveLayout();}).observe(panel);
    window.addEventListener('resize',()=>{const panelRect=panel.getBoundingClientRect(),fabRect=fab.getBoundingClientRect();positionElement(panel,panelRect.left,panelRect.top);positionElement(fab,fabRect.left,fabRect.top);});
    restoreLayout();if(window.lucide)lucide.createIcons();
  }

  window.createProductionCampaign = async function(name) { return request("/api/campaigns", {method: "POST", body: JSON.stringify({name: name, stage: "机会"})}); };
  async function loadTenantData(){updateIdentity();const currentCampaignId=tenantData.campaigns?.[0]?.id||'ACT-2026-0921';const paths=['/api/campaigns','/api/graph','/api/imports','/api/data-pipelines','/api/model-providers','/api/agent-domains','/api/agent-runs','/api/opportunities','/api/opportunity-insight/sources','/api/opportunity-insight/runs','/api/audience-tags','/api/audience-packages','/api/persona-dimensions','/api/persona-segments','/api/product-packages','/api/product-catalog','/api/content-assets','/api/audience-snapshots','/api/approvals','/api/execution-batches','/api/channel-tasks','/api/knowledge/documents'];const values=await Promise.all(paths.map(path=>request(path)));let mineru=null;if(activeTenant()?.role==='admin'){try{mineru=await request('/api/integrations/mineru');}catch{mineru=null;}}const [campaigns,graph,imports,pipelines,providers,domains,runs,opportunities,opportunitySources,opportunityRuns,audienceTags,audiencePackages,personaDimensions,personaSegments,productPackages,productCatalog,contentAssets,audienceSnapshots,approvals,executionBatches,channelTasks,documents]=values;let effectSummary={};try{effectSummary=await request(`/api/campaigns/${encodeURIComponent(campaigns[0]?.id||currentCampaignId)}/effect-summary`);}catch{effectSummary={};}tenantData={campaigns,graph,imports,pipelines,providers,domains,runs,opportunities,opportunitySources,opportunityRuns,audienceTags,audiencePackages,personaDimensions,personaSegments,productPackages,productCatalog,contentAssets,audienceSnapshots,approvals,executionBatches,channelTasks,documents,effectSummary,mineru};renderOpportunities();renderOpportunityInsightPanel();renderAudienceStructure();renderKnowledgeDocuments();renderCampaigns();renderProducts();renderContents();renderApprovals();renderExecution();renderFeedback();renderDynamicGraph();renderPipelineQueue();renderImports();renderModels();renderMineru();const hasActive=pipelines.some(item=>['queued','running'].includes(item.status));clearTimeout(pipelinePollTimer);if(hasActive)pipelinePollTimer=setTimeout(()=>refreshPipelines().catch(()=>{}),1500);const hasInsight=opportunityRuns.some(item=>['queued','running'].includes(item.status));clearTimeout(opportunityPollTimer);if(hasInsight)opportunityPollTimer=setTimeout(()=>loadTenantData().catch(()=>{}),1500);}
  async function initializeSession(){
    try{mountMarketingAssistantV2();setTimeout(()=>{if(!q('#marketingAssistant')){try{mountMarketingAssistantV2();}catch(cause){console.error('assistant remount failed',cause);}}},0);}catch(cause){console.error('营销助手挂载失败',cause);}
    try{injectNavigation();}catch(cause){console.error('导航扩展失败',cause);}
    try{bindProductionActions();}catch(cause){console.error('生产功能绑定失败',cause);}
    try{await loadTenantData();}catch(cause){console.error('租户数据加载失败',cause);toast(cause.message||'租户数据加载失败，请稍后重试');}
    if(window.lucide)lucide.createIcons();
  }
  function boot(){try{session=JSON.parse(localStorage.getItem(sessionKey)||'null');}catch{session=null;}if(!session)return createLogin();tenantId=session.tenants?.[0]?.id || null; localStorage.removeItem(tenantKey);q('.app').style.visibility='visible';initializeSession().catch(cause=>{console.error(cause);toast(cause.message||'租户数据加载失败，请稍后重试');});}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
