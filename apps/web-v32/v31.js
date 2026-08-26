(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const drawer = $('#businessDrawer');
  const body = $('#drawerBody');
  const foot = $('#drawerFoot');
  let mode = '';

  const closeDrawer = () => drawer.classList.remove('open');
  const kv = rows => `<div class="drawer-kv">${rows.map(([k,v]) => `<span>${k}</span><b>${v}</b>`).join('')}</div>`;
  const section = (title, html) => `<section class="drawer-section"><div class="drawer-section-title">${title}</div><div class="drawer-section-body">${html}</div></section>`;
  const trail = current => {
    const steps = ['机会','客群','产品','内容','审批','执行','复盘'];
    const index = steps.indexOf(current);
    return `<div class="step-trail">${steps.map((s,i) => `${i ? '<i>›</i>' : ''}<span class="${i < index ? 'done' : i === index ? 'current' : ''}">${s}</span>`).join('')}</div>`;
  };
  const openDrawer = (title, subtitle, html, actions = '') => {
    $('#drawerTitle').textContent = title;
    $('#drawerSubtitle').textContent = subtitle;
    body.innerHTML = html;
    foot.innerHTML = `<button class="btn" data-drawer="close">关闭</button>${actions}`;
    drawer.classList.add('open');
    if (window.lucide) lucide.createIcons();
  };
  const opportunity = name => openDrawer(name || '上海—三亚国庆早鸟机会','经营机会 · OPP-2026-0821-05',
    trail('机会') + section('机会判断',kv([['机会来源','航班余座、搜索比价、节假日窗口'],['目标航线','上海浦东/虹桥—三亚凤凰'],['目标旅客','近14天搜索且尚未出票的可触达旅客'],['机会规模','36,420人'],['收入潜力','预计增量收入186万元，预测ROI 4.8']])) + section('AI洞察','<div class="drawer-ai"><b>机会洞察智能域建议</b><br>家庭同行旅客对托运行李和优选座位需求明显，建议组合早鸟运价、预付费行李和优选座位。</div>') + section('关联业务对象','<div class="drawer-list"><button data-nav="audiences"><span>三亚高意向未购客群</span><b>36,420人 ›</b></button><button data-open="product"><span>三亚国庆早鸟产品包</span><b>适配率91.6% ›</b></button></div>'),
    '<button class="btn" data-drawer="ignore">暂不采用</button><button class="btn primary" data-drawer="createCampaign">创建营销活动</button>');
  const product = () => openDrawer('三亚国庆早鸟产品包','活动产品包 · PKG-2026-0834 · 产品管理平台同步',
    trail('产品') + section('产品包构成',kv([['核心客票','上海—三亚指定航班经济舱早鸟运价'],['辅营产品','20kg预付费行李、前排优选座位'],['权益卡券','目的地接送优惠券、会员里程加赠'],['适用范围','指定航班、指定日期、符合资格的实名旅客'],['可售状态','价格、库存、卡券有效期校验通过'],['销售渠道','东航App、官网、微信、短信落地页']])) + section('AI匹配','<div class="drawer-ai"><b>产品匹配智能域 · 适配率91.6%</b><br>在航线、出行日期、价格敏感度、家庭辅营偏好和会员资格上均与目标客群匹配。</div>'),
    '<button class="btn" data-drawer="syncProduct">同步价格库存</button><button class="btn primary" data-drawer="useProduct">引用到活动</button>');
  const content = () => openDrawer('国庆三亚家庭出游内容','内容资产 · CNT-2026-1186 · V3',
    trail('内容') + section('渠道内容版本','<div class="drawer-list"><button><span>东航App · 家庭出游版</span><b>预测CTR 12.8%</b></button><button><span>短信 · 价格窗口提醒版</span><b>预测CTR 8.6%</b></button><button><span>微信 · 行程灵感版</span><b>预测CTR 10.9%</b></button></div>') + section('审核约束',kv([['可表达产品','早鸟运价、行李、优选座位、接送券'],['禁用表述','最低价、永久有效、无条件退改'],['事实校验','与产品管理平台规则一致'],['当前状态','待内容负责人确认']])) + section('AI生成','<div class="drawer-ai"><b>内容生成智能域</b><br>已按照客群偏好、渠道字数限制和产品事实生成3个版本。</div>'),
    '<button class="btn" data-drawer="regenerate">重新生成</button><button class="btn primary" data-drawer="approveContent">确认并引用</button>');
  const campaign = name => openDrawer(name || '上海—三亚国庆早鸟','营销活动 · ACT-2026-0921 · V3',
    trail('审批') + section('活动配置',kv([['活动目标','提升国庆上海—三亚出票及辅营渗透率'],['负责人','李洋 · 华东营销运营中心'],['目标客群','三亚高意向未购 · 快照36,420人'],['活动产品','三亚国庆早鸟产品包'],['内容策略','家庭出游版 + 价格敏感版'],['触达策略','App首触，24小时未响应短信补触'],['预算目标','预算32万元，目标ROI不低于4.0']])) + section('版本与流程','<div class="drawer-list"><button><span>V3 · 调整家庭客群及辅营组合</span><b>待营销审批</b></button><button><span>V2 · 增加短信补触策略</span><b>已归档</b></button><button><span>V1 · 初始草案</span><b>已归档</b></button></div>') + section('AI编排','<div class="drawer-ai"><b>活动编排检查通过</b><br>客群保护、产品资格、频控、内容事实和预算阈值已校验，等待人工审批。</div>'),
    '<button class="btn" data-drawer="duplicate">复制活动</button><button class="btn primary" data-nav="approvals">进入审批</button>');
  const form = type => {
    mode = type;
    const data = {
      audience:['新建动态客群','客群名称','三亚高意向未购旅客','圈选条件','近14天搜索上海至三亚航班、尚未出票、允许营销触达','计算并保存'],
      product:['新建活动产品包','产品包名称','三亚家庭出游组合包','组合说明','客票运价 + 预付费行李 + 优选座位 + 接送优惠券','校验并保存'],
      content:['新建营销内容','内容名称','国庆三亚家庭出游内容','生成要求','面向家庭同行旅客，突出行李和座位权益，生成App、短信、微信版本','生成并保存']
    }[type];
    openDrawer(data[0],'创建业务对象并保存为草稿',section('基本信息',`<div class="drawer-form"><label>${data[1]}<input value="${data[2]}"></label><label>${data[3]}<textarea>${data[4]}</textarea></label></div>`) + '<div class="drawer-ai"><b>AI辅助校验</b><br>保存前将自动执行画像权限、产品资格或内容事实检查。</div>',`<button class="btn" data-drawer="saveDraft">保存草稿</button><button class="btn primary" data-drawer="saveEntity">${data[5]}</button>`);
  };
  const search = () => openDrawer('全局业务搜索','检索机会、客群、产品包、内容和活动',section('搜索条件','<div class="drawer-form"><label>关键字<input value="三亚"></label><label>对象类型<select><option>全部业务对象</option><option>营销活动</option><option>客群</option><option>产品包</option><option>内容</option></select></label></div>') + section('相关对象','<div class="drawer-list"><button data-open="campaign"><span>上海—三亚国庆早鸟</span><b>营销活动 ›</b></button><button data-nav="audiences"><span>三亚高意向未购</span><b>动态客群 ›</b></button><button data-open="product"><span>三亚国庆早鸟产品包</span><b>产品包 ›</b></button></div>'),'<button class="btn primary" data-drawer="search">查询</button>');

  $$('.menu-toggle').forEach(b => b.addEventListener('click', e => { e.stopPropagation(); b.closest('.menu-group').classList.toggle('open'); }));
  drawer.addEventListener('click', e => { if (e.target === drawer) closeDrawer(); });
  $$('.selection-box,.content-option').forEach(e => e.addEventListener('click', () => e.classList.toggle('selected')));

  document.addEventListener('click', e => {
    const nav = e.target.closest('[data-nav]');
    if (nav) { closeDrawer(); activate(nav.dataset.nav); return; }
    const d = e.target.closest('[data-drawer]')?.dataset.drawer;
    if (d) {
      if (d === 'workspace') { closeDrawer(); toast('工作空间已切换，数据权限已刷新'); return; }
      if (d === 'close') closeDrawer();
      if (d === 'createCampaign' || d === 'useProduct' || d === 'duplicate') { closeDrawer(); document.querySelector('[data-action="createCampaign"]')?.click(); }
      if (d === 'saveDraft') { closeDrawer(); toast('草稿已保存，可从对应工作台继续编辑'); }
      if (d === 'saveEntity') { closeDrawer(); toast(`${{audience:'客群',product:'产品包',content:'内容任务'}[mode]}已创建并生成业务编号`); }
      if (d === 'syncProduct') toast('已从产品管理平台同步最新价格、库存和卡券状态');
      if (d === 'regenerate') toast('已重新生成3个渠道内容版本');
      if (d === 'approveContent') { closeDrawer(); toast('内容已确认并引用到活动V3'); }
      if (d === 'search') toast('查询完成：找到1个活动、2个客群、3个产品包和4个内容资产');
      if (d === 'ignore') { closeDrawer(); toast('机会已标记为暂不采用，将在条件变化后重新评估'); }
      return;
    }
    const open = e.target.closest('[data-open]')?.dataset.open;
    if (open) { if (open === 'product') product(); if (open === 'campaign') campaign(); return; }
    if (e.target.closest('.global-search')) { search(); return; }
    const opp = e.target.closest('[data-open-opportunity]');
    if (opp) { opportunity(opp.dataset.openOpportunity); return; }
    const camp = e.target.closest('[data-open-campaign]');
    if (camp) { campaign(camp.dataset.openCampaign); return; }
    const action = e.target.closest('[data-action]')?.dataset.action;
    if (action === 'newAudience') form('audience');
    if (action === 'newProduct') form('product');
    if (action === 'newContent') form('content');
    if (['viewProduct','useProduct'].includes(action)) product();
    if (['reviewContent','viewContent'].includes(action)) content();
    if (['viewVersion','compareVersion','rollbackVersion'].includes(action)) campaign();
    if (action === 'switchWorkspace') openDrawer('切换工作空间','根据岗位切换数据和功能权限',section('工作空间','<div class="drawer-list"><button data-drawer="workspace"><span>华东区域营销运营</span><b>当前</b></button><button data-drawer="workspace"><span>全国会员营销</span><b>可切换</b></button><button><span>国际航线营销</span><b>需申请</b></button></div>'));
    const plain = e.target.closest('button');
    if (plain && !action && !plain.dataset.view && !plain.dataset.menu && !plain.dataset.approval && !plain.dataset.role && !plain.dataset.decision && !plain.dataset.graphFilter && !plain.dataset.close && !plain.id) {
      const label = plain.textContent.trim();
      if (label === '查询' || label === '筛选') { toast(label + '完成，当前工作台数据已刷新'); return; }
      if (label === '查看产品') { product(); return; }
    }
    const generic = e.target.closest('td.action,button.action');
    if (generic && !action && !opp && !camp) {
      const view = $('.view.active')?.id;
      if (view === 'products') product(); else if (view === 'contents') content(); else if (view === 'campaigns' || view === 'overview') campaign(generic.closest('tr')?.querySelector('strong')?.textContent); else opportunity(generic.closest('tr')?.querySelector('strong')?.textContent);
    }
  });
})();
