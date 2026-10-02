// All backend API calls. Vite proxies /api → http://localhost:8000

async function parseResponse(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

/** Health check to verify the backend is up and the index is loaded. */
export async function getHealth() {
  return parseResponse(await fetch("/api/health"));
}

/**
 * Ask a question with optional conversation history.
 * @param {string} question - The user's question
 * @param {Array}  history  - Last N {role, content} messages
 * @param {number} topK     - Number of chunks to retrieve
 */
export async function askQuestion(question, history = [], topK = 4) {
  return parseResponse(
    await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history, top_k: topK }),
    })
  );
}

/**
 * Retrieval-only search – returns raw chunks without LLM.
 * Useful for debugging.
 */
export async function searchChunks(question, topK = 4) {
  return parseResponse(
    await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, top_k: topK }),
    })
  );
}

/**
 * Submit thumbs-up / thumbs-down feedback.
 * @param {string} question
 * @param {string} answer
 * @param {number} rating   -1 = thumbs down, 1 = thumbs up
 * @param {string} comment  Optional free-text
 */
export async function submitFeedback(question, answer, rating, comment = "") {
  return parseResponse(
    await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, answer, rating, comment }),
    })
  );
}
