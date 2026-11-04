import { useState } from 'react'
import type { Nav } from '../../App'
import { Card, CategoryBadge } from '../../components/ui'
import { api } from '../../lib/api'
import { CATEGORY_META, fmtDateTime, pct } from '../../lib/categories'
import type { Evaluation, MultimodalEval, ReclassifySummary, RedTeamResults } from '../../lib/types'

export function MultimodalCard({ mm }: { mm: MultimodalEval }) {
  const engines = Object.entries(mm.engines)
  return (
    <Card title="Vision: posts where the image changes the meaning" subtitle={`${mm.size} hand-labelled synthetic items · ${mm.note}`}>
      <table className="w-full text-xs">
        <thead><tr className="text-left text-ink-2">
          <th className="py-1 font-medium">Engine</th><th className="py-1 text-right font-medium">Exact</th>
          <th className="py-1 text-right font-medium">Harmful caught</th><th className="py-1 text-right font-medium">+ to review</th>
          <th className="py-1 text-right font-medium">Benign flagged</th>
        </tr></thead>
        <tbody className="divide-y divide-line">
          {engines.map(([k, e]) => (
            <tr key={k} className={k === 'muse_vision' ? 'font-semibold' : ''}>
              <td className="py-1.5">{e.label}</td>
              <td className="tabular text-right">{pct(e.accuracy)}</td>
              <td className="tabular text-right">{e.harmful_caught}/{e.harmful_items}</td>
              <td className="tabular text-right">{e.harmful_routed_to_review}</td>
              <td className="tabular text-right">{e.benign_flagged_harmful}/{e.benign_items}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-xs">
          <thead><tr className="text-left text-ink-2">
            <th className="py-1 font-medium">Image</th><th className="py-1 font-medium">Caption</th><th className="py-1 font-medium">Gold</th>
            {engines.map(([k, e]) => <th key={k} className="py-1 font-medium">{e.label.split(' (')[0]}</th>)}
          </tr></thead>
          <tbody className="divide-y divide-line">
            {mm.items.map((i) => (
              <tr key={i.id} title={i.note}>
                <td className="py-1">
                  <img src={`/api/media/${i.image}`} alt="" className={`h-10 w-10 rounded object-cover ${CATEGORY_META[i.gold].harmful ? 'blur-[3px]' : ''}`} />
                </td>
                <td className="py-1">“{i.text}”{i.hash_match && <span className="ml-1 rounded bg-critical/10 px-1 text-[10px] text-critical">PDQ match</span>}</td>
                <td className="py-1"><CategoryBadge category={i.gold} /></td>
                {engines.map(([k]) => (
                  <td key={k} className={`py-1 ${i.predictions[k] === i.gold ? '' : 'opacity-60'}`}><CategoryBadge category={i.predictions[k]} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

const OUTCOME_ORDER = ['evaded', 'false_alarm', 'routed_to_review', 'mislabelled', 'caught', 'correct'] as const

export function RedTeamCard({ rt }: { rt: RedTeamResults }) {
  const names = Object.keys(rt.classifiers)
  return (
    <Card title="AI red-team stress test" subtitle={`${rt.size} adversarial posts written by ${rt.set.generator} · evaluated ${fmtDateTime(rt.evaluated_at)}`}>
      <p className="mb-2 rounded-md bg-[#eda100]/15 p-2 text-xs">
        <strong>Unverified, and flattering to Muse.</strong> Labels are the generator's intent, not a human's, and the same model
        family wrote and judged these posts, which favours Muse. Use this to find blind spots by tactic, not as accuracy.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead><tr className="text-left text-ink-2">
            <th className="py-1 font-medium">Tactic</th><th className="py-1 font-medium">Intended</th>
            {names.map((n) => <th key={n} className="py-1 text-right font-medium">{n}</th>)}
          </tr></thead>
          <tbody className="divide-y divide-line">
            {Object.entries(rt.tactics).map(([t, meta]) => (
              <tr key={t} title={meta.description}>
                <td className="py-1.5">{t.replaceAll('_', ' ')}{meta.language !== 'en' && <span className="ml-1 text-ink-3">({meta.language})</span>}</td>
                <td className="py-1.5"><CategoryBadge category={meta.intended_label} /></td>
                {names.map((n) => {
                  const c = rt.classifiers[n].by_tactic[t] ?? {}
                  const total = Object.values(c).reduce((a, b) => a + (b ?? 0), 0)
                  const bad = (c.evaded ?? 0) + (c.false_alarm ?? 0)
                  return (
                    <td key={n} className="tabular py-1.5 text-right"
                      title={OUTCOME_ORDER.filter((o) => c[o]).map((o) => `${o.replaceAll('_', ' ')}: ${c[o]}`).join(', ')}
                      style={{ background: total ? `rgba(208, 59, 59, ${(0.6 * bad) / total})` : undefined }}>
                      {total ? `${bad}/${total}` : '–'}
                    </td>
                  )
                })}
              </tr>
            ))}
            <tr className="font-semibold">
              <td className="py-1.5" colSpan={2}>Evasion rate (harmful not flagged, not routed to review)</td>
              {names.map((n) => <td key={n} className="tabular text-right">{rt.classifiers[n].evasion_rate === null ? '–' : pct(rt.classifiers[n].evasion_rate!)}</td>)}
            </tr>
            <tr className="font-semibold">
              <td className="py-1.5" colSpan={2}>False-alarm rate (benign flagged harmful)</td>
              {names.map((n) => <td key={n} className="tabular text-right">{rt.classifiers[n].false_alarm_rate === null ? '–' : pct(rt.classifiers[n].false_alarm_rate!)}</td>)}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-[11px] text-ink-3">Cells show failures / items (evaded or false alarm). Hover for the full outcome mix. Regenerate with <code>python scripts/red_team.py --regenerate</code>.</p>
      {names.map((n) => rt.classifiers[n].failures.length > 0 && (
        <details key={n} className="mt-2 text-xs">
          <summary className="cursor-pointer text-ink-2">{n}: {rt.classifiers[n].failures.length} failure examples</summary>
          <ul className="mt-1 space-y-1">
            {rt.classifiers[n].failures.slice(0, 12).map((f) => (
              <li key={f.id} className="flex flex-wrap items-center gap-1">
                <span className="text-ink-3">{f.tactic.replaceAll('_', ' ')}</span> “{f.text}” → <CategoryBadge category={f.predicted} />
              </li>
            ))}
          </ul>
        </details>
      ))}
    </Card>
  )
}

export function LearningCard({ learning, reviewer, nav, onDone }: {
  learning: Evaluation['learning']
  reviewer: string
  nav: Nav
  onDone: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const [result, setResult] = useState<ReclassifySummary | undefined>(learning.last_run?.details)
  const run = async () => {
    setBusy(true)
    setError(undefined)
    try {
      setResult(await api.reclassify(reviewer))
      onDone()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card title="Learning loop: reviewer decisions as few-shot examples"
      subtitle="No retraining. The most similar reviewed posts are shown to Muse as examples when it classifies a post.">
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <span><strong className="text-sm">{learning.examples}</strong> reviewed examples ({learning.corrections} corrections)</span>
        <button onClick={run} disabled={busy || learning.examples === 0}
          className="rounded-lg bg-accent shadow-sm shadow-accent/20 px-3 py-1.5 font-medium text-white hover:bg-accent/90 disabled:opacity-50"
          title="Re-run the classifier over every post; human review decisions are kept">
          {busy ? 'Reclassifying… (about 30 s)' : 'Reclassify with reviewer feedback'}
        </button>
        {learning.examples === 0 && (
          <button className="text-ink-2 underline" onClick={() => nav.goto('review')}>Review some posts first</button>
        )}
      </div>
      {error && <p className="mt-2 text-xs text-critical" role="alert">{error}</p>}
      {result && (
        <div className="mt-3 space-y-1 text-xs">
          <p>
            {result.model} with {result.reviewer_examples} examples: <strong>{result.changed}</strong> of {result.posts} model labels changed.
            {result.agreement_before !== null && (
              <> Agreement with reviewers on {result.reviewed_posts} reviewed posts: {pct(result.agreement_before)} → <strong>{pct(result.agreement_after ?? 0)}</strong>.</>
            )}
            {result.usage && ` ${result.usage.calls} Muse calls, ~$${result.usage.cost_usd.toFixed(3)}.`}
          </p>
          {result.transitions.length > 0 && (
            <ul className="flex flex-wrap gap-2">
              {result.transitions.slice(0, 8).map((t) => (
                <li key={`${t.from}-${t.to}`} className="flex items-center gap-1 rounded border border-line px-1.5 py-0.5">
                  <CategoryBadge category={t.from} /> → <CategoryBadge category={t.to} /> <span className="tabular">×{t.count}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="text-[11px] text-ink-3">{result.note}</p>
        </div>
      )}
    </Card>
  )
}
