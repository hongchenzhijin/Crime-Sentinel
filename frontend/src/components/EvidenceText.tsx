import { CATEGORY_META } from '../lib/categories'
import type { EvidenceSpan } from '../lib/types'

interface Segment {
  text: string
  span?: EvidenceSpan
}

/** Split text into plain and highlighted segments. Overlapping spans keep the first (earliest, longest). */
export function segment(text: string, spans: EvidenceSpan[]): Segment[] {
  const sorted = [...spans].sort((a, b) => a.start - b.start || b.end - a.end)
  const out: Segment[] = []
  let pos = 0
  for (const s of sorted) {
    if (s.start < pos || s.end > text.length) continue
    if (s.start > pos) out.push({ text: text.slice(pos, s.start) })
    out.push({ text: text.slice(s.start, s.end), span: s })
    pos = s.end
  }
  if (pos < text.length) out.push({ text: text.slice(pos) })
  return out
}

export function EvidenceText({ text, spans }: { text: string; spans: EvidenceSpan[] }) {
  return (
    <p className="text-sm leading-relaxed whitespace-pre-wrap text-ink">
      {segment(text, spans).map((seg, i) => {
        if (!seg.span) return <span key={i}>{seg.text}</span>
        const isKeyword = seg.span.cue_category === 'KEYWORD_SIGNAL'
        const color = isKeyword ? '#8a8880' : CATEGORY_META[seg.span.cue_category as keyof typeof CATEGORY_META].color
        return (
          <mark
            key={i}
            title={seg.span.note}
            className="rounded-sm bg-transparent px-0.5 text-ink"
            style={{
              boxShadow: `inset 0 -0.45em 0 ${color}33`,
              borderBottom: `2px ${isKeyword ? 'dotted' : 'solid'} ${color}`,
            }}
          >
            {seg.text}
          </mark>
        )
      })}
    </p>
  )
}
