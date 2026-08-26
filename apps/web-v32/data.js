(() => {
  const addRows = (selector, rows) => {
    const table = document.querySelector(selector);
    if (!table || table.dataset.enriched) return;
    table.dataset.enriched = 'true';
    table.insertAdjacentHTML('beforeend', rows.map(r => `<tr>${r.map((c,i) => `<td${i === r.length - 1 ? ' class="action"' : ''}>${c}</td>`).join('')}</tr>`).join(''));
  };
  addRows('#opportunities .table', [
    ['上海—昆明暑期返程', '旅游航线 · 返程窗口', '酒店退订↑18% · 返程搜索↑27%', '21,680', '89', '<span class="status warn">待处理</span>', '详情'],
    ['广州—上海周末快线', '商务干线 · 高频出行', '周五晚搜索↑21% · 去程已购', '15,920', '85', '<span class="status warn">待处理</span>', '详情'],
    ['境外中转行李需求', '国际中转 · 辅营机会', '中转时长3—8小时 · 行李购买率低', '8,740', '79', '<span class="status">观察</span>', '详情']
  ]);
  addRows('#audiences .table', [
    ['国际中转高价值客群', '12,680', '中转时长 · 商务舱 · 贵宾室偏好', 'V3', '<span class="status good">可用</span>', '画像'],
    ['空铁联运潜客', '26,310', '高铁站周边 · 跨城搜索 · 远程值机偏好', 'V2', '<span class="status good">可用</span>', '画像'],
    ['银卡升金临界会员', '6,480', '近12月里程 · 航段缺口 · 两舱偏好', 'V5', '<span class="status good">可用</span>', '画像'],
    ['企业差旅协议客户', '4,920', '协议价 · 京沪频次 · 周一/周五出行', 'V4', '<span class="status good">可用</span>', '画像']
  ]);
  addRows('#products .table', [
    ['京沪商务升舱包', '商务干线', '公务舱升舱 + 贵宾室 + 优先行李', 'V4', '<span class="status good">可用</span>', '12', '详情'],
    ['空铁联运便捷出行包', '空铁联运', '航空客票 + 高铁联程 + 城市航站楼服务', 'V2', '<span class="status good">可用</span>', '6', '详情'],
    ['国际中转安心服务包', '国际及地区', '联程客票 + 中转住宿 + 贵宾室 + 保险', 'V3', '<span class="status warn">待复核</span>', '3', '复核'],
    ['C919体验权益包', '客舱体验', '指定航班选座 + 机上Wi-Fi + 里程加赠', 'V1', '<span class="status good">可用</span>', '2', '详情']
  ]);
  addRows('#contents .table', [
    ['空铁联运·到站即出发', '空铁联运便捷出行', 'App / 官网', 'V2', '<span class="status good">已通过</span>', '查看'],
    ['银卡升金·差一航段提醒', '会员升金激励', 'App / 短信', 'V3', '<span class="status warn">待审核</span>', '审核'],
    ['国际中转·贵宾室权益提醒', '国际中转安心服务', '微信 / 邮件', 'V1', '<span class="status good">已通过</span>', '查看'],
    ['企业差旅·协议价续签提醒', '企业客户续签', '邮件 / 客户经理', 'V2', '<span class="status good">已通过</span>', '查看']
  ]);
  addRows('#campaigns .table', [
    ['ACT-2026-0906', '<strong>空铁联运暑期返程</strong>', '执行', 'V2 · 生效', '王晨', '08-20 16:30', '<span class="status good">运行中</span>', '进入活动'],
    ['ACT-2026-0898', '<strong>银卡升金临界激励</strong>', '内容', 'V3 · 待审核', '周宁', '08-20 15:12', '<span class="status warn">待审核</span>', '进入活动'],
    ['ACT-2026-0876', '<strong>国际中转安心服务推广</strong>', '复盘', 'V4 · 已完成', '陈涛', '08-19 18:40', '<span class="status">已完成</span>', '查看复盘'],
    ['ACT-2026-0869', '<strong>企业差旅协议价续签</strong>', '审批', 'V1 · 草案', '林晓', '08-19 14:25', '<span class="status warn">待审批</span>', '进入活动']
  ]);
  addRows('#execution .table', [
    ['官网活动落地页', '6,820', '6,712', '18', '1.4秒', '<span class="status good">正常</span>'],
    ['会员中心消息', '4,180', '4,102', '26', '3.2秒', '<span class="status good">正常</span>'],
    ['OTA / NDC回传', '2,460', '2,438', '7', '12.6秒', '<span class="status warn">延迟</span>']
  ]);
})();