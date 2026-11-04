"""Post images: PDQ perceptual hashing, hash-list matching and near-duplicate detection.

PDQ is Meta's open-source perceptual image hash (github.com/facebook/ThreatExchange), the format used by
industry hash-sharing programmes for known terrorist and violent-extremist imagery. A 256-bit hash survives
resizing, recolouring, re-compression, small crops and caption overlays, so a re-upload of a known image is
recognised without anyone having to look at it again. Hashing runs locally: it works offline, and the image
never leaves the machine.

A hash match says "this is (nearly) the same picture", nothing more. It never classifies a post by itself:
it adds a signal and makes sure a human reviews the post.
"""

from __future__ import annotations

import base64
import io
import json
import sqlite3
from functools import lru_cache
from pathlib import Path

from app import config
from app.schemas.models import HARMFUL_CATEGORIES, Category, ClassificationResult, Post

# Hamming distance (out of 256 bits) at or below which two PDQ hashes are treated as the same image.
# 31 is the threshold recommended in Meta's PDQ documentation.
MATCH_THRESHOLD = 31
# PDQ quality below 50 means the image has little detail (e.g. very dark), so matches are less reliable.
MIN_QUALITY = 50


def media_path(file: str) -> Path:
    path = (config.MEDIA_DIR / file).resolve()
    if path.parent != config.MEDIA_DIR.resolve():
        raise ValueError(f"media file outside the media folder: {file}")
    return path


def pdq_hash(path: Path) -> tuple[str, int]:
    """PDQ hash of an image as 64 hex characters, plus PDQ's quality score (0-100)."""
    import numpy as np
    import pdqhash
    from PIL import Image

    bits, quality = pdqhash.compute(np.asarray(Image.open(path).convert("RGB")))
    return f"{int(''.join(str(int(b)) for b in bits), 2):064x}", int(quality)


def hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def load_hashlist() -> tuple[dict, ...]:
    return _load_hashlist(config.HASHLIST_PATH)


@lru_cache(maxsize=4)
def _load_hashlist(path: Path) -> tuple[dict, ...]:
    if not path.exists():
        return ()
    return tuple(json.loads(path.read_text(encoding="utf-8"))["entries"])


def match_hashlist(pdq: str, hashlist: tuple[dict, ...] | None = None) -> dict | None:
    """Closest hash-list entry within MATCH_THRESHOLD, or None."""
    best = None
    for entry in load_hashlist() if hashlist is None else hashlist:
        d = hamming(pdq, entry["pdq"])
        if d <= MATCH_THRESHOLD and (best is None or d < best["distance"]):
            best = {"entry_id": entry["id"], "label": entry["label"], "category": entry["category"],
                    "source": entry["source"], "distance": d}
    return best


def store_media(conn: sqlite3.Connection, post: Post) -> list[dict]:
    """Hash a post's images and store the hashes and any hash-list match. Returns the stored rows."""
    rows = []
    conn.execute("DELETE FROM media WHERE post_id = ?", (post.id,))
    for idx, m in enumerate(post.media):
        path = media_path(m.file)
        pdq, quality, match = None, None, None
        if path.exists():
            pdq, quality = pdq_hash(path)
            match = match_hashlist(pdq)
            if match:
                match["low_quality"] = quality < MIN_QUALITY
        conn.execute("INSERT INTO media (post_id, idx, file, pdq, quality, hash_match) VALUES (?, ?, ?, ?, ?, ?)",
                     (post.id, idx, m.file, pdq, quality, json.dumps(match) if match else None))
        rows.append({"file": m.file, "pdq": pdq, "quality": quality, "hash_match": match})
    return rows


def all_hashes(conn: sqlite3.Connection) -> dict[str, list[tuple[str, str]]]:
    """post_id -> [(pdq, file)] for every hashed image."""
    out: dict[str, list[tuple[str, str]]] = {}
    for r in conn.execute("SELECT post_id, pdq, file FROM media WHERE pdq IS NOT NULL ORDER BY post_id, idx"):
        out.setdefault(r["post_id"], []).append((r["pdq"], r["file"]))
    return out


def post_media(conn: sqlite3.Connection, post_id: str) -> list[dict]:
    """Media of one post with hash, quality, hash-list match and near-duplicates elsewhere in the dataset."""
    rows = conn.execute("SELECT * FROM media WHERE post_id = ? ORDER BY idx", (post_id,)).fetchall()
    post = conn.execute("SELECT media FROM posts WHERE id = ?", (post_id,)).fetchone()
    alt = {m["file"]: m.get("alt_text", "") for m in json.loads(post["media"])} if post else {}
    others = [(pid, h, f) for pid, hs in all_hashes(conn).items() if pid != post_id for h, f in hs]
    out = []
    for r in rows:
        dups = []
        if r["pdq"]:
            dups = sorted(({"post_id": pid, "file": f, "distance": hamming(r["pdq"], h)} for pid, h, f in others
                           if hamming(r["pdq"], h) <= MATCH_THRESHOLD), key=lambda d: d["distance"])
        out.append({"file": r["file"], "url": f"/api/media/{r['file']}", "alt_text": alt.get(r["file"], ""),
                    "pdq": r["pdq"], "quality": r["quality"],
                    "hash_match": json.loads(r["hash_match"]) if r["hash_match"] else None,
                    "near_duplicates": dups[:20], "near_duplicate_count": len(dups)})
    return out


def apply_hash_matches(result: ClassificationResult, matches: list[dict]) -> tuple[ClassificationResult, bool]:
    """Fold hash-list matches into a classification. Returns (result, needs_priority_review).

    A match to a list of harmful imagery never sets a harmful category on its own (a news post may show the same
    image). If the classifier did not find harm, the post becomes UNCERTAIN so a human decides.
    """
    harmful = {c.value for c in HARMFUL_CATEGORIES}
    hits = [m for m in matches if m and m["category"] in harmful]
    if not hits:
        return result, False
    signals = set(result.signals) | {f"pdq_hashlist_match:{m['entry_id']}" for m in hits}
    if any(m.get("low_quality") for m in hits):
        signals.add("pdq_low_quality_hash")
    best = min(hits, key=lambda m: m["distance"])
    note = (f" An attached image matches the hash list entry '{best['label']}' (PDQ distance {best['distance']}"
            f"/256, threshold {MATCH_THRESHOLD}); a hash match identifies the picture, not the post's intent.")
    category = result.category
    if category.value not in harmful and category != Category.UNCERTAIN_REQUIRES_REVIEW:
        category = Category.UNCERTAIN_REQUIRES_REVIEW
        note += " The text was not classified as harmful, so a human must decide."
    return result.model_copy(update={"category": category, "signals": sorted(signals),
                                     "explanation": result.explanation + note}), True


def image_part(path: Path, max_side: int = 768) -> dict:
    """Downscaled JPEG data-URL part for a vision request (keeps image tokens and cost down)."""
    from PIL import Image

    img = Image.open(path).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}}
