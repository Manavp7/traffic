import { useState } from "react";
import { post } from "../api";

type Msg = { role: "user" | "bot"; text: string; tool?: string };

const SUGGESTIONS = [
  "Why is traffic bad today?",
  "Which junction causes maximum congestion?",
  "How many accidents this month?",
  "What is the congestion cost today?",
  "What should we do about it?",
  "Expected traffic next hour?",
];

export default function Copilot() {
  const [messages, setMessages] = useState<Msg[]>([
    { role: "bot", text: "Ask me about congestion, accidents, costs, forecasts or actions." },
  ]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);

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
      <h3>AI Copilot</h3>
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
          placeholder="Ask the Copilot…"
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask(q)}
          style={{ flex: 1 }}
        />
        <button onClick={() => ask(q)}>Ask</button>
      </div>
    </div>
  );
}
