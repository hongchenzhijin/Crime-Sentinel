import type { Category, ReviewPriority, ReviewStatus } from './types'

// Categorical slots 1-7 of the validated reference palette, assigned in fixed
// order. UNCERTAIN is "no category yet" and uses neutral grey. Colour is never
// the only carrier of meaning: every coloured mark sits next to a text label.
export const CATEGORY_META: Record<Category, { label: string; short: string; color: string; harmful: boolean }> = {
  NEWS_REPORTING: { label: 'News reporting', short: 'News', color: '#2a78d6', harmful: false },
  ACADEMIC_OR_RESEARCH: { label: 'Academic / research', short: 'Research', color: '#eb6834', harmful: false },
  PREVENTION_OR_SUPPORT: { label: 'Prevention / support', short: 'Prevention', color: '#1baf7a', harmful: false },
  NEUTRAL_DISCUSSION: { label: 'Neutral discussion', short: 'Neutral', color: '#eda100', harmful: false },
  GLORIFICATION_OR_PRAISE: { label: 'Glorification / praise', short: 'Glorification', color: '#e87ba4', harmful: true },
  ENCOURAGEMENT_OR_RECRUITMENT: { label: 'Encouragement / recruitment', short: 'Encouragement', color: '#008300', harmful: true },
  EXPLICIT_THREAT_OR_INTENT: { label: 'Explicit threat / intent', short: 'Threat/intent', color: '#6250d6', harmful: true },
  UNCERTAIN_REQUIRES_REVIEW: { label: 'Uncertain - requires review', short: 'Uncertain', color: '#8a8880', harmful: false },
}

// Status palette (reserved for review priority; always paired with icon + label).
export const PRIORITY_META: Record<ReviewPriority, { label: string; color: string; icon: string }> = {
  urgent: { label: 'Urgent review', color: '#d03b3b', icon: '!!' },
  high: { label: 'High', color: '#ec835a', icon: '!' },
  normal: { label: 'Normal', color: '#fab219', icon: '•' },
  low: { label: 'Low', color: '#0ca30c', icon: '–' },
}

export const STATUS_LABEL: Record<ReviewStatus, string> = {
  pending: 'Pending review',
  confirmed: 'Confirmed',
  corrected: 'Corrected',
  marked_uncertain: 'Marked uncertain',
}

export const effectiveCategory = (c: { category: Category; reviewer_category: Category | null }): Category =>
  c.reviewer_category ?? c.category

export const fmtDate = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'

export const fmtDateTime = (iso: string | null | undefined): string =>
  iso
    ? new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
    : '—'

export const pct = (x: number, digits = 0): string => `${(x * 100).toFixed(digits)}%`
// Distinct hues for GraphRAG communities (identity only, no ordering implied).
export const COMMUNITY_COLORS = ['#2a78d6', '#d04a6a', '#2f8f5b', '#eda100', '#7a5cd6', '#1aa3a3', '#c2621f', '#5b6b7a', '#b5489a', '#6f8f1f']
export const communityColor = (id: string | null | undefined) =>
  id ? COMMUNITY_COLORS[(parseInt(id.replace(/\D/g, ''), 10) - 1) % COMMUNITY_COLORS.length] : '#d8d5cc'
