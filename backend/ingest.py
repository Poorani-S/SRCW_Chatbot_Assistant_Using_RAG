"""
CLI Ingestion Script for SRCW Assistant.
Builds the persistent FAISS index and chunks metadata from:
1. PDFs in backend/knowledge/pdfs/
2. Web pages from https://srcw.ac.in (backend/knowledge/urls.txt)
3. Hand-written FAQ in backend/knowledge/faq.md

Idempotent: Re-running completely rebuilds backend/data/index.faiss and backend/data/chunks.json.
"""
import hashlib
import io
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
import faiss
from fastembed import TextEmbedding
import httpx
import numpy as np
from pypdf import PdfReader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("srcw_ingest")

# Add parent directory to path so app.config can be imported
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import (
    CATEGORIES,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHUNKS_PATH,
    DATA_DIR,
    EMBED_MODEL,
    FAQ_FILE,
    INDEX_PATH,
    PDFS_DIR,
    URLS_FILE,
)


def categorize(text_or_url: str) -> str:
    """Classify chunk or URL into one of the predefined categories."""
    lowered = text_or_url.lower()

    if any(k in lowered for k in ["admission", "eligibility", "how to apply", "admissionenquiry", "admissionregulations"]):
        return "admissions"
    if any(k in lowered for k in ["programme", "programmesoffered", "courses", "curriculum", "degree", "b.sc", "bca", "b.com", "bba", "m.sc", "m.com"]):
        return "programmes"
    if any(k in lowered for k in ["department", "faculty", "commerce", "computer-science", "business-administration", "biochemistry", "microbiology", "mathematics", "english", "tamil"]):
        return "departments"
    if any(k in lowered for k in ["examination", "controller", "results", "cbcs", "exam", "marks", "grade"]):
        return "examination"
    if any(k in lowered for k in ["placement", "recruiter", "career", "guidance", "internship", "tcs", "infosys", "wipro"]):
        return "placement"
    if any(k in lowered for k in ["scholarship", "financial aid", "concession", "pudhumaipen", "free education"]):
        return "scholarship"
    if any(k in lowered for k in ["hostel", "transport", "bus", "mess", "boarding", "residence", "route"]):
        return "hostel_transport"
    if any(k in lowered for k in ["infrastructure", "library", "lab", "gym", "sports", "physicaleducation", "auditorium", "canteen"]):
        return "facilities"
    if any(k in lowered for k in ["contact", "address", "phone", "email", "reach", "location", "enquiry"]):
        return "contact"
    if any(k in lowered for k in ["news", "event", "blog", "celebration", "symposium", "conference", "club", "association"]):
        return "news_events"
    if any(k in lowered for k in ["antiragging", "complaint", "redressal", "equal", "policy", "iqac", "naac", "nirf", "statutory"]):
        return "policies"
    return "general"


