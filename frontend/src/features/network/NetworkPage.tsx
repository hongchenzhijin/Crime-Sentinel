import cytoscape, { type Core } from 'cytoscape'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Nav } from '../../App'
import { FilterBar } from '../../components/FilterBar'
import { Card, CategoryBadge, Empty, ErrorBox, Loading, Notice } from '../../components/ui'
import { api } from '../../lib/api'
import { CATEGORY_META, communityColor } from '../../lib/categories'
import { CATEGORIES, type EdgeType, type Graph, type GraphEdge, type GraphNode, type PostFilters, type Topic } from '../../lib/types'
import { useAsync } from '../../lib/useAsync'

const EDGE_META: Record<EdgeType, { label: string; desc: string; style: 'solid' | 'dashed' | 'dotted'; color: string }> = {
  MENTIONS_TOPIC: { label: 'Mentions topic', desc: 'Post tagged with a dataset topic', style: 'solid', color: '#94a3b8' },
  USES_HASHTAG: { label: 'Uses hashtag', desc: 'Post lists the hashtag publicly', style: 'solid', color: '#cbd5e1' },
  SIMILAR_CONTENT: { label: 'Similar meaning', desc: 'Multilingual sentence-embedding similarity above threshold', style: 'dashed', color: '#4f46e5' },
  SHARES_IMAGE: { label: 'Same image', desc: 'Attached images are PDQ perceptual near-duplicates', style: 'solid', color: '#d04a6a' },
  PUBLICLY_LINKED_TO: { label: 'Public reply/quote', desc: 'Post publicly replies to or quotes another', style: 'dotted', color: '#0f172a' },
}
const ALL_EDGES = Object.keys(EDGE_META) as EdgeType[]

type Selection = { kind: 'node'; node: GraphNode; degree: number } | { kind: 'edge'; edge: GraphEdge }

export function NetworkPage({ filters, setFilters, topics, nav }: {
  filters: PostFilters
  setFilters: (f: PostFilters) => void
  topics: Topic[]
  nav: Nav
}) {
  const [edgeTypes, setEdgeTypes] = useState<EdgeType[]>(['MENTIONS_TOPIC', 'USES_HASHTAG', 'PUBLICLY_LINKED_TO'])
  const graph = useAsync(() => api.network(filters, edgeTypes), [JSON.stringify(filters), edgeTypes.join()])
  const [selection, setSelection] = useState<Selection>()
  const [colorBy, setColorBy] = useState<'category' | 'community'>('category')

  const toggle = (t: EdgeType) =>
    setEdgeTypes((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]))

  return (
    <div className="space-y-3">
      <div className="z-10 rounded-xl border border-ink/15 bg-white/90 px-4 py-2.5 text-sm font-medium shadow-card backdrop-blur lg:sticky lg:top-[72px]" role="note">
        Connections indicate observed content relationships in this dataset; they do not establish membership,
        coordination, or intent.
      </div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <FilterBar value={filters} onChange={setFilters} topics={topics} fields={['category', 'topic', 'dates']} />
        <fieldset className="flex flex-wrap gap-3 text-xs">
          <legend className="mb-0.5 text-[11px] text-ink-2">Edge types</legend>
          {ALL_EDGES.map((t) => (
            <label key={t} className="flex items-center gap-1" title={EDGE_META[t].desc}>
              <input type="checkbox" checked={edgeTypes.includes(t)} onChange={() => toggle(t)} />
              <svg width="22" height="6" aria-hidden>
                <line x1="0" y1="3" x2="22" y2="3" stroke={EDGE_META[t].color} strokeWidth="2"
                  strokeDasharray={EDGE_META[t].style === 'dashed' ? '5 3' : EDGE_META[t].style === 'dotted' ? '1.5 2.5' : undefined} />
              </svg>
              {EDGE_META[t].label}
            </label>
          ))}
        </fieldset>
        <label className="flex items-center gap-1 text-xs">
          Colour posts by
          <select value={colorBy} onChange={(e) => setColorBy(e.target.value as 'category' | 'community')}
            className="rounded-lg border border-line bg-white px-2 py-1">
            <option value="category">category</option>
            <option value="community">GraphRAG community</option>
          </select>
        </label>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Card className="relative p-0">
          {graph.error && <div className="p-3"><ErrorBox error={graph.error} onRetry={graph.reload} /></div>}
          {graph.loading && !graph.data && <Loading label="Building graph…" />}
          {graph.data && graph.data.nodes.length === 0 && <Empty>No posts match these filters.</Empty>}
          {graph.data && graph.data.nodes.length > 0 && <CytoGraph graph={graph.data} onSelect={setSelection} colorBy={colorBy} />}
          {graph.data?.truncated && (
            <p className="absolute bottom-2 left-3 text-[11px] text-ink-3">Showing the most recent posts only; narrow filters to see more.</p>
          )}
        </Card>

        <div className="space-y-3">
          <Inspector selection={selection} nav={nav} setFilters={setFilters} />
          {colorBy === 'community' ? <CommunityLegend graph={graph.data} nav={nav} /> : <Legend graph={graph.data} />}
        </div>
      </div>
    </div>
  )
}


