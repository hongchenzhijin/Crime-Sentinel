"""Text embeddings for semantic similarity, semantic search and GraphRAG retrieval.

Meta's Model API has no embeddings model, so embeddings run locally with fastembed (ONNX, no GPU, no data leaves
the machine). The default model is multilingual, so a Bahasa Malaysia post sits next to its English equivalent.
If fastembed or the model is unavailable, a hashed bag-of-words embedder keeps everything working; the model
name is recorded with every vector so the UI can say which one produced a similarity.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
import zlib
from functools import lru_cache

import numpy as np

from app import config

log = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z0-9][a-z0-9']+")


class HashingEmbedder:
    """Offline fallback: L2-normalised hashed unigrams + bigrams. Captures wording, not meaning."""

    name = "hashed-bow-1024"
    similarity_threshold = 0.45
    dim = 1024

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            toks = _TOKEN.findall(re.sub(r"#\w+", " ", text.lower()))
            for t in toks + [f"{a} {b}" for a, b in zip(toks, toks[1:])]:
                h = zlib.crc32(t.encode())
                out[i, h % self.dim] += 1.0 if (h >> 16) & 1 else -1.0
        return _normalise(out)


class FastEmbedEmbedder:
    """Sentence embeddings with fastembed (multilingual MiniLM by default, 384 dimensions)."""

    similarity_threshold = 0.72

    def __init__(self, model: str = config.EMBEDDINGS_MODEL):
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model, cache_dir=str(config.EMBEDDINGS_CACHE))
        self._lock = threading.Lock()
        self.name = f"fastembed:{model.split('/')[-1]}"

    def embed(self, texts: list[str]) -> np.ndarray:
        with self._lock:
            return _normalise(np.asarray(list(self._model.embed(texts)), dtype=np.float32))


def _normalise(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms == 0, 1, norms)


@lru_cache(maxsize=1)
def get_embedder() -> HashingEmbedder | FastEmbedEmbedder:
    if config.EMBEDDINGS_MODE != "hash":
        try:
            return FastEmbedEmbedder()
        except Exception as exc:  # noqa: BLE001 - any failure (no package, no network) falls back
            log.warning("fastembed unavailable (%s); using hashed bag-of-words embeddings", exc)
    return HashingEmbedder()


def threshold_for(model: str) -> float:
    return HashingEmbedder.similarity_threshold if model == HashingEmbedder.name else FastEmbedEmbedder.similarity_threshold


def store_embeddings(conn: sqlite3.Connection, post_ids: list[str], texts: list[str]) -> str:
    embedder = get_embedder()
    vectors = embedder.embed(texts) if texts else np.zeros((0, 1), dtype=np.float32)
    conn.executemany("INSERT OR REPLACE INTO embeddings (post_id, model, vector) VALUES (?, ?, ?)",
                     [(pid, embedder.name, v.astype(np.float32).tobytes()) for pid, v in zip(post_ids, vectors)])
    return embedder.name


def load_embeddings(conn: sqlite3.Connection) -> tuple[list[str], np.ndarray, str | None]:
    """(post ids, matrix of unit vectors, model). Only vectors from the most common model are returned."""
    rows = conn.execute("SELECT post_id, model, vector FROM embeddings ORDER BY post_id").fetchall()
    if not rows:
        return [], np.zeros((0, 1), dtype=np.float32), None
    models = [r["model"] for r in rows]
    model = max(set(models), key=models.count)
    rows = [r for r in rows if r["model"] == model]
    return [r["post_id"] for r in rows], np.stack([np.frombuffer(r["vector"], dtype=np.float32) for r in rows]), model


def semantic_search(conn: sqlite3.Connection, query: str, k: int = 10) -> list[tuple[str, float]]:
    """Posts most similar in meaning to `query`, as (post_id, cosine similarity)."""
    ids, matrix, model = load_embeddings(conn)
    embedder = get_embedder()
    if not ids or model != embedder.name:
        return []
    scores = matrix @ embedder.embed([query])[0]
    top = np.argsort(-scores)[:k]
    return [(ids[i], round(float(scores[i]), 3)) for i in top]
