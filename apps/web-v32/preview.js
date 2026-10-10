/* 内页工作台界面。首页保持东东原布局，进入业务内页后启用统一工作台导航。 */
(function () {
  'use strict';

  const groups = [
    { key: 'cockpit', label: '营销驾驶舱', icon: 'layout-dashboard', items: [['overview', '营销总览', 'gauge'], ['campaigns', '活动中心', 'send']] },
    { key: 'planning', label: '活动策划', icon: 'route', items: [['opportunities', '机会工作台', 'radar'], ['audiences', '客群画像', 'users-round'], ['products', '产品与权益', 'package'], ['contents', '内容工坊', 'file-pen-line']] },
    { key: 'execution', label: '活动执行', icon: 'workflow', items: [['approvals', '审批与发布', 'badge-check'], ['execution', '执行监控', 'activity'], ['feedback', '效果复盘', 'chart-no-axes-combined']] },
    { key: 'governance', label: '治理中心', icon: 'shield-check', items: [['search', '智能检索', 'search'], ['graph', '知识中心', 'brain-circuit'], ['permissions', '权限与审计', 'key']] },
  ];
  const titleMap = { smartspace: '智能空间', dongdong: '东东AI伙伴', overview: '营销总览', campaigns: '活动中心', opportunities: '机会工作台', audiences: '客群画像', products: '产品与权益', contents: '内容工坊', approvals: '审批与发布', execution: '执行监控', feedback: '效果复盘', search: '智能检索', graph: '知识中心', permissions: '权限与审计' };
  let sidebar;
  let sidebarToggle;
  let refreshTimer;
  let originalLogoSrc;
  let lastActiveView;
  const collapseKey = 'ceair-sidebar-groups';
  let collapsed;
  try { collapsed = JSON.parse(localStorage.getItem(collapseKey) || '{"planning":true,"execution":true,"governance":true}'); } catch { collapsed = {}; }
  if (!collapsed || typeof collapsed !== 'object' || Array.isArray(collapsed)) collapsed = {};

  function query(selector, root = document) { return root.querySelector(selector); }
  function queryAll(selector, root = document) { return Array.from(root.querySelectorAll(selector)); }
  function innerView() { return !query('#dongdong.active'); }
  function appReady() { const app = query('.app'); return !!app && getComputedStyle(app).visibility !== 'hidden'; }

  function buildSidebar() {
    if (sidebar) return sidebar;
    sidebar = document.createElement('aside');
    sidebar.className = 'preview-sidebar';
    sidebar.id = 'previewSidebar';
    sidebar.setAttribute('aria-label', '内页导航');
    sidebar.innerHTML = `<div class="preview-sidebar-head"><button class="preview-home" type="button" data-view="dongdong"><i data-lucide="bot"></i><span>东东首页</span></button><button class="preview-home" type="button" data-view="smartspace"><i data-lucide="messages-square"></i><span>智能空间</span></button></div><div class="preview-sidebar-scroll">${groups.map(group => `<section class="preview-nav-group" data-preview-group="${group.key}"><button type="button" class="preview-nav-label" data-toggle-group="${group.key}" aria-expanded="${!collapsed[group.key]}" aria-controls="preview-group-${group.key}"><i data-lucide="${group.icon}"></i><span>${group.label}</span><i class="preview-group-chevron" data-lucide="chevron-down"></i></button><div class="preview-nav-items" id="preview-group-${group.key}"${collapsed[group.key] ? ' hidden' : ''}>${group.items.map(([view, label, icon]) => `<button type="button" data-view="${view}" data-preview-view="${view}"><i data-lucide="${icon}"></i><span>${label}</span></button>`).join('')}</div></section>`).join('')}</div><div class="preview-sidebar-foot"><div class="preview-tenant"><span class="preview-avatar">用</span><div><b>当前工作区</b><small>当前用户</small></div></div></div>`;
    const app = query('.app');
    app?.insertBefore(sidebar, query('.main'));
    if (!sidebarToggle && app) {
      sidebarToggle = document.createElement('button');
      sidebarToggle.type = 'button';
      sidebarToggle.className = 'preview-sidebar-toggle';
      sidebarToggle.setAttribute('aria-controls', sidebar.id);
      sidebarToggle.setAttribute('aria-expanded', 'false');
      sidebarToggle.setAttribute('aria-label', '打开内页导航');
      sidebarToggle.textContent = '导航';
      app.insertBefore(sidebarToggle, sidebar);
      sidebarToggle.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        setSidebarOpen(sidebarToggle.getAttribute('aria-expanded') !== 'true');
      });
    }
    if (window.lucide) window.lucide.createIcons({ root: sidebar });
    return sidebar;
  }

  function syncProductionItems() {
    if (!sidebar) return;
    const host = query('[data-preview-group="governance"] .preview-nav-items', sidebar);
    if (!host) return;
    const dynamic = [
      ['imports', '数据接入', 'database'],
      ['models', '模型配置', 'server-cog'],
      ['tenants', '租户与用户', 'building-2'],
    ];
    dynamic.forEach(([view, label, icon]) => {
      const source = query(`.topnav [data-view="${view}"]`);
      if (!source) return;
      let button = query(`[data-preview-view="${view}"]`, host);
      if (!button) {
        button = document.createElement('button');
        button.type = 'button';
        button.dataset.view = view;
        button.dataset.previewView = view;
        button.innerHTML = `<i data-lucide="${icon}"></i><span>${label}</span>`;
        host.appendChild(button);
        if (window.lucide) window.lucide.createIcons({ root: button });
      }
      button.hidden = getComputedStyle(source).display === 'none';
    });
  }

  function setSidebarOpen(open) {
    if (!sidebar || !sidebarToggle) return;
    const narrow = window.matchMedia('(max-width: 820px)').matches;
    const expanded = narrow && !!open;
    sidebar.classList.toggle('is-open', expanded);
    sidebarToggle.setAttribute('aria-expanded', String(expanded));
    sidebarToggle.setAttribute('aria-label', expanded ? '收起内页导航' : '打开内页导航');
    sidebar.setAttribute('aria-hidden', narrow ? String(!expanded) : 'false');
  }

  function buildPreviewControls() {
    const topbar = query('.topbar');
    if (!topbar || query('.preview-topbar-actions')) return;
    const actions = document.createElement('div');
    actions.className = 'preview-topbar-actions';
    actions.innerHTML = `<button type="button" class="preview-topbar-home" data-view="dongdong"><i data-lucide="arrow-left"></i><span>东东首页</span></button>`;
    topbar.appendChild(actions);
    if (window.lucide) window.lucide.createIcons({ root: actions });
  }

  function updateLogo(isInner) {
    const logo = query('.brand .logo img');
    if (!logo) return;
    if (!originalLogoSrc) originalLogoSrc = logo.getAttribute('src');
    logo.src = isInner ? './brand/ceair-symbol.svg' : originalLogoSrc;
  }

  function updateActiveNav() {
    const active = query('.view.active')?.id || 'dongdong';
    if (active !== lastActiveView) {
      const group = query(`[data-preview-view="${active}"]`, sidebar)?.closest('.preview-nav-group');
      if (group) setGroupExpanded(group, true);
      lastActiveView = active;
    }
    queryAll('[data-preview-view], .preview-home, .preview-topbar-home').forEach(button => {
      const selected = button.dataset.view === active;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-current', selected ? 'page' : 'false');
    });
    queryAll('.preview-nav-group').forEach(group => group.classList.toggle('active', !!query(`.preview-nav-items [data-preview-view].active`, group)));
    const identity = query('.topnav .user');
    const tenant = query('.preview-tenant b', sidebar);
    const user = query('.preview-tenant small', sidebar);
    const avatar = query('.preview-avatar', sidebar);
    const tenantText = query('b', identity)?.textContent || '当前工作区';
    const userText = query('span', identity)?.textContent || '正在加载用户';
    if (tenant.textContent !== tenantText) tenant.textContent = tenantText;
    if (user.textContent !== userText) user.textContent = userText;
    const initial = identity?.dataset.displayName?.slice(0, 1) || '用';
    if (avatar.textContent !== initial) avatar.textContent = initial;
  }

  function setGroupExpanded(group, expanded) {
    const button = query('[data-toggle-group]', group), items = query('.preview-nav-items', group);
    button.setAttribute('aria-expanded', String(expanded));
    items.hidden = !expanded;
    collapsed[group.dataset.previewGroup] = !expanded;
    try { localStorage.setItem(collapseKey, JSON.stringify(collapsed)); } catch { /* Navigation remains usable without storage. */ }
  }

  function refresh() {
    if (!appReady()) return;
    const isInner = innerView();
    document.body.classList.toggle('preview-ui', isInner);
    document.body.classList.toggle('preview-home', !isInner);
    buildSidebar();
    syncProductionItems();
    buildPreviewControls();
    if (!isInner || (sidebarToggle && !window.matchMedia('(max-width: 820px)').matches)) {
      setSidebarOpen(false);
    } else if (sidebarToggle) {
      setSidebarOpen(sidebar.classList.contains('is-open'));
    }
    updateLogo(isInner);
    updateActiveNav();
    if (window.lucide) window.lucide.createIcons();
  }

  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(refresh, 20);
  }

  function install() {
    buildSidebar();
    buildPreviewControls();
    document.addEventListener('click', event => {
      const groupToggle = event.target.closest('[data-toggle-group]');
      if (groupToggle) {
        event.preventDefault();
        setGroupExpanded(groupToggle.closest('.preview-nav-group'), groupToggle.getAttribute('aria-expanded') !== 'true');
        return;
      }
      if (sidebar && sidebarToggle && sidebar.classList.contains('is-open') && !event.target.closest('#previewSidebar, .preview-sidebar-toggle')) {
        setSidebarOpen(false);
      }
      const previewNav = event.target.closest('[data-preview-view], .preview-home, .preview-topbar-home');
      if (previewNav && typeof window.activate === 'function') {
        event.preventDefault();
        window.activate(previewNav.dataset.view);
        if (window.matchMedia('(max-width: 820px)').matches) setSidebarOpen(false);
      }
      if (event.target.closest('[data-view]')) scheduleRefresh();
    }, true);
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && sidebar?.classList.contains('is-open')) {
        event.preventDefault();
        setSidebarOpen(false);
        sidebarToggle?.focus();
      }
    });
    const observer = new MutationObserver(scheduleRefresh);
    observer.observe(document.body, { subtree: true, attributes: true, attributeFilter: ['class', 'style'] });
    refresh();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();
})();
