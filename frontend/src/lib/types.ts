// Typed mirror of backend/app/schemas/models.py. Keep in sync.

export const CATEGORIES = [
  'NEWS_REPORTING',
  'ACADEMIC_OR_RESEARCH',
  'PREVENTION_OR_SUPPORT',
  'NEUTRAL_DISCUSSION',
  'GLORIFICATION_OR_PRAISE',
  'ENCOURAGEMENT_OR_RECRUITMENT',
  'EXPLICIT_THREAT_OR_INTENT',
  'UNCERTAIN_REQUIRES_REVIEW',
] as const
export type Category = (typeof CATEGORIES)[number]

export type ReviewStatus = 'pending' | 'confirmed' | 'corrected' | 'marked_uncertain'
export type ReviewPriority = 'urgent' | 'high' | 'normal' | 'low'
export type ReviewAction = 'confirm' | 'change' | 'mark_uncertain'
export type EdgeType = 'USES_HASHTAG' | 'MENTIONS_TOPIC' | 'SIMILAR_CONTENT' | 'PUBLICLY_LINKED_TO' | 'SHARES_IMAGE'

export interface Post {
  id: string
  source_type: 'synthetic' | 'permitted_research'
  source_name: string
  source_url: string | null
  published_at: string
  text: string
  language: string
  hashtags: string[]
  public_topic_ids: string[]
  author_reference: string | null
  interaction_reference_ids: string[]
  is_synthetic: boolean
  media: { file: string; alt_text: string }[]
}

export interface MediaObservation {
  file: string
  observation: string
  image_text: string
  visual_evidence: string
  engine: string
}

export interface HashMatch {
  entry_id: string
  label: string
  category: Category
  source: string
  distance: number
  low_quality?: boolean
}

export interface PostMedia {
  file: string
  url: string
  alt_text: string
  pdq: string | null
  quality: number | null
  hash_match: HashMatch | null
  near_duplicates: { post_id: string; file: string; distance: number }[]
  near_duplicate_count: number
}

export interface EvidenceSpan {
  start: number
  end: number
  text: string
  cue_category: Category | 'KEYWORD_SIGNAL'
  note: string
}

export interface Classification {
  post_id: string
  category: Category
  confidence: number
  evidence_spans: EvidenceSpan[]
  explanation: string
  signals: string[]
  model_name: string
  model_version: string
  category_scores: Record<string, number>
  media_observations: MediaObservation[]
  classified_at: string
  review_status: ReviewStatus
  review_priority: ReviewPriority
  reviewer_category: Category | null
  reviewer_note: string | null
  reviewed_at: string | null
}

export interface Topic {
  id: string
  label: string
  description: string
  is_synthetic: boolean
}

export interface PostWithClassification {
  post: Post
  classification: Classification
  topics: Topic[]
}

export interface PostPage {
  items: PostWithClassification[]
  total: number
  page: number
  page_size: number
}

export interface DatasetInfo {
  source_names: string[]
  is_synthetic: boolean
  synthetic_count: number
  total_posts: number
  period_start: string | null
  period_end: string | null
  ingested_at: string | null
  retention_days: number
}

export interface AuditEntry {
  id: number
  timestamp: string
  actor: string
  action: string
  post_id: string | null
  details: Record<string, unknown>
}

export interface DashboardSummary {
  total_posts: number
  by_category: Record<Category, number>
  by_model_category: Record<Category, number>
  by_review_status: Partial<Record<ReviewStatus, number>>
  pending_by_priority: Record<ReviewPriority, number>
  pending_review: number
  pending_review_pct: number
  urgent_threat_pending: number
  harmful_content_posts: number
  repeated_glorification_signal_posts: number
  confidence_histogram: { bucket: string; count: number }[]
  top_topics: { topic_id: string; label: string; count: number }[]
  confidence_note: string
  evaluation_false_positive_rate: number
  baseline_false_positive_rate: number
  evaluation_set_size: number
  dataset: DatasetInfo
}

