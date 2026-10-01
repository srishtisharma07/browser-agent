"""
AI Browser Agent – FastAPI backend entry point.

Phase 1 – Initialisation only.
Agent, LangGraph, Playwright and Gemini are NOT wired up yet.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AI Browser Agent",
    description="SIH260171 – AI-Powered Browser Assistant / Agent (backend API)",
    version="0.1.0",
)

# Allow requests from the Vite dev server during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["health"])
async def health_check() -> dict:
    """
    Simple liveness probe.

    Returns:
        JSON payload confirming the service is up.
    """
    return {
        "status": "ok",
        "service": "ai-browser-agent",
    }
