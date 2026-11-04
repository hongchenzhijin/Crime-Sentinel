"""Central configuration for Crime Sentinel.

Values can be overridden with environment variables so the demo runs with no
external credentials by default.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
SYNTHETIC_DIR = DATA_DIR / "synthetic"

DB_PATH = Path(os.getenv("CRIME_SENTINEL_DB", str(PROJECT_ROOT / "backend" / "crime_sentinel.db")))
DEMO_POSTS_PATH = SYNTHETIC_DIR / "posts.json"
DEMO_TOPICS_PATH = SYNTHETIC_DIR / "topics.json"
EVAL_SET_PATH = SYNTHETIC_DIR / "labelled_eval_set.json"

# Built dashboard (`npm run build`), served by the API itself in single-server deployments.
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

APP_NAME = "Crime Sentinel"
APP_VERSION = "0.1.0"

# Data retention: records ingested longer ago than this are deleted by
# `scripts/load_demo_data.py --purge-expired`. Synthetic demo data is
# re-created on every load.
RETENTION_DAYS = int(os.getenv("CRIME_SENTINEL_RETENTION_DAYS", "30"))

# Trend safeguard: buckets with fewer posts than this are reported as
# "insufficient sample" instead of being presented as a trend.
MIN_TREND_SAMPLE = int(os.getenv("CRIME_SENTINEL_MIN_TREND_SAMPLE", "5"))

# Optional LLM classifier (OpenAI-compatible chat completions endpoint, e.g. a
# hosted Llama model or a local Ollama server). Disabled unless both are set.
LLM_BASE_URL = os.getenv("CRIME_SENTINEL_LLM_BASE_URL")
LLM_API_KEY = os.getenv("CRIME_SENTINEL_LLM_API_KEY", "")
LLM_MODEL = os.getenv("CRIME_SENTINEL_LLM_MODEL")

CORS_ORIGINS = os.getenv(
    "CRIME_SENTINEL_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

# Post images (synthetic) and the simulated industry hash-sharing list they are matched against.
MEDIA_DIR = SYNTHETIC_DIR / "media"
MEDIA_MANIFEST_PATH = SYNTHETIC_DIR / "media_manifest.json"
HASHLIST_PATH = SYNTHETIC_DIR / "hashlist.json"
MULTIMODAL_EVAL_PATH = SYNTHETIC_DIR / "labelled_multimodal_set.json"
RED_TEAM_SET_PATH = SYNTHETIC_DIR / "red_team_set.json"
RED_TEAM_RESULTS_PATH = SYNTHETIC_DIR / "red_team_results.json"

# Local text embeddings (Meta's Model API has no embeddings model): `auto` uses fastembed's multilingual MiniLM
# and falls back to hashed bag-of-words; `hash` forces the fallback (used by tests, needs no model download).
EMBEDDINGS_MODE = os.getenv("CRIME_SENTINEL_EMBEDDINGS", "auto")
EMBEDDINGS_MODEL = os.getenv("CRIME_SENTINEL_EMBEDDINGS_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
EMBEDDINGS_CACHE = PROJECT_ROOT / "backend" / ".cache" / "fastembed"

# Muse evaluation results, cached between restarts (recomputed when eval sets, prompts or models change).
EVAL_CACHE_PATH = PROJECT_ROOT / "backend" / ".cache" / "evaluation.json"
