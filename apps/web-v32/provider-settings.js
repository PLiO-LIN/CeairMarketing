(function () {
  'use strict';
  const vendors = [
    { id: 'bailian', name: '阿里云百炼', host: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: ['qwen3.8-flash', 'qwen-plus', 'qwen-max'], matches: /aliyuncs|bailian|百炼/ },
    { id: 'token-plan', logo: 'bailian', name: '阿里云 Token Plan', host: 'https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1', models: ['qwen3.8-flash', 'qwen3.8-max', 'auto'], matches: /token-plan|token plan/i },
    { id: 'openai', name: 'OpenAI', host: 'https://api.openai.com/v1', models: [], matches: /api\.openai\.com|openai/i },
    { id: 'deepseek', name: 'DeepSeek', host: 'https://api.deepseek.com/v1', models: ['deepseek-chat', 'deepseek-reasoner'], matches: /deepseek/i },
    { id: 'silicon', name: '硅基流动', host: 'https://api.siliconflow.cn/v1', models: [], matches: /siliconflow|硅基/ },
    { id: 'moonshot', name: 'Kimi', host: 'https://api.moonshot.cn/v1', models: ['kimi-k2.5'], matches: /moonshot|kimi/i },
    { id: 'zhipu', name: '智谱', host: 'https://open.bigmodel.cn/api/paas/v4', models: ['glm-5'], matches: /bigmodel|zhipu|智谱/i },
    { id: 'volcengine', name: '火山引擎', host: 'https://ark.cn-beijing.volces.com/api/v3', models: [], matches: /volces|volcengine|火山/ },
    { id: 'google', name: 'Google Gemini', host: 'https://generativelanguage.googleapis.com/v1beta/openai', models: [], matches: /googleapis|gemini/i },
    { id: 'custom', name: '自定义兼容服务', host: '', models: [] },
    { id: 'mock', name: '内置受控模型', host: '', models: ['ceair-governed-mock-v1'] },
  ];
  window.createProviderSettings = function (api) {
    const { request, escapeHtml: esc, bindModal, toast } = api;
    let tenant = null, selected = null;
    const drafts = new Map(), modelLists = new Map();
    const $ = (selector, root = document) => root.querySelector(selector);
    const vendorFor = item => item.provider_type === 'mock' ? vendors.at(-1) : vendors.find(v => v.id === 'token-plan' && v.matches.test(item.base_url + ' ' + item.display_name)) || vendors.find(v => v.matches?.test(item.base_url + ' ' + item.display_name)) || vendors.find(v => v.id === 'custom');
    const logo = vendor => `<img class="provider-logo" src="./brand/${vendor.id === 'mock' ? 'dongdong-robot.svg' : vendor.id === 'custom' ? 'providers/custom.svg' : 'providers/' + (vendor.logo || vendor.id) + '.svg'}" alt="${esc(vendor.name)} Logo">`;
    function syncTenant() {
      if (tenant !== api.tenant()) { tenant = api.tenant(); selected = null; drafts.clear(); modelLists.clear(); }
    }
    function modal(title, body) {
      const layer = document.createElement('div'); layer.className = 'production-modal provider-modal';
      layer.innerHTML = `<div class="production-modal-card provider-modal-card"><div class="production-modal-head"><b>${esc(title)}</b><button class="btn" type="button" data-close>关闭</button></div><div class="production-modal-body">${body}</div></div>`;
      document.body.append(layer); bindModal(layer); return layer;
    }
    function read(form) {
      const data = Object.fromEntries(new FormData(form));
      for (const key of ['timeout_seconds', 'temperature', 'max_tokens']) data[key] = Number(data[key]);
      data.enabled = form.elements.enabled.checked; data.is_default = form.elements.is_default.checked;
      delete data.vendor; return data;
    }
    function options(form, item, discovered) {
      const select = form.elements.model_name, current = select.value || item.model_name;
      const ids = [...new Set([current, ...(discovered || vendorFor(item).models).map(m => typeof m === 'string' ? m : m.id)].filter(Boolean))];
      select.innerHTML = ids.map(id => `<option value="${esc(id)}">${esc(id)}</option>`).join('') || '<option value="">请选择模型</option>';
      if (current) select.value = current;
    }
    function formHTML(item, creating = false) {
      const vendor = vendorFor(item);
      return `<form class="provider-form" data-provider-form>
        ${creating ? `<label>模型厂商<select name="vendor">${vendors.map(v => `<option value="${v.id}">${esc(v.name)}</option>`).join('')}</select></label>` : ''}
        <div class="provider-config-heading">${logo(vendor)}<div><h2>${esc(item.display_name || vendor.name)}</h2><span>${esc(vendor.name)}</span></div>${item.is_default ? '<span class="provider-badge">默认服务</span>' : ''}</div>
        <label>配置名称<input name="display_name" value="${esc(item.display_name)}" required minlength="2" maxlength="80"></label>
        <input type="hidden" name="provider_type" value="${esc(item.provider_type)}">
        <label>API Key<input name="api_key" type="password" autocomplete="new-password" value="${esc(item.api_key || '')}" placeholder="${item.api_key_configured ? '已配置 · 留空保持原密钥' : '输入 API Key'}"></label>
        <label>服务地址<input name="base_url" type="url" value="${esc(item.base_url)}" placeholder="https://…/v1" ${item.provider_type === 'mock' ? '' : 'required'}></label>
        <div class="provider-model-field"><label>对话模型<select name="model_name" required aria-label="对话模型"></select></label><button class="btn" type="button" data-discover>可用模型</button><button class="btn" type="button" data-custom-model>自定义</button></div>
        <div class="provider-toggles"><label><input name="enabled" type="checkbox" ${item.enabled ? 'checked' : ''}>启用服务</label><label><input name="is_default" type="checkbox" ${item.is_default ? 'checked' : ''}>设为默认</label></div>
        <details class="provider-advanced"><summary>高级参数</summary><div class="provider-parameters"><label>超时（秒）<input name="timeout_seconds" type="number" min="5" max="300" required value="${item.timeout_seconds}"></label><label>Temperature<input name="temperature" type="number" min="0" max="2" step="0.1" required value="${item.temperature}"></label><label>最大输出 Token<input name="max_tokens" type="number" min="128" max="32768" required value="${item.max_tokens}"></label></div></details>
        <div class="provider-inline-status" role="status" aria-live="polite"></div>
        <div class="provider-footer"><button class="btn primary" type="submit">保存配置</button>${creating ? '' : '<button class="btn" type="button" data-test>测试对话与工具</button><button class="btn" type="button" data-usage>调用用量</button>'}</div>
      </form>`;
    }
    function status(form, message, error = false) { const el = $('.provider-inline-status', form); el.textContent = message; el.classList.toggle('is-error', error); }
    function bindForm(form, item, { layer } = {}) {
      options(form, item, modelLists.get(item.id));
      form.addEventListener('input', () => { if (item.id) { drafts.set(item.id, read(form)); form.dataset.dirty = 'true'; } });
      form.addEventListener('change', () => { if (item.id) { drafts.set(item.id, read(form)); form.dataset.dirty = 'true'; } });
      $('[data-discover]', form).onclick = () => showModels(form, item);
      $('[data-custom-model]', form).onclick = () => {
        const custom = modal('自定义模型标识', '<form class="provider-form" data-custom-form><label>模型标识<input name="model_id" required maxlength="120" placeholder="填写厂商模型 ID 或部署 ID"></label><button class="btn primary" type="submit">加入下拉选项</button></form>');
        $('[data-custom-form]', custom).onsubmit = e => { e.preventDefault(); const value = e.target.elements.model_id.value.trim(); if (!value) return; form.elements.model_name.add(new Option(value, value, false, true)); form.dispatchEvent(new Event('input')); custom.__closeProductionModal(); };
      };
      form.onsubmit = async e => {
        e.preventDefault(); if (!api.canEdit()) return;
        const button = $('[type=submit]', form), startedTenant = tenant, values = read(form);
        if (!values.api_key) delete values.api_key;
        button.disabled = true; status(form, '正在保存…');
        try {
          const saved = await request(item.id ? `/api/model-providers/${item.id}` : '/api/model-providers', { method: item.id ? 'PUT' : 'POST', body: JSON.stringify(values) });
          if (startedTenant !== api.tenant()) return;
          drafts.delete(item.id); modelLists.delete(item.id); selected = saved.id;
          form.dataset.dirty = ''; form.elements.api_key.value = ''; layer?.__closeProductionModal();
          toast('模型配置已保存'); await api.onSaved(); render(true);
        } catch (cause) { status(form, cause.message, true); }
        finally { button.disabled = false; }
      };
      const test = $('[data-test]', form);
      if (test) test.onclick = async () => {
        if (form.dataset.dirty === 'true') { status(form, '请先保存配置，再测试当前模型。', true); return; }
        test.disabled = true; status(form, '正在测试对话、流式回复与只读工具调用…');
        try { const result = await request(`/api/model-providers/${item.id}/test`, { method: 'POST' }); status(form, result.message, !result.ok); }
        catch (cause) { status(form, cause.message, true); } finally { test.disabled = false; }
      };
      const usage = $('[data-usage]', form); if (usage) usage.onclick = () => showUsage(item);
      if (layer) form.elements.vendor.onchange = () => {
        const vendor = vendors.find(v => v.id === form.elements.vendor.value);
        form.elements.display_name.value = vendor.name; form.elements.base_url.value = vendor.host;
        form.elements.provider_type.value = vendor.id === 'mock' ? 'mock' : 'openai-compatible';
        form.elements.base_url.required = vendor.id !== 'mock'; form.elements.api_key.value = '';
        const next = { ...read(form), model_name: vendor.models[0] || '' }; form.elements.model_name.innerHTML = '';
        options(form, next, vendor.models); $('.provider-config-heading', form).innerHTML = `${logo(vendor)}<div><h2>${esc(vendor.name)}</h2></div>`;
      };
    }
    async function showModels(form, item) {
      const layer = modal('可用模型', '<div class="provider-model-search"><input aria-label="搜索模型" placeholder="搜索模型"><button class="btn" type="button" data-refresh>刷新</button></div><div class="provider-model-status" role="status"></div><div class="provider-model-results"></div>');
      const search = $('input', layer), list = $('.provider-model-results', layer), message = $('.provider-model-status', layer);
      let models = [], busy = false;
      const draw = () => {
        const matches = models.filter(m => m.id.toLowerCase().includes(search.value.trim().toLowerCase()));
        list.innerHTML = matches.map(m => `<button class="provider-model-option" type="button" data-model-id="${esc(m.id)}"><span><b>${esc(m.id)}</b><small>${esc(m.owned_by || '')}</small></span><span>${m.id === form.elements.model_name.value ? '已选' : '选择'}</span></button>`).join('') || '<div class="provider-empty">没有匹配模型</div>';
      };
      const discover = async () => {
        if (busy) return; busy = true; const startedTenant = tenant; const button = $('[data-refresh]', layer); button.disabled = true; message.textContent = '正在从厂商接口获取模型…';
        try {
          const values = read(form);
          const result = await request('/api/model-providers/discover', { method: 'POST', body: JSON.stringify({ provider_id: item.id || null, provider_type: values.provider_type, base_url: values.base_url, api_key: values.api_key || '', model_name: values.model_name, timeout_seconds: values.timeout_seconds }) });
          if (startedTenant !== api.tenant() || !layer.isConnected) return;
          models = result.models || []; if (item.id) modelLists.set(item.id, models); options(form, values, models);
          message.textContent = `${models.length} 个模型 · 对话需支持工具调用`; message.classList.remove('is-error'); draw();
        } catch (cause) { message.textContent = cause.message; message.classList.add('is-error'); }
        finally { busy = false; button.disabled = false; }
      };
      search.oninput = draw; $('[data-refresh]', layer).onclick = discover;
      list.onclick = e => { const button = e.target.closest('[data-model-id]'); if (!button) return; form.elements.model_name.value = button.dataset.modelId; form.dispatchEvent(new Event('input')); status(form, '已选择模型，保存配置后生效。'); layer.__closeProductionModal(); };
      await discover();
    }
    async function showUsage(item) {
      const layer = modal('调用用量 · ' + item.display_name, '<div data-usage-body role="status">正在加载…</div>'), body = $('[data-usage-body]', layer);
      try { const data = await request(`/api/model-providers/${item.id}/usage`); body.innerHTML = `<div class="usage-metrics">${[['请求次数', data.request_count], ['输入 Token', data.prompt_tokens], ['输出 Token', data.completion_tokens], ['总 Token', data.total_tokens]].map(([label, n]) => `<div><span>${label}</span><b>${Number(n).toLocaleString()}</b></div>`).join('')}</div><table class="table"><tr><th>模型</th><th>请求</th><th>Token</th></tr>${data.by_model.map(m => `<tr><td>${esc(m.model_name)}</td><td>${m.request_count}</td><td>${m.total_tokens.toLocaleString()}</td></tr>`).join('')}</table>`; }
      catch (cause) { body.textContent = cause.message; body.classList.add('is-error'); }
    }
    function render(force = false) {
      syncTenant(); const list = $('#modelTable'), host = $('#providerConfig'); if (!list || !host) return;
      const providers = api.providers(); if (!providers.some(p => p.id === selected)) selected = providers.find(p => p.is_default)?.id || providers[0]?.id;
      $('#modelCount').textContent = providers.length + ' 个';
      list.innerHTML = providers.map(item => `<button class="provider-list-item ${item.id === selected ? 'is-selected' : ''}" type="button" data-select-provider="${item.id}" aria-pressed="${item.id === selected}" title="${esc(item.display_name)} · ${esc(item.model_name)}">${logo(vendorFor(item))}<span><b>${esc(item.display_name)}</b><small>${esc(item.model_name)}</small></span><em>${item.is_default ? '默认' : item.enabled ? '启用' : '停用'}</em></button>`).join('');
      list.onclick = e => { const button = e.target.closest('[data-select-provider]'); if (!button) return; const form = $('[data-provider-form]', host); if (form?.dataset.dirty === 'true') drafts.set(selected, read(form)); selected = Number(button.dataset.selectProvider); render(true); };
      const item = providers.find(p => p.id === selected);
      if (!item) { host.innerHTML = '<div class="provider-empty">添加模型服务后开始配置</div>'; return; }
      if (!force && Number(host.dataset.provider) === selected && $('[data-provider-form]', host)) return;
      host.dataset.provider = selected; const draft = drafts.get(selected); host.innerHTML = formHTML({ ...item, ...draft });
      const form = $('[data-provider-form]', host); bindForm(form, { ...item, ...draft }); if (draft) form.dataset.dirty = 'true';
      if (!api.canEdit()) form.querySelectorAll('input,select,button').forEach(el => { el.disabled = true; });
    }
    function create() {
      syncTenant(); if (!api.canEdit()) return;
      const preset = vendors[0], item = { display_name: preset.name, provider_type: 'openai-compatible', base_url: preset.host, model_name: preset.models[0], timeout_seconds: 180, temperature: 0.3, max_tokens: 8192, enabled: true, is_default: false };
      const layer = modal('添加模型服务', formHTML(item, true)); bindForm($('[data-provider-form]', layer), item, { layer });
    }
    return { render, create };
  };
})();
