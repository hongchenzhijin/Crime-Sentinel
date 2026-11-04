import { useState } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Nav } from '../../App'
import { FilterBar } from '../../components/FilterBar'
import { Card, Empty, ErrorBox, Loading, Notice } from '../../components/ui'
import { api } from '../../lib/api'
import { CATEGORY_META } from '../../lib/categories'
import { CATEGORIES, type PostFilters, type Topic, type Trends } from '../../lib/types'
import { useAsync } from '../../lib/useAsync'

const AXIS = { fontSize: 11, fill: '#64748b' }
const fmtBucket = (d: string) => new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })

export function TrendsPage({ filters, setFilters, topics, nav }: {
  filters: PostFilters
  setFilters: (f: PostFilters) => void
  topics: Topic[]
  nav: Nav
}) {
  const [granularity, setGranularity] = useState<'week' | 'day'>('week')
  const t = useAsync(() => api.trends(filters, granularity), [JSON.stringify(filters), granularity])

  return (
    <div className="space-y-4">
      <Notice tone="caution">
        <strong>Simulated trends.</strong> The demo dataset has a deliberately constructed timeline. {t.data?.caveat}
      </Notice>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <FilterBar value={filters} onChange={setFilters} topics={topics} fields={['category', 'topic', 'dates']} />
        <div className="flex rounded-lg border border-line bg-white text-xs" role="group" aria-label="Granularity">
          {(['week', 'day'] as const).map((g) => (
            <button key={g} onClick={() => setGranularity(g)}
              className={`px-3 py-1 ${granularity === g ? 'bg-accent text-white' : 'text-ink-2 hover:bg-line/40'} first:rounded-l-lg last:rounded-r-lg`}>
              {g === 'week' ? 'Weekly' : 'Daily'}
            </button>
          ))}
        </div>
      </div>

      {t.error && <ErrorBox error={t.error} onRetry={t.reload} />}
      {t.loading && !t.data && <Loading />}
      {t.data && t.data.series.length === 0 && <Empty>No posts match these filters.</Empty>}
      {t.data && t.data.series.length > 0 && <TrendCharts t={t.data} nav={nav} />}
    </div>
  )
}

