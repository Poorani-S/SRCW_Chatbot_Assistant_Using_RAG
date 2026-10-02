"""
Evaluation Script for SRCW RAG Pipeline.
Measures retrieval hit-rate against 20 gold-standard question/source pairs.

Usage:
    python backend/eval/evaluate.py

Output: Hit@K accuracy and per-question breakdown, useful for tuning CHUNK_SIZE / TOP_K.
"""
import json
import sys
from pathlib import Path

# Add backend directory to path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app import rag
from app.config import TOP_K

QUESTIONS_FILE = Path(__file__).parent / "questions.json"


def run_evaluation():
    print("=== SRCW RAG Evaluation ===\n")

    # Load index
    try:
        rag.load_index()
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # Load questions
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        questions = json.load(f)

    total = len(questions)
    hits_at_k = 0
    category_hits = 0
    results = []

    for q in questions:
        qid = q["id"]
        question = q["question"]
        expected_urls = q["expected_sources"]
        expected_category = q["expected_category"]

        # Retrieve
        retrieved, best_score = rag.retrieve(question, k=TOP_K)

        # Check URL hit: at least one retrieved URL matches an expected URL
        retrieved_urls = [r["source_url"] for r in retrieved]
        url_hit = any(
            any(expected in ret_url or ret_url in expected for ret_url in retrieved_urls)
            for expected in expected_urls
        )

        # Check category hit
        retrieved_categories = [r["category"] for r in retrieved]
        cat_hit = expected_category in retrieved_categories

        if url_hit:
            hits_at_k += 1
        if cat_hit:
            category_hits += 1

        status = "✅" if url_hit else "❌"
        cat_status = "✅" if cat_hit else "❌"

        result = {
            "id": qid,
            "question": question,
            "url_hit": url_hit,
            "category_hit": cat_hit,
            "best_score": round(best_score, 3),
            "top_retrieved": [r["source_url"] for r in retrieved[:2]],
        }
        results.append(result)

        print(f"[{qid:02d}] {status} URL | {cat_status} Cat | Score: {best_score:.3f} | Q: {question[:60]}")
        if not url_hit:
            print(f"       Expected: {expected_urls}")
            print(f"       Got:      {retrieved_urls}")
        print()

    # Summary
    url_accuracy = hits_at_k / total * 100
    cat_accuracy = category_hits / total * 100

    print("=" * 60)
    print(f"Total Questions : {total}")
    print(f"TOP_K           : {TOP_K}")
    print(f"URL Hit@K       : {hits_at_k}/{total} = {url_accuracy:.1f}%")
    print(f"Category Hit@K  : {category_hits}/{total} = {cat_accuracy:.1f}%")
    print("=" * 60)

    return {
        "total": total,
        "url_hits": hits_at_k,
        "url_accuracy": url_accuracy,
        "category_hits": category_hits,
        "category_accuracy": cat_accuracy,
        "results": results,
    }


if __name__ == "__main__":
    run_evaluation()
