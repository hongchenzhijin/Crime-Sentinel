import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DatasetBanner } from '../components/DatasetBanner'
import { segment } from '../components/EvidenceText'
import { toQuery } from './api'
import { CATEGORY_META } from './categories'
import { CATEGORIES, type EvidenceSpan } from './types'

describe('toQuery', () => {
  it('skips empty values and repeats arrays', () => {
    expect(toQuery({ a: 'x', b: undefined, c: '', d: ['p', 'q'], e: 0 })).toBe('?a=x&d=p&d=q&e=0')
    expect(toQuery({})).toBe('')
  })
})

describe('segment', () => {
  const span = (start: number, end: number, text: string): EvidenceSpan => ({
    start, end, text, cue_category: 'GLORIFICATION_OR_PRAISE', note: '',
  })

  it('splits text around evidence spans and preserves the full text', () => {
    const text = 'he is a legend honestly'
    const segs = segment(text, [span(8, 14, 'legend')])
    expect(segs.map((s) => s.text)).toEqual(['he is a ', 'legend', ' honestly'])
    expect(segs.map((s) => s.text).join('')).toBe(text)
  })

  it('drops overlapping and out-of-range spans', () => {
    const text = 'abcdef'
    const segs = segment(text, [span(0, 4, 'abcd'), span(2, 5, 'cde'), span(4, 99, 'x')])
    expect(segs.map((s) => s.text).join('')).toBe(text)
    expect(segs.filter((s) => s.span)).toHaveLength(1)
  })
})

describe('category metadata', () => {
  it('covers every category with a label and colour', () => {
    for (const c of CATEGORIES) {
      expect(CATEGORY_META[c].label).toBeTruthy()
      expect(CATEGORY_META[c].color).toMatch(/^#[0-9a-f]{6}$/)
    }
  })
})

describe('DatasetBanner', () => {
  it('labels synthetic data visibly', () => {
    render(
      <DatasetBanner
        state={{
          loading: false, error: undefined, reload: () => {},
          data: {
            source_names: ['Demo'], is_synthetic: true, synthetic_count: 3, total_posts: 3,
            period_start: '2026-09-01T00:00:00Z', period_end: '2026-10-01T00:00:00Z', ingested_at: null, retention_days: 30,
          },
        }}
      />,
    )
    expect(screen.getByTestId('dataset-banner')).toHaveTextContent(/synthetic data/i)
  })
})
