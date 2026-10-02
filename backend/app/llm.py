"""
LLM abstraction layer supporting OpenAI-compatible APIs (Gemini, Ollama, OpenRouter).
Includes question rewriting for conversational follow-ups and streaming support.
Auto-retries on 429 (quota) and 503 (overload) with exponential back-off.
"""
import time
from typing import Generator
from openai import OpenAI
from .config import PROVIDER, PROVIDERS


def info() -> dict:
    """Return active provider and model information."""
    return {"provider": PROVIDER, "model": PROVIDERS[PROVIDER]["model"]}


def _get_client() -> OpenAI:
    """Initialize OpenAI client for current provider."""
    cfg = PROVIDERS[PROVIDER]
    if PROVIDER != "ollama" and not cfg["api_key"]:
        raise RuntimeError(
            f"API key for '{PROVIDER}' is not configured. Please add it to backend/.env"
        )
    return OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])


def rewrite_question(question: str, history: list[dict] | None = None) -> str:
    """
    Rewrite a follow-up question into a standalone, search-friendly query using conversation history.
    E.g.: 'What about the fees?' -> 'What are the fees for BCA at SRCW?'
    """
    if not history or len(history) == 0:
        return question

    cfg = PROVIDERS[PROVIDER]
    if PROVIDER != "ollama" and not cfg.get("api_key"):
        return question

    try:
        client = _get_client()
        # Format recent history (up to last 6 messages)
        recent_history = history[-6:]
        history_text = "\n".join(
            f"{msg.get('role', 'user').capitalize()}: {msg.get('content', '')}"
            for msg in recent_history
        )

        rewrite_prompt = (
            "You are a search query reformulation assistant for Sri Ramakrishna College of Arts & Science for Women (SRCW).\n"
            "Given the chat history below and a follow-up question, rephrase the follow-up question to be a single, "
            "self-contained standalone search query.\n"
            "- Do NOT answer the question.\n"
            "- If the question is already complete and self-contained, return it unchanged.\n"
            "- If it refers to pronouns or previous context (like 'it', 'the course', 'fees'), include the specific entity from history.\n"
            "- Return ONLY the rephrased question with no preamble, quotes or explanation."
        )

        res = client.chat.completions.create(
            model=cfg["model"],
            temperature=0.0,
            messages=[
                {"role": "system", "content": rewrite_prompt},
                {
                    "role": "user",
                    "content": f"Chat History:\n{history_text}\n\nFollow-up Question: {question}\n\nStandalone Question:",
                },
            ],
            timeout=8.0,
        )
        rewritten = res.choices[0].message.content.strip()
        # Clean quotes if any
        if rewritten.startswith('"') and rewritten.endswith('"'):
            rewritten = rewritten[1:-1].strip()
        return rewritten if rewritten else question
    except Exception as e:
        # Fallback to original question if rewriting fails or times out
        return question


def chat(system: str, user: str, history: list[dict] | None = None) -> str:
    """Send chat prompt to LLM. Retries up to 3x on quota/overload errors."""
    client = _get_client()
    cfg = PROVIDERS[PROVIDER]

    messages = [{"role": "system", "content": system}]
    if history:
        for msg in history[-6:]:
            role = msg.get("role")
            content = msg.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user})

    last_err = None
    for attempt in range(3):
        try:
            res = client.chat.completions.create(
                model=cfg["model"],
                temperature=0.2,
                messages=messages,
            )
            return res.choices[0].message.content
        except Exception as e:
            last_err = e
            err_str = str(e)
            # Retry on quota (429) or server overload (503)
            if "429" in err_str or "503" in err_str:
                wait = 2 ** attempt  # 1s, 2s, 4s
                time.sleep(wait)
            else:
                raise  # Non-retryable error
    raise last_err


def chat_stream(system: str, user: str, history: list[dict] | None = None) -> Generator[str, None, None]:
    """Stream token chunks from the LLM."""
    client = _get_client()
    cfg = PROVIDERS[PROVIDER]

    messages = [{"role": "system", "content": system}]
    if history:
        for msg in history[-6:]:
            role = msg.get("role")
            content = msg.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user})

    response = client.chat.completions.create(
        model=cfg["model"],
        temperature=0.2,
        messages=messages,
        stream=True,
    )

    for chunk in response:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta
