import { useEffect, useState } from 'react'
import type { Nav } from '../../App'
import { FilterBar } from '../../components/FilterBar'
import { CategoryBadge, ConfidenceMeter, Empty, ErrorBox, Loading, PriorityBadge, StatusBadge } from '../../components/ui'
import { api } from '../../lib/api'
import { CATEGORY_META, effectiveCategory, fmtDate } from '../../lib/categories'
import type { PostFilters, PostWithClassification, Topic } from '../../lib/types'
import { useAsync } from '../../lib/useAsync'
import { PostDetail } from './PostDetail'

const PAGE_SIZE = 15

export function ReviewPage({ filters, setFilters, topics, selectedId, setSelectedId, reviewer, nav }: {
  filters: PostFilters
  setFilters: (f: PostFilters) => void
  topics: Topic[]
  selectedId?: string
  setSelectedId: (id?: string) => void
  reviewer: string
  nav: Nav
}) {
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState('priority')
  const list = useAsync(() => api.posts(filters, page, PAGE_SIZE, sort), [JSON.stringify(filters), page, sort])

  useEffect(() => {
    setPage(1)
  }, [JSON.stringify(filters), sort])
  useEffect(() => {
    if (!selectedId && list.data?.items.length) setSelectedId(list.data.items[0].post.id)
  }, [list.data, selectedId, setSelectedId])

  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <FilterBar
          value={filters}
          onChange={setFilters}
          topics={topics}
          fields={['search', 'category', 'topic', 'status', 'language', 'dates', 'confidence']}
        />
        <label className="flex flex-col gap-0.5 text-[11px] text-ink-2">
          Sort
          <select className="rounded-lg border border-line bg-white px-2 py-1 text-xs text-ink" value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="priority">Review priority</option>
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="confidence_asc">Lowest confidence</option>
            <option value="confidence_desc">Highest confidence</option>
          </select>
        </label>
      </div>
      {(filters.hashtag || filters.priority) && (
        <div className="flex gap-2 text-xs text-ink-2">
          {filters.hashtag && <span className="rounded bg-line/60 px-2 py-0.5">Hashtag: #{filters.hashtag}</span>}
          {filters.priority && <span className="rounded bg-line/60 px-2 py-0.5">Priority: {filters.priority}</span>}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(320px,2fr)_3fr]">
        <section className="rounded-2xl border border-line/80 bg-surface shadow-card" aria-label="Posts">
          <div className="flex items-center justify-between border-b border-line px-3 py-2 text-xs text-ink-2">
            <span>{list.data ? `${list.data.total} posts` : ' '}</span>
            <div className="flex items-center gap-1">
              <button className="rounded px-2 py-0.5 hover:bg-line/50 disabled:opacity-30" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹ Prev</button>
              <span className="tabular">{page} / {pages}</span>
              <button className="rounded px-2 py-0.5 hover:bg-line/50 disabled:opacity-30" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next ›</button>
            </div>
          </div>
          {list.error && <div className="p-3"><ErrorBox error={list.error} onRetry={list.reload} /></div>}
          {list.loading && !list.data && <Loading />}
          {list.data && list.data.items.length === 0 && <Empty>No posts match these filters.</Empty>}
          <ul className={`divide-y divide-line ${list.loading ? 'opacity-60' : ''}`}>
            {list.data?.items.map((item) => (
              <PostRow key={item.post.id} item={item} selected={item.post.id === selectedId} onSelect={() => setSelectedId(item.post.id)} />
            ))}
          </ul>
        </section>

        <section aria-label="Post detail">
          {selectedId ? (
            <PostDetail
              key={selectedId}
              postId={selectedId}
              reviewer={reviewer}
              nav={nav}
              onFilter={(f) => setFilters(f)}
              onReviewed={list.reload}
            />
          ) : (
            <Empty>Select a post to inspect its evidence.</Empty>
          )}
        </section>
      </div>
    </div>
  )
}

function PostRow({ item, selected, onSelect }: { item: PostWithClassification; selected: boolean; onSelect: () => void }) {
  const c = item.classification
  const cat = effectiveCategory(c)
  const harmful = CATEGORY_META[cat].harmful
  return (
    <li>
      <button
        onClick={onSelect}
        className={`block w-full px-3 py-2.5 text-left ${selected ? 'bg-accent/8 ring-1 ring-accent/40 ring-inset' : 'hover:bg-line/30'}`}
        aria-current={selected}
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <CategoryBadge category={cat} />
          {c.review_status === 'pending' && <PriorityBadge priority={c.review_priority} />}
          <span className="ml-auto text-[11px] text-ink-3">{fmtDate(item.post.published_at)}</span>
        </div>
        <p className={`mt-1 line-clamp-2 text-xs ${harmful ? 'italic text-ink-3' : 'text-ink-2'}`}>
          {harmful ? 'Content warning: text hidden in list view. Open to view.' : item.post.text}
        </p>
        <div className="mt-1 flex items-center justify-between">
          <span className="font-mono text-[11px] text-ink-3">{item.post.id}{item.post.language !== 'en' && ` · ${item.post.language}`}</span>
          <div className="flex items-center gap-2">
            <StatusBadge status={c.review_status} />
            <ConfidenceMeter value={c.confidence} />
          </div>
        </div>
      </button>
    </li>
  )
}