def clean_text(text: str) -> str:
    """Normalize whitespace and strip unneeded characters."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_by_paragraphs_or_sliding(
    text: str,
    prefix: str,
    size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """
    Split text into chunks. Prefers paragraph/sentence boundaries,
    falling back to sliding window if chunks exceed size.
    """
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    chunks = []
    current_chunk = []
    current_len = len(prefix)

    for p in paragraphs:
        p_len = len(p)
        if current_len + p_len + 1 <= size:
            current_chunk.append(p)
            current_len += p_len + 1
        else:
            if current_chunk:
                combined = " ".join(current_chunk).strip()
                chunks.append(f"{prefix}\n{combined}")
                # Keep last paragraph for smooth transition if within overlap
                if len(current_chunk[-1]) <= overlap:
                    current_chunk = [current_chunk[-1], p]
                    current_len = len(prefix) + len(current_chunk[0]) + p_len + 2
                else:
                    current_chunk = [p]
                    current_len = len(prefix) + p_len + 1
            else:
                # Paragraph alone exceeds size, use sliding window
                start = 0
                while start < len(p):
                    sub = p[start : start + size - len(prefix) - 2].strip()
                    if sub:
                        chunks.append(f"{prefix}\n{sub}")
                    if start + size >= len(p):
                        break
                    start += size - overlap
                current_chunk = []
                current_len = len(prefix)

    if current_chunk:
        combined = " ".join(current_chunk).strip()
        chunks.append(f"{prefix}\n{combined}")

    return chunks


def load_pdfs(pdf_dir: Path) -> list[dict[str, Any]]:
    """Ingest all PDF files from backend/knowledge/pdfs/."""
    chunks = []
    if not pdf_dir.exists():
        logger.warning(f"PDF directory {pdf_dir} does not exist. Creating it.")
        pdf_dir.mkdir(parents=True, exist_ok=True)
        return chunks

    pdf_files = list(pdf_dir.glob("*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDF(s) in {pdf_dir}")

    for pdf_file in pdf_files:
        try:
            reader = PdfReader(str(pdf_file))
            file_title = pdf_file.stem.replace("_", " ").title()
            logger.info(f"Processing PDF: {pdf_file.name} ({len(reader.pages)} pages)")

            for page_num, page in enumerate(reader.pages, start=1):
                raw_text = clean_text(page.extract_text() or "")
                if not raw_text or len(raw_text) < 30:
                    continue

                prefix = f"[SRCW Document: {file_title} | Page {page_num}]"
                cat = categorize(raw_text + " " + file_title)
                page_chunks = chunk_by_paragraphs_or_sliding(raw_text, prefix)

                for chunk_text in page_chunks:
                    chunks.append({
                        "text": chunk_text,
                        "source_title": f"{file_title} (p.{page_num})",
                        "source_url": f"pdf:{pdf_file.name}#page={page_num}",
                        "page": page_num,
                        "category": cat,
                    })
        except Exception as e:
            logger.warning(f"Failed to read PDF {pdf_file.name}: {e}")

    return chunks


def load_urls(urls_file: Path) -> list[dict[str, Any]]:
    """Fetch and parse all web pages listed in urls.txt."""
    chunks = []
    if not urls_file.exists():
        logger.warning(f"URLs file {urls_file} does not exist.")
        return chunks

    with open(urls_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    logger.info(f"Loaded {len(urls)} URL(s) to fetch from {urls_file}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 SRCW-Assistant-Bot/1.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    with httpx.Client(timeout=12.0, verify=False, follow_redirects=True, headers=headers) as client:
        for url in urls:
            try:
                logger.info(f"Fetching: {url}")
                res = client.get(url)
                if res.status_code != 200:
                    logger.warning(f"Skipping {url}: HTTP {res.status_code}")
                    continue

                soup = BeautifulSoup(res.text, "html.parser")

                # Remove non-content elements
                for element in soup(["script", "style", "nav", "header", "footer", "aside", "noscript", "svg", "form"]):
                    element.decompose()

                # Extract page title
                page_title = "SRCW"
                if soup.title and soup.title.string:
                    page_title = clean_text(soup.title.string)
                elif soup.h1:
                    page_title = clean_text(soup.h1.get_text())

                # Clean up repeated title prefixes
                page_title = re.sub(r"Sri Ramakrishna College of Arts & Science for Women \|?", "", page_title, flags=re.I).strip()
                page_title = re.sub(r"Sri Ramakrishna College for Women \|?", "", page_title, flags=re.I).strip()
                if not page_title:
                    page_title = url.rstrip("/").split("/")[-1].replace("-", " ").title()

                # Categorize page
                cat = categorize(url + " " + page_title)

                # Group by sections based on headings
                body = soup.body or soup
                headings = body.find_all(["h1", "h2", "h3", "h4", "p", "li", "td"])

                section_text_blocks = []
                current_heading = page_title
                current_block = []

                for el in headings:
                    name = el.name.lower()
                    text = clean_text(el.get_text())
                    if not text or len(text) < 4:
                        continue

                    if name in ["h1", "h2", "h3", "h4"]:
                        if current_block:
                            section_text_blocks.append((current_heading, " ".join(current_block)))
                            current_block = []
                        current_heading = text
                    else:
                        current_block.append(text)

                if current_block:
                    section_text_blocks.append((current_heading, " ".join(current_block)))

                # If no headings were grouped, fallback to entire stripped text
                if not section_text_blocks:
                    all_text = clean_text(body.get_text())
                    if all_text:
                        section_text_blocks.append((page_title, all_text))

                # Chunk each section
                for sec_heading, sec_content in section_text_blocks:
                    if len(sec_content) < 30:
                        continue
                    prefix = f"[SRCW | {page_title} - {sec_heading}]"
                    sec_cat = categorize(sec_heading + " " + sec_content + " " + cat)
                    text_chunks = chunk_by_paragraphs_or_sliding(sec_content, prefix)

                    for chunk_str in text_chunks:
                        chunks.append({
                            "text": chunk_str,
                            "source_title": f"{page_title} - {sec_heading}",
                            "source_url": url,
                            "page": None,
                            "category": sec_cat,
                        })

            except Exception as e:
                logger.warning(f"Failed to fetch or parse {url}: {e}")

    return chunks


def load_faq(faq_path: Path) -> list[dict[str, Any]]:
    """Parse handwritten FAQ in markdown format, splitting by heading."""
    chunks = []
    if not faq_path.exists():
        logger.warning(f"FAQ file {faq_path} not found.")
        return chunks

    with open(faq_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by ## or ### headings
    sections = re.split(r"\n(?=##?\s+)", content)
    logger.info(f"Loaded {len(sections)} section(s) from FAQ: {faq_path.name}")

    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        lines = sec.split("\n", 1)
        heading_line = lines[0].lstrip("#").strip()
        body = lines[1].strip() if len(lines) > 1 else ""

        if not body:
            continue

        prefix = f"[SRCW Official FAQ: {heading_line}]"
        cat = categorize(heading_line + " " + body)
        sec_chunks = chunk_by_paragraphs_or_sliding(body, prefix)

        for chunk_text in sec_chunks:
            chunks.append({
                "text": chunk_text,
                "source_title": f"FAQ - {heading_line}",
                "source_url": "https://srcw.ac.in",
                "page": None,
                "category": cat,
            })

    return chunks


def deduplicate_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove near-duplicate chunks based on normalized text hash."""
    seen_hashes = set()
    unique = []

    for c in chunks:
        # Normalize text for hashing: remove punctuation, lowercase, strip whitespace
        norm = re.sub(r"\W+", "", c["text"].lower())
        h = hashlib.md5(norm.encode("utf-8")).hexdigest()
        if h not in seen_hashes:
            seen_hashes.add(h)
            unique.append(c)

    logger.info(f"Deduplicated chunks: {len(chunks)} -> {len(unique)} (removed {len(chunks) - len(unique)} duplicates)")
    return unique


