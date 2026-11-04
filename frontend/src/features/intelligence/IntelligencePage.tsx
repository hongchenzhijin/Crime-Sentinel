import { useState, type ReactNode } from 'react'
import type { Nav } from '../../App'
import { Card, CategoryBadge, Empty, ErrorBox, Loading, Notice } from '../../components/ui'
import { api } from '../../lib/api'
import { CATEGORY_META, communityColor, fmtDate, pct } from '../../lib/categories'
import { CATEGORIES, type AskResult, type Category, type Community, type RiskLevel, type SemanticResults } from '../../lib/types'
import { useAsync } from '../../lib/useAsync'

const RISK_META: Record<RiskLevel, { label: string; className: string }> = {
  high: { label: 'High', className: 'bg-critical text-white' },
  elevated: { label: 'Elevated', className: 'bg-[#eda100] text-ink' },
  moderate: { label: 'Moderate', className: 'bg-line text-ink' },
  low: { label: 'Low', className: 'border border-line text-ink-2' },
}
const RISK_ORDER: RiskLevel[] = ['high', 'elevated', 'moderate', 'low']

const EXAMPLES = [
  'Which communities are escalating, and why?',
  'Is glorification spreading through images or re-shared edits?',
  'Where is the anniversary countdown discussed, and how is it framed?',
  'What prevention or counter-speech content exists that moderators could amplify?',
]

export function IntelligencePage({ reviewer, nav, selected, setSelected }: {
  reviewer: string
  nav: Nav
  selected?: string
  setSelected: (id?: string) => void
}) {
  const communities = useAsync(() => api.communities(), [])
  const [building, setBuilding] = useState(false)
  const [buildError, setBuildError] = useState<string>()

  const rebuild = async () => {
    setBuilding(true)
    setBuildError(undefined)
    try {
      await api.buildCommunities(reviewer)
      communities.reload()
    } catch (e) {
      setBuildError((e as Error).message)
    } finally {
      setBuilding(false)
    }
  }

  const list = [...(communities.data ?? [])].sort((a, b) =>
    RISK_ORDER.indexOf(a.risk.final) - RISK_ORDER.indexOf(b.risk.final) || b.stats.size - a.stats.size)

  return (
    <div className="space-y-4">
      <Notice>
        <strong>GraphRAG over the content graph.</strong> Posts are linked by meaning (multilingual embeddings), re-shared
        images (PDQ hashes), distinctive hashtags and public replies, then clustered with Louvain. Meta Muse summarises each
        cluster and answers questions with citations that are checked against what it was shown. Communities are clusters of
        <em> content</em>, never groups of people.
      </Notice>

      <AskPanel reviewer={reviewer} nav={nav} onCommunity={setSelected} />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Communities ({list.length})</h2>
        <div className="flex items-center gap-2 text-xs">
          {list[0] && <span className="text-ink-3">Built {fmtDate(list[0].built_at)} · {list[0].engine}</span>}
          <button onClick={rebuild} disabled={building}
            className="rounded-lg border border-line bg-white px-3 py-1.5 font-medium hover:bg-line/40 disabled:opacity-50"
            title="Recompute the graph, the communities and their Muse summaries (audited)">
            {building ? 'Rebuilding…' : 'Rebuild communities'}
          </button>
        </div>
      </div>
      {buildError && <p className="text-xs text-critical" role="alert">{buildError}</p>}
      {communities.error && <ErrorBox error={communities.error} onRetry={communities.reload} />}
      {communities.loading && !communities.data && <Loading />}
      {communities.data && list.length === 0 && <Empty>No communities yet. Click "Rebuild communities".</Empty>}
      <div className="grid gap-3 xl:grid-cols-2">
        {list.map((c) => (
          <CommunityCard key={c.id} c={c} nav={nav} highlighted={selected === c.id} onSelect={() => setSelected(c.id)} />
        ))}
      </div>

      <SemanticSearch nav={nav} />
    </div>
  )
}

