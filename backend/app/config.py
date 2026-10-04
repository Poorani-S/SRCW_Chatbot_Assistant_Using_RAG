"""
Configuration module for SRCW Assistant.
Loads settings from environment variables and sets up directory paths,
LLM providers, RAG parameters, and college metadata.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
ROOT_DIR = BACKEND_DIR.parent

# Load .env file
load_dotenv(BACKEND_DIR / ".env")

# LLM Provider configuration
PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

PROVIDERS = {
    "ollama": {
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "api_key": "ollama",
        "model": os.getenv("OLLAMA_MODEL", "llama3.2"),
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key": os.getenv("GEMINI_API_KEY", ""),
        "model": os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": os.getenv("OPENROUTER_API_KEY", ""),
        "model": os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
    },
}

if PROVIDER not in PROVIDERS:
    raise ValueError(f"LLM_PROVIDER must be one of {list(PROVIDERS.keys())}, got '{PROVIDER}'")

# RAG knobs
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 700))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 120))
TOP_K = int(os.getenv("TOP_K", 4))
SCORE_THRESHOLD = float(os.getenv("SCORE_THRESHOLD", 0.42))

# Lightweight embedding model (runs under 100MB RAM, ideal for Render free tier)
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

# Data & Knowledge directories
DATA_DIR = BACKEND_DIR / "data"
KNOWLEDGE_DIR = BACKEND_DIR / "knowledge"
PDFS_DIR = KNOWLEDGE_DIR / "pdfs"
URLS_FILE = KNOWLEDGE_DIR / "urls.txt"
FAQ_FILE = KNOWLEDGE_DIR / "faq.md"

INDEX_PATH = DATA_DIR / "index.faiss"
CHUNKS_PATH = DATA_DIR / "chunks.json"
FEEDBACK_PATH = DATA_DIR / "feedback.jsonl"
UNANSWERED_PATH = DATA_DIR / "unanswered.jsonl"

# Categories
CATEGORIES = [
    "admissions",
    "programmes",
    "departments",
    "examination",
    "placement",
    "scholarship",
    "facilities",
    "hostel_transport",
    "contact",
    "news_events",
    "policies",
    "general",
]

# Security & CORS
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,https://srcw.ac.in",
    ).split(",")
    if origin.strip()
]

RATE_LIMIT = os.getenv("RATE_LIMIT", "20/minute")

# Official SRCW Contact Info for Fallback
COLLEGE_NAME = "Sri Ramakrishna College of Arts & Science for Women (SRCW)"
COLLEGE_ADDRESS = "395, Sarojini Naidu Road, New Siddhapudur, Coimbatore - 641044"
COLLEGE_PHONE = "+91 7373144766"
COLLEGE_EMAIL = "enquiry@srcw.ac.in"
COLLEGE_WEBSITE = "https://srcw.ac.in"

FALLBACK_MESSAGE = (
    f"I don't have that specific information in the official published SRCW records. "
    f"Please contact the college office directly:\n\n"
    f"📍 **Address**: {COLLEGE_ADDRESS}\n"
    f"📞 **Phone**: {COLLEGE_PHONE}\n"
    f"✉️ **Email**: {COLLEGE_EMAIL}\n"
    f"🌐 **Website**: [{COLLEGE_WEBSITE}]({COLLEGE_WEBSITE})"
)
