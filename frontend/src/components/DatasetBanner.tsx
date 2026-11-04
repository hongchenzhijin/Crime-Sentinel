import { fmtDate } from '../lib/categories'
import type { DatasetInfo } from '../lib/types'
import type { AsyncState } from '../lib/useAsync'

/** Always-visible statement of where the data comes from and whether it is synthetic. */
export function DatasetBanner({ state }: { state: AsyncState<DatasetInfo> }) {
  const d = state.data
  if (state.error) {
    return (
      <div className="mb-5 rounded-xl border border-critical/30 bg-critical/5 px-4 py-2.5 text-xs text-ink" role="alert">
        <strong className="text-critical">Backend unavailable:</strong> {state.error.message}. Start it with{' '}
        <code className="rounded bg-white px-1">uvicorn app.main:app</code> in <code className="rounded bg-white px-1">backend/</code>.
      </div>
    )
  }
  if (!d) return <div className="mb-5 h-9" />
  return (
    <div
      className={`mb-5 flex flex-wrap items-center gap-x-5 gap-y-1 rounded-xl border px-4 py-2 text-xs text-ink-2 ${
        d.is_synthetic ? 'border-dashed border-ink-3/40 bg-white/60' : 'border-warning/40 bg-warning/10'
      }`}
      data-testid="dataset-banner"
    >
      <strong className="flex items-center gap-2 text-[11px] font-semibold tracking-wide text-ink uppercase">
        <span className={`h-2 w-2 rounded-full ${d.is_synthetic ? 'bg-accent' : 'bg-warning'}`} aria-hidden />
        {d.is_synthetic ? 'Synthetic data - not real posts or people' : 'Contains permitted research data'}
      </strong>
      <span>Source: <span className="text-ink">{d.source_names.join(', ') || 'none loaded'}</span></span>
      <span>
        Period: <span className="text-ink">{fmtDate(d.period_start)} – {fmtDate(d.period_end)}</span>
      </span>
      <span><span className="tabular text-ink">{d.total_posts}</span> posts</span>
      <span>Retention: <span className="text-ink">{d.retention_days} days</span></span>
    </div>
  )
}
