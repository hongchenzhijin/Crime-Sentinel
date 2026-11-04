import { Component, type ErrorInfo, type ReactNode } from 'react'
import { CATEGORY_META, PRIORITY_META, STATUS_LABEL, pct } from '../lib/categories'
import type { Category, ReviewPriority, ReviewStatus } from '../lib/types'

export function Card({ title, subtitle, actions, children, className = '' }: {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`rounded-2xl border border-line/80 bg-surface p-5 shadow-card ${className}`}>
      {(title || actions) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title && <h2 className="text-[15px] font-semibold tracking-tight text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs leading-relaxed text-ink-3">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

export function PageHeader({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-ink-2">{description}</p>}
      </div>
      {actions}
    </div>
  )
}

export function StatTile({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'critical' }) {
  return (
    <div className={`relative overflow-hidden rounded-2xl border bg-surface p-4 shadow-card ${tone === 'critical' ? 'border-critical/30' : 'border-line/80'}`}>
      <span className={`absolute inset-x-0 top-0 h-1 ${tone === 'critical' ? 'bg-critical' : 'bg-gradient-to-r from-accent to-accent-2'}`} aria-hidden />
      <div className="text-[11px] font-semibold tracking-wide text-ink-3 uppercase">{label}</div>
      <div className={`tabular mt-2 text-3xl font-semibold tracking-tight ${tone === 'critical' ? 'text-critical' : 'text-ink'}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-ink-3">{hint}</div>}
    </div>
  )
}

export function CategoryBadge({ category, size = 'sm' }: { category: Category; size?: 'sm' | 'md' }) {
  const meta = CATEGORY_META[category]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium whitespace-nowrap text-ink ${
        size === 'md' ? 'px-3 py-1 text-sm' : 'px-2 py-0.5 text-xs'
      }`}
      style={{ background: `${meta.color}1f`, boxShadow: `inset 0 0 0 1px ${meta.color}40` }}
      title={category}
    >
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: meta.color }} aria-hidden />
      {meta.label}
    </span>
  )
}

export function PriorityBadge({ priority }: { priority: ReviewPriority }) {
  const meta = PRIORITY_META[priority]
  return (
    <span className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-xs font-medium text-ink" title={`Review priority: ${meta.label}`}>
      <span
        className="inline-flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-bold text-white"
        style={{ background: meta.color }}
        aria-hidden
      >
        {meta.icon}
      </span>
      {meta.label}
    </span>
  )
}

export function StatusBadge({ status }: { status: ReviewStatus }) {
  const style = status === 'pending' ? 'border-dashed border-ink-3/40 text-ink-2' : 'border-good/30 bg-good/10 text-good'
  return <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap ${style}`}>{STATUS_LABEL[status]}</span>
}

export function ConfidenceMeter({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-2" title="Model confidence in the content category - not a probability that anyone is dangerous">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-line">
        <div className="h-full rounded-full bg-gradient-to-r from-accent to-accent-2" style={{ width: pct(value) }} />
      </div>
      <span className="tabular text-xs text-ink-2">{pct(value)}</span>
    </div>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 p-8 text-sm text-ink-3" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
      {label}
    </div>
  )
}

export function ErrorBox({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="rounded-2xl border border-critical/30 bg-critical/5 p-4 text-sm" role="alert">
      <p className="font-semibold text-critical">Could not load data</p>
      <p className="mt-1 text-ink-2">{error.message}</p>
      <p className="mt-1 text-xs text-ink-3">Is the backend running on port 8000, and has the demo data been loaded?</p>
      {onRetry && (
        <button onClick={onRetry} className="mt-3 rounded-lg border border-line bg-white px-3 py-1 text-xs font-medium hover:border-accent hover:text-accent">
          Retry
        </button>
      )}
    </div>
  )
}

/** Contains a render crash to the page it happened in, so the rest of the console keeps working. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error?: Error }> {
  state: { error?: Error } = {}
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack)
  }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="rounded-2xl border border-critical/30 bg-critical/5 p-6 text-sm" role="alert">
        <p className="font-semibold text-critical">This view hit an error</p>
        <p className="mt-1 font-mono text-xs text-ink-2">{this.state.error.message}</p>
        <p className="mt-2 text-xs text-ink-3">
          This usually means the backend is running an older version than the frontend. Restart it, then retry.
        </p>
        <button
          onClick={() => this.setState({ error: undefined })}
          className="mt-3 rounded-lg border border-line bg-white px-3 py-1 text-xs font-medium hover:border-accent hover:text-accent"
        >
          Retry
        </button>
      </div>
    )
  }
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="p-8 text-center text-sm text-ink-3">{children}</div>
}

export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'caution' }) {
  const cls = tone === 'caution'
    ? 'border-warning/40 bg-warning/10 [&>span]:bg-warning/20 [&>span]:text-[#9a5b00]'
    : 'border-accent/20 bg-accent/5 [&>span]:bg-accent/10 [&>span]:text-accent'
  return (
    <div className={`flex items-start gap-3 rounded-xl border px-4 py-3 text-[13px] leading-relaxed text-ink-2 ${cls}`}>
      <span aria-hidden className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold">
        {tone === 'caution' ? '!' : 'i'}
      </span>
      <div className="[&_strong]:text-ink">{children}</div>
    </div>
  )
}

export function SyntheticTag() {
  return (
    <span className="rounded-full border border-dashed border-ink-3/60 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-ink-2 uppercase">
      Synthetic
    </span>
  )
}
