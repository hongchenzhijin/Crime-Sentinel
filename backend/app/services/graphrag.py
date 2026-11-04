"""GraphRAG: community detection over the content graph, Muse community summaries, and cited Q&A.

1. Build a weighted graph of POSTS (never people): semantic similarity (embeddings), the same image re-shared
   (PDQ), shared distinctive hashtags, and public reply/quote links.
2. Split it into communities with Louvain modularity (networkx).
3. Describe each community with computed statistics, and have Muse write a title, summary, themes and trajectory
   citing post ids. A rule-based risk level is computed from the statistics; the higher of the two risk levels is
   shown, and a gap of two or more levels is flagged for a human (the same two-engine pattern as elsewhere).
4. Answer analyst questions with global context (all community summaries) plus local context (posts retrieved by
   semantic search). Citations are checked against what Muse was shown; anything else is dropped.

Communities are clusters of content, not groups of people, and the tool refuses questions about identities.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from itertools import combinations
from math import log

import networkx as nx
import numpy as np

from app.agent.muse import FAST_MODEL, MuseClient, MuseError
from app.db import repository as repo
from app.schemas.models import HARMFUL_CATEGORIES, Category, PostWithClassification
from app.services import embeddings, media
from app.services.graph import image_edges

RISK_LEVELS = ["low", "moderate", "elevated", "high"]
MIN_COMMUNITY_SIZE = 3
SEMANTIC_NEIGHBOURS = 5
GENERIC_HASHTAG_SHARE = 0.25  # hashtags on more than this share of posts say nothing about a community
HARMFUL = {c.value for c in HARMFUL_CATEGORIES}

SUMMARY_SYSTEM = """You summarise clusters of public social-media posts for a trust-and-safety analyst studying
online communities around violent attacks. A cluster is a group of related POSTS, not people. Describe the content
only: never speculate about authors, identities or locations, and never repeat operational detail.
Use the statistics given; do not invent numbers. Cite post ids only from the sample.
Respond with JSON only: {"title": "max 6 words", "summary": "2-3 sentences", "themes": ["max 4 short phrases"],
"risk_level": "low" | "moderate" | "elevated" | "high", "trajectory": "one sentence on change over time",
"cited_post_ids": [str], "uncertainties": "one sentence"}"""

ASK_SYSTEM = """You answer a trust-and-safety analyst's question about a dataset of public posts, using ONLY the
community summaries and retrieved posts provided. Communities are clusters of content, not groups of people.
Never identify, profile or speculate about individuals, and never provide operational detail. If the context does
not answer the question, say so. Cite community ids like [c03] and post ids like [post_0123] inline for every claim.
Respond with JSON only: {"answer": "concise answer with inline citations", "cited_community_ids": [str],
"cited_post_ids": [str], "confidence": number 0-1, "caveats": "one sentence"}"""

_IDENTITY_QUESTION = re.compile(
    r"\b(real names?|identit(y|ies)|who (is|are) (the )?(authors?|posters?|users?|accounts?|people|person)|"
    r"home address|where (does|do) .{0,30} live|dox+|phone number|unmask|de-?anonymi[sz]e)\b", re.I)


def _effective(item: PostWithClassification) -> str:
    return (item.classification.reviewer_category or item.classification.category).value


def build_post_graph(conn: sqlite3.Connection, items: list[PostWithClassification]) -> nx.Graph:
    g = nx.Graph()
    ids = [i.post.id for i in items]
    g.add_nodes_from(ids)

    def add(a: str, b: str, w: float, kind: str) -> None:
        if a == b:
            return
        if g.has_edge(a, b):
            g[a][b]["weight"] += w
            g[a][b]["kinds"].add(kind)
        else:
            g.add_edge(a, b, weight=w, kinds={kind})

    vec_ids, matrix, model = embeddings.load_embeddings(conn)
    if model:
        index = {pid: n for n, pid in enumerate(vec_ids)}
        rows = [index[p] for p in ids if p in index]
        present = [p for p in ids if p in index]
        if rows:
            m = matrix[rows]
            sims = m @ m.T
            threshold = embeddings.threshold_for(model)
            for a in range(len(present)):
                for b in np.argsort(-sims[a])[1:SEMANTIC_NEIGHBOURS + 1]:
                    if sims[a, b] >= threshold:
                        add(present[a], present[b], float(sims[a, b]), "semantic")

    for e in image_edges(ids, media.all_hashes(conn)):
        add(e.source, e.target, 1.5, "same_image")

    df = Counter(t for i in items for t in set(i.post.hashtags))
    by_tag: dict[str, list[str]] = {}
    for i in items:
        for t in i.post.hashtags:
            by_tag.setdefault(t, []).append(i.post.id)
    for tag, members in by_tag.items():
        if 2 <= df[tag] <= max(2, GENERIC_HASHTAG_SHARE * len(items)):
            w = 0.6 * log(len(items) / df[tag]) / log(len(items))
            for a, b in combinations(members, 2):
                add(a, b, w, "hashtag")

    known = set(ids)
    for i in items:
        for ref in i.post.interaction_reference_ids:
            if ref in known:
                add(i.post.id, ref, 0.8, "reply")
    return g


def _stats(members: list[PostWithClassification], g: nx.Graph, topics: dict, end) -> dict:
    cats = Counter(_effective(i) for i in members)
    harmful = sum(n for c, n in cats.items() if c in HARMFUL)
    dates = sorted(i.post.published_at for i in members)
    recent = sum(1 for d in dates if d > end - timedelta(days=14))
    prior = sum(1 for d in dates if end - timedelta(days=28) < d <= end - timedelta(days=14))
    tags = Counter(t for i in members for t in i.post.hashtags)
    tops = Counter(t for i in members for t in i.post.public_topic_ids)
    sub = g.subgraph([i.post.id for i in members])
    edge_kinds = Counter(k for _, _, d in sub.edges(data=True) for k in d["kinds"])
    return {
        "size": len(members),
        "categories": dict(cats.most_common()),
        "harmful_share": round(harmful / len(members), 3),
        "threat_posts": cats.get(Category.EXPLICIT_THREAT_OR_INTENT.value, 0),
        "awaiting_review": sum(1 for i in members if i.classification.review_status == "pending"),
        "top_hashtags": [t for t, _ in tags.most_common(5)],
        "topics": [topics[t].label for t, _ in tops.most_common(3) if t in topics],
        "languages": dict(Counter(i.post.language for i in members)),
        "first_post": dates[0].isoformat(), "last_post": dates[-1].isoformat(),
        "posts_last_14_days": recent, "posts_prior_14_days": prior,
        "images": sum(len(i.post.media) for i in members),
        "hashlist_matches": sum(1 for i in members if any(s.startswith("pdq_hashlist_match") for s in i.classification.signals)),
        "link_types": dict(edge_kinds),
    }


def rules_risk(stats: dict) -> str:
    if stats["threat_posts"] or stats["harmful_share"] >= 0.5:
        return "high"
    if stats["harmful_share"] >= 0.25 or stats["hashlist_matches"]:
        return "elevated"
    return "moderate" if stats["harmful_share"] > 0 else "low"


def _sample(members: list[PostWithClassification], g: nx.Graph, n: int = 10) -> list[PostWithClassification]:
    """Representative posts: harmful and high-degree first, so the summary sees what matters."""
    deg = dict(g.degree([i.post.id for i in members], weight="weight"))
    return sorted(members, key=lambda i: (_effective(i) not in HARMFUL, -deg.get(i.post.id, 0)))[:n]


def _offline_summary(stats: dict) -> dict:
    top = next(iter(stats["categories"]))
    label = top.replace("_", " ").lower()
    trend = stats["posts_last_14_days"] - stats["posts_prior_14_days"]
    return {
        "title": f"{label.capitalize()} cluster"[:60],
        "summary": f"{stats['size']} posts, mostly {label} ({stats['categories'][top]} posts). "
                   f"{stats['harmful_share']:.0%} are in harmful categories. Topics: {', '.join(stats['topics']) or 'none'}.",
        "themes": [f"#{t}" for t in stats["top_hashtags"][:4]],
        "risk_level": None,
        "trajectory": f"{stats['posts_last_14_days']} posts in the last 14 days vs {stats['posts_prior_14_days']} "
                      f"in the 14 days before ({'+' if trend >= 0 else ''}{trend}).",
        "cited_post_ids": [],
        "uncertainties": "Template summary (Muse offline): statistics only, no reading of the content.",
    }


def _muse_summary(muse: MuseClient, stats: dict, sample: list[PostWithClassification]) -> dict:
    lines = "\n".join(f"[{i.post.id}] ({_effective(i)}) {i.post.text[:240]}"
                      + (" [has image]" if i.post.media else "") for i in sample)
    r = muse.chat("graphrag_summary", SUMMARY_SYSTEM, f"Statistics:\n{json.dumps(stats)}\n\nSample posts:\n{lines}",
                  model=FAST_MODEL, reasoning_effort="low", max_tokens=600, temperature=0.2)
    d = r.data or {}
    allowed = {i.post.id for i in sample}
    return {
        "title": str(d.get("title", ""))[:60] or "Untitled cluster",
        "summary": str(d.get("summary", ""))[:600],
        "themes": [str(t)[:60] for t in (d.get("themes") or [])][:4],
        "risk_level": d.get("risk_level") if d.get("risk_level") in RISK_LEVELS else None,
        "trajectory": str(d.get("trajectory", ""))[:300],
        "cited_post_ids": [p for p in (d.get("cited_post_ids") or []) if p in allowed],
        "uncertainties": str(d.get("uncertainties", ""))[:300],
        "engine": f"muse:{r.model}",
    }


def build_communities(conn: sqlite3.Connection, muse: MuseClient | None = None, actor: str = "system") -> dict:
    muse = muse or MuseClient()
    items = repo.all_posts(conn)
    if not items:
        return {"communities": 0}
    by_id = {i.post.id: i for i in items}
    g = build_post_graph(conn, items)
    parts = nx.community.louvain_communities(g, weight="weight", resolution=1.0, seed=7)
    parts = sorted((sorted(p) for p in parts if len(p) >= MIN_COMMUNITY_SIZE), key=len, reverse=True)
    topics = repo.get_topics(conn)
    end = max(i.post.published_at for i in items)

    jobs = []
    for n, ids in enumerate(parts, 1):
        members = [by_id[p] for p in ids]
        stats = _stats(members, g, topics, end)
        jobs.append((f"c{n:02d}", ids, stats, _sample(members, g)))

    def describe(job):
        cid, ids, stats, sample = job
        summary = None
        if muse.enabled:
            try:
                summary = _muse_summary(muse, stats, sample)
            except MuseError:
                summary = None
        summary = summary or {**_offline_summary(stats), "engine": "template"}
        r_risk = rules_risk(stats)
        m_risk = summary.pop("risk_level")
        final = max([r_risk, m_risk] if m_risk else [r_risk], key=RISK_LEVELS.index)
        gap = abs(RISK_LEVELS.index(r_risk) - RISK_LEVELS.index(m_risk)) if m_risk else 0
        return cid, ids, {**summary, "id": cid, "stats": stats, "risk": {
            "final": final, "rules": r_risk, "muse": m_risk, "needs_human_check": gap >= 2}}

    with ThreadPoolExecutor(max_workers=6) as pool:
        described = list(pool.map(describe, jobs))

    conn.execute("DELETE FROM community_members")
    conn.execute("DELETE FROM communities")
    now = repo.utcnow().isoformat()
    for cid, ids, data in described:
        conn.execute("INSERT INTO communities (id, built_at, engine, size, data) VALUES (?, ?, ?, ?, ?)",
                     (cid, now, data["engine"], len(ids), json.dumps(data)))
        conn.executemany("INSERT INTO community_members (community_id, post_id) VALUES (?, ?)", [(cid, p) for p in ids])
    clustered = sum(len(ids) for _, ids, _ in described)
    summary = {"communities": len(described), "posts": len(items), "clustered_posts": clustered,
               "graph_edges": g.number_of_edges(), "algorithm": "louvain (networkx), seed 7",
               "summaries": "muse" if muse.enabled else "template", "usage": muse.ledger.as_dict()}
    repo.write_audit(conn, actor, "build_graphrag_communities", None, summary)
    conn.commit()
    return summary


def list_communities(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM communities ORDER BY size DESC").fetchall()
    members: dict[str, list[str]] = {}
    for r in conn.execute("SELECT community_id, post_id FROM community_members ORDER BY post_id"):
        members.setdefault(r["community_id"], []).append(r["post_id"])
    return [{**json.loads(r["data"]), "built_at": r["built_at"], "post_ids": members.get(r["id"], [])} for r in rows]


def membership(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["post_id"]: r["community_id"] for r in conn.execute("SELECT * FROM community_members")}


def ask(conn: sqlite3.Connection, question: str, muse: MuseClient | None = None, actor: str = "demo_reviewer",
        k: int = 12) -> dict:
    muse = muse or MuseClient()
    question = question.strip()
    repo.write_audit(conn, actor, "graphrag_question", None, {"question": question[:500]})
    conn.commit()
    if _IDENTITY_QUESTION.search(question):
        return {"question": question, "refused": True, "engine": "policy",
                "answer": "This tool analyses content, not people. It does not identify, profile or locate anyone, "
                          "so it cannot answer questions about identities.",
                "cited_community_ids": [], "cited_post_ids": [], "retrieved_posts": [], "communities_considered": []}

    communities = list_communities(conn)
    member_of = membership(conn)
    hits = embeddings.semantic_search(conn, question, k)
    retrieved = []
    for pid, score in hits:
        item = repo.get_post(conn, pid)
        if item:
            retrieved.append({"post_id": pid, "score": score, "community": member_of.get(pid),
                              "category": _effective(item), "published_at": item.post.published_at.isoformat(),
                              "text": item.post.text[:240]})
    base = {"question": question, "refused": False, "retrieved_posts": retrieved,
            "communities_considered": [c["id"] for c in communities]}
    if not muse.enabled:
        return {**base, "engine": "retrieval-only", "answer": None, "cited_community_ids": [], "cited_post_ids": [],
                "confidence": None, "caveats": "Muse is not configured: showing retrieved posts and communities only."}

    context = "\n".join(
        f"[{c['id']}] {c['title']} | risk {c['risk']['final']} | {c['stats']['size']} posts | "
        f"categories {c['stats']['categories']} | hashtags {c['stats']['top_hashtags']} | "
        f"last 14d {c['stats']['posts_last_14_days']} vs prior {c['stats']['posts_prior_14_days']}\n"
        f"   {c['summary']} Trajectory: {c['trajectory']}" for c in communities)
    posts = "\n".join(f"[{p['post_id']}] (community {p['community'] or 'none'}, {p['category']}, "
                      f"{p['published_at'][:10]}, similarity {p['score']}) {p['text']}" for p in retrieved)
    try:
        r = muse.chat("graphrag_ask", ASK_SYSTEM,
                      f"Question: {question}\n\nCommunity summaries:\n{context}\n\nRetrieved posts:\n{posts}",
                      model=FAST_MODEL, reasoning_effort="low", max_tokens=900, temperature=0.1)
    except MuseError as exc:
        return {**base, "engine": "retrieval-only", "answer": None, "cited_community_ids": [], "cited_post_ids": [],
                "confidence": None, "caveats": f"Muse call failed ({exc}); showing retrieval results only."}
    d = r.data or {}
    known_c = {c["id"] for c in communities}
    known_p = {p["post_id"] for p in retrieved} | {pid for c in communities for pid in c["cited_post_ids"]}
    answer = str(d.get("answer", ""))[:2000]
    cited_c = sorted(set(c for c in (d.get("cited_community_ids") or []) if c in known_c)
                     | {m for m in re.findall(r"\[(c\d+)\]", answer) if m in known_c})
    cited_p = sorted(set(p for p in (d.get("cited_post_ids") or []) if p in known_p)
                     | {m for m in re.findall(r"\[(post_[\w-]+)\]", answer) if m in known_p})
    dropped = [m for m in re.findall(r"\[((?:c\d+)|(?:post_[\w-]+))\]", answer) if m not in known_c | known_p]
    caveats = str(d.get("caveats", ""))[:300]
    if dropped:
        caveats += f" Removed {len(dropped)} citation(s) to items Muse was not shown."
    return {**base, "engine": f"muse:{r.model}", "answer": answer, "cited_community_ids": cited_c,
            "cited_post_ids": cited_p, "confidence": d.get("confidence"), "caveats": caveats.strip(),
            "unverified_citations": dropped, "usage": muse.ledger.as_dict()}
