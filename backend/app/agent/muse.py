"""Client for Meta's Muse models via the Meta Model API (OpenAI-compatible).

Docs: https://dev.meta.ai/docs  - base URL https://api.meta.ai/v1, Bearer MODEL_API_KEY.

Every call records model, latency, token usage and estimated cost so the
mission log can show exactly where Muse was used. If no key is configured the
client reports `enabled = False` and callers fall back to labelled scripted
behaviour - the UI always says which engine produced each step.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _load_env_file() -> None:
    """Minimal .env loader (backend/.env) so the key never has to be committed or typed into code."""
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env_file()

BASE_URL = os.getenv("MUSE_BASE_URL", "https://api.meta.ai/v1").rstrip("/")
API_KEY = os.getenv("MODEL_API_KEY", "")
FAST_MODEL = os.getenv("MUSE_MODEL", "muse-spark-1.3")          # persona, governor, per-post analysis
DEEP_MODEL = os.getenv("MUSE_DEEP_MODEL", "muse-spark-1.3")     # long-context community assessment; try muse-wonder-1.0
IMAGE_MODEL = os.getenv("MUSE_IMAGE_MODEL", "muse-image-1.0")

# Muse counts hidden reasoning tokens against max_tokens, so `max_tokens` in chat() is the budget for the visible
# answer and this headroom is added on top (only tokens actually used are billed). Measured 2026-11-03: a short
# classification spent ~170 reasoning tokens at "minimal" and ~400-470 at "low".
REASONING_HEADROOM = {"minimal": 1000, "low": 2000, "medium": 4000, "high": 8000, None: 2000}

# USD per 1M tokens (dev.meta.ai/docs/pricing-rate-limits, read 2026-11-03).
PRICING = {
    "muse-spark-1.3": (1.25, 4.25),
    "muse-spark-1.2": (1.25, 4.25),
    "muse-spark-1.1": (1.25, 4.25),
    "muse-spark-1.3-contributor": (0.10, 0.20),
    "muse-wonder-1.0": (4.00, 20.00),
}


class MuseError(Exception):
    pass


@dataclass
class MuseResult:
    text: str
    data: Any
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cost_usd: float


@dataclass
class UsageLedger:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    by_purpose: dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, purpose: str, r: MuseResult) -> None:
        with self._lock:
            self.calls += 1
            self.input_tokens += r.input_tokens
            self.output_tokens += r.output_tokens
            self.cost_usd += r.cost_usd
            self.by_purpose[purpose] = self.by_purpose.get(purpose, 0) + 1

    def as_dict(self) -> dict:
        return {"calls": self.calls, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "cost_usd": round(self.cost_usd, 4), "by_purpose": dict(self.by_purpose)}


def extract_json(text: str) -> Any:
    """Parse the first JSON object/array in a model reply (tolerates ```json fences)."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise MuseError(f"model did not return JSON: {text[:200]}")


def image_part(path: Path) -> dict:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


class MuseClient:
    def __init__(self, api_key: str = API_KEY, base_url: str = BASE_URL, ledger: UsageLedger | None = None,
                 force_offline: bool = False):
        self.api_key = api_key
        self.base_url = base_url
        self.enabled = bool(api_key) and not force_offline
        self.ledger = ledger or UsageLedger()
        # Optional parameters the endpoint rejected once; not sent again.
        self._unsupported: set[str] = set()

    def chat(
        self,
        purpose: str,
        system: str,
        user: str | list[dict],
        model: str = FAST_MODEL,
        json_output: bool = True,
        reasoning_effort: str | None = None,
        max_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> MuseResult:
        if not self.enabled:
            raise MuseError("Muse is not configured (set MODEL_API_KEY)")
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens + REASONING_HEADROOM.get(reasoning_effort, 2000),
            "temperature": temperature,
        }
        if json_output and "response_format" not in self._unsupported:
            body["response_format"] = {"type": "json_object"}
        if reasoning_effort and "reasoning_effort" not in self._unsupported:
            body["reasoning_effort"] = reasoning_effort

        started = time.perf_counter()
        resp = self._post("/chat/completions", body)
        latency = int((time.perf_counter() - started) * 1000)

        try:
            choice = resp["choices"][0]
            text = choice["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise MuseError(f"unexpected response shape: {str(resp)[:200]}") from exc
        if not text.strip() and choice.get("finish_reason") == "length":
            raise MuseError("token budget used up by reasoning before any answer was written")
        usage = resp.get("usage") or {}
        tin, tout = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        reasoning = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0))
        pin, pout = PRICING.get(model, PRICING["muse-spark-1.3"])
        result = MuseResult(
            text=text,
            data=extract_json(text) if json_output else None,
            model=resp.get("model", model),
            latency_ms=latency,
            input_tokens=tin,
            output_tokens=tout,
            reasoning_tokens=reasoning,
            cost_usd=(tin * pin + tout * pout) / 1_000_000,
        )
        self.ledger.add(purpose, result)
        return result

    def _post(self, path: str, body: dict, retries: int = 3) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        delay = 0.5
        for attempt in range(retries + 1):
            try:
                r = httpx.post(f"{self.base_url}{path}", headers=headers, json=body, timeout=90)
            except httpx.HTTPError as exc:
                if attempt == retries:
                    raise MuseError(f"network error: {exc}") from exc
                time.sleep(delay)
                delay *= 2
                continue
            if r.status_code == 400:
                # Drop optional parameters the endpoint does not accept, then retry once without them.
                dropped = [k for k in ("response_format", "reasoning_effort") if k in body and k in r.text]
                if dropped:
                    for k in dropped:
                        body.pop(k)
                        self._unsupported.add(k)
                    continue
            if r.status_code in (429, 500, 502, 503) and attempt < retries:
                time.sleep(float(r.headers.get("retry-after", delay)))
                delay *= 2
                continue
            if r.status_code >= 400:
                raise MuseError(f"HTTP {r.status_code}: {r.text[:300]}")
            return r.json()
        raise MuseError("retries exhausted")

    def generate_image(self, prompt: str, size: str = "1024x1024") -> bytes:
        if not self.enabled:
            raise MuseError("Muse is not configured (set MODEL_API_KEY)")
        resp = self._post("/images/generations", {"model": IMAGE_MODEL, "prompt": prompt, "size": size, "n": 1})
        item = resp["data"][0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        return httpx.get(item["url"], timeout=60).content