export interface GraphNode {
  id: string
  type: 'POST' | 'HASHTAG' | 'TOPIC' | 'PUBLIC_COMMUNITY_REFERENCE'
  label: string
  category: Category | null
  weight: number
  provenance: string
  community: string | null
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  type: EdgeType
  weight: number
  method: string
  provenance: string
}

export interface Graph {
  nodes: GraphNode[]
  edges: GraphEdge[]
  disclaimer: string
  truncated: boolean
}

export interface TrendBucket {
  bucket_start: string
  total_posts: number
  unique_author_pseudonyms: number | null
  sufficient_sample: boolean
  categories: Partial<Record<Category, number>>
  topics: Record<string, number>
}

export interface EmergingTopic {
  topic_id: string
  label: string
  recent_count: number
  previous_count: number
  ratio: number
  meets_sample_threshold: boolean
  emerging: boolean
}

export interface Trends {
  granularity: 'day' | 'week'
  min_sample: number
  series: TrendBucket[]
  topics: Topic[]
  emerging_topics: {
    window_days: number
    min_recent_count: number
    min_ratio: number
    reference_end: string | null
    topics: EmergingTopic[]
  }
  caveat: string
  is_synthetic: boolean
}

export interface ClassMetrics {
  precision: number
  recall: number
  f1: number
  support: number
  predicted: number
}

export interface EvalExample {
  id: string
  text: string
  language: string
  gold: Category
  predicted: Category
  note: string
}

export interface ModelEvaluation {
  model: string
  n: number
  accuracy: number
  macro_f1: number
  per_class: Record<Category, ClassMetrics>
  confusion_matrix: { labels: Category[]; matrix: number[][] }
  harm_binary: {
    false_positive_rate: number
    false_positives: number
    non_harmful_items: number
    missed_harmful: number
    harmful_items: number
    harmful_routed_to_review: number
    harmful_recall: number
  }
  by_language: Record<string, { n: number; accuracy: number; macro_f1: number }>
  false_positive_examples: EvalExample[]
  false_negative_examples: EvalExample[]
  routed_to_review_examples: EvalExample[]
  usage?: { calls: number; input_tokens: number; output_tokens: number; cost_usd: number }
}

export interface Evaluation {
  dataset: { path: string; size: number; label_distribution: Record<string, number>; languages: Record<string, number> }
  contextual: ModelEvaluation
  baseline: ModelEvaluation
  muse: ModelEvaluation | null
  multimodal: MultimodalEval | null
  red_team: RedTeamResults | null
  learning: { examples: number; corrections: number; last_run: { timestamp: string; details: ReclassifySummary } | null }
  limitations: string[]
  reviewer_feedback: {
    reviewed: number
    agreement_rate: number | null
    corrections: { model_category: Category; reviewer_category: Category; count: number }[]
    note: string
  }
}

export interface PostFilters {
  category?: Category
  review_status?: ReviewStatus
  priority?: ReviewPriority
  topic_id?: string
  hashtag?: string
  date_from?: string
  date_to?: string
  min_confidence?: number
  max_confidence?: number
  language?: string
  search?: string
}

// ---- Sandbox platform & Sentinel missions ----
export interface SbUser { id: string; name: string; bio: string; avatar_color: string; is_persona?: boolean }

export interface SbGroup {
  id: string
  name: string
  privacy: 'public' | 'private' | 'secret'
  member_count: number
  description: string
  cover_color: string
  admin: SbUser
  protected_space: boolean
  join_questions: string[]
  viewer_is_member: boolean
  viewer_request_status: string | null
  can_read_feed: boolean
}

