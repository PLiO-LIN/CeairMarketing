/* A2UI v0.9.1 DOM renderer for the advertised Ceair catalog.
 * Flat component graph + JSON Pointer data model; no HTML/code from the agent.
 */
(function () {
  'use strict';
  const catalogId = 'ceair-marketing:assistant-v1';
  const pages = new Set(['overview','campaigns','opportunities','audiences','products','contents','approvals','execution','feedback','graph','imports','models','tenants','permissions']);
  const allowed = new Set(['Text','Column','Row','Card','Button','Divider','Chart','DataTable','TaskCard','MarketingStage']);
  const blocked = new Set(['__proto__','prototype','constructor']);
  const pointer = path => { if (typeof path !== 'string' || !path.startsWith('/')) throw Error('无效的数据路径'); const keys = path === '/' ? [] : path.slice(1).split('/').map(k => k.replace(/~1/g,'/').replace(/~0/g,'~')); if (keys.some(k => blocked.has(k))) throw Error('不允许的数据路径'); return keys; };
  const read = (model, binding) => binding && typeof binding === 'object' && 'path' in binding ? pointer(binding.path).reduce((v,k) => v?.[k],model) : binding;
  const node = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = String(text); return e; };
  const number = value => Number.isFinite(Number(value)) ? Math.max(0,Number(value)) : 0;
  const colors = ['#245b9e','#5494c5','#8dbbd8','#c62340','#d77988','#9daabd'];
  function table(columns, rows) {
    const scroll = node('div','a2ui-table-scroll'), table = node('table','table'), head = node('thead'), tr = node('tr');
    columns.forEach(c => tr.append(node('th','',c))); head.append(tr); table.append(head);
    const body = node('tbody'); rows.forEach(row => { const line = node('tr'); row.forEach(c => line.append(node('td','',c))); body.append(line); }); table.append(body); scroll.append(table); return scroll;
  }
  function chart(data) {
    const box = node('section','a2ui-chart'), header = node('div','a2ui-chart-head'), title = node('div');
    title.append(node('h3','',data.title || '统计'));
    if(data.unit!=='%' && !data.hideTotal)title.append(node('span','a2ui-chart-total',data.values.reduce((s,v)=>s+number(v),0).toLocaleString('zh-CN') + (data.unit || '条')));
    const controls = node('div','a2ui-chart-controls'), body = node('div','a2ui-chart-body'); header.append(title,controls); box.append(header,body);
    const labels = data.labels.slice(0,40), values = data.values.slice(0,40).map(number), total = values.reduce((s,v)=>s+v,0), max = Math.max(...values,1);
    const modes = data.hideTotal||data.unit==='%'?[['bar','柱状'],['table','明细']]:[['bar','柱状'],['donut','占比'],['table','明细']]; let mode = 'bar';
    function draw() {
      body.replaceChildren(); controls.querySelectorAll('[data-mode]').forEach(b => { b.classList.toggle('active',b.dataset.mode===mode); b.setAttribute('aria-pressed',String(b.dataset.mode===mode)); });
      if (!labels.length) { body.append(node('p','a2ui-empty','暂无统计记录')); return; }
      if (mode==='table') { body.append(table(['分类','数值（'+(data.unit||'条')+'）'],labels.map((l,i)=>[l,values[i].toLocaleString('zh-CN')]))); return; }
      if (mode==='donut') {
        let offset=0; const stops=values.map((v,i)=>{ const from=offset; offset+=total?v/total*100:0; return colors[i%colors.length]+' '+from+'% '+offset+'%'; });
        const disk=node('div','a2ui-donut'); disk.style.background=total?'conic-gradient('+stops.join(',')+')':'#e5ecf3'; disk.setAttribute('role','img'); disk.setAttribute('aria-label',labels.map((l,i)=>l+' '+values[i]).join('，')); disk.append(node('span','',total.toLocaleString('zh-CN'))); body.append(disk);
        const legend=node('div','a2ui-legend'); labels.forEach((l,i)=>{const row=node('div'),dot=node('i');dot.style.background=colors[i%colors.length];row.append(dot,node('span','',l),node('b','',total?(values[i]/total*100).toFixed(1)+'%':'0%'));legend.append(row);});body.append(legend); return;
      }
      const bars=node('div','a2ui-bars'); labels.forEach((l,i)=>{const row=node('div','a2ui-bar-row'),track=node('div','a2ui-bar-track'),fill=node('i');fill.style.width=(values[i]/max*100)+'%';fill.style.background=colors[i%colors.length];track.append(fill);row.append(node('span','',l),track,node('b','',values[i].toLocaleString('zh-CN')+(data.unit||'')));bars.append(row);});body.append(bars);
    }
    modes.forEach(([value,label])=>{const b=node('button','',label);b.type='button';b.dataset.mode=value;b.onclick=()=>{mode=value;draw();};controls.append(b);});
    const exportButton=node('button','','导出');exportButton.type='button';exportButton.onclick=()=>{const cell=v=>'"'+String(v).replace(/^[=+@\-]/,"'").replace(/"/g,'""')+'"';const csv='\ufeff分类,数值\r\n'+labels.map((l,i)=>cell(l)+','+values[i]).join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=node('a');a.href=url;a.download=(data.title||'统计')+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};controls.append(exportButton);
    box.append(node('small','a2ui-source',data.source||'当前工作区后台记录')); draw(); return box;
  }
  window.createA2UIRenderer = function (host, api) {
    const surfaces = new Map(), applied = [];
    function marketingStage(data,surface) {
      const box=node('details','a2ui-marketing-stage'),head=node('summary','a2ui-stage-head');box.open=['holiday-demand','holiday-ontology','holiday-plan'].includes(data.id);
      head.append(node('h3','',data.title));box.append(head);
      if(data.summary)box.append(node('p','a2ui-stage-summary',data.summary));
      if(data.controls){
        const form=node('form','a2ui-scenario-controls');
        const field=(name,label,options,value,type='text')=>{const wrap=node('label','',label),control=node(options?'select':'input');control.name=name;if(options)options.forEach(o=>{const op=node('option','',typeof o==='string'?o:o.label);op.value=typeof o==='string'?o:o.value;control.append(op);});else control.type=type;control.value=value??'';wrap.append(control);form.append(wrap);return control;};
        field('route_id','航线',data.controls.routes,data.params.route_id);field('segment','客群',data.controls.segments,data.params.segment);field('channel','渠道',data.controls.channels,data.params.channel);
        field('product_id','候选产品',data.controls.products,data.params.product_id);
        field('start','出发日期',null,data.params.start,'date');field('end','结束日期',null,data.params.end,'date');const budget=field('budget_yuan','预算（元）',null,data.params.budget_yuan,'number');budget.min=0;budget.max=10000000;
        const b=node('button','btn','重新分析');b.type='submit';form.append(b);form.onsubmit=e=>{e.preventDefault();if(api.busy?.()){api.toast('请等待本轮分析结束');return;}if(!form.reportValidity())return;const v=Object.fromEntries(new FormData(form));api.ask?.(`分析节假日出行营销：${v.start} 至 ${v.end}，${v.route_id}，${v.segment}，${v.channel}，${v.product_id}，预算${v.budget_yuan}元`);};box.append(form);
      }
      if(data.metrics){const grid=node('div','a2ui-stage-metrics');data.metrics.forEach(m=>{const cell=node('div');cell.append(node('span','',m.label),node('b','',typeof m.value==='number'?m.value.toLocaleString('zh-CN'):m.value));grid.append(cell);});box.append(grid);}
      if(data.chart)box.append(chart({...data.chart,hideTotal:true}));
      if(data.table){const detail=node('details','a2ui-stage-detail');detail.append(node('summary','','查看明细'),table(data.table.columns,data.table.rows));box.append(detail);}
      if(data.reference?.rows?.length){const detail=node('details','a2ui-stage-detail');detail.append(node('summary','','爬取报价参考 · 待核验'),table(data.reference.columns,data.reference.rows));box.append(detail);}
      if(data.checks?.length){const detail=node('details','a2ui-stage-detail');detail.append(node('summary','','资格与约束 · '+data.checks.length));const list=node('div','a2ui-rule-list');data.checks.forEach(c=>{const line=node('div','a2ui-rule'),state=node('span','a2ui-rule-state',c.status);state.dataset.state=c.status;line.append(node('b','',c.name),state,node('span','a2ui-rule-detail',c.detail));list.append(line);});detail.append(list);box.append(detail);}
      if(data.graph?.paths?.length){
        const graph=node('div','a2ui-evidence-graph'),toolbar=node('div','a2ui-graph-toolbar'),canvas=node('div','a2ui-paths'),inspector=node('div','a2ui-node-inspector');inspector.setAttribute('role','status');
        const lookup=new Map(data.graph.nodes.map(n=>[n.id,n]));let omitted='',selectedPath=0;
        const select=node('select');select.setAttribute('aria-label','本体关系对照');[['','完整本体'],['operates_on','移除航线归属'],['uses_product','移除票价产品'],['includes_ancillary','移除辅营包含']].forEach(([value,label])=>{const o=node('option','',label);o.value=value;select.append(o);});toolbar.append(node('b','','本体证据路径'),select);graph.append(toolbar,canvas,inspector);
        const pathPicker=node('select');pathPicker.setAttribute('aria-label','证据路径');data.graph.paths.forEach((p,i)=>{const op=node('option','',p.title+' · '+(i+1));op.value=String(i);pathPicker.append(op);});toolbar.append(pathPicker);
        function draw(){canvas.replaceChildren();[data.graph.paths[selectedPath]].forEach(path=>{const row=node('div','a2ui-graph-path');row.append(node('small','',path.title));const flow=node('div','a2ui-path-flow');path.nodes.forEach((id,i)=>{if(i){const r=path.relations[i-1],edge=node('span','a2ui-graph-edge'+(r===omitted?' missing':''),r===omitted?'关系缺失 ✕':({'has_cabin':'提供舱位','has_fare':'对应票价','uses_product':'票价产品','operates_on':'执飞航线','arrives_at':'到达机场','includes_ancillary':'包含辅营','has_metric':'库存观测'}[r]||r));flow.append(edge);}const n=lookup.get(id),b=node('button','a2ui-graph-node');b.type='button';b.append(node('small','',n?.type||'对象'),node('b','',n?.label||id));b.onclick=()=>{inspector.replaceChildren(node('b','',n?.label||id),node('p','',`来源：${n?.source||'未知'} · ${n?.dataset||''} / ${n?.record||id}`));if(n?.facts)inspector.append(table(['属性','观测值'],Object.entries(n.facts).map(([k,v])=>[k,v==null?'未知':String(v)])));};flow.append(b);});row.append(flow);canvas.append(row);});if(omitted){const comparison=data.comparison?.find(c=>c.relation===omitted);inspector.replaceChildren(node('b','','对照结果'),node('p','',comparison?.without||'关系缺失，停止组合'),node('small','','原始本体未修改；实际缺边由后台校验阻断。'));}else inspector.replaceChildren(node('small','','点击对象查看来源、版本与观测值'));}
        pathPicker.onchange=()=>{selectedPath=Number(pathPicker.value);draw();};
        let comparisonRevision=0;
        select.onchange=async()=>{omitted=select.value;draw();const revision=++comparisonRevision;if(!omitted)return;inspector.replaceChildren(node('p','','后台正在重新计算关系约束…'));try{const result=await api.request('/api/holiday-marketing/compare',{method:'POST',body:JSON.stringify({params:data.params,relation:omitted})});if(revision!==comparisonRevision)return;inspector.replaceChildren(node('b','','后台对照结果'),table(['条件','完整本体','忽略该关系'],[['有效航班',result.baseline.qualified_flights,result.omitted.qualified_flights],['候选产品',result.baseline.qualified_products,result.omitted.qualified_products],['生成方案',result.baseline.ready?'可生成':'阻断',result.omitted.ready?'可生成':'阻断']]),node('small','',result.summary));}catch(error){if(revision===comparisonRevision)inspector.replaceChildren(node('p','assistant-ui-error',error.message));}};draw();box.append(graph);
      }
      if(data.proposal){const p=data.proposal,card=node('div','a2ui-proposal');card.append(node('b','',p.name),node('span','a2ui-rule-state',p.status),node('p','',p.content.title),node('blockquote','',p.content.body));box.append(card);}
      if(data.evidence?.length||data.sources){const detail=node('details','a2ui-stage-detail');detail.append(node('summary','','查看依据与口径'));data.evidence?.forEach(t=>detail.append(node('p','',t)));if(data.sources)detail.append(table(['数据集','记录数','来源','口径'],data.sources.map(s=>[s.dataset,s.rows,s.source,s.mode])));box.append(detail);}
      data.actions?.forEach(a=>{if(a.kind!=='draft')return;const b=node('button','btn primary',a.label),status=node('div','a2ui-action-status');status.setAttribute('role','status');b.type='button';b.onclick=async()=>{if(api.busy?.()){api.toast('请等待本轮分析结束');return;}b.disabled=true;status.textContent='重新校验方案…';try{const result=await api.request('/api/assistant/ui-action',{method:'POST',body:JSON.stringify({version:'v0.9.1',action:{name:'prepare_holiday_draft',surfaceId:surface.id,sourceComponentId:'content',timestamp:new Date().toISOString(),context:{conversation_id:api.conversationId()}}})});status.textContent='';if(!status.querySelector('.assistant-task-card')){const anchor=node('span');status.append(anchor);api.task(result.task,anchor);anchor.remove();}}catch(error){status.textContent=error.message;}finally{b.disabled=false;}};box.append(b,status);});
      return box;
    }
    function render(surface) {
      if (!surface.components.has('root')) return;
      const visited = new Set();
      function component(id, depth=0) {
        if (depth>24 || visited.has(id)) throw Error('界面组件引用异常');
        const c=surface.components.get(id);if(!c)throw Error('界面组件尚未完整'); if (!allowed.has(c.component)) throw Error('不支持的界面组件');visited.add(id);
        let e; const value = binding => read(surface.model,binding);
        if (c.component==='Text') e=node('div','a2ui-text',value(c.text)||'');
        if (['Column','Row','Card'].includes(c.component)) {e=node('div','a2ui-'+c.component.toLowerCase());const ids=c.component==='Card'?[c.child]:c.children;if(!Array.isArray(ids))throw Error('不支持的布局绑定');ids.forEach(child=>e.append(component(child,depth+1)));}
        if(c.component==='Divider') e=node('hr');
        if(c.component==='Button'){e=node('button','btn'+(c.variant==='primary'?' primary':''));e.type='button';e.append(component(c.child,depth+1));e.onclick=async()=>{const action=c.action?.event;if(!action||action.name!=='open_page'||!pages.has(action.context?.page))return; e.disabled=true;try{const result=await api.request('/api/assistant/ui-action',{method:'POST',body:JSON.stringify({version:'v0.9.1',action:{name:action.name,surfaceId:surface.id,sourceComponentId:c.id,timestamp:new Date().toISOString(),context:action.context}})});api.navigate(result.page);}catch(error){api.toast(error.message);}finally{e.disabled=false;}};}
        if(c.component==='Chart'){const data=value(c.data);if(!data||!Array.isArray(data.labels)||!Array.isArray(data.values))throw Error('统计数据格式异常');e=chart(data);}
        if(c.component==='DataTable'){const data=value(c.data);if(!data||!Array.isArray(data.columns)||!Array.isArray(data.rows))throw Error('明细数据格式异常');e=node('section','a2ui-data-table');e.append(node('h3','',data.title),table(data.columns,data.rows));if(pages.has(data.page)){const b=node('button','btn','查看全部（'+number(data.total)+'）');b.type='button';b.onclick=()=>api.navigate(data.page);e.append(b);}}
        if(c.component==='TaskCard'){const item=value(c.task);if(!item?.id)throw Error('任务数据格式异常');e=node('div','a2ui-task');const anchor=node('span');e.append(anchor);api.task(item,anchor);anchor.remove();}
        if(c.component==='MarketingStage'){const data=value(c.data);if(!data?.id||!data.title)throw Error('营销过程数据格式异常');e=marketingStage(data,surface);}
        visited.delete(id); e.dataset.componentId=c.id; return e;
      }
      const signature=JSON.stringify([surface.model,[...surface.components]]);if(signature===surface.signature)return;
      const root=component('root');surface.element.replaceChildren(root);surface.signature=signature;
    }
    function accept(message) {
      if(message.version!=='v0.9.1')throw Error('不支持的A2UI版本');
      const fingerprint=JSON.stringify(message);
      const keys=['createSurface','updateDataModel','updateComponents','deleteSurface'].filter(k=>message[k]);if(keys.length!==1)throw Error('界面消息格式异常'); const op=keys[0],payload=message[op];
      if(typeof payload.surfaceId!=='string')throw Error('界面标识无效');
      if(op==='createSurface'){if(payload.catalogId!==catalogId)throw Error('界面组件目录未授权');if(surfaces.has(payload.surfaceId))throw Error('界面重复创建');const element=node('section','a2ui-surface');element.dataset.surfaceId=payload.surfaceId;host.append(element);surfaces.set(payload.surfaceId,{id:payload.surfaceId,element,components:new Map(),model:{}});}
      else {const s=surfaces.get(payload.surfaceId);if(!s)throw Error('界面未创建');if(op==='deleteSurface'){s.element.remove();surfaces.delete(s.id);}else{if(op==='updateComponents'){if(!Array.isArray(payload.components)||payload.components.length>150)throw Error('界面组件数量异常');for(const c of payload.components){if(!allowed.has(c.component)||typeof c.id!=='string')throw Error('不支持的界面组件');s.components.set(c.id,c);}}else{const path=pointer(payload.path||'/');if(!path.length)s.model=payload.value??{};else{let parent=s.model;for(const k of path.slice(0,-1)){if(!parent[k]||typeof parent[k]!=='object')parent[k]={};parent=parent[k];}if('value' in payload)parent[path.at(-1)]=payload.value;else delete parent[path.at(-1)];}}render(s);}}
      applied.push(fingerprint);
    }
    return { accept, restore: messages => { let skip=0; while(skip<applied.length&&skip<messages.length&&applied[skip]===JSON.stringify(messages[skip]))skip++; messages.slice(skip).forEach(accept); } };
  };
})();
