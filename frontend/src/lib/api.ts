import type {
  AskResult,
  AuditEntry,
  Community,
  PostMedia,
  ReclassifySummary,
  SemanticResults,
  Category,
  DashboardSummary,
  DatasetInfo,
  EdgeType,
  Mission,
  MuseStatus,
  SbGroup,
  SbPost,
  SbReport,
  SbThread,
  SbUser,
  Evaluation,
  Graph,
  PostFilters,
  PostPage,
  PostWithClassification,
  ReviewAction,
  Topic,
  Trends,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type Params = Record<string, string | number | undefined | string[]>

export function toQuery(params: Params): string {
  const q = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '') continue
    if (Array.isArray(value)) value.forEach((v) => q.append(key, v))
    else q.set(key, String(value))
  }
  const s = q.toString()
  return s ? `?${s}` : ''
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* keep status text */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

const filterParams = (f: PostFilters): Params => ({ ...f })

export const api = {
  health: () => request<{ status: string; posts_loaded: number }>('/health'),
  dataset: () => request<DatasetInfo>('/dataset'),
  topics: () => request<Topic[]>('/topics'),
  summary: (f: PostFilters = {}) => request<DashboardSummary>(`/dashboard/summary${toQuery(filterParams(f))}`),
  posts: (f: PostFilters, page = 1, pageSize = 20, sort = 'priority') =>
    request<PostPage>(`/posts${toQuery({ ...filterParams(f), page, page_size: pageSize, sort })}`),
  post: (id: string) => request<PostWithClassification>(`/posts/${encodeURIComponent(id)}`),
  postAudit: (id: string) => request<AuditEntry[]>(`/posts/${encodeURIComponent(id)}/audit`),
  review: (id: string, body: { action: ReviewAction; reviewer_category?: Category; note?: string; reviewer: string }) =>
    request<PostWithClassification>(`/posts/${encodeURIComponent(id)}/review`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  network: (f: PostFilters, edgeTypes: EdgeType[]) =>
    request<Graph>(`/network${toQuery({ ...filterParams(f), edge_types: edgeTypes })}`),
  trends: (f: PostFilters, granularity: 'day' | 'week') =>
    request<Trends>(`/trends${toQuery({ ...filterParams(f), granularity })}`),
  evaluation: () => request<Evaluation>('/evaluation'),
  audit: (limit = 100) => request<AuditEntry[]>(`/audit?limit=${limit}`),
  exportReport: (reviewer: string) => request<Record<string, unknown>>(`/export/report${toQuery({ reviewer })}`),
  postMedia: (id: string) => request<PostMedia[]>(`/posts/${encodeURIComponent(id)}/media`),
  semanticSearch: (q: string, k = 10) => request<SemanticResults>(`/search/semantic${toQuery({ q, k })}`),
  communities: () => request<Community[]>('/graphrag/communities'),
  buildCommunities: (reviewer: string) =>
    request<{ communities: number; clustered_posts: number }>('/graphrag/build', { method: 'POST', body: JSON.stringify({ reviewer }) }),
  ask: (question: string, reviewer: string) =>
    request<AskResult>('/graphrag/ask', { method: 'POST', body: JSON.stringify({ question, reviewer }) }),
  reclassify: (reviewer: string) =>
    request<ReclassifySummary>('/learning/reclassify', { method: 'POST', body: JSON.stringify({ reviewer }) }),
}


export const sandboxApi = {
  users: () => request<SbUser[]>('/sandbox/users'),
  groups: (viewer: string, q = '') => request<SbGroup[]>(`/sandbox/groups${toQuery({ viewer, q })}`),
  group: (id: string, viewer: string) => request<SbGroup>(`/sandbox/groups/${id}${toQuery({ viewer })}`),
  feed: (id: string, viewer: string) => request<SbPost[]>(`/sandbox/groups/${id}/feed${toQuery({ viewer })}`),
  messages: (viewer: string) => request<SbThread[]>(`/sandbox/messages${toQuery({ viewer })}`),
  reports: () => request<SbReport[]>('/sandbox/reports'),
  reset: () => request<{ status: string }>('/sandbox/reset', { method: 'POST' }),
}

export const missionApi = {
  status: () => request<MuseStatus>('/muse/status'),
  start: (body: { brief: string; auto_approve: string; pace: number }) =>
    request<{ id: string }>('/missions', { method: 'POST', body: JSON.stringify(body) }),
  list: () => request<{ id: string; created_at: string; status: string; mode: string }[]>('/missions'),
  get: (id: string, after = 0) => request<Mission>(`/missions/${id}?after=${after}`),
  stop: (id: string) => request<{ stopped: boolean }>(`/missions/${id}/stop`, { method: 'POST' }),
  decide: (approvalId: number, body: { approve: boolean; reviewer: string; note?: string; edited_text?: string }) =>
    request<{ status: string }>(`/approvals/${approvalId}`, { method: 'POST', body: JSON.stringify(body) }),
}

export const sandboxJoin = (groupId: string, viewer: string, answers: string[]) =>
  request<{ status: string; note?: string }>(`/sandbox/groups/${groupId}/join`, {
    method: 'POST',
    body: JSON.stringify({ viewer, answers }),
  })