function RiskBadge({ level }: { level: RiskLevel }) {
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${RISK_META[level].className}`}>{RISK_META[level].label} risk</span>
}

function CommunityChip({ id, onClick }: { id: string; onClick?: () => void }) {
  return (
    <button onClick={onClick} className="inline-flex items-center gap-1 rounded-full border border-line px-1.5 py-0 align-baseline font-mono text-[11px] hover:bg-line/40">
      <span className="h-2 w-2 rounded-full" style={{ background: communityColor(id) }} />{id}
    </button>
  )
}

function PostChip({ id, nav }: { id: string; nav: Nav }) {
  return (
    <button onClick={() => nav.goto('review', { postId: id })}
      className="rounded border border-dashed border-line px-1 font-mono text-[11px] text-ink-2 hover:bg-line/40">{id}</button>
  )
}

function CategoryBar({ categories, size }: { categories: Partial<Record<Category, number>>; size: number }) {
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-line" aria-label="Category mix">
      {CATEGORIES.filter((k) => categories[k]).map((k) => (
        <div key={k} title={`${CATEGORY_META[k].label}: ${categories[k]}`}
          style={{ width: `${(100 * (categories[k] ?? 0)) / size}%`, background: CATEGORY_META[k].color }} />
      ))}
    </div>
  )
}

function CommunityCard({ c, nav, highlighted, onSelect }: { c: Community; nav: Nav; highlighted: boolean; onSelect: () => void }) {
  const s = c.stats
  const delta = s.posts_last_14_days - s.posts_prior_14_days
  return (
    <Card
      className={highlighted ? 'ring-2 ring-ink' : ''}
      title={<span className="flex items-center gap-2"><CommunityChip id={c.id} onClick={onSelect} />{c.title}</span>}
      subtitle={`${s.size} posts · ${fmtDate(s.first_post)} – ${fmtDate(s.last_post)} · ${Object.entries(s.languages).map(([l, n]) => `${n} ${l}`).join(', ')}`}
      actions={<RiskBadge level={c.risk.final} />}
    >
      <div className="space-y-2 text-xs">
        <CategoryBar categories={s.categories} size={s.size} />
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-ink-2">
          <span><strong className="text-ink">{pct(s.harmful_share)}</strong> harmful categories</span>
          <span>last 14 days <strong className="text-ink">{s.posts_last_14_days}</strong> vs {s.posts_prior_14_days} before
            <span className={delta > 0 ? 'text-critical' : 'text-ink-3'}> ({delta >= 0 ? '+' : ''}{delta})</span></span>
          {s.images > 0 && <span>{s.images} images · <strong className={s.hashlist_matches ? 'text-critical' : ''}>{s.hashlist_matches} hash-list matches</strong></span>}
          {s.threat_posts > 0 && <span className="font-semibold text-critical">{s.threat_posts} threat post(s)</span>}
          <span>{s.awaiting_review} awaiting review</span>
        </div>
        <p className="text-sm text-ink">{c.summary}</p>
        {c.trajectory && <p className="text-ink-2"><span className="font-medium text-ink">Trajectory:</span> {c.trajectory}</p>}
        {c.themes.length > 0 && (
          <div className="flex flex-wrap gap-1">{c.themes.map((t) => <span key={t} className="rounded-full bg-line/60 px-2 py-0.5">{t}</span>)}</div>
        )}
        <div className="flex flex-wrap items-center gap-1 text-ink-3">
          {s.top_hashtags.map((h) => <span key={h}>#{h}</span>)}
          {s.topics.length > 0 && <span>· {s.topics.join(', ')}</span>}
        </div>
        {c.cited_post_ids.length > 0 && (
          <div className="flex flex-wrap items-center gap-1"><span className="text-ink-2">Evidence:</span>{c.cited_post_ids.map((p) => <PostChip key={p} id={p} nav={nav} />)}</div>
        )}
        <p className="text-[11px] text-ink-3">
          Risk: rules {c.risk.rules}{c.risk.muse ? ` · Muse ${c.risk.muse}` : ''} → shown {c.risk.final} (the higher of the two).
          {c.risk.needs_human_check && <strong className="text-critical"> Engines disagree by two levels or more: human check needed.</strong>}
          {c.uncertainties && ` ${c.uncertainties}`} Summary by {c.engine}; model-generated, not proof.
        </p>
      </div>
    </Card>
  )
}

function AskPanel({ reviewer, nav, onCommunity }: { reviewer: string; nav: Nav; onCommunity: (id: string) => void }) {
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<AskResult>()
  const [error, setError] = useState<string>()
  const [showHarmful, setShowHarmful] = useState(false)

  const submit = async (q: string) => {
    if (q.trim().length < 3) return
    setQuestion(q)
    setBusy(true)
    setError(undefined)
    try {
      setResult(await api.ask(q, reviewer))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const renderAnswer = (text: string): ReactNode[] =>
    text.split(/(\[(?:c\d+|post_[\w-]+)\])/g).map((part, i) => {
      const m = part.match(/^\[(c\d+|post_[\w-]+)\]$/)
      if (!m) return <span key={i}>{part}</span>
      return m[1].startsWith('c')
        ? <CommunityChip key={i} id={m[1]} onClick={() => onCommunity(m[1])} />
        : <PostChip key={i} id={m[1]} nav={nav} />
    })

  return (
    <Card title="Ask the intelligence graph" subtitle="Questions are logged in the audit trail. Questions about identities are refused.">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); submit(question) }}>
        <input value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={500}
          placeholder="e.g. Which communities are escalating, and why?"
          className="flex-1 rounded-lg border border-line bg-white px-3 py-2 text-sm" />
        <button disabled={busy || question.trim().length < 3}
          className="rounded-lg bg-accent shadow-sm shadow-accent/20 px-4 py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50">
          {busy ? 'Thinking…' : 'Ask'}
        </button>
      </form>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {EXAMPLES.map((q) => (
          <button key={q} onClick={() => submit(q)} disabled={busy}
            className="rounded-full border border-line px-2 py-0.5 text-[11px] text-ink-2 hover:bg-line/40">{q}</button>
        ))}
      </div>
      {error && <p className="mt-2 text-xs text-critical" role="alert">{error}</p>}
      {result && (
        <div className="mt-3 space-y-2">
          <div className={`rounded-lg p-3 text-sm ${result.refused ? 'border border-critical/40 bg-critical/5' : 'bg-line/30'}`}>
            <p className="mb-1 text-[11px] font-semibold tracking-wide text-ink-2 uppercase">
              {result.refused ? 'Refused by policy' : `Answer · ${result.engine}`}
              {typeof result.confidence === 'number' && ` · confidence ${pct(result.confidence)}`}
            </p>
            <p className="leading-relaxed">{result.answer ? renderAnswer(result.answer) : 'No generated answer (Muse offline). Retrieved evidence is shown below.'}</p>
            {result.caveats && <p className="mt-2 text-xs text-ink-2">Caveats: {result.caveats}</p>}
            {!result.refused && <p className="mt-1 text-[11px] text-ink-3">Model-generated; every citation was checked against the context Muse was given. Verify before acting.</p>}
          </div>
          {result.retrieved_posts.length > 0 && (
            <details>
              <summary className="cursor-pointer text-xs text-ink-2">
                {result.retrieved_posts.length} posts retrieved by semantic search (local context) · {result.communities_considered.length} community summaries (global context)
              </summary>
              <label className="mt-1 flex items-center gap-1 text-[11px] text-ink-2">
                <input type="checkbox" checked={showHarmful} onChange={(e) => setShowHarmful(e.target.checked)} /> show text of harmful-category posts
              </label>
              <ul className="mt-1 space-y-1">
                {result.retrieved_posts.map((p) => (
                  <li key={p.post_id} className="flex items-start gap-2 text-xs">
                    <span className="tabular w-10 shrink-0 text-ink-3">{p.score.toFixed(2)}</span>
                    <PostChip id={p.post_id} nav={nav} />
                    {p.community && <CommunityChip id={p.community} onClick={() => onCommunity(p.community!)} />}
                    <CategoryBadge category={p.category} />
                    <span className="text-ink-2">{CATEGORY_META[p.category].harmful && !showHarmful ? '[text hidden]' : p.text}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </Card>
  )
}

function SemanticSearch({ nav }: { nav: Nav }) {
  const [q, setQ] = useState('')
  const [res, setRes] = useState<SemanticResults>()
  const [busy, setBusy] = useState(false)
  const run = async () => {
    if (q.trim().length < 2) return
    setBusy(true)
    try { setRes(await api.semanticSearch(q, 10)) } finally { setBusy(false) }
  }
  return (
    <Card title="Semantic search" subtitle="Finds posts by meaning rather than keywords, across languages (try a Bahasa Malaysia query).">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); run() }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} maxLength={300} placeholder="e.g. remember the victims, not the attacker"
          className="flex-1 rounded-lg border border-line bg-white px-3 py-1.5 text-sm" />
        <button disabled={busy} className="rounded-lg border border-line bg-white px-3 py-1.5 text-sm font-medium hover:bg-line/40 disabled:opacity-50">Search</button>
      </form>
      {res && (
        <div className="mt-2">
          <p className="text-[11px] text-ink-3">Embeddings: {res.model ?? 'none'} (local; no text leaves the machine)</p>
          <ul className="mt-1 space-y-1">
            {res.results.map(({ score, item }) => {
              const cat = item.classification.reviewer_category ?? item.classification.category
              return (
                <li key={item.post.id} className="flex items-start gap-2 text-xs">
                  <span className="tabular w-10 shrink-0 text-ink-3">{score.toFixed(2)}</span>
                  <PostChip id={item.post.id} nav={nav} />
                  <CategoryBadge category={cat} />
                  <span className="text-ink-2">{CATEGORY_META[cat].harmful ? '[harmful-category text hidden; open the post]' : item.post.text}</span>
                  {item.post.language !== 'en' && <span className="rounded bg-line/60 px-1 text-[10px]">{item.post.language}</span>}
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </Card>
  )
}
