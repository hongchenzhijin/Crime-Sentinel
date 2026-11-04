import { useEffect, useRef, useState } from 'react'
import { Card, Notice } from '../../components/ui'
import { missionApi } from '../../lib/api'
import type { Mission, MissionApproval, MissionEvent, MuseStatus } from '../../lib/types'
import { useAsync } from '../../lib/useAsync'

const PHASES = ['plan', 'discover', 'triage', 'approach', 'observe', 'inbox', 'escalate', 'handoff']
const ACTOR: Record<string, { icon: string; label: string; color: string }> = {
  system: { icon: '⚙', label: 'System', color: '#64748b' },
  planner: { icon: '🧭', label: 'Planner', color: '#4f46e5' },
  persona: { icon: '🎭', label: 'Persona', color: '#6250d6' },
  governor: { icon: '🛡', label: 'Safety Governor', color: '#0f172a' },
  analyst: { icon: '🔎', label: 'Analyst', color: '#1baf7a' },
  reporter: { icon: '📨', label: 'Reporter', color: '#eb6834' },
  platform: { icon: '🌐', label: 'Platform', color: '#64748b' },
  human: { icon: '🧑', label: 'Human', color: '#eda100' },
}
const TIER_COLOR: Record<string, string> = {
  benign: '#0ca30c', monitor: '#fab219', glorification_community: '#ec835a', active_recruitment: '#d03b3b', imminent_threat: '#d03b3b',
}

