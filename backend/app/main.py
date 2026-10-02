"""
FastAPI application for SRCW Assistant.
Endpoints:
  GET  /api/health     - Status check, LLM provider info, index stats
  POST /api/search     - Retrieval-only (for debugging)
  POST /api/ask        - Full RAG: retrieve + LLM answer
  POST /api/feedback   - Thumbs up/down feedback from users
  POST /api/ingest     - Admin trigger to re-run ingestion (token-protected)
"""
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from . import llm, rag
from .config import (
    ALLOWED_ORIGINS,
    CHUNKS_PATH,
    FALLBACK_MESSAGE,
    FEEDBACK_PATH,
    INDEX_PATH,
    RATE_LIMIT,
    SCORE_THRESHOLD,
    TOP_K,
    UNANSWERED_PATH,
    DATA_DIR,
)

logger = logging.getLogger("srcw_api")

# ─── Rate limiter ────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT])

# ─── FastAPI App ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="SRCW Assistant API",
    description="AI-powered virtual assistant for Sri Ramakrishna College of Arts & Science for Women, Coimbatore",
    version="1.0.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS: allow configured origins for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Startup: load the FAISS index ──────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    """Load FAISS index and chunk metadata from disk at app startup."""
    try:
        rag.load_index()
        logger.info("SRCW knowledge base loaded successfully.")
    except FileNotFoundError as e:
        logger.warning(f"Index not found at startup: {e}")
        logger.warning("Run 'python backend/ingest.py' to build the knowledge base.")


# ─── Request / Response Models ────────────────────────────────────────────────
class AskBody(BaseModel):
    question: str = Field(..., min_length=2, max_length=1000)
    history: list[dict] = Field(default_factory=list, max_items=12)
    top_k: int = Field(default=TOP_K, ge=1, le=10)

    @validator("question")
    def question_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Question cannot be empty.")
        return v.strip()


class SearchBody(BaseModel):
    question: str = Field(..., min_length=2, max_length=1000)
    top_k: int = Field(default=TOP_K, ge=1, le=10)


class FeedbackBody(BaseModel):
    question: str
    answer: str
    rating: int = Field(..., ge=-1, le=1)  # -1=thumbs down, 0=neutral, 1=thumbs up
    comment: str = ""


# ─── Helper: append JSONL record ─────────────────────────────────────────────
def _append_jsonl(path: Path, record: dict) -> None:
    """Append a record to a JSONL file (creates file if needed)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _log_unanswered(question: str, standalone: str, best_score: float) -> None:
    """Log a question that hit the no-answer threshold for staff review."""
    _append_jsonl(
        UNANSWERED_PATH,
        {
            "timestamp": datetime.utcnow().isoformat(),
            "original_question": question,
            "standalone_question": standalone,
            "best_score": best_score,
        },
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────
@app.get("/api/health")
@limiter.exempt
async def health():
    """Backend health check. Returns LLM provider info and index statistics."""
    index_stats = {}
    if rag.is_index_loaded():
        index_stats = {
            "vectors": rag._index.ntotal,
            "chunks": len(rag._chunks),
            "index_file": str(INDEX_PATH),
        }
    return {
        "status": "ok",
        "index_loaded": rag.is_index_loaded(),
        **llm.info(),
        **index_stats,
    }


@app.post("/api/search")
@limiter.limit(RATE_LIMIT)
async def search(request: Request, body: SearchBody):
    """
    Retrieval-only endpoint (no LLM call). Useful for debugging chunk quality
    and tuning CHUNK_SIZE / TOP_K / SCORE_THRESHOLD.
    """
    if not rag.is_index_loaded():
        raise HTTPException(503, "Knowledge base not loaded. Run: python backend/ingest.py")

    hits, best_score = rag.retrieve(body.question, body.top_k)
    return {
        "question": body.question,
        "best_score": best_score,
        "threshold": SCORE_THRESHOLD,
        "sources": hits,
    }


@app.post("/api/ask")
@limiter.limit(RATE_LIMIT)
async def ask(request: Request, body: AskBody):
    """
    Full RAG pipeline:
    1. Safety check (off-topic / injection)
    2. Rewrite follow-up into standalone question using history
    3. Hybrid FAISS + BM25 retrieval
    4. Score threshold gate (return fallback if best score < threshold)
    5. Build prompt + call LLM
    6. Return {answer, sources, standalone_question}
    """
    if not rag.is_index_loaded():
        raise HTTPException(503, "Knowledge base not loaded. Run: python backend/ingest.py")

    question = body.question.strip()

    # 1. Safety gate: off-topic / prompt injection
    if rag.is_off_topic(question):
        return {
            "answer": (
                "I'm specifically designed to help with questions about "
                "Sri Ramakrishna College of Arts & Science for Women (SRCW). "
                "I can't help with that request. Please ask me about admissions, "
                "courses, facilities, scholarships, or anything else related to SRCW! 😊"
            ),
            "sources": [],
            "standalone_question": question,
        }

    # 2. Rewrite follow-up question into standalone
    standalone = question
    if body.history and len(body.history) > 0:
        try:
            standalone = llm.rewrite_question(question, body.history)
        except Exception:
            standalone = question  # Fallback to original if rewriting fails

    # 3. Retrieve relevant chunks (hybrid: FAISS + BM25)
    try:
        hits, best_score = rag.retrieve(standalone, body.top_k)
    except Exception as e:
        raise HTTPException(500, f"Retrieval failed: {e}")

    # 4. Score threshold gate
    if best_score < SCORE_THRESHOLD:
        _log_unanswered(question, standalone, best_score)
        return {
            "answer": FALLBACK_MESSAGE,
            "sources": [],
            "standalone_question": standalone,
        }

    # 5. Build LLM prompt and get answer
    prompt = rag.build_prompt(standalone, hits)
    try:
        answer = llm.chat(rag.SYSTEM_PROMPT, prompt, history=body.history)
    except Exception as e:
        raise HTTPException(502, f"LLM call failed ({llm.info()['provider']}): {e}")

    # Format sources for the frontend (strip full chunk text for bandwidth)
    sources = [
        {
            "title": h["source_title"],
            "url": h["source_url"],
            "page": h["page"],
            "snippet": h["snippet"],
            "score": h["score"],
            "category": h["category"],
        }
        for h in hits
    ]

    return {
        "answer": answer,
        "sources": sources,
        "standalone_question": standalone,
    }


@app.post("/api/feedback")
@limiter.limit("30/minute")
async def feedback(request: Request, body: FeedbackBody):
    """Store user thumbs up/down feedback for quality monitoring."""
    record = {
        "timestamp": datetime.utcnow().isoformat(),
        "question": body.question,
        "answer_preview": body.answer[:300],
        "rating": body.rating,
        "comment": body.comment,
    }
    _append_jsonl(FEEDBACK_PATH, record)
    return {"status": "recorded", "rating": body.rating}


@app.post("/api/ingest")
@limiter.limit("2/hour")
async def trigger_ingest(request: Request):
    """
    Admin endpoint to rebuild the knowledge base index on-demand.
    This runs synchronously so the response may take 30-60+ seconds.
    """
    try:
        # Import and run ingestion inline
        import sys
        backend_dir = str(Path(__file__).resolve().parent.parent)
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        from ingest import run_ingestion

        result = run_ingestion()

        # Reload the index in memory
        rag.load_index()

        return {"status": "success", **result}
    except Exception as e:
        raise HTTPException(500, f"Ingestion failed: {e}")


# ---- Serve the built React app (single-service deploy) ----
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if DIST.exists():
    if (DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        file = (DIST / full_path).resolve()
        if full_path and file.is_file() and DIST.resolve() in file.parents:
            return FileResponse(file)          # e.g. logo, favicon
        return FileResponse(DIST / "index.html")  # the React app