function TrendCharts({ t, nav }: { t: Trends; nav: Nav }) {
  const insufficient = t.series.filter((b) => !b.sufficient_sample).length
  const catRows = t.series.map((b) => ({
    bucket: b.bucket_start,
    ...(b.sufficient_sample ? Object.fromEntries(CATEGORIES.map((c) => [c, b.categories[c] ?? 0])) : {}),
    _insufficient: b.sufficient_sample ? 0 : b.total_posts,
  }))
  const topicIds = [...new Set(t.series.flatMap((b) => Object.keys(b.topics)))]
  const topicMax = Math.max(1, ...t.series.flatMap((b) => Object.values(b.topics)))
  const label = (id: string) => t.topics.find((x) => x.id === id)?.label ?? id
  const emerging = new Set(t.emerging_topics.topics.filter((x) => x.emerging).map((x) => x.topic_id))

  return (
    <>
      <Card
        title="Post volume by category over time"
        subtitle={`Stacked ${t.granularity === 'week' ? 'weekly' : 'daily'} counts. Buckets with fewer than ${t.min_sample} posts are shown as a grey 'insufficient sample' bar without a breakdown.`}
      >
        {insufficient > 0 && <p className="mb-2 text-xs text-ink-3">{insufficient} bucket(s) below the minimum sample threshold.</p>}
        <div className="h-80">
          <ResponsiveContainer>
            <BarChart data={catRows} margin={{ left: -16, right: 8 }}>
              <CartesianGrid vertical={false} stroke="#e2e8f0" />
              <XAxis dataKey="bucket" tickFormatter={fmtBucket} tick={AXIS} axisLine={false} tickLine={false} minTickGap={12} />
              <YAxis tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip
                cursor={{ fill: '#4f46e50d' }}
                labelFormatter={(l) => `${t.granularity === 'week' ? 'Week of' : ''} ${fmtBucket(String(l))}`}
                formatter={(v, name) => [v, name === '_insufficient' ? 'Insufficient sample (no breakdown)' : CATEGORY_META[name as keyof typeof CATEGORY_META]?.label ?? name]}
              />
              <Legend
                formatter={(v) => <span className="text-xs text-ink">{v === '_insufficient' ? 'Insufficient sample' : CATEGORY_META[v as keyof typeof CATEGORY_META]?.short}</span>}
                iconType="circle"
                iconSize={8}
              />
              {CATEGORIES.map((c) => (
                <Bar isAnimationActive={false} key={c} dataKey={c} stackId="a" fill={CATEGORY_META[c].color} stroke="#ffffff" strokeWidth={1} />
              ))}
              <Bar isAnimationActive={false} dataKey="_insufficient" stackId="a" fill="#cbd5e1" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card title="Topic activity" subtitle="One panel per topic on a shared scale. Gaps mark buckets below the minimum sample threshold.">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {topicIds.map((id) => {
            const rows = t.series.map((b) => ({ bucket: b.bucket_start, count: b.sufficient_sample ? (b.topics[id] ?? 0) : null }))
            return (
              <button key={id} className="rounded-lg border border-line p-2 text-left hover:bg-line/20"
                onClick={() => nav.goto('review', { filters: { topic_id: id }, postId: '' })} title="Open posts for this topic">
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="font-medium text-ink">{label(id)}</span>
                  {emerging.has(id) && <span className="rounded-full bg-critical/10 px-2 py-0.5 text-[10px] font-semibold text-critical">EMERGING · simulated</span>}
                </div>
                <div className="h-24">
                  <ResponsiveContainer>
                    <AreaChart data={rows} margin={{ top: 6, left: -28, right: 4, bottom: 0 }}>
                      <XAxis dataKey="bucket" hide />
                      <YAxis domain={[0, topicMax]} tick={{ fontSize: 9, fill: '#64748b' }} axisLine={false} tickLine={false} allowDecimals={false} />
                      <Tooltip labelFormatter={(l) => fmtBucket(String(l))} formatter={(v) => [v ?? 'insufficient sample', 'posts']} />
                      <Area isAnimationActive={false} type="monotone" dataKey="count" stroke="#4f46e5" strokeWidth={2} fill="#4f46e5" fillOpacity={0.12} connectNulls={false} dot={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </button>
            )
          })}
        </div>
      </Card>

      <Card
        title="Emerging-topic check"
        subtitle={`Last ${t.emerging_topics.window_days} days of the dataset vs. the ${t.emerging_topics.window_days} days before. Flagged only with ≥ ${t.emerging_topics.min_recent_count} recent posts and ≥ ${t.emerging_topics.min_ratio}× growth.`}
      >
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-ink-2">
              <th className="py-1 font-medium">Topic</th>
              <th className="py-1 text-right font-medium">Previous</th>
              <th className="py-1 text-right font-medium">Recent</th>
              <th className="py-1 text-right font-medium">Ratio</th>
              <th className="py-1 pl-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {t.emerging_topics.topics.map((r) => (
              <tr key={r.topic_id}>
                <td className="py-1.5">{r.label}</td>
                <td className="tabular py-1.5 text-right">{r.previous_count}</td>
                <td className="tabular py-1.5 text-right">{r.recent_count}</td>
                <td className="tabular py-1.5 text-right">{r.ratio}×</td>
                <td className="py-1.5 pl-3">
                  {r.emerging ? <strong>Emerging (simulated)</strong> : !r.meets_sample_threshold ? <span className="text-ink-3">Below sample threshold</span> : <span className="text-ink-2">Stable</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-[11px] text-ink-3">An increase in discussion volume is not evidence of increased real-world danger.</p>
      </Card>
    </>
  )
}