export function MissionPage({ reviewer }: { reviewer: string }) {
  const status = useAsync<MuseStatus>(() => missionApi.status(), [])
  const [missionId, setMissionId] = useState<string | undefined>(() => localStorage.getItem('cs.mission') ?? undefined)
  const [mission, setMission] = useState<Mission>()
  const [events, setEvents] = useState<MissionEvent[]>([])
  const [brief, setBrief] = useState('')
  const [autoApprove, setAutoApprove] = useState('messages')
  const [pace, setPace] = useState(0.9)
  const [showSandbox, setShowSandbox] = useState(true)
  const [error, setError] = useState<string>()
  const lastId = useRef(0)

  useEffect(() => {
    if (status.data && !brief) setBrief(status.data.default_brief)
  }, [status.data, brief])

  useEffect(() => {
    if (!missionId) missionApi.list().then((l) => l[0] && setMissionId(l[0].id)).catch(() => {})
  }, [missionId])

  useEffect(() => {
    if (!missionId) return
    localStorage.setItem('cs.mission', missionId)
    lastId.current = 0
    setEvents([])
    let active = true
    const poll = async () => {
      try {
        const m = await missionApi.get(missionId, lastId.current)
        if (!active) return
        setMission(m)
        if (m.events.length) {
          lastId.current = m.events[m.events.length - 1].id
          setEvents((prev) => [...prev, ...m.events])
        }
      } catch (e) {
        if (active) setError((e as Error).message)
      }
    }
    poll()
    const id = setInterval(poll, 1000)
    return () => {
      active = false
      clearInterval(id)
    }
  }, [missionId])

  const start = async () => {
    setError(undefined)
    try {
      const { id } = await missionApi.start({ brief, auto_approve: autoApprove, pace })
      setMissionId(id)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const running = mission && ['starting', 'running', 'awaiting_approval'].includes(mission.status)
  const phase = events.length ? events[events.length - 1].phase : undefined
  const pending = mission?.approvals.filter((a) => a.status === 'pending') ?? []
  const assessments = events.filter((e) => e.kind === 'assessment')
  const reports = events.filter((e) => e.kind === 'report_sent')
  const blocks = events.filter((e) => e.kind === 'verdict' && e.detail.decision !== 'allow').length

  return (
    <div className="space-y-3">
      <Notice>
        <strong>Sentinel agent.</strong> A governed undercover research persona finds closed communities that glorify
        violence. Meta Muse plans, drafts in character, judges safety, analyses text and images, and writes reports.
        Code enforces the rules of engagement, and humans approve outbound actions and every report. Runs only on the
        sandbox platform.
      </Notice>

      <div className="grid gap-3 xl:grid-cols-[340px_1fr]">
        <div className="space-y-3">
          <Card title="New mission">
            <label className="block text-[11px] text-ink-2">Intelligence brief
              <textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={5}
                className="mt-0.5 w-full rounded-lg border border-line bg-white p-2 text-xs text-ink" />
            </label>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <label className="text-[11px] text-ink-2">Human approval
                <select value={autoApprove} onChange={(e) => setAutoApprove(e.target.value)} className="mt-0.5 w-full rounded-lg border border-line bg-white px-2 py-1 text-xs text-ink">
                  <option value="none">Approve everything</option>
                  <option value="messages">Approve reports only</option>
                  <option value="all">Auto (testing only)</option>
                </select>
              </label>
              <label className="text-[11px] text-ink-2">Pace (s/step)
                <input type="number" min={0} max={5} step={0.1} value={pace} onChange={(e) => setPace(Number(e.target.value))}
                  className="mt-0.5 w-full rounded-lg border border-line bg-white px-2 py-1 text-xs text-ink" />
              </label>
            </div>
            <div className="mt-3 flex gap-2">
              <button onClick={start} disabled={!!running}
                className="flex-1 rounded-lg bg-accent shadow-sm shadow-accent/20 px-3 py-2 text-sm font-semibold text-white hover:bg-accent/90 disabled:opacity-40">
                {running ? 'Mission running…' : '▶ Launch mission'}
              </button>
              {running && mission && (
                <button onClick={() => missionApi.stop(mission.id)} className="rounded-lg border border-line bg-white px-3 py-2 text-sm">Stop</button>
              )}
            </div>
            {error && <p className="mt-2 text-xs text-critical">{error}</p>}
            <p className="mt-2 text-[11px] text-ink-3">Launching resets the sandbox world to its initial state.</p>
          </Card>

          <Card title="Intelligence engine" subtitle={status.data?.base_url}>
            {status.data && (
              <div className="space-y-1 text-xs">
                <div className="flex items-center gap-2">
                  <span className={`h-2.5 w-2.5 rounded-full ${status.data.enabled ? 'bg-good' : 'bg-warning'}`} />
                  {status.data.enabled ? 'Meta Muse connected' : 'Offline: scripted fallback (set MODEL_API_KEY)'}
                </div>
                <div className="text-ink-2">Agent model: <code>{status.data.fast_model}</code></div>
                <div className="text-ink-2">Long-context assessor: <code>{status.data.deep_model}</code></div>
                <div className="text-ink-2">Sandbox imagery: <code>{status.data.image_model}</code></div>
              </div>
            )}
            {mission && (
              <div className="mt-3 grid grid-cols-3 gap-2 border-t border-line pt-2 text-center">
                <Stat label="Muse calls" value={mission.usage.calls ?? 0} />
                <Stat label="Tokens" value={((mission.usage.input_tokens ?? 0) + (mission.usage.output_tokens ?? 0)).toLocaleString()} />
                <Stat label="Cost" value={`$${(mission.usage.cost_usd ?? 0).toFixed(3)}`} />
              </div>
            )}
          </Card>

          {pending.length > 0 && (
            <Card title={`⏸ Awaiting your approval (${pending.length})`} className="ring-2 ring-warning">
              {pending.map((a) => <ApprovalCard key={a.id} a={a} reviewer={reviewer} />)}
            </Card>
          )}

          {assessments.length > 0 && (
            <Card title="Community assessments">
              <ul className="space-y-2">
                {assessments.map((e) => (
                  <li key={e.id} className="text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-medium">{e.title.split('"')[1]}</span>
                      <span className="rounded px-1.5 py-0.5 text-[10px] font-bold whitespace-nowrap text-white" style={{ background: TIER_COLOR[e.detail.tier] ?? '#64748b' }}>
                        {String(e.detail.tier).replace(/_/g, ' ').toUpperCase()}
                      </span>
                    </div>
                    <p className="mt-0.5 text-ink-2">{e.detail.summary}</p>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-[11px] text-ink-3">{blocks} persona draft(s) blocked by the Safety Governor · {reports.length} report(s) sent</p>
            </Card>
          )}
        </div>

        <div className="space-y-3">
          <Card className="p-3">
            <div className="flex flex-wrap items-center gap-1">
              {PHASES.map((p, i) => {
                const idx = phase ? PHASES.indexOf(phase) : -1
                const state = i < idx || mission?.status === 'completed' ? 'done' : i === idx ? 'now' : 'todo'
                return (
                  <span key={p} className={`rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase ${
                    state === 'now' ? 'bg-gradient-to-r from-accent to-accent-2 text-white shadow-sm shadow-accent/30' : state === 'done' ? 'bg-accent/10 text-accent' : 'bg-line/50 text-ink-3'}`}>
                    {p}
                  </span>
                )
              })}
              <button onClick={() => setShowSandbox(!showSandbox)} className="ml-auto rounded-lg border border-line bg-white px-2.5 py-1 text-xs font-medium hover:border-accent/50 hover:text-accent">
                {showSandbox ? 'Hide' : 'Show'} sandbox view
              </button>
            </div>
          </Card>

          <div className={`grid gap-3 ${showSandbox ? '2xl:grid-cols-[1fr_520px]' : ''}`}>
            <Card title="Live agent log" subtitle="Every step: who acted, which engine produced it, and why.">
              <Timeline events={events} />
            </Card>
            {showSandbox && (
              <Card className="overflow-hidden p-0">
                <div className="flex gap-1 border-b border-line p-2 text-xs">
                  {[['#fb/messages?viewer=u_persona&embed=1', 'Persona: Messenger'], ['#fb/group/g_rip?viewer=u_persona&embed=1', 'Persona: private group'],
                    ['#fb/group/g_ann?viewer=u_persona&embed=1', 'Persona: secret group'], ['#fb/integrity?viewer=u_integrity&embed=1', 'Meta Integrity inbox']].map(([src, label]) => (
                    <button key={src} className="rounded-full border border-line bg-white px-3 py-1 font-medium hover:border-accent/50 hover:text-accent"
                      onClick={() => { const f = document.getElementById('sbx-frame') as HTMLIFrameElement; f.src = `/${src}` }}>{label}</button>
                  ))}
                </div>
                <iframe id="sbx-frame" title="Sandbox platform" src="/#fb/messages?viewer=u_persona&embed=1" className="h-[760px] w-full" />
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return <div><div className="tabular text-sm font-semibold">{value}</div><div className="text-[10px] text-ink-3">{label}</div></div>
}

function ApprovalCard({ a, reviewer }: { a: MissionApproval; reviewer: string }) {
  const [text, setText] = useState<string>(a.payload.text ?? '')
  const [err, setErr] = useState<string>()
  const decide = async (approve: boolean) => {
    try {
      await missionApi.decide(a.id, { approve, reviewer, edited_text: a.kind === 'message' && text !== a.payload.text ? text : undefined })
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <div className="mb-2 rounded-md border border-line p-2 text-xs">
      <div className="font-semibold">{a.title}</div>
      {a.kind === 'message' && (
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} className="mt-1 w-full rounded border border-line p-1" />
      )}
      {a.kind === 'join' && (
        <ul className="mt-1 space-y-0.5 text-ink-2">{a.payload.answers?.map((x: any) => <li key={x.q}><em>{x.q}</em> → "{x.a}"</li>)}</ul>
      )}
      {a.kind === 'report' && (
        <div className="mt-1 space-y-1 text-ink-2">
          <p><strong className="text-ink">{String(a.payload.severity).toUpperCase()}</strong>: {a.payload.executive_summary}</p>
          <p>{a.payload.evidence?.length} evidence posts · {a.payload.recommended_action}</p>
        </div>
      )}
      {err && <p className="text-critical">{err}</p>}
      <div className="mt-2 flex gap-2">
        <button onClick={() => decide(true)} className="rounded-lg bg-accent px-2.5 py-1 font-semibold text-white hover:bg-accent/90">
          {a.kind === 'report' ? 'Approve & send to Meta Integrity' : 'Approve'}
        </button>
        <button onClick={() => decide(false)} className="rounded border border-line px-2 py-1">Reject</button>
      </div>
    </div>
  )
}

function Timeline({ events }: { events: MissionEvent[] }) {
  const box = useRef<HTMLDivElement>(null)
  // Scroll only the log itself; scrollIntoView would also scroll the page.
  useEffect(() => {
    box.current?.scrollTo({ top: box.current.scrollHeight, behavior: 'smooth' })
  }, [events.length])
  if (!events.length) return <p className="text-xs text-ink-3">Launch a mission to watch the agent work.</p>
  return (
    <div ref={box} className="max-h-[760px] space-y-1.5 overflow-y-auto pr-1">
      {events.map((e) => <EventRow key={e.id} e={e} />)}
    </div>
  )
}

function EventRow({ e }: { e: MissionEvent }) {
  const a = ACTOR[e.actor] ?? ACTOR.system
  const blocked = e.kind === 'verdict' && e.detail.decision !== 'allow'
  const allowed = e.kind === 'verdict' && e.detail.decision === 'allow'
  const urgent = (e.kind === 'assessment' && e.detail.tier === 'imminent_threat') || (e.kind === 'report_draft' && e.detail.severity === 'urgent')
  const engineMuse = e.engine.includes('muse')
  return (
    <details className={`rounded-lg border px-2.5 py-2 text-xs transition-colors hover:border-accent/30 ${blocked ? 'border-critical/50 bg-critical/5' : urgent ? 'border-critical bg-critical/10' : allowed ? 'border-good/40 bg-good/5' : 'border-line bg-white'}`}>
      <summary className="flex cursor-pointer list-none items-start gap-2">
        <span className="mt-0.5 w-4 text-center" aria-hidden>{a.icon}</span>
        <span className="w-24 shrink-0 font-semibold" style={{ color: a.color }}>{a.label}</span>
        <span className="min-w-0 flex-1 text-ink">{e.title}</span>
        <span className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] ${engineMuse ? 'bg-[#1877f2] text-white' : 'bg-line text-ink-2'}`} title="Engine that produced this step">
          {e.engine}
        </span>
      </summary>
      <EventDetail e={e} />
    </details>
  )
}

function EventDetail({ e }: { e: MissionEvent }) {
  const d = e.detail
  if (e.kind === 'verdict') {
    return (
      <div className="mt-1 ml-6 space-y-0.5 text-ink-2">
        {d.violations?.length > 0 && <p>Violations: {d.violations.join(', ')}</p>}
        {d.reasons?.map((r: string) => <p key={r}>• {r}</p>)}
        {d.judge_explanation && <p>Muse judge: {d.judge_explanation}</p>}
        {d.suggested_fix && <p>Suggested fix: {d.suggested_fix}</p>}
      </div>
    )
  }
  if (e.kind === 'draft') {
    return (
      <div className="mt-1 ml-6 space-y-0.5 text-ink-2">
        {d.answers?.map((x: any) => <p key={x.q}><em>{x.q}</em> → "{x.a}"</p>)}
        {d.rationale && <p className="text-ink-3">Persona rationale: {d.rationale}</p>}
      </div>
    )
  }
  if (e.kind === 'post') {
    const an = d.analysis
    return (
      <div className="mt-1 ml-6 space-y-0.5 text-ink-2">
        <p>"{d.text}" (by {d.author})</p>
        <p>Rules: {an.rules.category} ({Math.round(an.rules.confidence * 100)}%){an.muse && <> · Muse: {an.muse.category} ({Math.round(an.muse.confidence * 100)}%)</>} → <strong>{an.final_category}</strong> ({an.decision})</p>
        {an.muse?.rationale && <p>Muse rationale: {an.muse.rationale}</p>}
        {an.image && <p>Image ({an.image.engine}): {an.image.observation}</p>}
      </div>
    )
  }
  if (e.kind === 'assessment') {
    return (
      <div className="mt-1 ml-6 space-y-0.5 text-ink-2">
        <p>{d.summary}</p>
        <p>Rules tier: {d.rules_tier}{d.muse && <> · Muse tier: {d.muse.tier} ({Math.round((d.muse.confidence ?? 0) * 100)}%)</>}{d.tier_disagreement && ' · engines disagree, human check'}</p>
        <p>Key evidence: {d.key_evidence?.join(', ')}</p>
        {d.muse?.uncertainties && <p>Uncertainties: {d.muse.uncertainties}</p>}
      </div>
    )
  }
  if (e.kind === 'report_draft') {
    return (
      <div className="mt-1 ml-6 space-y-0.5 text-ink-2">
        <p>{d.executive_summary}</p>
        <p>Action: {d.recommended_action}</p>
        <p>{d.evidence?.length} evidence posts · policies: {[...new Set(d.evidence?.map((x: any) => x.policy))].join('; ')}</p>
      </div>
    )
  }
  return <pre className="mt-1 ml-6 max-h-48 overflow-auto text-[10px] whitespace-pre-wrap text-ink-3">{JSON.stringify(d, null, 2)}</pre>
}
