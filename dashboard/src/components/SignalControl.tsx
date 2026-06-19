import { useState } from "react";
import { post } from "../api";

export default function SignalControl() {
  const [status, setStatus] = useState<string>("");
  const [auto, setAuto] = useState(false);
  const [busy, setBusy] = useState(false);

  async function apply() {
    setBusy(true);
    try {
      const r = await post("/signals/apply", {});
      setStatus(`Applied adaptive plan to ${r.applied} signals`);
    } catch {
      setStatus("Failed to apply plan");
    } finally {
      setBusy(false);
    }
  }

  async function toggleAuto() {
    const next = !auto;
    setAuto(next);
    try {
      await post("/signals/auto", { enabled: next });
      setStatus(next ? "Auto-adaptive control ON" : "Auto-adaptive control OFF");
    } catch {
      setAuto(!next);
    }
  }

  return (
    <div className="card">
      <h3>Smart Signal Control</h3>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <button onClick={apply} disabled={busy}>{busy ? "Applying…" : "Apply adaptive plan"}</button>
        <button className="secondary" onClick={toggleAuto}>
          {auto ? "● Auto: ON" : "○ Auto: OFF"}
        </button>
      </div>
      {status && <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>{status}</div>}
      <div className="muted" style={{ marginTop: 6, fontSize: 11 }}>
        Max-pressure engine reallocates green time to the busiest approaches.
      </div>
    </div>
  );
}
