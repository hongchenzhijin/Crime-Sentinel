import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Nav } from '../../App'
import { Card, CategoryBadge, Empty, ErrorBox, Loading, Notice, PriorityBadge, StatTile } from '../../components/ui'
import { api } from '../../lib/api'
import { CATEGORY_META, pct } from '../../lib/categories'
import { CATEGORIES, type ReviewPriority } from '../../lib/types'
import { useAsync } from '../../lib/useAsync'

const AXIS = { fontSize: 11, fill: '#64748b' }

export function DashboardPage({ nav }: { nav: Nav }) {
  const { data: s, error, loading, reload } = useAsync(() => api.summary(), [])
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (loading || !s) return <Loading />
  if (s.total_posts === 0) return <Empty>No data loaded. Run <code>python scripts/load_demo_data.py</code>.</Empty>

  const categoryRows = CATEGORIES.map((c) => ({ category: c, label: CATEGORY_META[c].short, count: s.by_category[c] }))

  return (
    <div className="space-y-4">
      <Notice>
        This dashboard prioritises <strong>content and themes</strong> for human review. It does not score, rank, or
        identify people. {s.confidence_note}
      </Notice>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatTile label="Posts in dataset" value={s.total_posts} hint="synthetic demo data" />
        <StatTile label="Awaiting human review" value={`${s.pending_review_pct}%`} hint={`${s.pending_review} posts pending`} />
        <StatTile
          label="Urgent items awaiting review"
          value={s.urgent_threat_pending}
          tone={s.urgent_threat_pending ? 'critical' : undefined}
          hint="possible threat/intent content"
        />
        <StatTile label="Repeated glorification signals" value={s.repeated_glorification_signal_posts} hint="posts with 2+ praise cues" />
        <StatTile label="Harmful-content posts" value={s.harmful_content_posts} hint="glorification, encouragement, threat" />
        <StatTile
          label="False-positive rate (eval set)"
          value={pct(s.evaluation_false_positive_rate, 1)}
          hint={`keyword baseline: ${pct(s.baseline_false_positive_rate, 1)} · n=${s.evaluation_set_size}`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          title="Posts by classification category"
          subtitle="Uses the reviewer's category where a review exists, otherwise the model's. Click a bar to open those posts."
          className="lg:col-span-2"
        >
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={categoryRows} layout="vertical" margin={{ left: 8, right: 24 }}>
                <CartesianGrid horizontal={false} stroke="#e2e8f0" />
                <XAxis type="number" tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
                <YAxis type="category" dataKey="label" tick={AXIS} width={100} axisLine={false} tickLine={false} />
                <Tooltip
                  cursor={{ fill: '#4f46e50d' }}
                  formatter={(v) => [v, 'posts']}
                  labelFormatter={(_, p) => (p?.[0] ? CATEGORY_META[p[0].payload.category as keyof typeof CATEGORY_META].label : '')}
                />
                <Bar isAnimationActive={false}
                  dataKey="count"
                  radius={[0, 4, 4, 0]}
                  barSize={18}
                  label={{ position: 'right', fontSize: 11, fill: '#64748b' }}
                  onClick={(d) => nav.goto('review', { filters: { category: (d as { category?: never }).category } })}
                  className="cursor-pointer"
                >
                  {categoryRows.map((r) => <Cell key={r.category} fill={CATEGORY_META[r.category].color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Pending review by priority" subtitle="Priority reflects content category and model uncertainty only.">
          <ul className="divide-y divide-line">
            {(['urgent', 'high', 'normal', 'low'] as ReviewPriority[]).map((p) => (
              <li key={p}>
                <button
                  className="flex w-full items-center justify-between py-2 text-left hover:bg-line/30"
                  onClick={() => nav.goto('review', { filters: { priority: p, review_status: 'pending' } })}
                >
                  <PriorityBadge priority={p} />
                  <span className="tabular pr-1 text-sm font-semibold">{s.pending_by_priority[p]}</span>
                </button>
              </li>
            ))}
          </ul>
          <button
            className="mt-3 w-full rounded-lg bg-accent shadow-sm shadow-accent/20 px-3 py-2 text-sm font-medium text-white hover:bg-accent/90"
            onClick={() => nav.goto('review', { filters: { review_status: 'pending' } })}
          >
            Open review queue
          </button>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          title="Model confidence distribution"
          subtitle="Classifier confidence in a content category - not the probability that any person is dangerous."
          className="lg:col-span-2"
        >
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={s.confidence_histogram} margin={{ left: -16, right: 8 }}>
                <CartesianGrid vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="bucket" tick={AXIS} axisLine={false} tickLine={false} />
                <YAxis tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip cursor={{ fill: '#4f46e50d' }} formatter={(v) => [v, 'posts']} labelFormatter={(l) => `Confidence ${l}`} />
                <Bar isAnimationActive={false} dataKey="count" fill="#4f46e5" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Most active topics" subtitle="Post volume per dataset topic.">
          <ul className="space-y-1.5">
            {s.top_topics.map((t) => (
              <li key={t.topic_id}>
                <button
                  className="w-full rounded px-1 py-0.5 text-left hover:bg-line/30"
                  onClick={() => nav.goto('review', { filters: { topic_id: t.topic_id } })}
                >
                  <div className="flex justify-between text-xs">
                    <span className="text-ink">{t.label}</span>
                    <span className="tabular text-ink-2">{t.count}</span>
                  </div>
                  <div className="mt-0.5 h-1.5 rounded-full bg-line">
                    <div className="h-full rounded-full bg-accent" style={{ width: `${(100 * t.count) / s.top_topics[0].count}%` }} />
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card title="Model output vs. current (reviewed) categories" subtitle="How human review has changed the picture so far.">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-ink-2">
                <th className="py-1 font-medium">Category</th>
                <th className="py-1 text-right font-medium">Model output</th>
                <th className="py-1 text-right font-medium">After review</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {CATEGORIES.map((c) => (
                <tr key={c}>
                  <td className="py-1.5"><CategoryBadge category={c} /></td>
                  <td className="tabular py-1.5 text-right">{s.by_model_category[c]}</td>
                  <td className="tabular py-1.5 text-right">{s.by_category[c]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
