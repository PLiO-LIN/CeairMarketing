(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const notify = message => window.toast ? window.toast(message) : console.info(message);
  const state = {
    paused: false,
    lastFilter: '',
    audit: []
  };

  const escapeHtml = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const rows = (table, query) => $$("tbody tr, tr", table).filter(row => row.querySelector('td')).filter(row => row.innerText.toLowerCase().includes(query.toLowerCase()));
  const filterTable = (input, tableSelector, emptyText = '没有匹配记录') => {
    const table = $(tableSelector);
    if (!table || !input) return;
    const query = input.value.trim();
    const all = $$("tr", table).filter(row => row.querySelector('td'));
    let visible = 0;
    all.forEach(row => {
      const show = !query || row.innerText.toLowerCase().includes(query.toLowerCase());
      row.style.display = show ? '' : 'none';
      if (show) visible++;
    });
    let empty = table.parentElement.querySelector('.v32-empty');
    if (!visible) {
      if (!empty) { empty = document.createElement('div'); empty.className = 'v32-empty'; table.parentElement.appendChild(empty); }
      empty.textContent = emptyText;
    } else if (empty) empty.remove();
    notify(query ? `已筛选 ${visible} 条记录` : `已显示全部 ${visible} 条记录`);
  };

  const tableMap = {
    opportunities: '#opportunities .opportunity-table',
    audiences: '#audiences .table',
    products: '#products .table',
    contents: '#contents .table',
    campaigns: '#campaigns .table'
  };
  const filterViews = () => {
    Object.entries(tableMap).forEach(([view, selector]) => {
      const panel = document.querySelector(`#${view}`);
      const input = panel?.querySelector('.toolbar-strip input');
      const button = panel?.querySelector('.toolbar-strip .btn');
      if (!input || !button || button.dataset.v32Bound) return;
      button.dataset.v32Bound = 'true';
      button.addEventListener('click', () => filterTable(input, selector));
      input.addEventListener('keydown', e => { if (e.key === 'Enter') filterTable(input, selector); });
    });
  };

  const updateStatus = (row, text, kind = 'good') => {
    if (!row) return;
    const status = row.querySelector('.status, .pill');
    if (status) { status.textContent = text; status.className = `status ${kind}`; }
  };

  const showDetail = (title, subtitle, content, actions = '') => {
    const drawer = $('#businessDrawer');
    if (!drawer) return;
    $('#drawerTitle').textContent = title;
    $('#drawerSubtitle').textContent = subtitle;
    $('#drawerBody').innerHTML = content;
    $('#drawerFoot').innerHTML = `<button class="btn" data-close="businessDrawer">关闭</button>${actions}`;
    drawer.classList.add('open');
    if (window.lucide) lucide.createIcons();
  };

  const showOperation = (title, message, next = '') => showDetail(title, '操作结果 · 已写入当前工作区', `<div class="drawer-section"><div class="drawer-section-title">系统回执</div><div class="drawer-section-body"><div class="drawer-ai"><b>${escapeHtml(message)}</b><br>操作人：张琳 · 华东营销运营中心<br>时间：刚刚 · 已生成审计记录</div></div></div>${next ? `<div class="drawer-section"><div class="drawer-section-title">下一步</div><div class="drawer-section-body">${next}</div></div>` : ''}`);

  const openAudienceProfile = () => showDetail('三亚高意向未购 · 客群画像', '客群快照 · AUD-2026-0421 · V4', `
    <div class="drawer-section"><div class="drawer-section-title">画像概览</div><div class="drawer-section-body"><div class="drawer-kv"><span>客群规模</span><b>36,420人</b><span>更新方式</span><b>可信数据空间同步 · 10:38</b><span>旅程阶段</span><b>比价期 / 未出票</b><span>触达资格</span><b>可触达 · 7天已触达1次</b></div></div></div>
    <div class="drawer-section"><div class="drawer-section-title">航空业务画像</div><div class="drawer-section-body"><div class="drawer-list"><button><span>航线偏好</span><b>沪三亚 · 未来21天</b></button><button><span>同行关系</span><b>家庭同行概率 78%</b></button><button><span>辅营偏好</span><b>行李 43% · 选座 31%</b></button><button><span>会员与价格</span><b>普卡 · 价格敏感</b></button></div></div></div>
    <div class="drawer-ai"><b>客群洞察智能域</b><br>关系扩展发现家庭同行子群，建议优先匹配“机票 + 行李 + 优选座位 + 接送券”产品包，并设置短信补触。</div>`, '<button class="btn primary" data-v32-action="bindAudience">绑定到当前活动</button>');

  const openProductProfile = () => showDetail('三亚国庆早鸟产品包', '活动产品包 · PKG-2026-0834 · 产品管理平台同步', `
    <div class="drawer-section"><div class="drawer-section-title">可售构成</div><div class="drawer-section-body"><div class="drawer-list"><button><span>客票与运价</span><b>经济舱早鸟 · 指定航班</b></button><button><span>增值服务</span><b>20kg行李 + 前排选座</b></button><button><span>权益卡券</span><b>接送优惠券 + 里程加赠</b></button><button><span>库存状态</span><b>价格 / 库存 / 有效期校验通过</b></button></div></div></div>
    <div class="drawer-ai"><b>产品匹配智能域</b><br>基于航线、日期、价格敏感度、会员资格与辅营偏好计算适配率 91.6%，可作为活动产品引用。</div>`, '<button class="btn" data-v32-action="syncInventory">同步价格与库存</button><button class="btn primary" data-v32-action="bindProduct">引用到活动</button>');

  const bindAction = (action, button) => {
    if (action === 'bindAudience') { button.textContent = '已绑定'; button.disabled = true; notify('客群快照已绑定到活动 V3'); }
    if (action === 'bindProduct') { button.textContent = '已引用'; button.disabled = true; notify('产品包已引用，已锁定当前价格与权益版本'); }
    if (action === 'syncInventory') { notify('同步完成：经济舱库存 126 个，行李与选座权益可用'); }
  };

  const approvalAdvance = (action) => {
    const item = $('.approval-item.active');
    const title = $('#approvalDetail')?.dataset.title || $('#decisionSubtitle')?.textContent || '当前活动';
    if (!item) return;
    if (action === 'approve') {
      const current = item.querySelector('em');
      if (current) { current.textContent = '合规复核'; current.className = 'pill'; }
      showOperation('审批节点已推进', `${title} 已通过当前审批，进入合规复核节点。`, '合规校验将继续检查客群保护、产品可售性、内容事实和渠道频控。');
    } else {
      updateStatus(item, '退回修改', 'warn');
      showOperation('活动已退回', `${title} 已退回创建人，需补充审批材料后重新提交。`, '待补充：预算依据、产品库存证明、内容事实来源。');
    }
  };

  const executionAction = action => {
    const control = $('#execution .control-item');
    if (action === 'pauseWindow') {
      state.paused = !state.paused;
      const button = control?.querySelector('[data-action="pauseWindow"]');
      if (button) button.textContent = state.paused ? '恢复窗口' : '暂停窗口';
      const text = control?.querySelector('span');
      if (text) text.textContent = state.paused ? '已暂停 · 已保留未发送名单与回传任务' : '09:00—20:00 · 已恢复运行';
      notify(state.paused ? '触达窗口已暂停，已发送任务不受影响' : '触达窗口已恢复');
    }
    if (action === 'retryFailed') notify('已创建补偿任务 RETRY-2026-0821-03：126人，短信通道重试中');
    if (action === 'viewAudienceSnapshot') showOperation('客群快照已打开', 'AUD-2026-0421 V4 已冻结 36,420 人，快照可用于审计与归因。');
  };

  const reviewAction = action => {
    if (action === 'generateReview') {
      const box = $('#reviewBox');
      if (box) box.innerHTML = `<div class="drawer-ai"><b>效果分析智能域 · 已生成复盘</b><br>家庭同行子群出票率 12.4%，高于整体 9.8%；App内容版贡献 61% 转化，短信补触贡献 18%。建议下一轮扩大“行李偏好”子群，并把短信补触延后 6 小时。</div><div class="review-actions"><button class="btn primary" data-v32-action="applyLearning">生成下一轮策略</button></div>`;
      notify('AI复盘完成：已生成客群、内容、时机和渠道建议');
    }
    if (action === 'applyLearning') notify('学习建议已写入策略草案：客群扩展、短信延后、行李权益优先');
    if (action === 'exportReview') notify('复盘报告已生成：含触达、点击、出票、辅营和归因明细');
  };

  const openRoleEditor = () => showDetail('编辑角色权限', '治理中心 · 权限变更需审计留痕', `
    <div class="drawer-section"><div class="drawer-section-title">当前角色：营销运营</div><div class="drawer-section-body"><div class="drawer-kv"><span>成员</span><b>28人</b><span>当前数据范围</span><b>华东区域</b><span>最近变更</span><b>2026-08-20 15:42 · 张琳</b></div></div></div>
    <div class="drawer-section"><div class="drawer-section-title">功能权限</div><div class="drawer-section-body"><div class="drawer-form"><label><input type="checkbox" checked> 查看与筛选机会、客群、产品包</label><label><input type="checkbox" checked> 创建活动与活动版本</label><label><input type="checkbox"> 审批与发布活动</label><label><input type="checkbox" checked> 查看执行与效果数据</label><label><input type="checkbox"> 导出敏感画像明细</label></div></div></div>`, '<button class="btn primary" data-v32-action="saveRole">保存权限变更</button>');
  const openScopeEditor = () => showDetail('调整数据范围', '治理中心 · 按区域、航线和敏感等级控制访问', `
    <div class="drawer-section"><div class="drawer-section-title">营销运营当前范围</div><div class="drawer-section-body"><div class="drawer-form"><label>区域<select><option>华东营销中心</option><option>全国营销中心</option><option>国际及地区营销中心</option></select></label><label>航线范围<select><option>上海、江苏、浙江、安徽</option><option>全部国内航线</option><option>国际及地区航线</option></select></label><label>敏感画像<input value="不含特殊旅客敏感画像"></label></div></div></div>
    <div class="drawer-ai"><b>权限策略提示</b><br>扩大到全国航线后，需重新确认活动审批范围；特殊旅客、未成年人和高敏感标签仍保持脱敏。</div>`, '<button class="btn primary" data-v32-action="saveScope">保存范围变更</button>');
  const bindSearch = () => {
    const search = $('.global-search');
    if (!search || search.dataset.v32Bound) return;
    search.dataset.v32Bound = 'true';
    search.addEventListener('click', e => { e.stopPropagation();
      showDetail('全局业务对象检索', '支持机会、客群、产品包、活动、内容和结果', `<div class="drawer-form"><label>输入对象名称或编号<input id="v32GlobalSearch" placeholder="如：三亚、ACT-2026-0921、PKG-2026-0834"></label><button class="btn primary" data-v32-action="globalSearch">检索</button></div><div id="v32SearchResult" class="drawer-list" style="margin-top:12px"><button><span>最近访问</span><b>上海—三亚国庆早鸟</b></button></div>`);
    });
  };

  document.addEventListener('click', e => {
    if (e.target.closest('[data-view]')) $('#businessDrawer')?.classList.remove('open');
    const b = e.target.closest('button');
    if (!b) return;
    const action = b.dataset.v32Action || b.dataset.action || b.dataset.approvalAction;
    if (b.dataset.v32Action === 'globalSearch') {
      const q = $('#v32GlobalSearch')?.value.trim() || '';
      const result = $('#v32SearchResult');
      if (result) result.innerHTML = q ? `<button><span>营销活动</span><b>${escapeHtml(q)} · 点击打开</b></button><button><span>关联业务对象</span><b>客群 / 产品包 / 渠道回传</b></button>` : '<div class="empty-action">请输入检索条件</div>';
      notify(q ? `检索完成：已找到与“${q}”相关的业务对象` : '请输入检索条件');
      return;
    }
    if (b.dataset.v32Action) { bindAction(b.dataset.v32Action, b); if (['generateReview','applyLearning','exportReview'].includes(b.dataset.v32Action)) reviewAction(b.dataset.v32Action); if (['saveRole','saveScope'].includes(b.dataset.v32Action)) { b.textContent = '已保存'; b.disabled = true; notify(b.dataset.v32Action === 'saveRole' ? '角色权限已保存，已生成权限审计记录' : '数据范围已保存，已生成范围变更审计记录'); } return; }
    if (b.dataset.approval) { const title=b.querySelector('b')?.textContent||'当前审批活动'; const detail=$('#approvalDetail'); if(detail){detail.dataset.title=title;detail.innerHTML=`<div class="approval-detail-hero"><span class="approval-icon activity"><i data-lucide="megaphone"></i></span><div><h3>${escapeHtml(title)}</h3><p>活动发布审批 · 当前版本 V3 · 负责人李洋</p></div><span class="pill red">待我审批</span></div><div class="approval-detail-grid"><div><b>活动目标</b><span>提升目标航线出票与辅营产品购买转化</span></div><div><b>客群范围</b><span>36,420 人 · 高意向未购客群</span></div><div><b>产品包</b><span>机票 + 行李 + 优选座位</span></div><div><b>触达渠道</b><span>东航 App、短信、微信</span></div><div><b>预算</b><span>¥320,000 · 需营销负责人确认</span></div><div><b>合规检查</b><span>客户授权、敏感词、频控均已通过</span></div></div><div class="approval-content-preview"><b>内容预览</b><p>国庆去三亚，机票、行李和优选座位一次安排，带孩子出行更从容。</p></div><div class="business-actions"><button class="btn" data-action="reject">退回修改</button><button class="btn primary" data-action="approve">审批通过</button></div>`;if(window.lucide)lucide.createIcons();}document.querySelectorAll('.approval-item').forEach(x=>x.classList.toggle('active',x===b));return; }
    if (action === 'viewOpportunityAudience') { openAudienceProfile(); return; }
    if (action === 'viewOpportunityProduct' || action === 'viewProduct') { openProductProfile(); return; }
    if (action === 'viewAudienceSnapshot' || action === 'retryFailed' || action === 'pauseWindow') { executionAction(action); return; }
    if (action === 'generateReview' || action === 'exportReview') { reviewAction(action); return; }
    if (action === 'approve' || action === 'reject') { approvalAdvance(action); return; }
    if (b.dataset.openOpportunity) { openAudienceProfile(); return; }
    if (b.dataset.openCampaign) { notify(`已打开活动工作台：${b.dataset.openCampaign}，可查看版本、审批和执行记录`); return; }
    if (b.dataset.audience) { openAudienceProfile(); return; }
    if (b.dataset.drawer === 'close') { $('#businessDrawer')?.classList.remove('open'); return; }
    if (action === 'editRole') { openRoleEditor(); return; }
    if (action === 'editScope') { openScopeEditor(); return; }
    if (action === 'globalSearch') {
      const q = $('#v32GlobalSearch')?.value.trim() || '';
      const result = $('#v32SearchResult');
      if (result) result.innerHTML = q ? `<button><span>营销活动</span><b>${escapeHtml(q)} · 点击打开</b></button><button><span>关联业务对象</span><b>客群 / 产品包 / 渠道回传</b></button>` : '<div class="empty-action">请输入对象名称或编号</div>';
      notify(q ? `检索完成：已找到与“${q}”相关的业务对象` : '请输入检索条件');
    }
  });

  const init = () => { filterViews(); bindSearch(); if (window.lucide) lucide.createIcons(); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();







