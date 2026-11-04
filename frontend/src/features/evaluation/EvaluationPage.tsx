import type { Nav } from '../../App'
import { Card, CategoryBadge, ErrorBox, Loading, Notice, StatTile } from '../../components/ui'
import { LearningCard, MultimodalCard, RedTeamCard } from './AiEvaluation'
import { api } from '../../lib/api'
import { CATEGORY_META, pct } from '../../lib/categories'
import type { EvalExample, ModelEvaluation } from '../../lib/types'
import { useAsync } from '../../lib/useAsync'

// Sequential blue ramp (reference palette) for confusion-matrix cells.
const RAMP = ['#ffffff', '#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95']

export function EvaluationPage({ reviewer, nav }: { reviewer: string; nav: Nav }) {
  const { data: ev, error, loading, reload } = useAsync(() => api.evaluation(), [])
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (loading || !ev) return <Loading />
  const rules = ev.contextual
  const base = ev.baseline
  // Muse is the primary classifier when configured; the contextual rules are then its safety net.
  const ctx = ev.muse ?? rules
  const name = ev.muse ? 'Meta Muse' : 'contextual'
  const vsRules = (v: string) => (ev.muse ? `rules ${v} · ` : '')

  return (
    <div className="space-y-4">
      <Notice tone="caution">
        Evaluated on <strong>{ev.dataset.size} synthetic, hand-labelled items</strong> ({Object.entries(ev.dataset.languages).map(([l, n]) => `${n} ${l}`).join(', ')}).
        This is a small test set written by the same team as the classifier cues - treat results as optimistic.
      </Notice>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label={`Macro-F1 (${name})`} value={ctx.macro_f1.toFixed(2)}
          hint={`${vsRules(rules.macro_f1.toFixed(2))}keyword baseline: ${base.macro_f1.toFixed(2)}`} />
        <StatTile label="False-positive rate" value={pct(ctx.harm_binary.false_positive_rate, 1)}
          hint={`non-harmful posts flagged harmful · ${vsRules(pct(rules.harm_binary.false_positive_rate, 1))}baseline ${pct(base.harm_binary.false_positive_rate, 1)}`} />
        <StatTile label="Harmful-content recall" value={pct(ctx.harm_binary.harmful_recall, 1)}
          hint={`${vsRules(pct(rules.harm_binary.harmful_recall, 1))}baseline ${pct(base.harm_binary.harmful_recall, 1)} · ${ctx.harm_binary.harmful_routed_to_review} routed to review`} />
        <StatTile label="Reviewer agreement (live)"
          value={ev.reviewer_feedback.agreement_rate === null ? '—' : pct(ev.reviewer_feedback.agreement_rate)}
          hint={`${ev.reviewer_feedback.reviewed} reviewed posts in the demo dataset`} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <PerClass title={`${ev.muse ? 'Meta Muse classifier' : 'Contextual classifier'} · ${ctx.model}${ctx.usage ? ` · ${ctx.usage.calls} calls, ~$${ctx.usage.cost_usd.toFixed(3)}` : ''}`} m={ctx} compare={base} />
        <Confusion m={ctx} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Examples title={`False positives - ${name} classifier`} subtitle="Non-harmful content (news, research, prevention, neutral) labelled harmful." items={ctx.false_positive_examples} />
        <Examples title={`False negatives - ${name} classifier`} subtitle="Harmful content the classifier missed (not even routed to review)." items={ctx.false_negative_examples} />
        <Examples title="Routed to human review" subtitle="Items the classifier declined to decide on." items={ctx.routed_to_review_examples} />
        <Examples title="False positives - keyword baseline" subtitle="Why keyword filters alone are not enough." items={base.false_positive_examples} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Performance by language">
          <table className="w-full text-xs">
            <thead><tr className="text-left text-ink-2"><th className="py-1 font-medium">Language</th><th className="py-1 text-right font-medium">n</th><th className="py-1 text-right font-medium">Accuracy</th><th className="py-1 text-right font-medium">Macro-F1</th></tr></thead>
            <tbody className="divide-y divide-line">
              {Object.entries(ctx.by_language).map(([lang, r]) => (
                <tr key={lang}><td className="py-1.5">{lang === 'ms' ? 'Bahasa Malaysia (unsupported → review)' : lang === 'en' ? 'English' : lang}</td>
                  <td className="tabular text-right">{r.n}</td><td className="tabular text-right">{pct(r.accuracy)}</td><td className="tabular text-right">{r.macro_f1.toFixed(2)}</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Limitations">
          <ul className="list-disc space-y-1 pl-4 text-xs text-ink-2">
            {ev.limitations.map((l) => <li key={l}>{l}</li>)}
            <li>{ev.reviewer_feedback.note}</li>
          </ul>
        </Card>
      </div>

      {ev.multimodal && <MultimodalCard mm={ev.multimodal} />}
      <div className="grid gap-4 xl:grid-cols-2">
        {ev.red_team && <RedTeamCard rt={ev.red_team} />}
        {ev.learning && <LearningCard learning={ev.learning} reviewer={reviewer} nav={nav} onDone={reload} />}
      </div>
    </div>
  )
}

function PerClass({ title, m, compare }: { title: string; m: ModelEvaluation; compare: ModelEvaluation }) {
  return (
    <Card title="Per-category precision / recall / F1" subtitle={title}>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-ink-2">
              <th className="py-1 font-medium">Category</th>
              <th className="py-1 text-right font-medium">Precision</th>
              <th className="py-1 text-right font-medium">Recall</th>
              <th className="py-1 text-right font-medium">F1</th>
              <th className="py-1 text-right font-medium">Baseline F1</th>
              <th className="py-1 text-right font-medium">Support</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {Object.entries(m.per_class).map(([cat, r]) => (
              <tr key={cat}>
                <td className="py-1.5"><CategoryBadge category={cat as keyof typeof CATEGORY_META} /></td>
                <td className="tabular text-right">{r.precision.toFixed(2)}</td>
                <td className="tabular text-right">{r.recall.toFixed(2)}</td>
                <td className="tabular text-right font-semibold">{r.f1.toFixed(2)}</td>
                <td className="tabular text-right text-ink-3">{compare.per_class[cat as keyof typeof CATEGORY_META].f1.toFixed(2)}</td>
                <td className="tabular text-right">{r.support}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[11px] text-ink-3">Overall accuracy {pct(m.accuracy)} is shown for completeness only - classes are imbalanced.</p>
    </Card>
  )
}

function Confusion({ m }: { m: ModelEvaluation }) {
  const { labels, matrix } = m.confusion_matrix
  const max = Math.max(1, ...matrix.flat())
  return (
    <Card title="Confusion matrix" subtitle="Rows = human label, columns = model prediction. Diagonal = correct.">
      <div className="overflow-x-auto">
        <table className="text-[11px]">
          <thead>
            <tr>
              <th />
              {labels.map((l) => (
                <th key={l} className="h-24 w-9 align-bottom font-medium text-ink-2">
                  <div className="w-9 origin-bottom-left translate-x-4 -rotate-45 whitespace-nowrap">{CATEGORY_META[l].short}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {labels.map((row, i) => (
              <tr key={row}>
                <th className="pr-2 text-right font-medium whitespace-nowrap text-ink-2">{CATEGORY_META[row].short}</th>
                {matrix[i].map((v, j) => {
                  const step = v === 0 ? 0 : Math.max(1, Math.round((v / max) * (RAMP.length - 1)))
                  return (
                    <td key={j} title={`${CATEGORY_META[row].label} → predicted ${CATEGORY_META[labels[j]].label}: ${v}`}
                      className={`tabular h-9 w-9 border-2 border-surface text-center ${i === j ? 'font-bold' : ''}`}
                      style={{ background: RAMP[step], color: step >= 4 ? '#fff' : '#0f172a', borderRadius: 4 }}>
                      {v || ''}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function Examples({ title, subtitle, items }: { title: string; subtitle: string; items: EvalExample[] }) {
  return (
    <Card title={`${title} (${items.length})`} subtitle={subtitle}>
      {items.length === 0 ? (
        <p className="text-xs text-ink-3">None in this test set.</p>
      ) : (
        <ul className="max-h-64 space-y-2 overflow-y-auto pr-1">
          {items.map((e) => (
            <li key={e.id} className="rounded-md border border-line p-2 text-xs">
              <p className="text-ink">“{e.text}”</p>
              <div className="mt-1 flex flex-wrap items-center gap-1 text-ink-2">
                <span>label</span> <CategoryBadge category={e.gold} /> <span>predicted</span> <CategoryBadge category={e.predicted} />
              </div>
              {e.note && <p className="mt-1 text-[11px] text-ink-3">{e.note}</p>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
