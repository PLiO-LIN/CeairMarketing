import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, Bot, Building2, CheckCircle2, ChevronRight, CircleCheck,
  Database, FileUp, GitBranch, LayoutDashboard, LogOut, Network, Play, Plus,
  Radio, RefreshCw, Save, Search, ServerCog, Settings2, ShieldCheck, Upload,
  UsersRound, X, MessageSquare, BookOpen, Check, XCircle, Eye, Clock3, Sparkles,
} from 'lucide-react'
import './App.css'

type Tenant = { id: number; code: string; name: string; role: string }
type Session = { access_token: string; display_name: string; tenants: Tenant[]; is_platform_admin: boolean }
type Campaign = { id: string; name: string; stage: string; status: string; version: string; owner: string; audience_size: number; product_package: string; budget_yuan: number; roi_target: number }
type AgentDomain = { id: string; name: string; module: string; responsibility: string; input_types: string[]; output_types: string[] }
type RuntimeEvent = { id: string; event_type: string; timestamp: string }
type AgentRun = { id: string; campaign_id: string; domain_id: string; status: string; summary: string; events?: RuntimeEvent[]; created_at?: string; operator?: string }
type GraphNode = { id: string; type: string; label: string; source: string; confidence: number; attributes: Record<string, unknown> }
type GraphEdge = { source: string; relation: string; target: string; confidence: number; evidence: string }
type MarketingGraph = { nodes: GraphNode[]; edges: GraphEdge[] }
type GraphStats = { entity_count: number; relation_count: number; entity_types: Record<string, number>; source_count: number }
type ImportJob = { id: string; dataset_type: string; file_name: string; file_format: string; status: string; total_rows: number; accepted_rows: number; rejected_rows: number; errors: Array<{ row: number; message: string }>; created_at: string }
type DataPipelineJob = { id: string; file_name: string; file_format: string; source_type: string; status: string; current_stage: string; mineru_task_id: string; provider_id: number | null; total_entities: number; total_relations: number; accepted_entities: number; accepted_relations: number; rejected_items: number; result: { events?: Array<Record<string, unknown>>; candidates?: { entities?: Array<Record<string, unknown>>; relations?: Array<Record<string, unknown>> }; review?: Record<string, unknown>; [key: string]: unknown }; error_message: string; created_at: string; started_at?: string; completed_at?: string }
type ModelProvider = { id: number; display_name: string; provider_type: string; base_url: string; model_name: string; timeout_seconds: number; temperature: number; max_tokens: number; enabled: boolean; is_default: boolean; api_key_configured: boolean }
type PlatformUser = { id: number; username: string; display_name: string; enabled: boolean; is_platform_admin: boolean; memberships: Tenant[] }
type ProviderForm = { display_name: string; provider_type: string; base_url: string; model_name: string; api_key: string; timeout_seconds: number; temperature: number; max_tokens: number; enabled: boolean; is_default: boolean }

const API = import.meta.env.VITE_API_BASE ?? ''
const emptyProvider: ProviderForm = { display_name: '', provider_type: 'openai-compatible', base_url: '', model_name: '', api_key: '', timeout_seconds: 60, temperature: 0.3, max_tokens: 2048, enabled: true, is_default: false }
const lifecycle = [['01', '机会识别'], ['02', '产品引用'], ['03', '内容生产'], ['04', '审批管控'], ['05', '触达执行'], ['06', '效果复盘']]

