import { useCallback, useEffect, useState } from 'react'
import { DatasetBanner } from './components/DatasetBanner'
import { ErrorBoundary, PageHeader } from './components/ui'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { EvaluationPage } from './features/evaluation/EvaluationPage'
import { IntelligencePage } from './features/intelligence/IntelligencePage'
import { MissionPage } from './features/mission/MissionPage'
import { NetworkPage } from './features/network/NetworkPage'
import { ReviewPage } from './features/review/ReviewPage'
import { TrendsPage } from './features/trends/TrendsPage'
import { api } from './lib/api'
import type { PostFilters, Topic } from './lib/types'
import { useAsync } from './lib/useAsync'
import { SafetyPage } from './pages/SafetyPage'

// Stroke icon paths (24x24 viewBox).
const ICONS = {
  mission: 'M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 16.8l-6.2 4.5 2.4-7.4L2 9.4h7.6z',
  dashboard: 'M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z',
  review: 'M9 11l3 3 8-8M20 12v7a2 2 0 01-2 2H6a2 2 0 01-2-2V5a2 2 0 012-2h9',
  intelligence: 'M12 3a6 6 0 016 6c0 2.2-1.2 3.8-2.5 5S14 16.5 14 18h-4c0-1.5-.2-2.7-1.5-4S6 11.2 6 9a6 6 0 016-6zM10 21h4',
  network: 'M6 6m-2.5 0a2.5 2.5 0 105 0 2.5 2.5 0 10-5 0M18 6m-2.5 0a2.5 2.5 0 105 0 2.5 2.5 0 10-5 0M12 18m-2.5 0a2.5 2.5 0 105 0 2.5 2.5 0 10-5 0M8 7.5l3 8M16 7.5l-3 8M8.5 6h7',
  trends: 'M3 17l6-6 4 4 8-8M15 7h6v6',
  evaluation: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  safety: 'M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z',
} as const

const TABS = [
  { id: 'mission', label: 'Mission Control', desc: 'Launch and supervise the governed undercover research agent on the sandbox platform.' },
  { id: 'dashboard', label: 'Dashboard', desc: 'Content and themes prioritised for human review. Click any chart to drill into the posts.' },
  { id: 'review', label: 'Review queue', desc: 'Inspect evidence, then confirm, correct, or mark each classification as uncertain.' },
  { id: 'intelligence', label: 'Intelligence', desc: 'GraphRAG over the content graph: clustered communities, cited answers, and semantic search.' },
  { id: 'network', label: 'Network', desc: 'How posts relate through topics, hashtags, shared images, similar meaning, and public replies.' },
  { id: 'trends', label: 'Trends', desc: 'Category and topic volume over time, with an emerging-topic check.' },
  { id: 'evaluation', label: 'Evaluation', desc: 'How well the classifiers perform on a hand-labelled test set, and where they fail.' },
  { id: 'safety', label: 'Safety & audit', desc: 'What the system does and does not do, its safeguards, and the full audit log.' },
] as const
export type TabId = (typeof TABS)[number]['id']

export interface Nav {
  goto: (tab: TabId, opts?: { filters?: PostFilters; postId?: string; communityId?: string }) => void
}

const tabFromHash = (): TabId => {
  const h = window.location.hash.slice(1)
  return (TABS.find((t) => t.id === h)?.id ?? 'mission') as TabId
}

function Icon({ d, className = 'h-[18px] w-[18px]' }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d={d} />
    </svg>
  )
}

