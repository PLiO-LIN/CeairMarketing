/* A2UI v0.9.1 DOM renderer for the advertised Ceair catalog.
 * Flat component graph + JSON Pointer data model; no HTML/code from the agent.
 */
(function () {
  'use strict';
  const catalogId = 'ceair-marketing:assistant-v1';
  const pages = new Set(['overview','campaigns','opportunities','audiences','products','contents','approvals','execution','feedback','graph','imports','models','tenants','permissions']);
  const allowed = new Set(['Text','Column','Row','Card','Button','Divider','Chart','DataTable','TaskCard']);
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
    title.append(node('h3','',data.title || '统计'),node('span','a2ui-chart-total',data.values.reduce((s,v)=>s+number(v),0).toLocaleString('zh-CN') + (data.unit || '条')));
    const controls = node('div','a2ui-chart-controls'), body = node('div','a2ui-chart-body'); header.append(title,controls); box.append(header,body);
    const labels = data.labels.slice(0,40), values = data.values.slice(0,40).map(number), total = values.reduce((s,v)=>s+v,0), max = Math.max(...values,1);
    const modes = [['bar','柱状'],['donut','占比'],['table','明细']]; let mode = 'bar';
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
