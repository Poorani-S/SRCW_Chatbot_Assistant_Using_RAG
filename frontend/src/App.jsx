/**
 * App.jsx – Root component for SRCW Assistant.
 * Renders the sidebar (brand, health status, language toggle)
 * and the main chat panel.
 */
import { useEffect, useState } from "react";
import { Wifi, WifiOff, RefreshCw, Globe } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Chat from "@/components/Chat";
import { getHealth } from "@/lib/api";

export default function App() {
  const [health, setHealth] = useState(null);   // null=checking, false=down, object=ok
  const [lang, setLang]     = useState("en");   // "en" | "ta"

  const fetchHealth = () => {
    setHealth(null);
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(false));
  };

  useEffect(() => {
    fetchHealth();
    // Re-check every 60s to detect backend going down
    const id = setInterval(fetchHealth, 60_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="grid h-screen grid-cols-1 md:grid-cols-[300px_1fr] overflow-hidden">

      {/* ════════════════ Sidebar ════════════════ */}
      <aside className="glass-sidebar flex flex-col gap-5 overflow-y-auto border-b border-border/50 p-5 md:border-b-0 md:border-r hidden md:flex">

        {/* Brand */}
        <div className="flex items-center gap-3 pt-1">
          <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-emerald-950/80 to-[#03523c]/40 border border-emerald-500/30 flex items-center justify-center shrink-0 shadow-md shadow-emerald-950/50 p-1.5 animate-glow-pulse">
            <img
              src="/crest.svg"
              alt="SRCW Crest Emblem"
              className="h-full w-full object-contain filter drop-shadow-[0_1px_4px_rgba(0,0,0,0.5)]"
              onError={(e) => {
                e.target.style.display = "none";
                e.target.parentElement.innerHTML = '<span class="text-xl">🏛️</span>';
              }}
            />
          </div>
          <div className="min-w-0">
            <h1 className="text-base font-bold leading-tight text-foreground tracking-tight">
              SRCW Chatbot
            </h1>
            <p className="text-[11px] text-emerald-400 font-medium mt-0.5 leading-tight">
              Educate to Empower
            </p>
          </div>
        </div>

        {/* College info card */}
        <div className="rounded-xl bg-emerald-950/30 border border-emerald-500/20 p-4 space-y-3 shadow-sm">
          <div className="flex items-start gap-2.5">
            <div className="w-6 h-6 rounded-md bg-emerald-500/15 border border-emerald-500/25 flex items-center justify-center shrink-0 mt-0.5 text-xs">
              🏛️
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-foreground leading-snug">
                Sri Ramakrishna College of Arts & Science for Women
              </p>
              <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                <span className="text-[10px] px-1.5 py-0.5 rounded font-semibold bg-[#c8a634]/15 text-[#e5be44] border border-[#c8a634]/30">
                  NAAC A+ Grade
                </span>
                <span className="text-[10px] text-muted-foreground">
                  Bharathiar Univ.
                </span>
              </div>
            </div>
          </div>
          <div className="space-y-1.5 text-[11px] text-muted-foreground pt-1 border-t border-emerald-500/10">
            <p className="flex items-center gap-1.5"><span>📍</span> New Siddhapudur, Coimbatore – 641044</p>
            <p className="flex items-center gap-1.5"><span>📞</span> +91 7373144766</p>
            <p className="flex items-center gap-1.5"><span>✉️</span> enquiry@srcw.ac.in</p>
            <a
              href="https://srcw.ac.in"
              target="_blank"
              rel="noreferrer"
              className="text-emerald-400 hover:text-emerald-300 font-medium transition-colors inline-flex items-center gap-1 mt-1"
            >
              🌐 srcw.ac.in ↗
            </a>
          </div>
        </div>

        {/* Language toggle */}
        <div>
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2 font-semibold">
            Language / மொழி
          </p>
          <div className="flex gap-2">
            <button
              className={`chip flex-1 justify-center text-center transition-all ${lang === "en" ? "border-emerald-500/60 bg-emerald-500/20 text-white font-semibold shadow-sm shadow-emerald-900/40" : "opacity-80 hover:opacity-100"}`}
              onClick={() => setLang("en")}
            >
              🇬🇧 English
            </button>
            <button
              className={`chip flex-1 justify-center text-center transition-all ${lang === "ta" ? "border-emerald-500/60 bg-emerald-500/20 text-white font-semibold shadow-sm shadow-emerald-900/40" : "opacity-80 hover:opacity-100"}`}
              onClick={() => setLang("ta")}
            >
              🇮🇳 தமிழ்
            </button>
          </div>
        </div>

        {/* Status at bottom */}
        <div className="mt-auto space-y-2 text-xs">
          {health === null && (
            <p className="flex items-center gap-2 text-muted-foreground animate-fade-in">
              <span className="inline-block h-2 w-2 rounded-full bg-muted-foreground animate-pulse" />
              Connecting to backend…
            </p>
          )}

          {health === false && (
            <div
              role="alert"
              className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-destructive animate-fade-in"
            >
              <div className="flex items-center gap-2 mb-1">
                <WifiOff className="size-3.5 shrink-0" />
                <span className="font-medium text-xs">Backend not reachable</span>
              </div>
              <p className="text-[11px] opacity-80">
                Start the server:<br />
                <code className="font-mono">uvicorn app.main:app --reload</code>
              </p>
              <button
                onClick={fetchHealth}
                className="mt-2 text-[11px] flex items-center gap-1 opacity-70 hover:opacity-100"
              >
                <RefreshCw className="size-3" /> Retry
              </button>
            </div>
          )}

          {health && health !== false && (
            <div className="space-y-2 animate-fade-in">
              <div className="flex items-center gap-2">
                <Wifi className="size-3.5 text-emerald-400" />
                <span className="text-emerald-400 text-[11px] font-medium">Backend connected</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <Badge variant="primary" className="text-[10px]">
                  {health.provider} · {health.model?.split("/").pop() || health.model}
                </Badge>
                {health.chunks && (
                  <Badge variant="outline" className="text-[10px]">
                    {health.chunks} chunks indexed
                  </Badge>
                )}
              </div>
            </div>
          )}
        </div>
      </aside>

      {/* ════════════════ Main Chat ════════════════ */}
      <main className="chat-bg min-h-0 overflow-hidden flex flex-col">
        <Chat
          lang={lang}
          onLangToggle={() => setLang((l) => (l === "en" ? "ta" : "en"))}
        />
      </main>
    </div>
  );
}