export default function App() {
  const [tab, setTab] = useState<TabId>(tabFromHash)
  const [filters, setFilters] = useState<PostFilters>({})
  const [selectedPost, setSelectedPost] = useState<string>()
  const [selectedCommunity, setSelectedCommunity] = useState<string>()
  const [reviewer, setReviewer] = useState(() => localStorage.getItem('cs.reviewer') ?? 'demo_reviewer')
  const [exporting, setExporting] = useState(false)
  const topics = useAsync<Topic[]>(() => api.topics(), [])
  const dataset = useAsync(() => api.dataset(), [])

  useEffect(() => {
    const onHash = () => setTab(tabFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  useEffect(() => {
    localStorage.setItem('cs.reviewer', reviewer)
  }, [reviewer])

  const goto = useCallback<Nav['goto']>((next, opts) => {
    if (opts?.filters) setFilters(opts.filters)
    if (opts?.postId !== undefined) setSelectedPost(opts.postId)
    if (opts?.communityId !== undefined) setSelectedCommunity(opts.communityId)
    window.location.hash = next
    setTab(next)
  }, [])

  const exportReport = async () => {
    setExporting(true)
    try {
      const report = await api.exportReport(reviewer)
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `crime-sentinel-report-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) {
      alert(`Export failed: ${(e as Error).message}`)
    } finally {
      setExporting(false)
    }
  }

  const topicList = topics.data ?? []
  const nav: Nav = { goto }
  const current = TABS.find((t) => t.id === tab)!

  return (
    <div className="min-h-screen lg:pl-64">
      {/* Sidebar (desktop) */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col bg-[#0b1020] text-slate-300 lg:flex">
        <div className="flex items-center gap-3 px-5 py-5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-accent to-accent-2 text-white shadow-lg shadow-accent/30" aria-hidden>
            <Icon d={ICONS.safety} className="h-5 w-5" />
          </div>
          <div>
            <div className="text-[15px] leading-tight font-semibold text-white">Crime Sentinel</div>
            <div className="text-[11px] text-slate-400">Governed AI research agent</div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-2" aria-label="Main">
          <div className="px-3 pb-2 text-[10px] font-semibold tracking-widest text-slate-500 uppercase">Workspace</div>
          {TABS.map((t) => {
            const active = tab === t.id
            return (
              <a
                key={t.id}
                href={`#${t.id}`}
                aria-current={active ? 'page' : undefined}
                className={`group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                  active ? 'bg-white/10 font-medium text-white shadow-[inset_2px_0_0_0_#818cf8]' : 'text-slate-400 hover:bg-white/5 hover:text-slate-100'
                }`}
              >
                <span className={active ? 'text-indigo-300' : 'text-slate-500 group-hover:text-slate-300'}>
                  <Icon d={ICONS[t.id]} />
                </span>
                {t.label}
              </a>
            )
          })}
        </nav>
        <div className="m-3 rounded-xl border border-white/10 bg-white/5 p-3 text-[11px] leading-relaxed text-slate-400">
          Research prototype. Classifies content, never people. Humans make every decision.
        </div>
      </aside>

      {/* Top bar */}
      <header className="sticky top-0 z-20 border-b border-line/70 bg-white/75 backdrop-blur-xl">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 lg:px-8">
          <div className="flex items-center gap-2 lg:hidden">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-accent-2 text-white" aria-hidden>
              <Icon d={ICONS.safety} className="h-4 w-4" />
            </div>
            <span className="font-semibold">Crime Sentinel</span>
          </div>
          <div className="hidden items-center gap-2 text-sm text-ink-3 lg:flex">
            <span>Console</span>
            <span aria-hidden>/</span>
            <span className="font-medium text-ink">{current.label}</span>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <label className="flex items-center gap-2 rounded-lg border border-line bg-white py-1 pr-1 pl-2.5 text-ink-3 shadow-sm">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent/10 text-[10px] font-bold text-accent uppercase" aria-hidden>
                {reviewer.slice(0, 1)}
              </span>
              <span className="sr-only">Reviewer</span>
              <input
                className="w-32 border-0 bg-transparent px-1 py-0.5 text-ink focus:shadow-none"
                value={reviewer}
                maxLength={64}
                aria-label="Reviewer"
                onChange={(e) => setReviewer(e.target.value || 'demo_reviewer')}
              />
            </label>
            <a href="#fb" className="rounded-lg border border-line bg-white px-3 py-1.5 font-medium text-ink shadow-sm hover:border-accent/50 hover:text-accent">
              Sandbox platform ↗
            </a>
            <button
              onClick={exportReport}
              disabled={exporting}
              className="rounded-lg bg-gradient-to-r from-accent to-accent-2 px-3 py-1.5 font-medium text-white shadow-sm shadow-accent/30 hover:opacity-90 disabled:opacity-50"
              title="Download aggregate statistics and redacted reviewed examples (logged in the audit trail)"
            >
              {exporting ? 'Exporting…' : 'Export report'}
            </button>
          </div>
        </div>
        {/* Tabs (mobile / tablet) */}
        <nav className="flex gap-1 overflow-x-auto px-4 pb-2 lg:hidden" aria-label="Main">
          {TABS.map((t) => (
            <a
              key={t.id}
              href={`#${t.id}`}
              aria-current={tab === t.id ? 'page' : undefined}
              className={`flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs whitespace-nowrap ${
                tab === t.id ? 'bg-ink font-medium text-white' : 'text-ink-2 hover:bg-line/60'
              }`}
            >
              <Icon d={ICONS[t.id]} className="h-3.5 w-3.5" />
              {t.label}
            </a>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-[1440px] px-5 py-6 lg:px-8">
        <DatasetBanner state={dataset} />
        <PageHeader title={current.label} description={current.desc} />
        <div key={tab} className="animate-fade-in">
          <ErrorBoundary>
            {tab === 'mission' && <MissionPage reviewer={reviewer} />}
            {tab === 'dashboard' && <DashboardPage nav={nav} />}
            {tab === 'review' && (
              <ReviewPage
                filters={filters}
                setFilters={setFilters}
                topics={topicList}
                selectedId={selectedPost}
                setSelectedId={setSelectedPost}
                reviewer={reviewer}
                nav={nav}
              />
            )}
            {tab === 'intelligence' && (
              <IntelligencePage reviewer={reviewer} nav={nav} selected={selectedCommunity} setSelected={setSelectedCommunity} />
            )}
            {tab === 'network' && <NetworkPage filters={filters} setFilters={setFilters} topics={topicList} nav={nav} />}
            {tab === 'trends' && <TrendsPage filters={filters} setFilters={setFilters} topics={topicList} nav={nav} />}
            {tab === 'evaluation' && <EvaluationPage reviewer={reviewer} nav={nav} />}
            {tab === 'safety' && <SafetyPage />}
          </ErrorBoundary>
        </div>
      </main>

      <footer className="mx-auto max-w-[1440px] px-5 pb-8 text-[11px] text-ink-3 lg:px-8">
        Crime Sentinel is a research prototype, not a validated threat-assessment system. It classifies content, never
        people, and takes no automated action. Human reviewers make all decisions.
      </footer>
    </div>
  )
}
