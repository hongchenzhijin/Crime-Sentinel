"""Crime Sentinel API entrypoint: `uvicorn app.main:app --reload` from backend/."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import config
from app.api.agent_routes import router as agent_router
from app.api.routes import router

app = FastAPI(
    title=f"{config.APP_NAME} API",
    version=config.APP_VERSION,
    description="Crime Sentinel: a governed undercover research agent (Meta Muse) operating on a sandbox social "
    "platform, plus a content-classification and human-review console. Classifies content, never people.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(router)
app.include_router(agent_router)

# Single-server deployment (e.g. Replit): serve the built dashboard from frontend/dist when it exists.
# Mounted last so the /api routes above take precedence.
if config.FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="frontend")
