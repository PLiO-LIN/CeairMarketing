(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const labels = {'opportunity-insight':'机会洞察','audience-insight':'客群洞察','product-match':'产品匹配','activity-orchestration':'活动编排','content-generation':'内容生成','effect-analysis':'效果分析'};
  const kinds = {'opportunity-insight':'机会建议','audience-insight':'圈选条件','product-match':'价值主张','activity-orchestration':'策略与触点计划','content-generation':'文案与视觉模板','effect-analysis':'渠道复盘'};
  window.ceairOntologyLabels = {Campaign:'营销活动',CampaignVersion:'活动版本',Opportunity:'营销机会',AudienceSnapshot:'冻结客群',ProductPackage:'产品包',ContentAsset:'内容资产',AgentRun:'智能体运行',Evidence:'业务证据',ExecutionBatch:'执行批次',Feedback:'渠道反馈',Review:'效果复盘',KnowledgeDocument:'来源文档',KnowledgeChunk:'知识片段',Route:'航线',MarketSignal:'市场信号',KnowledgeClaim:'知识事实',CustomerNeed:'旅客需求',StrategyPlan:'策略方案',BusinessRule:'业务规则',TouchpointPlan:'触点计划',Recommendation:'营销建议',ValueProposition:'价值主张',CustomerAggregate:'聚合客群',ApprovalTask:'审批任务',HumanDecision:'人工决策',Channel:'触达渠道'};
  const stages = [['MarketSignal','需求信号'],['Opportunity','营销机会'],['AudienceSnapshot','冻结客群'],['ProductPackage','产品版本'],['ContentAsset','渠道内容'],['ApprovalTask','人工审批'],['ExecutionBatch','执行批次'],['Feedback','渠道反馈'],['Review','效果复盘'],['AgentRun','智能体运行'],['StrategyPlan','策略方案'],['HumanDecision','人工决策'],['KnowledgeDocument','来源文档'],['KnowledgeChunk','知识片段'],['Evidence','决策证据']];
  function host(id, parent, position = 'append') {
    let node = $('#' + id);
    if (!node) {
      node = document.createElement('section'); node.id = id; node.className = 'demo-panel';
      if (position === 'after') parent.after(node); else if(position==='prepend') parent.prepend(node); else parent.append(node);
    }
    return node;
  }
  function modal(title, html) {
    const layer = document.createElement('div'); layer.className = 'production-modal demo-modal';
    layer.setAttribute('role','dialog'); layer.setAttribute('aria-modal','true');
    layer.innerHTML = '<div class="production-modal-card"><div class="production-modal-head"><b>' + esc(title) + '</b><button class="btn" data-demo-close>关闭</button></div><div class="production-modal-body">' + html + '</div></div>';
    const previous = document.activeElement;
    const close = () => { layer.remove(); previous?.focus(); };
    layer.addEventListener('click', e => { if (e.target === layer || e.target.closest('[data-demo-close]')) close(); });
    layer.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
    document.body.append(layer); $('[data-demo-close]', layer).focus(); return layer;
  }
  function bars(items, suffix = '') {
    const max = Math.max(1, ...items.map(i => i.value));
    return items.map(i => '<div class="demo-bar"><span>' + esc(i.label) + '</span><div><i style="width:' + Math.round(i.value/max*100) + '%"></i></div><b>' + Number(i.value).toLocaleString('zh-CN') + suffix + '</b></div>').join('');
  }
  function compactPanel(node, title, action) {
    const heading = $('.demo-heading', node);
    $('h2', heading).textContent = title;
    $('small', heading)?.remove();
    const content = document.createElement('div');
    Array.from(node.children).filter(child => child !== heading).forEach(child => content.append(child));
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'btn'; button.textContent = action;
    button.onclick = () => modal(title, content.innerHTML);
    heading.append(button); node.classList.add('demo-compact');
  }
  function traceHTML(run) {
    const titles = {'agent/run-started':'开始任务','ontology/context-loaded':'本体约束','business/context-loaded':'读取业务依据','model/provider-selected':'选择模型','tool/pre-execute':'读取受控输入','tool/post-execute':'形成结果','business/result-generated':'生成候选结果','governance/human-review':'等待人工确认','business/result-accepted':'人工确认并保存','governance/guard-checked':'业务门禁校验','model/invocation-failed':'模型调用失败','agent/run-finished':'结束任务'};
    return '<ol class="demo-trace">' + (run.events || []).map(e => '<li><b>' + esc(titles[e.event_type] || '运行步骤') + '</b><p>' + esc(e.payload?.detail || (e.payload?.accepted === false ? '校验未通过，停止进入下一阶段' : e.payload?.required ? '业务人员确认后保存草稿' : titles[e.event_type] || '记录运行过程')) + '</p><details><summary>技术记录</summary><pre>' + esc(JSON.stringify(e.payload, null, 2)) + '</pre></details></li>').join('') + '</ol>';
  }
  window.ceairTraceHTML = traceHTML;
  function posterSVG(visual, title) {
    const business = visual?.theme === 'business';
    const gradient = 'ceair-sea-' + (business ? 'business' : 'family');
    const headline = String(visual?.headline || title || '提前规划，一起出发');
    const lines = headline.match(/.{1,12}/gu) || ['一起出发'];
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 720" role="img" aria-label="个性化营销视觉模板"><defs><linearGradient id="' + gradient + '" x2="0" y2="1"><stop stop-color="' + (business?'#102c64':'#7ed7ef') + '"/><stop offset="1" stop-color="' + (business?'#527cbd':'#e4f8fa') + '"/></linearGradient></defs><rect width="600" height="720" fill="url(#' + gradient + ')"/><circle cx="476" cy="172" r="68" fill="#fff4cb" opacity=".9"/><path d="M0 395 Q150 330 300 402 T600 378 V720 H0Z" fill="' + (business?'#315383':'#239fc1') + '"/><path d="M0 491 Q170 414 325 492 T600 460 V720 H0Z" fill="' + (business?'#e8eef6':'#f9edcf') + '"/><path d="M455 455L469 284Q442 274 404 307Q425 251 463 263Q425 205 405 225Q434 182 471 249Q510 191 548 218Q507 224 482 264Q540 247 560 294Q510 273 485 288L478 455Z" fill="' + (business?'#153b6c':'#246956') + '"/><text x="40" y="56" font-family="Microsoft YaHei,sans-serif" font-size="19" fill="' + (business?'#fff':'#173f75') + '">中国东方航空 · CHINA EASTERN</text><text x="40" y="98" font-family="Microsoft YaHei,sans-serif" font-size="13" fill="' + (business?'#e9f1ff':'#315b78') + '">个性化营销视觉 · 可编辑模板</text>' + lines.slice(0,3).map((line,i)=>'<text x="40" y="' + (155+i*49) + '" font-family="Microsoft YaHei,sans-serif" font-size="35" font-weight="700" fill="' + (business?'#fff':'#173f75') + '">' + esc(line) + '</text>').join('') + '<text x="40" y="553" font-family="Microsoft YaHei,sans-serif" font-size="29" font-weight="700" fill="#173f75">' + esc(String(visual?.destination || '家庭出游').slice(0,17)) + '</text><text x="40" y="596" font-family="Microsoft YaHei,sans-serif" font-size="19" fill="#315b78">' + esc(String(visual?.benefit || '行李 · 优选座位').slice(0,23)) + '</text><rect x="40" y="623" width="168" height="46" rx="23" fill="#cc2038"/><text x="74" y="652" font-family="Microsoft YaHei,sans-serif" font-size="19" fill="white">查看出游方案</text><text x="40" y="700" font-family="Microsoft YaHei,sans-serif" font-size="12" fill="#64778d">竞赛虚构案例 · 权益和可售性以最终产品规则为准</text></svg>';
  }
  window.ceairPosterSVG = posterSVG;
  window.ceairOpenVisual = function (asset) {
    const initial = asset.generation_context?.visual || {headline: asset.title, destination:'出游推荐', benefit:asset.name, theme:'family'};
    const layer = modal('个性化视觉内容 · 模板排版', '<p class="demo-note">文案引用内容资产；视觉采用可编辑模板，确认后另存为待审核内容草稿。真实模型与受控样例在运行记录中分别标注。</p><div class="demo-visual-layout"><div data-poster-preview class="demo-poster">' + posterSVG(initial,asset.title) + '</div><form data-visual-form><label>主标题<input name="headline" maxlength="36" value="' + esc(initial.headline || asset.title) + '"></label><label>目的地／客群<input name="destination" maxlength="17" value="' + esc(initial.destination || '出游推荐') + '"></label><label>权益短句<input name="benefit" maxlength="23" value="' + esc(initial.benefit || asset.name) + '"></label><label>客群风格<select name="theme"><option value="family">家庭出游 · 海滨</option><option value="business">会员品质 · 深蓝</option></select></label><button class="btn primary" type="submit">下载视觉 SVG</button><button class="btn" type="button" data-save-visual>保存视觉草稿</button><p data-visual-state>视觉仍需业务审核。</p></form></div>');
    const form = $('[data-visual-form]',layer); form.elements.theme.value=initial.theme || 'family';
    const values = () => Object.fromEntries(new FormData(form));
    form.addEventListener('input',()=>{$('[data-poster-preview]',layer).innerHTML=posterSVG(values(),asset.title);});
    form.addEventListener('submit',e=>{e.preventDefault();const blob=new Blob([posterSVG(values(),asset.title)],{type:'image/svg+xml;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=asset.external_id+'-visual.svg';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
    $('[data-save-visual]',layer).onclick=async()=>{const button=$('[data-save-visual]',layer);button.disabled=true;try{await window.ceairSaveVisual(asset,values());$('[data-visual-state]',layer).textContent='已另存为待审核视觉草稿，审批中的原内容版本保留。';}catch(e){$('[data-visual-state]',layer).textContent=e.message;}finally{button.disabled=false;}};
  };
  window.ceairCompetition = {
    render({demo,data,request,showRun,runDomain}) {
      for (const node of document.querySelectorAll('.demo-panel')) node.hidden=!demo?.enabled;
      if (!demo?.enabled) return;
      const stat = host('demoHomeSummary',$('#dongdongQuick'),'after');
      stat.innerHTML='<div class="demo-stat-grid"><div><b>' + data.personaDimensions.length + '</b><span>画像字段</span></div><div><b>' + data.campaigns.length + '</b><span>营销活动</span></div><div><b>' + data.runs.length + '</b><span>运行记录</span></div><div><b>' + data.graph.nodes.length + '</b><span>本体实例</span></div></div><p class="demo-note">模拟数据 · 2026-09-18 · 受控模型</p>';
      const cases=host('demoCaseGallery',$('#overview .page-head'),'after');
      cases.innerHTML='<div class="demo-heading"><div><small>营销活动概览 · 模拟业务日期 2026-09-18</small><h2>从待审批到效果复盘</h2></div><span class="demo-badge">虚构聚合数据</span></div><div class="demo-case-grid">' + demo.cases.map(c=>'<article><span class="demo-badge">' + esc(c.status) + '</span><h3>' + esc(c.name) + '</h3><p>' + c.audience_size.toLocaleString('zh-CN') + '人 · ' + esc(c.version) + '</p><button class="btn" data-demo-case="' + esc(c.id) + '">查看链路与校验</button></article>').join('') + '</div>';
      cases.onclick=async e=>{try{const id=e.target.closest('[data-demo-case]')?.dataset.demoCase;if(!id)return;const ready=await request('/api/campaigns/'+encodeURIComponent(id)+'/readiness');const c=demo.cases.find(c=>c.id===id);modal(c.name,'<p class="demo-note">当前状态：'+esc(c.status)+'；实际价格与库存待上游核验。</p><div class="demo-check-list">'+ready.checks.map(v=>'<div><b class="'+(v.passed?'pass':'block')+'">'+(v.passed?'通过':'待补齐')+'</b><span><strong>'+esc(v.label)+'</strong><small>'+esc(v.detail)+'</small></span></div>').join('')+'</div>'+chainHTML(data,id));}catch(error){modal('校验加载失败','<p>'+esc(error.message)+'</p>');}};
      const profile=host('demoDynamicProfile',$('#audiences .page-head'),'after');profile.dataset.subviewPanel='personas packages';
      profile.innerHTML='<div class="demo-heading"><div><small>动态旅客画像 · 聚合样例</small><h2>行为信号如何变成可触达客群</h2></div><span class="demo-badge">36,420人快照</span></div><div class="demo-profile-grid"><div><h3>从关注到决策</h3><div class="demo-timeline">'+demo.profile.timeline.map(t=>'<article><small>'+esc(t.date)+'</small><b>'+esc(t.stage)+'</b><p>'+esc(t.event)+'</p><strong>意向 '+Math.round(t.intent*100)+'%</strong></article>').join('')+'</div></div><div><h3>圈选与保护排除</h3>'+bars(demo.profile.funnel)+'<p class="demo-note">排除510人：已出票、未授权或营销疲劳。人数由模拟聚合口径提供。</p></div><div><h3>客源地域</h3>'+bars(demo.profile.regions)+'</div><div><h3>服务偏好</h3>'+bars(demo.profile.preferences,'%')+'</div></div><details><summary>查看圈选规则与口径</summary><p>'+esc(demo.profile.rule)+'</p></details>';
      const signals=host('demoSignalEvidence',$('#opportunities .page-head'),'after');
      signals.dataset.subviewPanel='domain list';
      signals.innerHTML='<div class="demo-heading"><div><small>网络需求洞察 · 可追溯来源</small><h2>搜索、酒店和攻略共同支撑机会</h2></div><span class="demo-badge">演示评分92</span></div><div class="demo-signal-grid">'+demo.signals.map(s=>'<article><small>'+esc(s.source)+'</small><h3>'+esc(s.title)+'</h3><b>'+s.current.toLocaleString('zh-CN')+'<em>'+esc(s.unit)+'</em></b><p>对比上期 '+s.previous.toLocaleString('zh-CN')+' · '+(s.growth>0?'+':'')+s.growth+(s.unit.endsWith('%')?'个百分点':'%')+'</p><small>'+esc(s.window)+' · 证据置信度'+Math.round(s.confidence*100)+'%</small></article>').join('')+'</div><p class="demo-note">'+esc(demo.scoring)+'；评分规则用于展示，不代表模型预测准确率。</p>';
      if(demo.score_components)signals.insertAdjacentHTML('beforeend','<details><summary>评分依据 · 四项加权四舍五入为92</summary><div class="demo-case-grid">'+demo.score_components.map(c=>'<article><b>'+esc(c.label)+' '+c.score+'</b><p>权重'+c.weight+'% · '+esc(c.basis)+'</p></article>').join('')+'</div></details>');
      compactPanel(profile, '动态画像', '画像详情');
      compactPanel(signals, '需求信号', '查看依据');
      const agents=host('demoAgentCollaboration',$('#overview'));
      agents.innerHTML='<div class="demo-heading"><div><small>六大智能域 + 子智能体协作</small><h2>输入有依据，输出有业务对象</h2></div><button class="btn" data-agent-failure>查看阻断案例</button></div><div class="demo-agent-grid">'+Object.entries(labels).map(([id,label])=>{const runs=data.runs.filter(r=>r.domain_id===id);return '<article><small>'+esc(label)+'</small><h3>'+esc(kinds[id])+'</h3><p>'+esc(id==='opportunity-insight'?'市场信号 + 航线经营 + 产品商业化 → 商机候选':'读取业务版本与本体契约 → 生成候选 → 人工确认')+'</p><span>'+runs.length+'条记录</span><div><button class="btn" data-demo-run="'+esc(runs.find(r=>r.status!=='failed')?.id || '')+'">查看样例</button><button class="btn" data-demo-domain="'+id+'">运行</button></div></article>';}).join('')+'</div>';
      agents.onclick=async e=>{const run=e.target.closest('[data-demo-run]')?.dataset.demoRun;const domain=e.target.closest('[data-demo-domain]')?.dataset.demoDomain;if(domain)runDomain(domain);if(run)showRun(await request('/api/agent-runs/'+encodeURIComponent(run)));if(e.target.closest('[data-agent-failure]')){const failed=data.runs.find(r=>r.status==='failed');if(failed)showRun(await request('/api/agent-runs/'+encodeURIComponent(failed.id)));}};
      $('.demo-heading h2', agents).textContent='智能域';
      $('.demo-heading small', agents)?.remove();
      agents.querySelectorAll('article p').forEach(node=>node.remove());
      agents.querySelectorAll('[data-demo-run]').forEach(button=>{button.textContent='查看结果';if(!button.dataset.demoRun)button.disabled=true;});
      const touch=host('demoTouchpointReasons',$('#execution'));
      touch.innerHTML='<div class="demo-heading"><div><small>渠道与时机选择 · 主案例策略</small><h2>首触、补触与保护规则</h2></div></div><div class="demo-case-grid">'+demo.touchpoints.map(p=>'<article><span class="demo-badge">'+esc(p.role)+'</span><h3>'+esc(p.channel)+' · '+esc(p.time)+'</h3><p>'+esc(p.reason)+'</p><small>触发：'+esc(p.trigger)+'</small><p>'+esc(p.frequency)+'</p></article>').join('')+'</div><p class="demo-note">当前渠道联调按渠道任务分配；上述条件补触为策略示例，真实响应去重与调度由标准接口承接。</p>';
      compactPanel(touch, '触达策略', '策略详情');
      const ontology=host('demoOntologyChain',$('#graph .page-head'),'after');
      ontology.dataset.subviewPanel='instances';
      ontology.classList.add('demo-compact');
      ontology.innerHTML='<div class="demo-heading"><h2>本体业务链路</h2><select aria-label="选择本体案例" data-chain-case>'+demo.cases.map(c=>'<option value="'+esc(c.id)+'">'+esc(c.name)+'</option>').join('')+'</select><button type="button" class="btn" data-chain-detail>链路详情</button></div>';
      window.ceairSetChainCase=cid=>{if(demo.cases.some(c=>c.id===cid))$('[data-chain-case]',ontology).value=cid;};
      $('[data-chain-detail]',ontology).onclick=()=>modal('本体业务链路',chainHTML(data,$('[data-chain-case]',ontology).value));
      $('[data-chain-case]',ontology).onchange=e=>{window.ceairSetChainCase(e.target.value);const picker=$('[data-graph-case]');if(picker){picker.value=e.target.value;picker.dispatchEvent(new Event('change'));}};
      const learn=host('demoAttributionStatus',$('#feedback'));
      learn.innerHTML='<div class="demo-heading"><div><small>效果分析边界</small><h2>渠道事件可复盘，收益等待交易归因</h2></div><span class="demo-badge">'+esc(demo.attribution.status)+'</span></div><p>送达、点击和转化均采用渠道事件口径，不能直接相加作为去重旅客人数。</p><div class="demo-status-row">'+demo.attribution.missing.map(v=>'<span>待接入 · '+esc(v)+'</span>').join('')+'</div><p class="demo-note">没有订单收入与归因依据时，收入和ROI保持待回流。</p>';
      compactPanel(learn, '交易归因', '归因详情');
      const visual=host('demoVisualLibrary',$('#contents'));
      visual.dataset.subviewPanel='preview';
      visual.innerHTML='<div class="demo-heading"><div><small>AIGC文案 + 视觉模板</small><h2>基于客群与产品配置视觉内容</h2></div><span class="demo-badge">确认后保存 · 人工审核</span></div><div class="demo-visual-grid">'+data.contentAssets.filter(a=>a.generation_context?.visual&&a.status==='已审核'&&a.channel==='App').sort((a,b)=>(a.campaign_id==='ACT-2026-0921'?-1:0)-(b.campaign_id==='ACT-2026-0921'?-1:0)).slice(0,3).map(a=>'<article><div class="demo-poster">'+posterSVG(a.generation_context.visual,a.title)+'</div><h3>'+esc(a.name)+'</h3><button class="btn" data-demo-visual="'+a.id+'">编辑与导出视觉</button></article>').join('')+'</div>';
      visual.onclick=e=>{const id=e.target.closest('[data-demo-visual]')?.dataset.demoVisual;const asset=data.contentAssets.find(a=>String(a.id)===id);if(asset)window.ceairOpenVisual(asset);};
      $('.demo-heading h2',visual).textContent='视觉内容';
      $('.demo-heading small',visual)?.remove();
      $('.demo-heading h2',cases).textContent='活动概览';
      $('.demo-heading small',cases)?.remove();
      document.querySelectorAll('.demo-panel[data-subview-panel]').forEach(node=>{
        const selected=node.closest('.view')?.dataset.activeSubview;
        if(selected)node.hidden=!node.dataset.subviewPanel.split(/\s+/).includes(selected);
      });
    }
  };
  function chainHTML(data,cid) {
    const direct=data.graph.nodes.filter(n=>n.id===cid || n.attributes?.campaign_id===cid);
    const ids=new Set(direct.map(n=>n.id));
    // Include immediate business evidence; avoid unrelated cases through shared channels.
    for(let pass=0;pass<3;pass++) data.graph.edges.forEach(e=>{const target=data.graph.nodes.find(n=>n.id===e.target);if(ids.has(e.source)&&target&&(!target.attributes?.campaign_id||target.attributes.campaign_id===cid)&&!String(e.target).startsWith('ACT-'))ids.add(e.target);});
    // Include incoming document/claim evidence without traversing unrelated campaign branches.
    for(let pass=0;pass<3;pass++) data.graph.edges.forEach(e=>{const source=data.graph.nodes.find(n=>n.id===e.source);if(ids.has(e.target)&&source&&['KnowledgeDocument','KnowledgeChunk','KnowledgeClaim','Evidence','MarketSignal'].includes(source.type))ids.add(e.source);});
    return '<div class="demo-chain">'+stages.map(([type,label])=>{const nodes=data.graph.nodes.filter(n=>ids.has(n.id)&&n.type===type);return '<article><b>'+esc(label)+'</b>'+ (nodes.length?nodes.slice(0,6).map(n=>'<details><summary>'+esc(n.label)+'</summary><small>'+esc(n.attributes?.status || n.source)+'</small><p>来源：'+esc(n.source)+'</p><p>置信度：'+(n.attributes?.confidence_status==='未评估'?'未评估':Math.round(n.confidence*100)+'%')+'</p><pre>'+esc(JSON.stringify(n.attributes,null,2))+'</pre></details>').join(''):'<small>等待此阶段产生对象</small>')+'</article>';}).join('')+'</div>';
  }
})();