function CytoGraph({ graph, onSelect, colorBy }: { graph: Graph; onSelect: (s?: Selection) => void; colorBy: 'category' | 'community' }) {
  const ref = useRef<HTMLDivElement>(null)
  const cy = useRef<Core>(null)
  const nodeById = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph])
  const edgeById = useMemo(() => new Map(graph.edges.map((e) => [e.id, e])), [graph])

  useEffect(() => {
    if (!ref.current) return
    const instance = cytoscape({
      container: ref.current,
      elements: [
        ...graph.nodes.map((n) => ({
          data: {
            id: n.id,
            label: n.type === 'POST' ? '' : n.label,
            type: n.type,
            color: n.type === 'POST'
              ? (colorBy === 'community' ? communityColor(n.community) : n.category ? CATEGORY_META[n.category].color : '#94a3b8')
              : n.type === 'TOPIC' ? '#0f172a' : '#94a3b8',
            size: n.type === 'POST' ? 12 : Math.min(48, 18 + Math.sqrt(n.weight) * 4),
          },
        })),
        ...graph.edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target, type: e.type } })),
      ],
      style: [
        {
          selector: 'node',
          style: {
            'background-color': 'data(color)', width: 'data(size)', height: 'data(size)',
            'border-width': 2, 'border-color': '#ffffff', label: 'data(label)', 'font-size': 10, color: '#0f172a',
            'text-valign': 'bottom', 'text-margin-y': 3, 'text-background-color': '#ffffff',
            'text-background-opacity': 0.85, 'text-background-padding': '1px',
          },
        },
        { selector: 'node[type = "TOPIC"]', style: { shape: 'round-rectangle', 'font-weight': 'bold', 'font-size': 11 } },
        { selector: 'node[type = "HASHTAG"]', style: { shape: 'diamond', color: '#64748b' } },
        { selector: 'edge', style: { width: 1, 'line-color': '#cbd5e1', 'curve-style': 'haystack', opacity: 0.7 } },
        ...ALL_EDGES.map((t) => ({
          selector: `edge[type = "${t}"]`,
          style: {
            'line-color': EDGE_META[t].color, 'line-style': EDGE_META[t].style,
            ...(t === 'SIMILAR_CONTENT' || t === 'PUBLICLY_LINKED_TO' || t === 'SHARES_IMAGE' ? { width: 1.5, 'curve-style': 'bezier', opacity: 0.9 } : {}),
            ...(t === 'SHARES_IMAGE' ? { width: 2.5 } : {}),
            ...(t === 'PUBLICLY_LINKED_TO' ? { 'target-arrow-shape': 'triangle', 'target-arrow-color': '#0f172a', 'arrow-scale': 0.6 } : {}),
          },
        })),
        { selector: ':selected', style: { 'border-color': '#0f172a', 'border-width': 3, 'line-color': '#0f172a', opacity: 1 } },
        { selector: '.faded', style: { opacity: 0.12 } },
      ] as cytoscape.StylesheetJson,
      layout: { name: 'cose', animate: false, nodeRepulsion: () => 9000, idealEdgeLength: () => 60, randomize: true, componentSpacing: 60 } as cytoscape.LayoutOptions,
      wheelSensitivity: 0.3,
    })
    instance.on('tap', 'node', (evt) => {
      const n = nodeById.get(evt.target.id())
      if (!n) return
      instance.elements().addClass('faded')
      evt.target.closedNeighborhood().removeClass('faded')
      onSelect({ kind: 'node', node: n, degree: evt.target.degree(false) })
    })
    instance.on('tap', 'edge', (evt) => {
      const e = edgeById.get(evt.target.id())
      if (e) onSelect({ kind: 'edge', edge: e })
    })
    instance.on('tap', (evt) => {
      if (evt.target === instance) {
        instance.elements().removeClass('faded')
        onSelect(undefined)
      }
    })
    cy.current = instance
    return () => instance.destroy()
  }, [graph, nodeById, edgeById, onSelect, colorBy])

  return (
    <div className="relative">
      <div ref={ref} className="h-[620px] w-full" data-testid="network-canvas" />
      <button className="absolute top-2 right-2 rounded border border-line bg-white px-2 py-1 text-xs hover:bg-line/40" onClick={() => cy.current?.fit(undefined, 20)}>
        Fit
      </button>
    </div>
  )
}

