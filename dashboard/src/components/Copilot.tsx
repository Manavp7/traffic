import { useRef, useState } from "react";
import { post } from "../api";
import { t, type Lang } from "../i18n";

type Msg = { role: "user" | "bot"; text: string; tool?: string };

const SUGGESTIONS = [
  "Why is traffic bad today?",
  "Which junction causes maximum congestion?",
  "How many accidents this month?",
  "What is the congestion cost today?",
  "What should we do about it?",
  "Expected traffic next hour?",
];

export default function Copilot({ lang = "en" }: { lang?: Lang }) {
  const [messages, setMessages] = useState<Msg[]>([
    { role: "bot", text: "Ask me about congestion, accidents, costs, forecasts or actions." },
  ]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const recogRef = useRef<any>(null);

  function startVoice() {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      setMessages((m) => [...m, { role: "bot", text: "Voice input is not supported in this browser." }]);
      return;
    }
    const r = new SR();
    recogRef.current = r;
    r.lang = lang === "hi" ? "hi-IN" : "en-IN";
    r.interimResults = false;
    r.onresult = (e: any) => {
      const text = e.results[0][0].transcript;
      setQ(text);
      ask(text);
    };
    r.onend = () => setListening(false);
    setListening(true);
    r.start();
  }

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    setMessages((m) => [...m, { role: "user", text: question }]);
    setQ("");
    setBusy(true);
    try {
      const r = await post("/copilot", { question });
      setMessages((m) => [...m, { role: "bot", text: r.answer, tool: r.tool }]);
    } catch {
      setMessages((m) => [...m, { role: "bot", text: "Sorry, I could not reach the Copilot service." }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card copilot">
      <h3>{t("copilot_title", lang)}</h3>
      <div className="messages">
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.text}
            {m.tool && <div className="tool">via {m.tool}</div>}
          </div>
        ))}
        {busy && <div className="msg bot">Thinking…</div>}
      </div>
      <div className="suggest">
        {SUGGESTIONS.map((s) => (
          <button key={s} onClick={() => ask(s)}>{s}</button>
        ))}
      </div>
      <div className="input">
        <input
          value={q}
          placeholder={t("copilot_placeholder", lang)}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask(q)}
          style={{ flex: 1 }}
        />
        <button className="secondary" onClick={startVoice} disabled={listening}>
          {listening ? "…" : t("listen", lang)}
        </button>
        <button onClick={() => ask(q)}>{t("ask", lang)}</button>
      </div>
    </div>
  );
}