export interface SbComment { id: number; author: SbUser; created_at: string; text: string }
export interface SbPost {
  id: string
  group_id: string
  author: SbUser
  created_at: string
  text: string
  likes: number
  image: string | null
  image_alt: string | null
  pinned: boolean
  comments: SbComment[]
}
export interface SbMessage { id: number; from: SbUser; created_at: string; text: string; outgoing: boolean }
export interface SbThread { with: SbUser; messages: SbMessage[] }
export interface SbReport {
  id: number
  created_at: string
  mission_id: string | null
  group_id: string | null
  severity: string
  title: string
  status: string
  body: Record<string, any>
}

export interface MissionEvent {
  id: number
  ts: string
  phase: string
  actor: string
  kind: string
  title: string
  detail: Record<string, any>
  engine: string
}
export interface MissionApproval {
  id: number
  created_at: string
  kind: string
  title: string
  payload: Record<string, any>
  status: 'pending' | 'approved' | 'rejected'
  decided_by: string | null
}
export interface MuseUsage { calls: number; input_tokens: number; output_tokens: number; cost_usd: number; by_purpose: Record<string, number> }
export interface Mission {
  id: string
  created_at: string
  status: string
  mode: 'muse' | 'offline'
  brief: string
  auto_approve: string
  summary: Record<string, any>
  usage: Partial<MuseUsage>
  events: MissionEvent[]
  approvals: MissionApproval[]
}
export interface MuseStatus { enabled: boolean; base_url: string; fast_model: string; deep_model: string; image_model: string; default_brief: string }

export type RiskLevel = 'low' | 'moderate' | 'elevated' | 'high'

export interface Community {
  id: string
  title: string
  summary: string
  themes: string[]
  trajectory: string
  cited_post_ids: string[]
  uncertainties: string
  engine: string
  built_at: string
  post_ids: string[]
  risk: { final: RiskLevel; rules: RiskLevel; muse: RiskLevel | null; needs_human_check: boolean }
  stats: {
    size: number
    categories: Partial<Record<Category, number>>
    harmful_share: number
    threat_posts: number
    awaiting_review: number
    top_hashtags: string[]
    topics: string[]
    languages: Record<string, number>
    first_post: string
    last_post: string
    posts_last_14_days: number
    posts_prior_14_days: number
    images: number
    hashlist_matches: number
    link_types: Record<string, number>
  }
}

export interface AskResult {
  question: string
  refused: boolean
  engine: string
  answer: string | null
  cited_community_ids: string[]
  cited_post_ids: string[]
  confidence?: number | null
  caveats?: string
  unverified_citations?: string[]
  retrieved_posts: { post_id: string; score: number; community: string | null; category: Category; published_at: string; text: string }[]
  communities_considered: string[]
}

export interface SemanticResults {
  query: string
  model: string | null
  results: { score: number; item: PostWithClassification }[]
}

export interface ReclassifySummary {
  model: string
  reviewer_examples: number
  posts: number
  changed: number
  transitions: { from: Category; to: Category; count: number }[]
  reviewed_posts: number
  agreement_before: number | null
  agreement_after: number | null
  note: string
  usage?: { calls: number; cost_usd: number }
}

export interface RedTeamResults {
  set: { generated_at: string; generator: string; verified: boolean; note: string }
  size: number
  tactics: Record<string, { intended_label: Category; language: string; description: string }>
  classifiers: Record<string, {
    model: string
    evasion_rate: number | null
    false_alarm_rate: number | null
    by_tactic: Record<string, Partial<Record<'caught' | 'evaded' | 'routed_to_review' | 'false_alarm' | 'correct' | 'mislabelled', number>>>
    failures: { id: string; tactic: string; text: string; intended: Category; predicted: Category; outcome: string }[]
  }>
  evaluated_at: string
}

export interface MultimodalEval {
  size: number
  engines: Record<string, { label: string; accuracy: number; harmful_caught: number; harmful_routed_to_review: number;
    harmful_items: number; benign_flagged_harmful: number; benign_items: number }>
  items: { id: string; text: string; image: string; gold: Category; note: string; hash_match: boolean; predictions: Record<string, Category> }[]
  note: string
}