function Inspector({ selection, nav, setFilters }: { selection?: Selection; nav: Nav; setFilters: (f: PostFilters) => void }) {
  if (!selection) {
    return (
      <Card title="Inspector">
        <p className="text-xs text-ink-2">Click a node or edge to see what it is and how the connection was created.</p>
      </Card>
    )
  }
  if (selection.kind === 'edge') {
    const e = selection.edge
    return (
      <Card title={EDGE_META[e.type].label} subtitle={`${e.source} → ${e.target}`}>
        <dl className="space-y-1 text-xs">
          <dt className="text-ink-2">Method</dt><dd><code>{e.method}</code>{(e.type === 'SIMILAR_CONTENT' || e.type === 'SHARES_IMAGE') && ` (score ${e.weight})`}</dd>
          <dt className="text-ink-2">Provenance</dt><dd>{e.provenance}</dd>
        </dl>
      </Card>
    )
  }
  const n = selection.node
  return (
    <Card title={n.label} subtitle={n.type.replace('_', ' ').toLowerCase()}>
      <div className="space-y-2 text-xs">
        {n.category && <CategoryBadge category={n.category} />}
        {n.community && (
          <button className="ml-2 inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 hover:bg-line/40"
            onClick={() => nav.goto('intelligence', { communityId: n.community ?? undefined })}>
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: communityColor(n.community) }} />
            community {n.community}
          </button>
        )}
        <p className="text-ink-2">{n.provenance}.</p>
        <p>{selection.degree} connection(s) in the current view{n.type !== 'POST' && `; used by ${n.weight} post(s) in this dataset`}.</p>
        {n.type === 'POST' && (
          <button className="rounded-lg bg-accent shadow-sm shadow-accent/20 px-3 py-1.5 font-medium text-white" onClick={() => nav.goto('review', { postId: n.id })}>
            Open evidence panel
          </button>
        )}
        {n.type === 'HASHTAG' && (
          <button className="rounded-lg bg-accent shadow-sm shadow-accent/20 px-3 py-1.5 font-medium text-white"
            onClick={() => nav.goto('review', { filters: { hashtag: n.id.replace('hashtag:', '') }, postId: '' })}>
            Inspect posts using {n.label}
          </button>
        )}
        {n.type === 'TOPIC' && (
          <div className="flex flex-wrap gap-2">
            <button className="rounded-lg bg-accent shadow-sm shadow-accent/20 px-3 py-1.5 font-medium text-white" onClick={() => setFilters({ topic_id: n.id.replace('topic:', '') })}>
              Filter graph to topic
            </button>
            <button className="rounded-lg border border-line bg-white px-3 py-1.5 font-medium"
              onClick={() => nav.goto('review', { filters: { topic_id: n.id.replace('topic:', '') }, postId: '' })}>
              Open posts
            </button>
          </div>
        )}
        <Notice tone="caution">A shared hashtag, topic, or similar wording is not proof of membership, coordination, endorsement, or intent.</Notice>
      </div>
    </Card>
  )
}

function Legend({ graph }: { graph?: Graph }) {
  const counts = new Map<string, number>()
  graph?.nodes.forEach((n) => n.category && counts.set(n.category, (counts.get(n.category) ?? 0) + 1))
  return (
    <Card title="Legend">
      <ul className="space-y-1 text-xs">
        <li className="flex items-center gap-2"><span className="inline-block h-3 w-4 rounded-sm bg-ink" /> Topic (size = posts)</li>
        <li className="flex items-center gap-2"><span className="inline-block h-3 w-3 rotate-45 bg-[#94a3b8]" /> Hashtag (size = posts)</li>
        <li className="mt-1 text-ink-2">Posts (circles), coloured by current category:</li>
        {CATEGORIES.map((c) => (
          <li key={c} className="flex items-center justify-between">
            <span className="flex items-center gap-2"><span className="h-3 w-3 rounded-full" style={{ background: CATEGORY_META[c].color }} />{CATEGORY_META[c].label}</span>
            <span className="tabular text-ink-3">{counts.get(c) ?? 0}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] text-ink-3">No nodes represent people. Author pseudonyms are never drawn.</p>
    </Card>
  )
}

function CommunityLegend({ graph, nav }: { graph?: Graph; nav: Nav }) {
  const counts = new Map<string, number>()
  graph?.nodes.forEach((n) => n.type === 'POST' && counts.set(n.community ?? '', (counts.get(n.community ?? '') ?? 0) + 1))
  const ids = [...counts.keys()].filter(Boolean).sort()
  return (
    <Card title="Legend - GraphRAG communities">
      {ids.length === 0 && <p className="text-xs text-ink-2">No communities built yet. Build them on the Intelligence tab.</p>}
      <ul className="space-y-1 text-xs">
        {ids.map((c) => (
          <li key={c} className="flex items-center justify-between">
            <button className="flex items-center gap-2 hover:underline" onClick={() => nav.goto('intelligence', { communityId: c })}>
              <span className="h-3 w-3 rounded-full" style={{ background: communityColor(c) }} />community {c}
            </button>
            <span className="tabular text-ink-3">{counts.get(c)}</span>
          </li>
        ))}
        {counts.get('') ? <li className="flex justify-between text-ink-3"><span>not clustered</span><span>{counts.get('')}</span></li> : null}
      </ul>
      <p className="mt-2 text-[11px] text-ink-3">Communities are clusters of related posts (Louvain over meaning, shared images, distinctive hashtags and replies), never groups of people.</p>
    </Card>
  )
}