function App() {
  const [session, setSession] = useState<Session | null>(() => {
    const raw = localStorage.getItem('ceair-session'); return raw ? JSON.parse(raw) : null
  })
  const [tenantId, setTenantId] = useState<number | null>(() => Number(localStorage.getItem('ceair-tenant')) || null)
  const [view, setView] = useState('overview')
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [domains, setDomains] = useState<AgentDomain[]>([])
  const [providers, setProviders] = useState<ModelProvider[]>([])
  const [graph, setGraph] = useState<MarketingGraph>({ nodes: [], edges: [] })
  const [stats, setStats] = useState<GraphStats>({ entity_count: 0, relation_count: 0, entity_types: {}, source_count: 0 })
  const [imports, setImports] = useState<ImportJob[]>([])
  const [pipelines, setPipelines] = useState<DataPipelineJob[]>([])
  const [runs, setRuns] = useState<AgentRun[]>([])
  const [platformTenants, setPlatformTenants] = useState<Tenant[]>([])
  const [platformUsers, setPlatformUsers] = useState<PlatformUser[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [query, setQuery] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [running, setRunning] = useState('')
  const [providerPanel, setProviderPanel] = useState(false)
  const [editingProvider, setEditingProvider] = useState<number | null>(null)
  const [providerForm, setProviderForm] = useState<ProviderForm>(emptyProvider)
  const [chatMessages, setChatMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string; trace?: Array<Record<string, unknown>>; sources?: Array<Record<string, unknown>> }>>([])
  const [chatInput, setChatInput] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const [pipelineDetail, setPipelineDetail] = useState<DataPipelineJob | null>(null)
  const [floatingChatOpen, setFloatingChatOpen] = useState(false)
  const [floatingChatInput, setFloatingChatInput] = useState('')
  const [floatingChatBusy, setFloatingChatBusy] = useState(false)
  const [floatingChatMessages, setFloatingChatMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string; trace?: Array<Record<string, unknown>>; sources?: Array<Record<string, unknown>> }>>([])

  const activeTenant = session?.tenants.find((item) => item.id === tenantId) ?? session?.tenants[0]

  async function request<T>(path: string, init?: RequestInit, form = false): Promise<T> {
    const response = await fetch(`${API}${path}`, {
      ...init,
      headers: {
        ...(form ? {} : { 'Content-Type': 'application/json' }),
        Authorization: `Bearer ${session?.access_token ?? ''}`,
        'X-Tenant-ID': String(activeTenant?.id ?? ''),
        ...(init?.headers ?? {}),
      },
    })
    if (response.status === 401) { logout(); throw new Error('登录状态已过期，请重新登录') }
    if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail ?? `请求失败（${response.status}）`) }
    if (response.status === 204) return undefined as T
    return response.json()
  }

  async function loadTenantData() {
    if (!session || !activeTenant) return
    try {
      const [campaignData, domainData, providerData, graphData, statData, importData, runData, pipelineData] = await Promise.all([
        request<Campaign[]>('/api/campaigns'), request<AgentDomain[]>('/api/agent-domains'), request<ModelProvider[]>('/api/model-providers'),
        request<MarketingGraph>('/api/graph'), request<GraphStats>('/api/graph/stats'), request<ImportJob[]>('/api/imports'), request<AgentRun[]>('/api/agent-runs'), request<DataPipelineJob[]>('/api/data-pipelines'),
      ])
      setCampaigns(campaignData); setDomains(domainData); setProviders(providerData); setGraph(graphData); setStats(statData); setImports(importData); setRuns(runData); setPipelines(pipelineData)
      setSelectedId((current) => campaignData.some((item) => item.id === current) ? current : campaignData[0]?.id ?? '')
      setError('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '租户数据加载失败') }
  }

  async function loadPlatformData() {
    if (!session?.is_platform_admin) return
    try {
      const [tenants, users] = await Promise.all([request<Tenant[]>('/api/platform/tenants'), request<PlatformUser[]>('/api/platform/users')])
      setPlatformTenants(tenants); setPlatformUsers(users)
    } catch (cause) { setMessage(cause instanceof Error ? cause.message : '平台数据加载失败') }
  }

  useEffect(() => { void loadTenantData() }, [session?.access_token, activeTenant?.id])
  useEffect(() => {
    if (view !== 'imports' || !pipelines.some((item) => ['queued', 'running', 'awaiting_confirmation'].includes(item.status))) return
    const timer = window.setInterval(() => { void loadTenantData() }, 1800)
    return () => window.clearInterval(timer)
  }, [view, pipelines.map((item) => `${item.id}:${item.status}:${item.current_stage}`).join('|')])
  useEffect(() => { if (view === 'tenants') void loadPlatformData() }, [view, session?.access_token])
  useEffect(() => { if (!message) return; const timer = setTimeout(() => setMessage(''), 3500); return () => clearTimeout(timer) }, [message])

  function onLogin(value: Session) {
    localStorage.setItem('ceair-session', JSON.stringify(value)); setSession(value)
    const first = value.tenants[0]?.id ?? null; setTenantId(first); if (first) localStorage.setItem('ceair-tenant', String(first))
  }
  function switchTenant(value: number) { setTenantId(value); localStorage.setItem('ceair-tenant', String(value)); setView('overview') }
  function logout() { localStorage.removeItem('ceair-session'); localStorage.removeItem('ceair-tenant'); setSession(null); setTenantId(null) }

  async function runDomain(domainId: string) {
    if (!selectedId) { setMessage('当前租户没有可运行的活动'); return }
    setRunning(domainId)
    try {
      const result = await request<AgentRun>('/api/agent-runs', { method: 'POST', body: JSON.stringify({ campaign_id: selectedId, domain_id: domainId }) })
      setMessage(result.summary); await loadTenantData()
    } catch (cause) { setMessage(cause instanceof Error ? cause.message : '运行失败') } finally { setRunning('') }
  }

  async function uploadData(_datasetType: string, file: File) {
    const form = new FormData(); form.append('file', file)
    try {
      const result = await request<{ job: DataPipelineJob }>('/api/data-pipelines', { method: 'POST', body: form }, true)
      setPipelineDetail(result.job); setMessage('文件已进入数据处理流水线，系统将实时记录每一步处理过程'); await loadTenantData()
    } catch (cause) { setMessage(cause instanceof Error ? cause.message : '导入失败') }
  }

  async function reviewPipeline(job: DataPipelineJob, decision: 'approve' | 'reject') {
    try {
      const result = await request<DataPipelineJob>(`/api/data-pipelines/${job.id}/review`, { method: 'POST', body: JSON.stringify({ decision, note: decision === 'approve' ? '业务人员确认本次候选本体更新' : '业务人员驳回本次候选本体更新' }) })
      setPipelineDetail(result); setMessage(decision === 'approve' ? '已确认，本体更新完成' : '已驳回，本体未更新'); await loadTenantData()
    } catch (cause) { setMessage(cause instanceof Error ? cause.message : '审核操作失败') }
  }

  async function sendChat() {
    const content = chatInput.trim()
    if (!content || chatBusy) return
    const history = [...chatMessages, { role: 'user' as const, content }]
    setChatMessages(history); setChatInput(''); setChatBusy(true)
    try {
      const result = await request<{ conversation_id: string; answer: string; trace: Array<Record<string, unknown>>; sources: Array<Record<string, unknown>> }>('/api/agent-chat', { method: 'POST', body: JSON.stringify({ message: content, history: history.slice(0, -1).slice(-12) }) })
      setChatMessages([...history, { role: 'assistant', content: result.answer, trace: result.trace, sources: result.sources }])
    } catch (cause) { setChatMessages([...history, { role: 'assistant', content: cause instanceof Error ? cause.message : '智能体运行失败' }]) } finally { setChatBusy(false) }
  }

  async function sendFloatingChat() {
    const content = floatingChatInput.trim()
    if (!content || floatingChatBusy) return
    const history = [...floatingChatMessages, { role: 'user' as const, content }]
    setFloatingChatMessages(history); setFloatingChatInput(''); setFloatingChatBusy(true)
    try {
      const result = await request<{ conversation_id: string; answer: string; trace: Array<Record<string, unknown>>; sources: Array<Record<string, unknown>> }>('/api/agent-chat', { method: 'POST', body: JSON.stringify({ message: content, domain_id: 'marketing-copilot', history: history.slice(0, -1).slice(-12) }) })
      setFloatingChatMessages([...history, { role: 'assistant', content: result.answer, trace: result.trace, sources: result.sources }])
    } catch (cause) {
      setFloatingChatMessages([...history, { role: 'assistant', content: cause instanceof Error ? cause.message : '智能体运行失败，请稍后重试' }])
    } finally { setFloatingChatBusy(false) }
  }

  function openProvider(provider?: ModelProvider) {
    if (provider) {
      setEditingProvider(provider.id)
      setProviderForm({ display_name: provider.display_name, provider_type: provider.provider_type, base_url: provider.base_url, model_name: provider.model_name, api_key: '', timeout_seconds: provider.timeout_seconds, temperature: provider.temperature, max_tokens: provider.max_tokens, enabled: provider.enabled, is_default: provider.is_default })
    } else { setEditingProvider(null); setProviderForm(emptyProvider) }
    setProviderPanel(true)
  }
  async function saveProvider() {
    const payload: Partial<ProviderForm> = { ...providerForm }; if (editingProvider && !payload.api_key) delete payload.api_key
    try {
      await request(editingProvider ? `/api/model-providers/${editingProvider}` : '/api/model-providers', { method: editingProvider ? 'PUT' : 'POST', body: JSON.stringify(payload) })
      setProviderPanel(false); setMessage('模型配置已保存'); await loadTenantData()
    } catch (cause) { setMessage(cause instanceof Error ? cause.message : '保存失败') }
  }
  async function providerAction(provider: ModelProvider, action: 'test' | 'default' | 'delete') {
    try {
      if (action === 'delete' && !confirm(`确认删除“${provider.display_name}”吗？`)) return
      const method = action === 'delete' ? 'DELETE' : 'POST'
      const path = action === 'default' ? `/api/model-providers/${provider.id}/default` : action === 'test' ? `/api/model-providers/${provider.id}/test` : `/api/model-providers/${provider.id}`
      const result = await request<{ message?: string }>(path, { method })
      setMessage(action === 'test' ? result.message ?? '模型连接正常' : action === 'default' ? '默认模型已切换' : '模型配置已删除'); await loadTenantData()
    } catch (cause) { setMessage(cause instanceof Error ? cause.message : '操作失败') }
  }

  const filtered = useMemo(() => campaigns.filter((item) => `${item.id}${item.name}${item.product_package}${item.status}`.includes(query)), [campaigns, query])
  if (!session) return <Login onLogin={onLogin}/>

  const nav = [
    ['overview', '运营总览', LayoutDashboard], ['campaigns', '活动工作台', Activity], ['agents', '智能域运行', Bot],
    ['chat', '营销智能助手', MessageSquare], ['ontology', '营销知识', BookOpen], ['imports', '数据处理流水线', FileUp], ['models', '模型配置', ServerCog],
    ...(session.is_platform_admin ? [['tenants', '租户与用户', Building2] as const] : []),
  ] as const
  return <div className="app-shell production-shell">
    <aside className="sidebar">
      <div className="brand"><img className="brand-symbol" src={`${import.meta.env.BASE_URL}brand/ceair-symbol.svg`} alt="东方航空"/><div className="brand-copy"><img className="brand-wordmark" src={`${import.meta.env.BASE_URL}brand/ceair-wordmark.svg`} alt="中国东方航空"/><b>智能营销活动及服务平台</b></div></div>
      <div className="tenant-card"><Building2/><div><small>当前租户</small><b>{activeTenant?.name}</b><span>{activeTenant?.code} · {activeTenant?.role}</span></div></div>
      <nav><div className="nav-section"><p>业务工作台</p>{nav.map(([id, label, Icon]) => <button key={id} className={view === id ? 'active' : ''} onClick={() => setView(id)}><Icon size={16}/><span>{label}</span></button>)}</div></nav>
      <div className="operator"><b>{session.display_name}</b><span>{activeTenant?.role === 'admin' ? '租户管理员' : '营销运营人员'}</span><button onClick={logout}><LogOut/>退出</button></div>
    </aside>
    <main><header className="topbar"><div><span>东方航空</span><ChevronRight size={14}/><b>{nav.find(([id]) => id === view)?.[1]}</b></div><div className="top-actions"><select value={activeTenant?.id} onChange={(event) => switchTenant(Number(event.target.value))}>{session.tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}</select><label><Search/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索活动、产品包或实体"/></label><button title="刷新" onClick={() => void loadTenantData()}><RefreshCw/></button></div></header>
      {error && <div className="error-banner"><AlertTriangle/>{error}</div>}
      <div className="page">
        {view === 'overview' && <Overview campaigns={campaigns} stats={stats} imports={imports} providers={providers} tenant={activeTenant}/>} 
        {view === 'campaigns' && <Campaigns campaigns={filtered} selectedId={selectedId} onSelect={setSelectedId}/>} 
        {view === 'agents' && <Agents domains={domains} campaigns={campaigns} selectedId={selectedId} onSelect={setSelectedId} running={running} onRun={runDomain} runs={runs}/>} 
        {view === 'chat' && <ChatWorkspace messages={chatMessages} input={chatInput} busy={chatBusy} onInput={setChatInput} onSend={sendChat}/>} 
        {view === 'ontology' && <KnowledgeWorkspace graph={graph} stats={stats} request={request}/>} 
        {view === 'imports' && <DataPipelineWorkspace jobs={pipelines} detail={pipelineDetail} onDetail={setPipelineDetail} onUpload={uploadData} onReview={reviewPipeline}/>} 
        {view === 'models' && <Models providers={providers} canManage={activeTenant?.role === 'admin'} request={request} onAdd={() => openProvider()} onEdit={openProvider} onAction={providerAction}/>} 
        {view === 'tenants' && <TenantAdmin tenants={platformTenants} users={platformUsers} request={request} onReload={async () => { await loadPlatformData(); const updated = await request<{ tenants: Tenant[] }>('/api/auth/me'); const next = { ...session, tenants: updated.tenants }; localStorage.setItem('ceair-session', JSON.stringify(next)); setSession(next) }}/>} 
      </div>
    </main>
    {providerPanel && <ProviderDrawer form={providerForm} editing={editingProvider !== null} onChange={setProviderForm} onClose={() => setProviderPanel(false)} onSave={saveProvider}/>} 
    <FloatingCopilot open={floatingChatOpen} messages={floatingChatMessages} input={floatingChatInput} busy={floatingChatBusy} onToggle={() => setFloatingChatOpen((value) => !value)} onInput={setFloatingChatInput} onSend={sendFloatingChat} onNavigate={(target) => { setView(target); setFloatingChatOpen(false) }}/>
    {message && <button className="toast" onClick={() => setMessage('')}><CircleCheck/>{message}</button>}
  </div>
}

function Login({ onLogin }: { onLogin: (session: Session) => void }) {
  const [username, setUsername] = useState('admin'); const [password, setPassword] = useState(''); const [error, setError] = useState(''); const [loading, setLoading] = useState(false)
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setLoading(true); setError('')
    try {
      const response = await fetch(`${API}/api/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) })
      const body = await response.json(); if (!response.ok) throw new Error(body.detail ?? '登录失败'); onLogin(body)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '登录失败') } finally { setLoading(false) }
  }
  return <div className="login-screen"><section className="login-brand"><img src={`${import.meta.env.BASE_URL}brand/ceair-wordmark.svg`} alt="中国东方航空"/><div><span>INTELLIGENT MARKETING PLATFORM</span><h1>智能营销活动及服务平台</h1><p>活动全生命周期、六大智能域、租户数据隔离与营销本体协同。</p></div></section><form className="login-panel" onSubmit={submit}><div className="login-mark"><ShieldCheck/><span>PLATFORM ACCESS</span></div><h2>登录营销运营工作台</h2><label><span>用户名</span><input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username"/></label><label><span>密码</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" autoFocus/></label>{error && <p className="login-error">{error}</p>}<button className="primary" disabled={loading || !username || !password}>{loading ? '正在验证...' : '登录平台'}</button></form></div>
}

function Overview({ campaigns, stats, imports, providers, tenant }: { campaigns: Campaign[]; stats: GraphStats; imports: ImportJob[]; providers: ModelProvider[]; tenant?: Tenant }) {
  return <><div className="page-head"><div><h1>{tenant?.name}运营总览</h1><p>所有指标、活动、模型和图谱数据均限定在当前租户</p></div><span className="tenant-boundary"><ShieldCheck/>TENANT ISOLATED</span></div><div className="kpi-row"><Kpi label="在管营销活动" value={String(campaigns.length)} note="按租户独立统计"/><Kpi label="本体实体" value={stats.entity_count.toLocaleString()} note={`${Object.keys(stats.entity_types).length} 类业务对象`}/><Kpi label="本体关系" value={stats.relation_count.toLocaleString()} note={`${stats.source_count} 个数据来源`}/><Kpi label="可用模型" value={String(providers.filter((item) => item.enabled).length)} note={providers.find((item) => item.is_default)?.model_name ?? '尚未配置'}/></div><section className="panel"><div className="panel-title"><h2>营销活动生命周期</h2><span>活动主线</span></div><div className="lifecycle">{lifecycle.map(([no, label], index) => <div className="life-wrap" key={no}><div className="life-step"><b>{no}</b><span>{label}</span><small>{index < 3 ? '智能能力辅助决策' : '规则、审批与结果回传'}</small></div>{index < lifecycle.length - 1 && <ChevronRight/>}</div>)}</div></section><div className="content-grid"><section className="panel"><div className="panel-title"><h2>活动运行状态</h2><span>{campaigns.length} 项</span></div><table><thead><tr><th>活动</th><th>阶段</th><th>产品包</th><th>状态</th></tr></thead><tbody>{campaigns.map((item) => <tr key={item.id}><td><b>{item.name}</b><small>{item.id} · {item.version}</small></td><td>{item.stage}</td><td>{item.product_package}</td><td><em>{item.status}</em></td></tr>)}</tbody></table></section><section className="panel import-health"><div className="panel-title"><h2>数据接入质量</h2><span>最近批次</span></div>{imports.slice(0,4).map((job) => <div key={job.id}><CheckCircle2/><span><b>{job.file_name}</b><small>{job.accepted_rows} 成功 / {job.rejected_rows} 失败</small></span></div>)}{!imports.length && <p>尚无导入批次</p>}</section></div></>
}

function Campaigns({ campaigns, selectedId, onSelect }: { campaigns: Campaign[]; selectedId: string; onSelect: (id: string) => void }) {
  return <><div className="page-head"><div><h1>活动工作台</h1><p>统一管理当前租户下的活动版本、产品包、客群规模、预算与状态</p></div><button className="primary"><Plus/>新建活动</button></div><section className="panel"><table><thead><tr><th>活动编号 / 名称</th><th>阶段</th><th>活动产品包</th><th>客群规模</th><th>预算</th><th>责任人</th><th>状态</th></tr></thead><tbody>{campaigns.map((item) => <tr className={selectedId === item.id ? 'selected-row' : ''} key={item.id} onClick={() => onSelect(item.id)}><td><b>{item.name}</b><small>{item.id} · {item.version}</small></td><td>{item.stage}</td><td>{item.product_package}</td><td>{item.audience_size.toLocaleString()}</td><td>¥{item.budget_yuan.toLocaleString()}</td><td>{item.owner}</td><td><em>{item.status}</em></td></tr>)}</tbody></table>{!campaigns.length && <Empty icon={Activity} title="当前租户暂无活动" text="创建活动或从业务系统同步活动数据。"/>}</section></>
}

function Agents({ domains, campaigns, selectedId, onSelect, running, onRun, runs }: { domains: AgentDomain[]; campaigns: Campaign[]; selectedId: string; onSelect: (id: string) => void; running: string; onRun: (id: string) => void; runs: AgentRun[] }) {
  return <><div className="page-head"><div><h1>智能域运行工作台</h1><p>智能域只读取当前租户的活动、图谱、模型和策略上下文</p></div><select className="campaign-select" value={selectedId} onChange={(event) => onSelect(event.target.value)}><option value="">选择活动</option>{campaigns.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div><div className="agent-layout"><section className="domain-grid">{domains.map((domain, index) => <article className="domain-card" key={domain.id}><div className="domain-head"><span>{String(index + 1).padStart(2, '0')}</span><em>{domain.module}</em></div><Bot/><h2>{domain.name}</h2><p>{domain.responsibility}</p><div className="io"><div><b>INPUT</b><span>{domain.input_types.join(' · ')}</span></div><ChevronRight/><div><b>OUTPUT</b><span>{domain.output_types.join(' · ')}</span></div></div><button onClick={() => onRun(domain.id)} disabled={!selectedId || Boolean(running)}>{running === domain.id ? <RefreshCw className="spin"/> : <Play/>}{running === domain.id ? '运行中' : '运行智能域'}</button></article>)}</section><aside className="run-console"><div className="panel-title"><h2>租户运行审计</h2><Activity/></div>{runs.slice(0,10).map((run) => <div className="audit-run" key={run.id}><i/><div><b>{run.domain_id}</b><span>{run.campaign_id} · {run.status}</span><small>{run.summary}</small></div></div>)}{!runs.length && <div className="empty-console"><Bot/><b>暂无运行记录</b><span>运行智能域后记录模型、治理门禁和结果。</span></div>}</aside></div></>
}

function GraphWorkspace({ graph, stats }: { graph: MarketingGraph; stats: GraphStats }) {
  const [selected, setSelected] = useState<GraphNode | null>(null)
  return <><div className="page-head"><div><h1>营销关系图谱</h1><p>图谱来自当前租户数据库和导入批次，不再由页面或接口代码写死</p></div><div className="graph-summary"><span>{stats.entity_count} 实体</span><span>{stats.relation_count} 关系</span><span>{stats.source_count} 来源</span></div></div><div className="ontology-panel dynamic-ontology"><GraphCanvas graph={graph} onSelect={setSelected}/><aside className="relation-ledger"><div className="panel-title"><h2>{selected ? '实体详情' : '类型分布'}</h2><span>实时查询</span></div>{selected ? <div className="entity-detail"><em>{selected.type}</em><h3>{selected.label}</h3><p>{selected.id}</p><dl><dt>数据来源</dt><dd>{selected.source}</dd><dt>可信度</dt><dd>{Math.round(selected.confidence * 100)}%</dd>{Object.entries(selected.attributes).map(([key, value]) => <><dt key={`${key}-k`}>{key}</dt><dd key={`${key}-v`}>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd></>)}</dl></div> : Object.entries(stats.entity_types).map(([type, count]) => <div className="type-row" key={type}><span>{type}</span><b>{count}</b></div>)}</aside></div></>
}

function GraphCanvas({ graph, onSelect }: { graph: MarketingGraph; onSelect: (node: GraphNode) => void }) {
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({}); const drag = useRef<string | null>(null)
  useEffect(() => { const next: Record<string, { x: number; y: number }> = {}; graph.nodes.forEach((node, index) => { const ring = index % 2 ? 205 : 125; const angle = index * 2.399; next[node.id] = { x: 390 + Math.cos(angle) * ring, y: 280 + Math.sin(angle) * ring } }); setPositions(next) }, [graph.nodes.map((item) => item.id).join('|')])
  function move(event: React.PointerEvent<SVGSVGElement>) { if (!drag.current) return; const rect = event.currentTarget.getBoundingClientRect(); setPositions((current) => ({ ...current, [drag.current!]: { x: (event.clientX - rect.left) * 780 / rect.width, y: (event.clientY - rect.top) * 560 / rect.height } })) }
  return <div className="ontology-canvas graph-dynamic"><svg viewBox="0 0 780 560" onPointerMove={move} onPointerUp={() => drag.current = null} onPointerLeave={() => drag.current = null}><defs><marker id="graph-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z"/></marker></defs>{graph.edges.map((edge, index) => { const from = positions[edge.source]; const to = positions[edge.target]; if (!from || !to) return null; return <g key={`${edge.source}-${edge.target}-${index}`}><line x1={from.x} y1={from.y} x2={to.x} y2={to.y} markerEnd="url(#graph-arrow)"/><text x={(from.x + to.x) / 2} y={(from.y + to.y) / 2 - 6}>{edge.relation}</text></g> })}{graph.nodes.map((node) => { const point = positions[node.id]; if (!point) return null; return <g className={`graph-entity type-${node.type}`} transform={`translate(${point.x - 58} ${point.y - 28})`} key={node.id} onPointerDown={(event) => { drag.current = node.id; event.currentTarget.setPointerCapture(event.pointerId) }} onClick={() => onSelect(node)}><rect width="116" height="56"/><text className="node-type" x="58" y="18">{node.type}</text><text className="node-label" x="58" y="38">{node.label.length > 10 ? `${node.label.slice(0, 10)}…` : node.label}</text></g>})}</svg>{!graph.nodes.length && <Empty icon={Network} title="当前租户暂无图谱数据" text="从数据接入页导入实体和关系。"/>}</div>
}

function Imports({ jobs, onUpload }: { jobs: ImportJob[]; onUpload: (type: string, file: File) => void }) {
  const [type, setType] = useState('entities'); const [file, setFile] = useState<File | null>(null)
  return <><div className="page-head"><div><h1>数据接入与导入治理</h1><p>支持 CSV / JSON，按批次校验、去重、追溯并写入当前租户图谱</p></div></div><div className="import-layout"><section className="panel upload-panel"><div className="panel-title"><h2>新建导入批次</h2><span>最大 10MB</span></div><div className="dataset-tabs"><button className={type === 'entities' ? 'active' : ''} onClick={() => setType('entities')}><Database/>实体数据</button><button className={type === 'relations' ? 'active' : ''} onClick={() => setType('relations')}><GitBranch/>关系数据</button></div><label className="dropzone"><Upload/><b>{file?.name ?? '选择 CSV 或 JSON 文件'}</b><span>{type === 'entities' ? '必填：external_id、entity_type、label' : '必填：source_external_id、relation_type、target_external_id'}</span><input type="file" accept=".csv,.json" onChange={(event) => setFile(event.target.files?.[0] ?? null)}/></label><button className="primary import-button" disabled={!file} onClick={() => file && onUpload(type, file)}><FileUp/>校验并导入</button></section><section className="panel schema-panel"><div className="panel-title"><h2>接入约束</h2><span>租户级</span></div><div><ShieldCheck/><b>租户归属</b><p>所有实体、关系和批次自动绑定当前租户，关系不能跨租户连接。</p></div><div><CheckCircle2/><b>实体 Upsert</b><p>按 external_id 更新或新增，保留来源、属性、可信度和导入批次。</p></div><div><AlertTriangle/><b>错误隔离</b><p>错误行不会进入图谱，批次保留行号、原因和失败数据摘要。</p></div></section></div><section className="panel import-history"><div className="panel-title"><h2>导入历史</h2><span>{jobs.length} 个批次</span></div><table><thead><tr><th>批次 / 文件</th><th>数据类型</th><th>总行数</th><th>成功</th><th>失败</th><th>状态</th><th>时间</th></tr></thead><tbody>{jobs.map((job) => <tr key={job.id}><td><b>{job.file_name}</b><small>{job.id}</small></td><td>{job.dataset_type === 'entities' ? '实体' : '关系'}</td><td>{job.total_rows}</td><td className="success-text">{job.accepted_rows}</td><td className={job.rejected_rows ? 'danger-text' : ''}>{job.rejected_rows}</td><td>{job.status}</td><td>{new Date(job.created_at).toLocaleString('zh-CN')}</td></tr>)}</tbody></table>{!jobs.length && <Empty icon={FileUp} title="尚无导入批次" text="上传实体或关系数据后，这里将显示校验与处理结果。"/>}</section></>
}

function Models({ providers, canManage, request, onAdd, onEdit, onAction }: { providers: ModelProvider[]; canManage: boolean; request: <T>(path: string, init?: RequestInit, form?: boolean) => Promise<T>; onAdd: () => void; onEdit: (provider: ModelProvider) => void; onAction: (provider: ModelProvider, action: 'test' | 'default' | 'delete') => void }) {
  const [selectedId, setSelectedId] = useState<number | null>(providers.find((item) => item.is_default)?.id ?? providers[0]?.id ?? null)
  const [models, setModels] = useState<Array<{ id: string; owned_by: string }>>([])
  const [usage, setUsage] = useState<{ request_count: number; prompt_tokens: number; completion_tokens: number; total_tokens: number; by_model: Array<{ model_name: string; request_count: number; total_tokens: number }> } | null>(null)
  const [loading, setLoading] = useState(false)
  const selected = providers.find((item) => item.id === selectedId) ?? providers[0]
  async function loadProvider(provider: ModelProvider) { setSelectedId(provider.id); setLoading(true); try { const [modelData, usageData] = await Promise.all([request<{ models: Array<{ id: string; owned_by: string }> }>(`/api/model-providers/${provider.id}/models`), request<typeof usage>(`/api/model-providers/${provider.id}/usage`)]); setModels(modelData.models); setUsage(usageData) } catch { setModels([]); setUsage(null) } finally { setLoading(false) } }
  return <><div className="page-head"><div><h1>模型与智能体配置</h1><p>参考对话产品的提供商配置方式，统一管理接口、可用模型、默认路由和调用用量</p></div>{canManage && <button className="primary" onClick={onAdd}><Plus/>添加提供商</button>}</div><div className="model-console"><aside className="panel provider-list"><div className="panel-title"><h2>模型提供商</h2><span>{providers.length} 个</span></div>{providers.map((provider) => <button className={selected?.id === provider.id ? 'selected' : ''} onClick={() => void loadProvider(provider)} key={provider.id}><span><ServerCog/></span><div><b>{provider.display_name}</b><small>{provider.model_name}</small></div>{provider.is_default && <em>默认</em>}</button>)}</aside><section className="panel provider-detail">{selected ? <><header className="provider-detail-head"><div><span><ServerCog/></span><div><h2>{selected.display_name}</h2><p>{selected.provider_type} · {selected.base_url || '平台内置模型'}</p></div></div>{canManage && <div><button className="secondary" onClick={() => onAction(selected, 'test')}><Radio/>连接测试</button><button className="secondary" onClick={() => onEdit(selected)}><Settings2/>编辑</button></div>}</header><div className="provider-metrics"><div><small>默认模型</small><b>{selected.model_name}</b></div><div><small>调用次数</small><b>{usage?.request_count ?? '—'}</b></div><div><small>总 Token</small><b>{usage?.total_tokens?.toLocaleString() ?? '—'}</b></div><div><small>凭证状态</small><b>{selected.api_key_configured ? '已安全配置' : selected.provider_type === 'mock' ? '无需凭证' : '未配置'}</b></div></div><div className="provider-sections"><section><div className="section-heading"><div><b>可用模型</b><span>从提供商接口实时读取</span></div><button className="secondary" onClick={() => void loadProvider(selected)}><RefreshCw className={loading ? 'spin' : ''}/>刷新</button></div><div className="model-list">{models.map((model) => <div key={model.id}><span><Bot/></span><b>{model.id}</b><small>{model.owned_by || 'provider'}</small>{model.id === selected.model_name && <em>当前</em>}</div>)}{!models.length && <p>点击刷新读取可用模型列表。</p>}</div></section><section><div className="section-heading"><div><b>用量分布</b><span>按模型统计调用和 Token</span></div></div><div className="usage-list">{usage?.by_model?.map((item) => <div key={item.model_name}><b>{item.model_name}</b><span>{item.request_count} 次</span><em>{item.total_tokens.toLocaleString()} tokens</em></div>)}{!usage?.by_model?.length && <p>暂无调用记录。</p>}</div></section></div></> : <Empty icon={ServerCog} title="尚未配置模型" text="添加一个 OpenAI 兼容提供商后即可运行数据处理和营销智能体。"/>}</section></div></>
}

function TenantAdmin({ tenants, users, request, onReload }: { tenants: Tenant[]; users: PlatformUser[]; request: <T>(path: string, init?: RequestInit) => Promise<T>; onReload: () => Promise<void> }) {
  const [tenantForm, setTenantForm] = useState({ code: '', name: '' })
  const [userForm, setUserForm] = useState({ username: '', display_name: '', password: '', tenant_id: tenants[0]?.id ?? 0, role: 'viewer' })
  const [status, setStatus] = useState('')
  useEffect(() => { if (!userForm.tenant_id && tenants[0]) setUserForm((current) => ({ ...current, tenant_id: tenants[0].id })) }, [tenants])
  async function createTenant() {
    try { await request('/api/platform/tenants', { method: 'POST', body: JSON.stringify(tenantForm) }); setTenantForm({ code: '', name: '' }); setStatus('租户已创建'); await onReload() } catch (cause) { setStatus(cause instanceof Error ? cause.message : '创建失败') }
  }
  async function createUser() {
    try { await request('/api/platform/users', { method: 'POST', body: JSON.stringify(userForm) }); setUserForm({ ...userForm, username: '', display_name: '', password: '' }); setStatus('用户已创建并完成租户授权'); await onReload() } catch (cause) { setStatus(cause instanceof Error ? cause.message : '创建失败') }
  }
  return <><div className="page-head"><div><h1>租户与用户管理</h1><p>平台管理员创建运营组织、账号及租户角色，业务数据按租户强制隔离</p></div><span className="tenant-boundary"><ShieldCheck/>PLATFORM ADMIN</span></div><div className="tenant-admin-grid"><section className="panel admin-form"><div className="panel-title"><h2>新建租户</h2><span>运营组织</span></div><label><span>租户编码</span><input value={tenantForm.code} onChange={(event) => setTenantForm({ ...tenantForm, code: event.target.value.toUpperCase() })} placeholder="例如 CEA-NORTH"/></label><label><span>租户名称</span><input value={tenantForm.name} onChange={(event) => setTenantForm({ ...tenantForm, name: event.target.value })} placeholder="例如 华北营销运营中心"/></label><button className="primary" disabled={!tenantForm.code || !tenantForm.name} onClick={createTenant}><Plus/>创建租户</button></section><section className="panel admin-form"><div className="panel-title"><h2>新建运营用户</h2><span>账号与角色</span></div><div className="form-grid"><label><span>用户名</span><input value={userForm.username} onChange={(event) => setUserForm({ ...userForm, username: event.target.value })}/></label><label><span>姓名</span><input value={userForm.display_name} onChange={(event) => setUserForm({ ...userForm, display_name: event.target.value })}/></label></div><label><span>初始密码</span><input type="password" value={userForm.password} onChange={(event) => setUserForm({ ...userForm, password: event.target.value })}/></label><div className="form-grid"><label><span>授权租户</span><select value={userForm.tenant_id} onChange={(event) => setUserForm({ ...userForm, tenant_id: Number(event.target.value) })}>{tenants.map((tenant) => <option value={tenant.id} key={tenant.id}>{tenant.name}</option>)}</select></label><label><span>租户角色</span><select value={userForm.role} onChange={(event) => setUserForm({ ...userForm, role: event.target.value })}><option value="admin">管理员</option><option value="manager">经理</option><option value="analyst">分析师</option><option value="viewer">查看者</option></select></label></div><button className="primary" disabled={!userForm.username || !userForm.display_name || userForm.password.length < 8} onClick={createUser}><UsersRound/>创建并授权</button></section></div>{status && <div className="admin-status">{status}</div>}<div className="tenant-user-lists"><section className="panel"><div className="panel-title"><h2>租户清单</h2><span>{tenants.length} 个</span></div><table><thead><tr><th>编码</th><th>租户名称</th><th>状态</th></tr></thead><tbody>{tenants.map((tenant) => <tr key={tenant.id}><td>{tenant.code}</td><td>{tenant.name}</td><td><em>正常</em></td></tr>)}</tbody></table></section><section className="panel"><div className="panel-title"><h2>用户与授权</h2><span>{users.length} 人</span></div><table><thead><tr><th>用户</th><th>租户授权</th><th>平台角色</th></tr></thead><tbody>{users.map((user) => <tr key={user.id}><td><b>{user.display_name}</b><small>{user.username}</small></td><td>{user.memberships.map((item) => `${item.name}（${item.role}）`).join('、')}</td><td>{user.is_platform_admin ? '平台管理员' : '运营用户'}</td></tr>)}</tbody></table></section></div></>
}

function ProviderDrawer({ form, editing, onChange, onClose, onSave }: { form: ProviderForm; editing: boolean; onChange: (form: ProviderForm) => void; onClose: () => void; onSave: () => void }) {
  const field = <K extends keyof ProviderForm>(key: K, value: ProviderForm[K]) => onChange({ ...form, [key]: value })
  return <div className="drawer-backdrop" onMouseDown={onClose}><aside className="drawer" onMouseDown={(event) => event.stopPropagation()}><header><div><small>MODEL PROVIDER</small><h2>{editing ? '编辑模型配置' : '新增模型配置'}</h2></div><button onClick={onClose}><X/></button></header><div className="form-body"><label><span>配置名称</span><input value={form.display_name} onChange={(event) => field('display_name', event.target.value)}/></label><label><span>接口类型</span><select value={form.provider_type} onChange={(event) => field('provider_type', event.target.value)}><option value="openai-compatible">OpenAI 兼容接口</option><option value="mock">内置模拟模型</option></select></label><label><span>服务地址</span><input disabled={form.provider_type === 'mock'} value={form.base_url} onChange={(event) => field('base_url', event.target.value)} placeholder="https://api.example.com/v1"/></label><label><span>模型名称</span><input value={form.model_name} onChange={(event) => field('model_name', event.target.value)}/></label><label><span>API Key</span><input type="password" disabled={form.provider_type === 'mock'} value={form.api_key} onChange={(event) => field('api_key', event.target.value)} placeholder={editing ? '留空表示不修改' : '输入密钥'}/></label><div className="form-grid"><label><span>超时（秒）</span><input type="number" value={form.timeout_seconds} onChange={(event) => field('timeout_seconds', Number(event.target.value))}/></label><label><span>最大 Token</span><input type="number" value={form.max_tokens} onChange={(event) => field('max_tokens', Number(event.target.value))}/></label></div><label><span>温度：{form.temperature}</span><input type="range" min="0" max="2" step="0.1" value={form.temperature} onChange={(event) => field('temperature', Number(event.target.value))}/></label><div className="check-row"><label><input type="checkbox" checked={form.enabled} onChange={(event) => field('enabled', event.target.checked)}/>启用</label><label><input type="checkbox" checked={form.is_default} onChange={(event) => field('is_default', event.target.checked)}/>设为默认</label></div></div><footer><button onClick={onClose}>取消</button><button className="primary" disabled={!form.display_name || !form.model_name} onClick={onSave}><Save/>保存配置</button></footer></aside></div>
}

function DataPipelineWorkspace({ jobs, detail, onDetail, onUpload, onReview }: { jobs: DataPipelineJob[]; detail: DataPipelineJob | null; onDetail: (job: DataPipelineJob | null) => void; onUpload: (type: string, file: File) => void; onReview: (job: DataPipelineJob, decision: 'approve' | 'reject') => void }) {
  const [dragging, setDragging] = useState(false)
  const [selected, setSelected] = useState<DataPipelineJob | null>(detail)
  useEffect(() => { setSelected(detail) }, [detail])
  const stageLabels: Record<string, string> = { queued: '排队', received: '接收检查', extracting: '解析结构', extracted: '解析完成', 'knowledge-persisting': '知识入库', 'knowledge-ready': '知识就绪', 'agent-processing': '智能体处理', 'semantic-validation': '语义校验', 'awaiting-confirmation': '待人工确认', 'ontology-persisting': '更新本体', 'ontology-updated': '本体已更新', rejected: '已驳回', failed: '失败' }
  function accept(files: FileList | File[]) { const file = files[0]; if (file) onUpload('business-data', file) }
  const activeId = selected?.id ?? detail?.id
  const activeJob = jobs.find((job) => job.id === activeId) ?? selected ?? detail
  const events = (activeJob?.result?.events ?? []) as Array<Record<string, unknown>>
  const candidates = activeJob?.result?.candidates as { entities?: Array<Record<string, unknown>>; relations?: Array<Record<string, unknown>> } | undefined
  return <>
    <div className="page-head"><div><h1>数据处理流水线</h1><p>上传业务文件后，系统自动解析、清洗并调用数据处理智能体；本体更新必须经过人工二次确认</p></div><span className="status-pill"><Radio/> {jobs.filter((item) => ['running', 'awaiting_confirmation'].includes(item.status)).length} 个处理中</span></div>
    <div className="pipeline-layout">
      <section>
        <label className={`pipeline-dropzone ${dragging ? 'dragging' : ''}`} onDragEnter={(event) => { event.preventDefault(); setDragging(true) }} onDragOver={(event) => event.preventDefault()} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); accept(event.dataTransfer.files) }}>
          <input type="file" multiple accept=".txt,.md,.json,.csv,.pdf,.png,.jpg,.jpeg,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.html" onChange={(event) => event.target.files && accept(event.target.files)}/><div className="drop-icon"><Upload/></div><b>拖入文件开始处理</b><span>支持 PDF、Word、Excel、PPT、图片、CSV、JSON 等业务数据</span><small>上传后实时查看解析、模型处理、校验与溯源事件</small>
        </label>
        <section className="panel pipeline-jobs"><div className="panel-title"><h2>处理任务</h2><span>{jobs.length} 个任务</span></div>{jobs.map((job) => <button className={`pipeline-job ${activeJob?.id === job.id ? 'selected' : ''}`} key={job.id} onClick={() => { setSelected(job); onDetail(job) }}><span className="job-icon"><FileUp/></span><div><b>{job.file_name}</b><small>{job.id} · {job.file_format.toUpperCase()} · {new Date(job.created_at).toLocaleString('zh-CN')}</small></div><em className={`job-status ${job.status}`}>{job.status === 'awaiting_confirmation' ? '待确认' : job.status === 'completed' ? '已完成' : job.status === 'failed' ? '失败' : '处理中'}</em><ChevronRight/></button>)}{!jobs.length && <Empty icon={FileUp} title="尚无处理任务" text="拖入航线通知、服务规则或运营报表开始构建营销知识。"/>}</section>
      </section>
      <section className="panel pipeline-detail"><div className="panel-title"><h2>{activeJob ? '处理详情与溯源' : '选择一个处理任务'}</h2>{activeJob && <span>{stageLabels[activeJob.current_stage] ?? activeJob.current_stage}</span>}</div>{activeJob ? <><div className="pipeline-summary"><div><small>当前阶段</small><b>{stageLabels[activeJob.current_stage] ?? activeJob.current_stage}</b></div><div><small>候选对象</small><b>{activeJob.total_entities}</b></div><div><small>候选关系</small><b>{activeJob.total_relations}</b></div><div><small>模型任务</small><b>{activeJob.mineru_task_id || 'Harness'}</b></div></div><div className="pipeline-tabs"><div className="trace-list">{events.map((event, index) => <div className="trace-item" key={`${String(event.stage ?? event.event)}-${index}`}><span className={`trace-dot ${event.status === 'completed' ? 'done' : event.status === 'needs_review' ? 'review' : ''}`}>{event.status === 'completed' ? <Check/> : <Clock3/>}</span><div><b>{String(event.label ?? event.event ?? '运行事件')}</b><small>{event.timestamp ? new Date(String(event.timestamp)).toLocaleTimeString('zh-CN') : '已记录'}{event.model ? ` · 模型 ${String(event.model)}` : ''}{event.tool ? ` · 工具 ${String(event.tool)}` : ''}</small></div><em>{event.status === 'needs_review' ? '待确认' : event.status === 'running' ? '处理中' : event.status === 'completed' ? '完成' : ''}</em></div>)}</div>{candidates?.entities?.length ? <div className="candidate-preview"><b>候选本体对象</b>{candidates.entities.slice(0, 8).map((item, index) => <div key={index}><span>{String(item.entity_type ?? 'Evidence')}</span><strong>{String(item.label ?? item.external_id ?? '未命名对象')}</strong><em>{Math.round(Number(item.confidence ?? .5) * 100)}%</em></div>)}</div> : null}</div>{activeJob.status === 'awaiting_confirmation' && <div className="review-box"><div><Sparkles/><div><b>候选本体更新已生成</b><span>请核对对象、关系和来源证据。确认后才会写入正式营销知识图谱。</span></div></div><div className="review-actions"><button className="secondary" onClick={() => onReview(activeJob, 'reject')}><XCircle/>驳回更新</button><button className="primary" onClick={() => onReview(activeJob, 'approve')}><Check/>确认并更新本体</button></div></div>}</> : <Empty icon={Eye} title="查看处理溯源" text="选择左侧任务，查看文件解析、数据处理智能体和本体更新的每一步动态。"/>}</section>
    </div>
  </>
}

function ChatWorkspace({ messages, input, busy, onInput, onSend }: { messages: Array<{ role: 'user' | 'assistant'; content: string; trace?: Array<Record<string, unknown>>; sources?: Array<Record<string, unknown>> }>; input: string; busy: boolean; onInput: (value: string) => void; onSend: () => void }) {
  const last = messages[messages.length - 1]
  return <><div className="page-head"><div><h1>营销智能助手</h1><p>基于营销知识库、本体关系和活动上下文协助机会分析、客群判断、产品匹配与复盘</p></div><span className="status-pill"><Sparkles/> Harness 在线</span></div><div className="chat-layout"><section className="panel chat-panel"><div className="chat-top"><div><span className="assistant-avatar"><Bot/></span><div><b>东航营销 Copilot</b><small>知识检索 · 本体查询 · 活动分析 · 人工审核门禁</small></div></div><span className="online-dot">● 在线</span></div><div className="chat-messages">{messages.length === 0 && <div className="chat-empty"><Sparkles/><h2>从一个营销问题开始</h2><p>例如：分析近期上海—三亚航线的营销机会，结合客群和可用产品给出活动建议。</p><div className="prompt-chips"><button onClick={() => onInput('分析近期上海—三亚航线的营销机会')}>分析航线机会</button><button onClick={() => onInput('查询适合高频商务旅客的产品和权益')}>查找产品权益</button><button onClick={() => onInput('查看当前活动的转化表现和复盘建议')}>复盘活动表现</button></div></div>}{messages.map((message, index) => <div className={`chat-message ${message.role}`} key={`${message.role}-${index}`}><span className="message-avatar">{message.role === 'assistant' ? <Bot/> : '我'}</span><div className="message-body"><div className="message-meta">{message.role === 'assistant' ? '东航营销 Copilot' : '我'}</div><div className="message-content">{message.content}</div>{message.sources?.length ? <div className="source-strip"><BookOpen/>基于 {message.sources.length} 条知识与本体证据</div> : null}</div></div>)}</div><div className="chat-composer"><textarea value={input} onChange={(event) => onInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); onSend() } }} placeholder="描述营销问题，Copilot 将先检索知识和业务关系…"/><button className="primary" disabled={busy || !input.trim()} onClick={onSend}>{busy ? <RefreshCw className="spin"/> : <ChevronRight/>}</button></div></section><aside className="panel chat-trace"><div className="panel-title"><h2>运行轨迹</h2><span>{last?.trace?.length ?? 0} 个事件</span></div>{last?.trace?.length ? last.trace.map((event, index) => <div className="chat-trace-item" key={index}><span><Check/></span><div><b>{String(event.event ?? 'Agent step')}</b><small>{event.tool ? `工具：${String(event.tool)}` : event.model ? `模型：${String(event.model)}` : '已记录'}</small></div></div>) : <Empty icon={Radio} title="等待下一次运行" text="发送问题后，这里会展示知识检索、工具调用和模型推理轨迹。"/>}</aside></div></>
}

function KnowledgeWorkspace({ graph, stats, request }: { graph: MarketingGraph; stats: GraphStats; request: <T>(path: string, init?: RequestInit, form?: boolean) => Promise<T> }) {
  const [query, setQuery] = useState(''); const [knowledge, setKnowledge] = useState<Array<{ chunk_id: string; document_id: string; title: string; content: string; linked_objects: Array<Record<string, unknown>> }>>([])
  async function search() { try { setKnowledge(await request<typeof knowledge>(`/api/knowledge/search?q=${encodeURIComponent(query)}&limit=12`)) } catch { setKnowledge([]) } }
  return <><div className="page-head"><div><h1>营销知识</h1><p>知识文档、业务事实、本体关系和营销溯源统一管理，为智能体提供可信业务上下文</p></div><div className="knowledge-actions"><label><Search/><input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && void search()} placeholder="搜索航线、运价、活动、服务规则…"/></label><button className="secondary" onClick={() => void search()}><Search/>检索知识</button></div></div><div className="knowledge-kpis"><Kpi label="知识对象" value={String(stats.entity_count)} note="本体业务对象"/><Kpi label="关系连接" value={String(stats.relation_count)} note="可解释关系"/><Kpi label="来源文档" value={String(stats.source_count)} note="可回溯证据"/><Kpi label="知识类型" value={String(Object.keys(stats.entity_types).length)} note="统一语义模型"/></div><div className="knowledge-layout"><section className="panel knowledge-graph"><div className="panel-title"><h2>营销关系图谱</h2><span>知识底座 · {graph.nodes.length} 节点 · {graph.edges.length} 关系</span></div><GraphCanvas graph={graph} onSelect={() => undefined}/></section><section className="panel knowledge-results"><div className="panel-title"><h2>知识检索结果</h2><span>{knowledge.length ? `${knowledge.length} 条` : '按关键词检索'}</span></div>{knowledge.map((item) => <article className="knowledge-result" key={item.chunk_id}><b>{item.title}</b><p>{item.content.slice(0, 230)}{item.content.length > 230 ? '…' : ''}</p><small><BookOpen/> {item.linked_objects.length} 个关联业务对象 · {item.chunk_id}</small></article>)}{!knowledge.length && <Empty icon={BookOpen} title="知识与图谱统一查看" text="知识库保留来源证据，本体图谱表达对象关系；检索结果会同时展示可追溯依据。"/>}</section></div></>
}

function Kpi({ label, value, note }: { label: string; value: string; note: string }) { return <div className="kpi"><span>{label}</span><b>{value}</b><small>{note}</small></div> }

function FloatingCopilot({ open, messages, input, busy, onToggle, onInput, onSend, onNavigate }: { open: boolean; messages: Array<{ role: 'user' | 'assistant'; content: string; trace?: Array<Record<string, unknown>>; sources?: Array<Record<string, unknown>> }>; input: string; busy: boolean; onToggle: () => void; onInput: (value: string) => void; onSend: () => void; onNavigate: (target: string) => void }) {
  const last = messages[messages.length - 1]
  return <div className={`floating-copilot ${open ? 'open' : ''}`}>
    {open && <section className="floating-chat-panel">
      <header><div className="floating-chat-identity"><span><Bot/></span><div><b>东航营销智能体</b><small>Harness · 知识 · 本体 · 六大智能域</small></div></div><button title="关闭对话" onClick={onToggle}><X/></button></header>
      <div className="floating-chat-shortcuts"><button onClick={() => onInput('分析近期航线和市场机会')}>机会洞察</button><button onClick={() => onInput('查询可用营销产品和权益')}>产品匹配</button><button onClick={() => onInput('查看活动执行状态和处理任务')}>平台状态</button></div>
      <div className="floating-chat-messages">{!messages.length && <div className="floating-chat-empty"><Sparkles/><b>需要我协助什么？</b><span>我会先检索营销知识和本体关系，再调用授权的智能域工具。</span></div>}{messages.map((message, index) => <div className={`floating-message ${message.role}`} key={`${message.role}-${index}`}><span className="floating-message-avatar">{message.role === 'assistant' ? <Bot/> : '我'}</span><div><small>{message.role === 'assistant' ? '营销智能体' : '我'}</small><p>{message.content}</p>{message.sources?.length ? <em><BookOpen/> {message.sources.length} 条证据</em> : null}</div></div>)}</div>
      {last?.trace?.length ? <div className="floating-trace"><Activity/>已完成 {last.trace.length} 个 Harness 运行步骤</div> : null}
      <div className="floating-chat-composer"><textarea value={input} onChange={(event) => onInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); onSend() } }} placeholder="问问航线机会、客群、产品、活动或知识…"/><button className="primary" disabled={busy || !input.trim()} onClick={onSend}>{busy ? <RefreshCw className="spin"/> : <ChevronRight/>}</button></div>
      <footer><button onClick={() => onNavigate('chat')}><MessageSquare/>打开完整工作台</button><span>操作遵循权限与人工审核</span></footer>
    </section>}
    <button className="floating-copilot-button" title={open ? '关闭营销智能体' : '打开营销智能体'} onClick={onToggle}><span className="robot-pulse"/><Bot/></button>
  </div>
}

function Empty({ icon: Icon, title, text }: { icon: typeof Activity; title: string; text: string }) { return <div className="empty-state"><Icon/><b>{title}</b><span>{text}</span></div> }

// Kept for compatibility with legacy deep links while the unified workspaces are used by the main navigation.
void GraphWorkspace
void Imports

export default App
