/* Public AgentScope event timeline; thinking deltas are never transported. */
(function () {
  'use strict';
  const names={search_marketing_knowledge:'检索营销知识',query_marketing_ontology:'查询本体关系',inspect_campaign:'查询活动状态',list_available_products:'查询产品',inspect_data_pipeline:'查询数据进度',query_platform:'查询业务记录',platform_api_catalog:'选择业务能力',query_statistics:'生成统计图表',prepare_platform_task:'创建任务',remember_preference:'保存记忆',open_platform_page:'打开工作台'};
  const element=(tag,cls,text)=>{const e=document.createElement(tag);e.className=cls||'';if(text!=null)e.textContent=String(text);return e;};
  window.createAssistantProcess=function(host){
    const root=element('details','assistant-process');root.open=document.body.classList.contains('smartspace-mode');const summary=element('summary'),label=element('b','','执行过程'),status=element('span','','准备中'),list=element('div','assistant-process-list');summary.append(label,status);root.append(summary,list);host.prepend(root);
    const tools=new Map(),seen=new Set();let model,count=0,start;
    function step(title,item){count++;const e=element('details','assistant-process-step'),s=element('summary'),dot=element('i','process-dot'),titleNode=element('b','',title),state=element('span','process-state','进行中'),body=element('div','process-step-body');s.append(dot,titleNode,state);e.append(s,body);list.append(e);return {e,body,state,start:Date.parse(item.timestamp)||Date.now()};}
    function section(s,title,data){if(!s||data==null||data==='')return;const d=element('div','process-evidence');d.append(element('b','',title),element('pre','',typeof data==='string'?data:JSON.stringify(data,null,2)));s.body.append(d);}
    function finishStep(s,item,failed=false){if(!s)return;s.e.classList.add(failed?'is-error':'is-complete');const elapsed=Math.max(0,((Date.parse(item.timestamp)||Date.now())-s.start)/1000);s.state.textContent=(failed?'失败':'完成')+' · '+elapsed.toFixed(1)+'s';}
    function add(item){const key=JSON.stringify(item);if(seen.has(key))return;seen.add(key);start??=Date.parse(item.timestamp)||Date.now();const event=item.event;
      if(event==='harness/context-loaded'){const line=element('div','process-note','已加载当前工作区、业务权限与本体上下文');list.append(line);}
      if(event==='harness/model-started'){model=step('分析任务',item);section(model,'动作说明',item.summary||'分析任务并选择下一步操作');status.textContent='分析任务';}
      if(event==='harness/model-finished'){finishStep(model,item);section(model,'输出',item.summary||'模型输出完成');if(item.total_tokens)section(model,'用量',item.total_tokens+' tokens');}
      if(event==='agent/plan'){const line=element('div','process-note',item.summary);list.append(line);}
      if(event==='harness/tool-started'){const s=step(names[item.tool]||item.tool||'业务查询',item);tools.set(item.tool_call_id||item.tool,s);status.textContent=names[item.tool]||'执行业务查询';}
      if(event==='harness/tool-input')section(tools.get(item.tool_call_id),'输入参数',item.arguments);
      if(event==='harness/tool-finished'||event==='harness/tool-failed'){const s=tools.get(item.tool_call_id||item.tool);finishStep(s,item,event==='harness/tool-failed');if(s)section(s,'工具输出',item.result??item.summary??'已返回');status.textContent=event==='harness/tool-failed'?'工具返回错误':'整理结果';}
      if(event==='model/provider-fallback')list.append(element('div','process-note','已切换到备用模型'));
      label.textContent='执行过程'+(count?' · '+count+' 步':'');
    }
    function finish(failed=false,end=Date.now()){const seconds=start?Math.max(0,(end-start)/1000).toFixed(1):'0';status.textContent=(failed?'未完成':'已完成')+' · '+seconds+'s';root.classList.toggle('is-error',failed);root.open=false;if(failed){for(const s of [model,...tools.values()])if(s&&!s.e.classList.contains('is-complete')&&!s.e.classList.contains('is-error'))s.state.textContent='未完成';}}
    return {add,finish,restore:(items,failed)=>{items.forEach(add);finish(failed,Date.parse(items.at(-1)?.timestamp)||Date.now());},root};
  };
})();
