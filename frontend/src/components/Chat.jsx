/**
 * Chat.jsx – Main chat interface for SRCW Assistant.
 *
 * Features:
 *  - Welcome screen with suggestion chips
 *  - Message bubbles (user + assistant)
 *  - Skeleton typing loader
 *  - Copy button per answer
 *  - Thumbs up/down feedback
 *  - Source citation badges (clickable → expand snippet panel)
 *  - Clear chat button
 *  - English / Tamil UI label toggle
 *  - Conversation history sent to /api/ask for context-aware follow-ups
 */
import { useEffect, useRef, useState, useCallback } from "react";
import {
  BookOpen, Send, Loader2, Copy, Check, ThumbsUp, ThumbsDown,
  ChevronDown, ChevronUp, ExternalLink, Trash2, Globe, Sparkles,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { askQuestion, submitFeedback } from "@/lib/api";

/* ─── Static Data ─────────────────────────────────────────────────────────── */
const SUGGESTION_CHIPS = {
  en: [
    "What courses does SRCW offer?",
    "How do I apply for admission?",
    "What scholarships are available?",
    "Tell me about placements",
    "Is there a hostel & transport?",
    "Contact the college",
  ],
  ta: [
    "SRCW என்ன படிப்புகள் வழங்குகிறது?",
    "சேர்க்கை எப்படி விண்ணப்பிப்பது?",
    "என்ன உதவித்தொகைகள் உள்ளன?",
    "வேலைவாய்ப்பு பற்றி சொல்லுங்கள்",
    "விடுதி மற்றும் போக்குவரத்து உண்டா?",
    "கல்லூரியை தொடர்பு கொள்ள",
  ],
};

const LABELS = {
  en: {
    placeholder: "Ask about SRCW – admissions, courses, hostel…",
    send: "Send",
    clearChat: "Clear chat",
    sources: "Sources",
    passages: "passages",
    copyAnswer: "Copy answer",
    copied: "Copied!",
    disclaimer:
      "Answers are generated from SRCW's published information. Please confirm important details with the college office.",
    welcomeTitle: "Hi! I'm the SRCW Assistant 👋",
    welcomeSub: "Ask me anything about Sri Ramakrishna College of Arts & Science for Women.",
    tryThese: "Try one of these to get started:",
    assistantLabel: "SRCW Assistant",
    toggleLang: "தமிழ்",
  },
  ta: {
    placeholder: "SRCW பற்றி கேளுங்கள் – சேர்க்கை, படிப்புகள், விடுதி…",
    send: "அனுப்பு",
    clearChat: "உரையாடலை அழி",
    sources: "ஆதாரங்கள்",
    passages: "பகுதிகள்",
    copyAnswer: "பதிலை நகலெடு",
    copied: "நகலெடுக்கப்பட்டது!",
    disclaimer:
      "இந்த பதில்கள் SRCW இன் வெளியிடப்பட்ட தகவல்களிலிருந்து உருவாக்கப்பட்டுள்ளன. முக்கியமான விவரங்களை கல்லூரி அலுவலகத்துடன் உறுதிப்படுத்திக் கொள்ளுங்கள்.",
    welcomeTitle: "வணக்கம்! நான் SRCW உதவியாளர் 👋",
    welcomeSub:
      "ஸ்ரீ ராமகிருஷ்ணா கல்லூரி பற்றி எதையும் கேளுங்கள்.",
    tryThese: "தொடங்க இதில் ஒன்றை தேர்ந்தெடுங்கள்:",
    assistantLabel: "SRCW உதவியாளர்",
    toggleLang: "English",
  },
};

/* ─── Citation Badges ────────────────────────────────────────────────────── */
function CitationBadges({ sources, onCitationClick }) {
  if (!sources?.length) return null;
  // Dedupe by URL
  const unique = [];
  const seen = new Set();
  for (const s of sources) {
    const key = s.url || s.source_url;
    if (!seen.has(key)) { seen.add(key); unique.push(s); }
  }
  return (
    <div className="mt-2 pl-9 flex flex-wrap gap-1.5 animate-fade-in">
      {unique.map((s, i) => (
        <Badge
          key={i}
          variant="citation"
          onClick={() => onCitationClick(i)}
          title={`Score: ${s.score ?? "?"} — Click to view source`}
        >
          {s.page ? `p.${s.page}` : `#${i + 1}`}
        </Badge>
      ))}
    </div>
  );
}

/* ─── Sources Panel ─────────────────────────────────────────────────────── */
function SourcesPanel({ sources, highlightIdx }) {
  if (!sources?.length) return null;
  return (
    <div className="mt-3 pl-9 space-y-2 animate-slide-up">
      <p className="text-xs font-medium text-muted-foreground">
        {sources.length} source passage{sources.length !== 1 ? "s" : ""} used
      </p>
      <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
        {sources.map((s, i) => {
          const isPdf = (s.url || "").startsWith("pdf:");
          const url = isPdf ? null : s.url;
          return (
            <div
              key={i}
              id={`source-${i}`}
              className={`source-card p-3 ${highlightIdx === i ? "highlight" : ""}`}
            >
              <div className="flex items-start justify-between gap-2 mb-1.5">
                <div className="flex items-center gap-2 flex-wrap min-w-0">
                  <Badge variant="citation" className="shrink-0">
                    {s.page ? `p.${s.page}` : `#${i + 1}`}
                  </Badge>
                  {s.category && (
                    <Badge variant="category" className="shrink-0 capitalize">
                      {s.category.replace("_", " ")}
                    </Badge>
                  )}
                  <span className="text-[10px] text-muted-foreground truncate">
                    {s.title || s.source_title}
                  </span>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <span className="text-[10px] text-muted-foreground">
                    {s.score ? `${(s.score * 100).toFixed(0)}%` : ""}
                  </span>
                  {url && (
                    <a
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-muted-foreground hover:text-citation transition-colors"
                      title="Open source page"
                    >
                      <ExternalLink className="size-3" />
                    </a>
                  )}
                </div>
              </div>
              {s.snippet && (
                <p className="font-serif text-xs leading-relaxed text-muted-foreground line-clamp-3">
                  <mark className="bg-highlight/15 text-foreground px-0.5 rounded">
                    {s.snippet}
                  </mark>
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Skeleton Loader ────────────────────────────────────────────────────── */
function SkeletonResponse({ label }) {
  return (
    <div className="space-y-1 animate-fade-in">
      <div className="flex items-center gap-2 mb-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/15">
          <Sparkles className="size-3.5 text-primary animate-pulse" />
        </div>
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
      </div>
      <div className="pl-9 space-y-2">
        <div className="thinking-dots flex gap-1.5 py-1">
          <span /><span /><span />
        </div>
        <div className="space-y-1.5">
          <div className="skeleton-line h-3.5 w-4/5 rounded" />
          <div className="skeleton-line h-3.5 w-3/5 rounded" />
          <div className="skeleton-line h-3.5 w-2/3 rounded" />
        </div>
      </div>
    </div>
  );
}

/* ─── Answer Text with simple markdown rendering ─────────────────────────── */
function AnswerText({ content }) {
  // Convert basic markdown: **bold**, bullet lists, numbered lists, URLs
  const lines = content.split("\n");
  return (
    <div className="prose-answer">
      {lines.map((line, i) => {
        if (!line.trim()) return <br key={i} />;
        // Bold
        const formatted = line.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
        // URLs
        const withLinks = formatted.replace(
          /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
          '<a href="$2" target="_blank" rel="noreferrer">$1</a>'
        );
        // Bullet points
        if (line.trimStart().startsWith("- ") || line.trimStart().startsWith("• ")) {
          return (
            <ul key={i} className="pl-4">
              <li dangerouslySetInnerHTML={{ __html: withLinks.replace(/^[-•]\s*/, "") }} />
            </ul>
          );
        }
        // Numbered list
        if (/^\d+\.\s/.test(line.trimStart())) {
          return (
            <ol key={i} className="pl-4">
              <li dangerouslySetInnerHTML={{ __html: withLinks.replace(/^\d+\.\s*/, "") }} />
            </ol>
          );
        }
        return <p key={i} dangerouslySetInnerHTML={{ __html: withLinks }} />;
      })}
    </div>
  );
}

/* ─── Main Chat Component ─────────────────────────────────────────────────── */
export default function Chat({ lang, onLangToggle }) {
  const labels = LABELS[lang] || LABELS.en;
  const chips  = SUGGESTION_CHIPS[lang] || SUGGESTION_CHIPS.en;

  const [messages, setMessages]           = useState([]);
  const [input, setInput]                 = useState("");
  const [busy, setBusy]                   = useState(false);
  const [expandedSources, setExpandedSources] = useState(null);
  const [highlightIdx, setHighlightIdx]   = useState(null);
  const [copiedIdx, setCopiedIdx]         = useState(null);
  const [feedbackIdx, setFeedbackIdx]     = useState({}); // msgIdx → rating
  const endRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  // Build history array (last 6 messages) for the API
  const buildHistory = useCallback(() => {
    return messages.slice(-6).map((m) => ({
      role: m.role,
      content: m.content,
    }));
  }, [messages]);

  function handleCitationClick(msgIndex, srcIndex) {
    if (expandedSources === msgIndex) {
      // If already open for same message, just highlight
      setHighlightIdx(srcIndex);
    } else {
      setExpandedSources(msgIndex);
      setHighlightIdx(srcIndex);
    }
    // Clear highlight after animation
    setTimeout(() => setHighlightIdx(null), 2000);
    // Scroll to sources
    requestAnimationFrame(() => {
      const el = document.getElementById(`source-${srcIndex}`);
      el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }

  function toggleSources(msgIndex) {
    setExpandedSources(expandedSources === msgIndex ? null : msgIndex);
  }

  async function copyAnswer(text, idx) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedIdx(idx);
      setTimeout(() => setCopiedIdx(null), 2000);
    } catch {/* ignore */}
  }

  async function handleFeedback(msgIdx, rating) {
    const msg = messages[msgIdx];
    const prevMsg = messages[msgIdx - 1];
    setFeedbackIdx((f) => ({ ...f, [msgIdx]: rating }));
    try {
      await submitFeedback(
        prevMsg?.content || "",
        msg.content,
        rating
      );
    } catch {/* ignore: feedback is best-effort */}
  }

  async function send(question) {
    const q = (question || input).trim();
    if (!q || busy) return;

    const history = buildHistory();
    setMessages((m) => [...m, { role: "user", content: q }]);
    setInput("");
    setBusy(true);
    setExpandedSources(null);

    try {
      const res = await askQuestion(q, history);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: res.answer,
          sources: res.sources || [],
          standalone: res.standalone_question,
        },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `⚠️ ${e.message}`, error: true, sources: [] },
      ]);
    } finally {
      setBusy(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }

  function clearChat() {
    setMessages([]);
    setExpandedSources(null);
    setHighlightIdx(null);
    setFeedbackIdx({});
    setCopiedIdx(null);
    inputRef.current?.focus();
  }

  return (
    <div className="flex h-full flex-col">
      {/* ── Top bar (mobile / embedded header) ── */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/50 bg-card/40 backdrop-blur-sm md:hidden">
        <div className="flex items-center gap-2">
          <img src="/logo.svg" alt="SRCW" className="h-7 w-auto" onError={(e) => { e.target.style.display = "none"; }} />
          <span className="font-semibold text-sm text-foreground">SRCW Assistant</span>
        </div>
        <button
          onClick={onLangToggle}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-primary transition-colors"
        >
          <Globe className="size-3.5" /> {labels.toggleLang}
        </button>
      </div>

      {/* ── Message area ── */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">

        {/* Welcome state */}
        {messages.length === 0 && !busy && (
          <div className="flex flex-col items-center justify-center min-h-full gap-8 animate-fade-in pb-8">
            {/* Logo + greeting */}
            <div className="text-center space-y-3">
              <div className="flex justify-center animate-float">
                <div className="h-20 w-20 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center shadow-lg shadow-primary/10">
                  <img
                    src="/logo.svg"
                    alt="SRCW"
                    className="h-14 w-14 object-contain"
                    onError={(e) => {
                      e.target.style.display = "none";
                      e.target.parentElement.innerHTML = '<span class="text-3xl">🏫</span>';
                    }}
                  />
                </div>
              </div>
              <div>
                <h2 className="text-xl font-semibold text-foreground">{labels.welcomeTitle}</h2>
                <p className="text-sm text-muted-foreground mt-1 max-w-xs mx-auto">{labels.welcomeSub}</p>
              </div>
            </div>

            {/* Suggestion chips */}
            <div className="w-full max-w-lg">
              <p className="text-xs text-muted-foreground text-center mb-3">{labels.tryThese}</p>
              <div className="flex flex-wrap gap-2 justify-center">
                {chips.map((chip) => (
                  <button
                    key={chip}
                    className="chip"
                    onClick={() => send(chip)}
                    disabled={busy}
                  >
                    {chip}
                  </button>
                ))}
              </div>
            </div>

            {/* Disclaimer */}
            <p className="text-[11px] text-muted-foreground/60 text-center max-w-sm px-4 leading-relaxed">
              ⚠️ {labels.disclaimer}
            </p>
          </div>
        )}

        {/* Messages */}
        {messages.map((m, i) =>
          m.role === "user" ? (
            /* User bubble */
            <div
              key={i}
              className="flex justify-end animate-message-in"
              style={{ animationDelay: `${Math.min(i * 0.04, 0.3)}s` }}
            >
              <div className="max-w-[80%] md:max-w-[70%] user-bubble rounded-2xl rounded-br-md px-4 py-2.5 text-sm shadow-md">
                {m.content}
              </div>
            </div>
          ) : (
            /* Assistant message */
            <div
              key={i}
              className="space-y-1 animate-message-in"
              style={{ animationDelay: `${Math.min(i * 0.04, 0.3)}s` }}
            >
              {/* Avatar row */}
              <div className="flex items-center gap-2 mb-1">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/12 shrink-0">
                  <Sparkles className="size-3.5 text-primary" />
                </div>
                <span className="text-xs font-medium text-muted-foreground">{labels.assistantLabel}</span>
              </div>

              {/* Answer */}
              <div className="pl-9 max-w-[90%] md:max-w-[80%]">
                {m.error ? (
                  <p className="text-sm text-destructive">{m.content}</p>
                ) : (
                  <AnswerText content={m.content} />
                )}
              </div>

              {/* Citation badges + actions row */}
              {!m.error && (
                <>
                  <CitationBadges
                    sources={m.sources}
                    onCitationClick={(srcIdx) => handleCitationClick(i, srcIdx)}
                  />

                  {/* Action buttons row */}
                  <div className="pl-9 mt-2 flex items-center gap-1 flex-wrap">
                    {/* Show/hide sources */}
                    {m.sources?.length > 0 && (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => toggleSources(i)}
                        title={expandedSources === i ? "Hide sources" : `${labels.sources} (${m.sources.length})`}
                        className="text-xs gap-1 px-2 w-auto h-7"
                      >
                        <BookOpen className="size-3.5" />
                        <span className="text-[11px]">{m.sources.length}</span>
                        {expandedSources === i
                          ? <ChevronUp className="size-3" />
                          : <ChevronDown className="size-3" />
                        }
                      </Button>
                    )}

                    {/* Copy button */}
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => copyAnswer(m.content, i)}
                      title={copiedIdx === i ? labels.copied : labels.copyAnswer}
                    >
                      {copiedIdx === i
                        ? <Check className="size-3.5 text-emerald-400" />
                        : <Copy className="size-3.5" />
                      }
                    </Button>

                    {/* Thumbs up/down feedback */}
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => handleFeedback(i, 1)}
                      title="Helpful"
                      className={feedbackIdx[i] === 1 ? "text-emerald-400" : ""}
                    >
                      <ThumbsUp className="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => handleFeedback(i, -1)}
                      title="Not helpful"
                      className={feedbackIdx[i] === -1 ? "text-destructive" : ""}
                    >
                      <ThumbsDown className="size-3.5" />
                    </Button>
                  </div>

                  {/* Sources panel */}
                  {expandedSources === i && (
                    <SourcesPanel sources={m.sources} highlightIdx={highlightIdx} />
                  )}
                </>
              )}
            </div>
          )
        )}

        {/* Typing skeleton */}
        {busy && <SkeletonResponse label={labels.assistantLabel} />}

        <div ref={endRef} />
      </div>

      {/* ── Input bar ── */}
      <div className="border-t border-border/50 bg-card/50 backdrop-blur-sm px-4 py-3">
        {/* Disclaimer strip */}
        {messages.length > 0 && (
          <p className="text-[10px] text-muted-foreground/50 text-center mb-2 leading-snug">
            {labels.disclaimer}
          </p>
        )}

        <form
          className="flex gap-2 max-w-3xl mx-auto"
          onSubmit={(e) => { e.preventDefault(); send(); }}
        >
          <Input
            ref={inputRef}
            id="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
            }}
            disabled={busy}
            placeholder={labels.placeholder}
            aria-label="Your question for SRCW Assistant"
            maxLength={1000}
            autoComplete="off"
          />
          {/* Clear chat (shows only after first message) */}
          {messages.length > 0 && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={clearChat}
              title={labels.clearChat}
              aria-label={labels.clearChat}
              disabled={busy}
              className="shrink-0"
            >
              <Trash2 className="size-4" />
            </Button>
          )}
          <Button
            id="send-btn"
            type="submit"
            size="icon"
            disabled={busy || !input.trim()}
            aria-label={labels.send}
            className="shrink-0"
          >
            {busy
              ? <Loader2 className="size-4 animate-spin" />
              : <Send className="size-4" />
            }
          </Button>
        </form>
      </div>
    </div>
  );
}
