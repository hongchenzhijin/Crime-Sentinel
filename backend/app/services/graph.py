"""Content/topic graph construction.

Nodes are posts, hashtags, and topics - never people. Every edge records the
method that created it, because a shared hashtag or similar wording is not
evidence of membership, coordination, endorsement, or intent.
"""

from __future__ import annotations

import re
from itertools import combinations

import numpy as np

from app.schemas.models import Graph, GraphEdge, GraphNode, PostWithClassification, Topic
from app.services.media import MATCH_THRESHOLD, hamming

DISCLAIMER = (
    "Connections indicate observed content relationships in this dataset; "
    "they do not establish membership, coordination, or intent."
)
EDGE_TYPES = ("USES_HASHTAG", "MENTIONS_TOPIC", "SIMILAR_CONTENT", "PUBLICLY_LINKED_TO", "SHARES_IMAGE")
SIMILARITY_THRESHOLD = 0.3
MAX_SIMILAR_PER_POST = 2

_STOPWORDS = set(
    "the a an and or but if of to in on at for with about this that these those is are was were be been it its "
    "he she they them his her their i im i'm you your we our me my so just not no yes do did does have has had "
    "what who why how when where there here than then from into out up down over again very can will would "
    "should could all any some one more most other such only own same too also like get got really still".split()
)
_TOKEN = re.compile(r"[a-z][a-z']{2,}")


def _tokens(text: str) -> frozenset[str]:
    return frozenset(t for t in _TOKEN.findall(re.sub(r"#\w+", " ", text.lower())) if t not in _STOPWORDS)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def build_graph(
    items: list[PostWithClassification],
    topics: dict[str, Topic],
    edge_types: set[str] | None = None,
    max_posts: int = 200,
    vectors: dict[str, np.ndarray] | None = None,
    vector_model: str | None = None,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    image_hashes: dict[str, list[tuple[str, str]]] | None = None,
    communities: dict[str, str] | None = None,
) -> Graph:
    edge_types = edge_types or set(EDGE_TYPES)
    truncated = len(items) > max_posts
    if truncated:
        items = sorted(items, key=lambda i: i.post.published_at, reverse=True)[:max_posts]

    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    post_ids = {i.post.id for i in items}

    for item in items:
        p, c = item.post, item.classification
        nodes[p.id] = GraphNode(
            id=p.id,
            type="POST",
            label=p.id,
            category=c.reviewer_category or c.category,
            provenance=f"Post record from '{p.source_name}'" + (" (synthetic)" if p.is_synthetic else ""),
            community=(communities or {}).get(p.id),
        )
        if "USES_HASHTAG" in edge_types:
            for tag in p.hashtags:
                nid = f"hashtag:{tag}"
                node = nodes.setdefault(nid, GraphNode(
                    id=nid, type="HASHTAG", label=f"#{tag}", weight=0,
                    provenance="Hashtag listed in public post metadata",
                ))
                node.weight += 1
                edges.append(GraphEdge(
                    id=f"{p.id}->{nid}", source=p.id, target=nid, type="USES_HASHTAG",
                    method="metadata:hashtags",
                    provenance=f"Post {p.id} lists #{tag} in its public hashtags.",
                ))
        if "MENTIONS_TOPIC" in edge_types:
            for tid in p.public_topic_ids:
                nid = f"topic:{tid}"
                label = topics[tid].label if tid in topics else tid
                node = nodes.setdefault(nid, GraphNode(
                    id=nid, type="TOPIC", label=label, weight=0,
                    provenance="Topic defined in the dataset's topic list",
                ))
                node.weight += 1
                edges.append(GraphEdge(
                    id=f"{p.id}->{nid}", source=p.id, target=nid, type="MENTIONS_TOPIC",
                    method="metadata:public_topic_ids",
                    provenance=f"Post {p.id} is tagged with topic '{label}' in the dataset metadata.",
                ))
        if "PUBLICLY_LINKED_TO" in edge_types:
            for ref in p.interaction_reference_ids:
                if ref in post_ids:
                    edges.append(GraphEdge(
                        id=f"{p.id}->{ref}", source=p.id, target=ref, type="PUBLICLY_LINKED_TO",
                        method="metadata:interaction_reference_ids",
                        provenance=f"Post {p.id} publicly replies to or quotes post {ref}. "
                                   "A reply or quote is not endorsement.",
                    ))

    if "SIMILAR_CONTENT" in edge_types:
        if vectors and all(i.post.id in vectors for i in items):
            edges.extend(_semantic_edges(items, vectors, vector_model or "embedding", similarity_threshold))
        else:
            edges.extend(_similarity_edges(items))
    if "SHARES_IMAGE" in edge_types and image_hashes:
        edges.extend(image_edges([i.post.id for i in items], image_hashes))

    return Graph(nodes=list(nodes.values()), edges=edges, disclaimer=DISCLAIMER, truncated=truncated)


