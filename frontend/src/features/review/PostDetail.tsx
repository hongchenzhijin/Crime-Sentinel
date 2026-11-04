import { useState } from 'react'
import type { Nav } from '../../App'
import { EvidenceText } from '../../components/EvidenceText'
import { Card, CategoryBadge, ConfidenceMeter, ErrorBox, Loading, Notice, PriorityBadge, StatusBadge, SyntheticTag } from '../../components/ui'
import { api } from '../../lib/api'
import { CATEGORY_META, effectiveCategory, fmtDateTime } from '../../lib/categories'
import { CATEGORIES, type AuditEntry, type Category, type MediaObservation, type PostFilters, type ReviewAction } from '../../lib/types'
import { useAsync } from '../../lib/useAsync'

export function PostDetail({ postId, reviewer, nav, onFilter, onReviewed }: {
  postId: string
  reviewer: string
  nav: Nav
  onFilter: (f: PostFilters) => void
  onReviewed: () => void
}) {
  const detail = useAsync(() => api.post(postId), [postId])
  const audit = useAsync(() => api.postAudit(postId), [postId])
  const [revealed, setRevealed] = useState(false)

  if (detail.error) return <ErrorBox error={detail.error} onRetry={detail.reload} />
  if (!detail.data) return <Loading />
  const { post, classification: c, topics } = detail.data
  const current = effectiveCategory(c)
  const sensitive = CATEGORY_META[current].harmful || CATEGORY_META[c.category].harmful
  const showText = !sensitive || revealed
  const scores = Object.entries(c.category_scores).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])
  const maxScore = Math.max(1, ...scores.map(([, v]) => v))

  return (
    <div className="space-y-3">
      <Card
        title={<span className="font-mono">{post.id}</span>}
        subtitle={`${fmtDateTime(post.published_at)} · ${post.language === 'en' ? 'English' : post.language === 'ms' ? 'Bahasa Malaysia' : post.language} · ${post.source_name}`}
        actions={<div className="flex items-center gap-2">{post.is_synthetic && <SyntheticTag />}<StatusBadge status={c.review_status} /></div>}
      >
        {showText ? (
          <div className="rounded-lg border border-line bg-white p-3">
            <EvidenceText text={post.text} spans={c.evidence_spans} />
            <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-ink-3">
              <span><span className="border-b-2 border-ink-2">solid underline</span> = contextual cue (colour = category)</span>
              <span><span className="border-b-2 border-dotted border-ink-2">dotted underline</span> = sensitive keyword (discovery signal only)</span>
              <span>Hover a highlight for its meaning.</span>
            </div>
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-ink-3 bg-line/30 p-4 text-sm">
            <p className="font-medium">Content warning</p>
            <p className="mt-1 text-xs text-ink-2">
              This post was classified as <strong>{CATEGORY_META[current].label.toLowerCase()}</strong>. Text is hidden by
              default to limit reviewer exposure. Take breaks and step away if content is distressing.
            </p>
            <button className="mt-2 rounded-lg border border-line bg-white px-3 py-1 text-xs font-medium hover:bg-line/40" onClick={() => setRevealed(true)}>
              Show text
            </button>
          </div>
        )}

        <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
          {topics.map((t) => (
            <button key={t.id} className="rounded-full bg-line/60 px-2 py-0.5 hover:bg-line" title={t.description} onClick={() => onFilter({ topic_id: t.id })}>
              {t.label}
            </button>
          ))}
          {post.hashtags.map((h) => (
            <button key={h} className="rounded-full border border-line px-2 py-0.5 text-ink-2 hover:bg-line/40" onClick={() => onFilter({ hashtag: h })}>
              #{h}
            </button>
          ))}
          {post.interaction_reference_ids.map((r) => (
            <button key={r} className="rounded-full border border-dashed border-line px-2 py-0.5 text-ink-3 hover:bg-line/40" onClick={() => nav.goto('review', { postId: r })}>
              replies to {r}
            </button>
          ))}
        </div>
        {post.author_reference && (
          <p className="mt-2 text-[11px] text-ink-3">
            Author: non-reversible pseudonym <span className="font-mono">{post.author_reference}</span>. No identity mapping is stored.
          </p>
        )}
      </Card>

      {(post.media?.length ?? 0) > 0 && (
        <MediaPanel postId={post.id} observations={c.media_observations ?? []} sensitive={sensitive && !revealed} onReveal={() => setRevealed(true)} nav={nav} />
      )}

      <Card title="Model classification" subtitle={`${c.model_name} v${c.model_version} · classified ${fmtDateTime(c.classified_at)}`}>
        <div className="flex flex-wrap items-center gap-3">
          <CategoryBadge category={c.category} size="md" />
          <ConfidenceMeter value={c.confidence} />
          {c.review_status === 'pending' && <PriorityBadge priority={c.review_priority} />}
        </div>
        <p className="mt-1 text-[11px] text-ink-3">Confidence is model confidence in the category, not the probability that anyone is dangerous.</p>

        <div className="mt-3 rounded-lg bg-line/30 p-3">
          <p className="text-[11px] font-semibold tracking-wide text-ink-2 uppercase">Model-generated rationale - not proof</p>
          <p className="mt-1 text-sm text-ink">
            {showText ? c.explanation : 'Hidden with the post text because it quotes the post. Use "Show text" above to view.'}
          </p>
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div>
            <p className="mb-1 text-xs font-medium text-ink-2">Cue scores by category</p>
            {scores.length === 0 && <p className="text-xs text-ink-3">No contextual cues matched.</p>}
            <ul className="space-y-1">
              {scores.map(([cat, v]) => (
                <li key={cat} className="grid grid-cols-[110px_1fr_32px] items-center gap-2 text-xs">
                  <span className="truncate text-ink-2">{CATEGORY_META[cat as Category].short}</span>
                  <div className="h-1.5 rounded-full bg-line">
                    <div className="h-full rounded-full" style={{ width: `${(100 * v) / maxScore}%`, background: CATEGORY_META[cat as Category].color }} />
                  </div>
                  <span className="tabular text-right text-ink-2">{v}</span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-ink-2">Signals</p>
            <div className="flex flex-wrap gap-1">
              {c.signals.length === 0 && <span className="text-xs text-ink-3">None</span>}
              {c.signals.map((s) => <code key={s} className="rounded bg-line/50 px-1.5 py-0.5 text-[11px]">{s}</code>)}
            </div>
          </div>
        </div>
      </Card>

      <ReviewForm postId={postId} reviewer={reviewer} modelCategory={c.category} current={c.reviewer_category}
        onDone={() => { detail.reload(); audit.reload(); onReviewed() }} />

      <Card title="Audit trail" subtitle="Every reviewer action on this post is recorded.">
        {audit.loading && !audit.data ? <Loading /> : <AuditList entries={audit.data ?? []} />}
      </Card>
    </div>
  )
}

function ReviewForm({ postId, reviewer, modelCategory, current, onDone }: {
  postId: string
  reviewer: string
  modelCategory: Category
  current: Category | null
  onDone: () => void
}) {
  const [changeTo, setChangeTo] = useState<Category | ''>('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const [saved, setSaved] = useState<string>()

  const submit = async (action: ReviewAction) => {
    setBusy(true)
    setError(undefined)
    try {
      await api.review(postId, {
        action,
        reviewer,
        note: note || undefined,
        reviewer_category: action === 'change' ? (changeTo as Category) : undefined,
      })
      setSaved(action === 'confirm' ? 'Classification confirmed.' : action === 'change' ? 'Correction saved.' : 'Marked as uncertain.')
      setNote('')
      onDone()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Human review" subtitle={`Reviewing as ${reviewer}. The model's original output is always preserved.`}>
      {current && (
        <div className="mb-2 flex items-center gap-2 text-xs text-ink-2">
          Current reviewer decision: <CategoryBadge category={current} />
        </div>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <button disabled={busy} onClick={() => submit('confirm')}
          className="rounded-lg bg-accent shadow-sm shadow-accent/20 px-3 py-1.5 text-xs font-medium text-white hover:bg-accent/90 disabled:opacity-50">
          Confirm "{CATEGORY_META[modelCategory].short}"
        </button>
        <button disabled={busy} onClick={() => submit('mark_uncertain')}
          className="rounded-lg border border-line bg-white px-3 py-1.5 text-xs font-medium hover:bg-line/40 disabled:opacity-50">
          Mark uncertain
        </button>
        <div className="flex items-end gap-1">
          <select aria-label="Change category to" value={changeTo} onChange={(e) => setChangeTo(e.target.value as Category)}
            className="rounded-lg border border-line bg-white px-2 py-1.5 text-xs">
            <option value="">Change category to…</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_META[c].label}</option>)}
          </select>
          <button disabled={busy || !changeTo} onClick={() => submit('change')}
            className="rounded-lg border border-line bg-white px-3 py-1.5 text-xs font-medium hover:bg-line/40 disabled:opacity-50">
            Save correction
          </button>
        </div>
      </div>
      <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} rows={2}
        placeholder="Optional note (reason for decision). Do not record personal information."
        className="mt-2 w-full rounded-lg border border-line bg-white p-2 text-xs" />
      {error && <p className="mt-1 text-xs text-critical" role="alert">{error}</p>}
      {saved && !error && <p className="mt-1 text-xs text-good" role="status">✓ {saved}</p>}
      <div className="mt-2">
        <Notice>Reviews are stored for evaluation and audit. They do not trigger reports to any authority and do not retrain the model automatically.</Notice>
      </div>
    </Card>
  )
}

function AuditList({ entries }: { entries: AuditEntry[] }) {
  if (!entries.length) return <p className="text-xs text-ink-3">No reviewer actions yet.</p>
  return (
    <ul className="space-y-1.5 text-xs">
      {entries.map((e) => (
        <li key={e.id} className="flex flex-wrap gap-x-2 border-l-2 border-line pl-2">
          <span className="text-ink-3">{fmtDateTime(e.timestamp)}</span>
          <span className="font-medium">{e.actor}</span>
          <span className="text-ink-2">{e.action.replace('review_', '').replace('_', ' ')}</span>
          {typeof e.details.reviewer_category === 'string' && (
            <span className="text-ink-2">
              → {CATEGORY_META[e.details.reviewer_category as Category]?.label} (model: {CATEGORY_META[e.details.model_category as Category]?.short})
            </span>
          )}
          {typeof e.details.note === 'string' && e.details.note && <span className="text-ink-3 italic">"{e.details.note}"</span>}
        </li>
      ))}
    </ul>
  )
}

function MediaPanel({ postId, observations, sensitive, onReveal, nav }: {
  postId: string
  observations: MediaObservation[]
  sensitive: boolean
  onReveal: () => void
  nav: Nav
}) {
  const media = useAsync(() => api.postMedia(postId), [postId])
  if (media.error) return <ErrorBox error={media.error} onRetry={media.reload} />
  if (!media.data) return <Loading />
  return (
    <Card title="Attached images" subtitle="PDQ perceptual hash (local) and Meta Muse vision. A hash match identifies the picture, not the intent.">
      <div className="space-y-3">
        {media.data.map((m) => {
          const obs = observations.find((o) => o.file === m.file)
          return (
            <div key={m.file} className="grid gap-3 md:grid-cols-[180px_1fr]">
              <div className="relative overflow-hidden rounded-lg border border-line bg-line/30">
                <img src={m.url} alt={m.alt_text} className={`aspect-square w-full object-cover ${sensitive ? 'blur-xl' : ''}`} />
                {sensitive && (
                  <button onClick={onReveal} className="absolute inset-0 m-auto h-fit w-fit rounded-lg border border-line bg-white px-2 py-1 text-xs font-medium">
                    Show image
                  </button>
                )}
              </div>
              <div className="space-y-2 text-xs">
                {m.hash_match ? (
                  <div className="rounded-md border border-critical/50 bg-critical/5 p-2">
                    <p className="font-semibold text-critical">Matches hash list: {m.hash_match.label}</p>
                    <p className="text-ink-2">
                      Entry <code>{m.hash_match.entry_id}</code> · PDQ distance {m.hash_match.distance}/256 (match at ≤ 31) · {m.hash_match.source}
                      {m.hash_match.low_quality && ' · low-quality hash, treat with caution'}
                    </p>
                  </div>
                ) : (
                  <p className="text-ink-2">No hash-list match{m.pdq ? '' : ' (image not hashed)'}.</p>
                )}
                {m.pdq && <p className="text-ink-3">PDQ <code className="break-all">{m.pdq.slice(0, 32)}…</code> · quality {m.quality}</p>}
                {m.near_duplicate_count > 0 && (
                  <div className="flex flex-wrap items-center gap-1">
                    <span className="text-ink-2">Same image re-shared in {m.near_duplicate_count} other post(s):</span>
                    {m.near_duplicates.slice(0, 8).map((d) => (
                      <button key={d.post_id} title={`PDQ distance ${d.distance}`} onClick={() => nav.goto('review', { postId: d.post_id })}
                        className="rounded border border-dashed border-line px-1 font-mono text-[11px] hover:bg-line/40">{d.post_id}</button>
                    ))}
                  </div>
                )}
                {obs ? (
                  <div className="rounded-md bg-line/30 p-2">
                    <p className="text-[11px] font-semibold tracking-wide text-ink-2 uppercase">Vision ({obs.engine}) - model-generated</p>
                    <p className="mt-1">{obs.observation}</p>
                    {obs.image_text && <p className="mt-1"><span className="text-ink-2">Text in image (also checked by the rules engine):</span> “{obs.image_text}”</p>}
                    {obs.visual_evidence && <p className="mt-1"><span className="text-ink-2">Visual evidence:</span> {obs.visual_evidence}</p>}
                  </div>
                ) : (
                  <p className="text-ink-3">No vision analysis (Muse offline). Alt text: {m.alt_text || 'none'}</p>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}
