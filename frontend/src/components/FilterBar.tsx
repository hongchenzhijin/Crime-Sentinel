import { CATEGORIES, type PostFilters, type Topic } from '../lib/types'
import { CATEGORY_META, STATUS_LABEL } from '../lib/categories'

const input = 'rounded-lg border border-line bg-white px-2.5 py-1.5 text-xs text-ink shadow-sm'

type Field = 'category' | 'topic' | 'status' | 'dates' | 'confidence' | 'search' | 'language'

/** One row of filters, shared by every view so the same selection means the same thing everywhere. */
export function FilterBar({ value, onChange, topics, fields }: {
  value: PostFilters
  onChange: (f: PostFilters) => void
  topics: Topic[]
  fields: Field[]
}) {
  const set = <K extends keyof PostFilters>(k: K, v: PostFilters[K] | '') =>
    onChange({ ...value, [k]: v === '' ? undefined : v })
  const has = (f: Field) => fields.includes(f)
  const active = Object.values(value).some((v) => v !== undefined && v !== '')

  return (
    <div className="flex flex-wrap items-end gap-2">
      {has('search') && (
        <label className="flex flex-col gap-0.5 text-[11px] text-ink-2">
          Text contains
          <input className={`${input} w-40`} value={value.search ?? ''} placeholder="e.g. documentary"
            onChange={(e) => set('search', e.target.value)} />
        </label>
      )}
      {has('category') && (
        <label className="flex flex-col gap-0.5 text-[11px] text-ink-2">
          Category
          <select className={input} value={value.category ?? ''} onChange={(e) => set('category', e.target.value as PostFilters['category'])}>
            <option value="">All categories</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_META[c].label}</option>)}
          </select>
        </label>
      )}
      {has('topic') && (
        <label className="flex flex-col gap-0.5 text-[11px] text-ink-2">
          Topic
          <select className={input} value={value.topic_id ?? ''} onChange={(e) => set('topic_id', e.target.value)}>
            <option value="">All topics</option>
            {topics.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
        </label>
      )}
      {has('status') && (
        <label className="flex flex-col gap-0.5 text-[11px] text-ink-2">
          Review status
          <select className={input} value={value.review_status ?? ''} onChange={(e) => set('review_status', e.target.value as PostFilters['review_status'])}>
            <option value="">Any status</option>
            {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
      )}
      {has('language') && (
        <label className="flex flex-col gap-0.5 text-[11px] text-ink-2">
          Language
          <select className={input} value={value.language ?? ''} onChange={(e) => set('language', e.target.value)}>
            <option value="">Any</option>
            <option value="en">English</option>
            <option value="ms">Bahasa Malaysia</option>
          </select>
        </label>
      )}
      {has('dates') && (
        <>
          <label className="flex flex-col gap-0.5 text-[11px] text-ink-2">
            From
            <input type="date" className={input} value={value.date_from?.slice(0, 10) ?? ''}
              onChange={(e) => set('date_from', e.target.value ? `${e.target.value}T00:00:00Z` : '')} />
          </label>
          <label className="flex flex-col gap-0.5 text-[11px] text-ink-2">
            To
            <input type="date" className={input} value={value.date_to?.slice(0, 10) ?? ''}
              onChange={(e) => set('date_to', e.target.value ? `${e.target.value}T23:59:59Z` : '')} />
          </label>
        </>
      )}
      {has('confidence') && (
        <label className="flex flex-col gap-0.5 text-[11px] text-ink-2">
          Max model confidence
          <select className={input} value={value.max_confidence ?? ''}
            onChange={(e) => set('max_confidence', e.target.value ? Number(e.target.value) : '')}>
            <option value="">Any</option>
            <option value="0.5">≤ 50% (low)</option>
            <option value="0.7">≤ 70%</option>
          </select>
        </label>
      )}
      {active && (
        <button className="rounded-md px-2 py-1 text-xs text-accent hover:underline" onClick={() => onChange({})}>
          Clear filters
        </button>
      )}
    </div>
  )
}