def build_and_save_index(chunks: list[dict[str, Any]]) -> None:
    """Embed all chunks, build FAISS IndexFlatIP with normalized vectors, and save to disk."""
    if not chunks:
        raise ValueError("No chunks available to build index!")

    logger.info(f"Initializing multilingual embedding model: {EMBED_MODEL}")
    embedder = TextEmbedding(EMBED_MODEL)

    texts = [c["text"] for c in chunks]
    logger.info(f"Embedding {len(texts)} chunks...")
    t0 = time.time()
    embeddings = list(embedder.embed(texts))
    vecs = np.array(embeddings, dtype="float32")
    faiss.normalize_L2(vecs)
    embed_time = time.time() - t0
    logger.info(f"Embedded {len(texts)} chunks in {embed_time:.2f}s. Vector dimension: {vecs.shape[1]}")

    # Build FAISS index
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)

    # Ensure output directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Save FAISS index
    faiss.write_index(index, str(INDEX_PATH))
    logger.info(f"Saved FAISS index to {INDEX_PATH}")

    # Save chunk metadata
    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(chunks)} chunk metadata records to {CHUNKS_PATH}")


def run_ingestion() -> dict[str, Any]:
    """Execute complete ingestion pipeline and print statistics."""
    start_time = time.time()
    logger.info("=== Starting SRCW Knowledge Base Ingestion ===")

    # 1. Load PDFs
    pdf_chunks = load_pdfs(PDFS_DIR)

    # 2. Load URLs
    url_chunks = load_urls(URLS_FILE)

    # 3. Load FAQ
    faq_chunks = load_faq(FAQ_FILE)

    # Combine all chunks
    all_chunks = pdf_chunks + url_chunks + faq_chunks
    logger.info(
        f"Raw chunks extracted: {len(all_chunks)} "
        f"(PDFs: {len(pdf_chunks)}, URLs: {len(url_chunks)}, FAQ: {len(faq_chunks)})"
    )

    # Deduplicate
    unique_chunks = deduplicate_chunks(all_chunks)

    # Build and persist index
    build_and_save_index(unique_chunks)

    # Category breakdown
    cat_counts = {cat: 0 for cat in CATEGORIES}
    for c in unique_chunks:
        cat = c.get("category", "general")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    total_time = time.time() - start_time
    logger.info("=== Ingestion Summary ===")
    logger.info(f"Total Unique Chunks Indexed: {len(unique_chunks)}")
    for cat, count in cat_counts.items():
        if count > 0:
            logger.info(f"  - {cat}: {count} chunks")
    logger.info(f"Completed in {total_time:.2f} seconds.")

    return {
        "status": "success",
        "total_chunks": len(unique_chunks),
        "pdf_chunks": len(pdf_chunks),
        "url_chunks": len(url_chunks),
        "faq_chunks": len(faq_chunks),
        "categories": cat_counts,
        "elapsed_seconds": round(total_time, 2),
    }


if __name__ == "__main__":
    run_ingestion()