def _similarity_edges(items: list[PostWithClassification]) -> list[GraphEdge]:
    toks = {i.post.id: _tokens(i.post.text) for i in items}
    candidates: dict[str, list[tuple[float, str]]] = {pid: [] for pid in toks}
    for a, b in combinations(toks, 2):
        s = jaccard(toks[a], toks[b])
        if s >= SIMILARITY_THRESHOLD:
            candidates[a].append((s, b))
            candidates[b].append((s, a))
    seen: set[tuple[str, str]] = set()
    edges = []
    for pid, cands in candidates.items():
        for score, other in sorted(cands, reverse=True)[:MAX_SIMILAR_PER_POST]:
            key = tuple(sorted((pid, other)))
            if key in seen:
                continue
            seen.add(key)
            edges.append(GraphEdge(
                id=f"sim:{key[0]}:{key[1]}", source=key[0], target=key[1], type="SIMILAR_CONTENT",
                weight=round(score, 3), method="jaccard_word_overlap",
                provenance=f"Word-overlap (Jaccard) similarity {score:.2f} >= threshold {SIMILARITY_THRESHOLD}. "
                           "Similar wording is not evidence of coordination.",
            ))
    return edges


def _top_pairs(candidates: dict[str, list[tuple[float, str]]]) -> list[tuple[float, str, str]]:
    seen: set[tuple[str, str]] = set()
    out = []
    for pid, cands in candidates.items():
        for score, other in sorted(cands, reverse=True)[:MAX_SIMILAR_PER_POST]:
            key = tuple(sorted((pid, other)))
            if key not in seen:
                seen.add(key)
                out.append((score, key[0], key[1]))
    return out


def _semantic_edges(items: list[PostWithClassification], vectors: dict[str, np.ndarray], model: str,
                    threshold: float) -> list[GraphEdge]:
    ids = [i.post.id for i in items]
    m = np.stack([vectors[pid] for pid in ids])
    sims = m @ m.T
    candidates: dict[str, list[tuple[float, str]]] = {pid: [] for pid in ids}
    for a in range(len(ids)):
        for b in np.nonzero(sims[a] >= threshold)[0]:
            if b != a:
                candidates[ids[a]].append((float(sims[a, b]), ids[b]))
    return [GraphEdge(
        id=f"sim:{a}:{b}", source=a, target=b, type="SIMILAR_CONTENT", weight=round(score, 3),
        method=f"semantic_embedding:{model}",
        provenance=f"Cosine similarity of {model} sentence embeddings {score:.2f} >= threshold {threshold}. "
                   "Similar meaning is not evidence of coordination.",
    ) for score, a, b in _top_pairs(candidates)]


def image_edges(post_ids: list[str], image_hashes: dict[str, list[tuple[str, str]]]) -> list[GraphEdge]:
    """Edges between posts whose images are PDQ near-duplicates (the same picture re-shared)."""
    hashed = [(pid, h, f) for pid in post_ids for h, f in image_hashes.get(pid, [])]
    best: dict[tuple[str, str], tuple[int, str, str]] = {}
    for i, (pa, ha, fa) in enumerate(hashed):
        for pb, hb, fb in hashed[i + 1:]:
            if pa == pb:
                continue
            d = hamming(ha, hb)
            key = tuple(sorted((pa, pb)))
            if d <= MATCH_THRESHOLD and (key not in best or d < best[key][0]):
                best[key] = (d, fa, fb)
    return [GraphEdge(
        id=f"img:{a}:{b}", source=a, target=b, type="SHARES_IMAGE", weight=round(1 - d / 256, 3),
        method="pdq_perceptual_hash",
        provenance=f"Attached images are perceptual near-duplicates ({fa} / {fb}, PDQ Hamming distance {d}/256 "
                   f"<= {MATCH_THRESHOLD}). Re-sharing an image is not evidence of coordination.",
    ) for (a, b), (d, fa, fb) in best.items()]
