import { useState } from "react";
import { post, formatInr } from "../api";
import { usePoll } from "../hooks";

export default function Enforcement() {
  const summary = usePoll<any>("/enforcement/challans/summary", 8000).data;
  const challans = usePoll<any[]>("/enforcement/challans", 8000).data || [];
  const watchlist = usePoll<any[]>("/enforcement/watchlist", 10000).data || [];
  const scores = usePoll<any[]>("/safety/driver-scores?n=8", 10000).data || [];
  const nearMiss = usePoll<any[]>("/safety/near-miss", 10000).data || [];
  const [plate, setPlate] = useState("");
  const [msg, setMsg] = useState("");

  async function issue() {
    const r = await post("/enforcement/challans/issue", {});
    setMsg(`Issued ${r.issued} challans`);
  }
  async function addWatch() {
    if (!plate) return;
    await post("/enforcement/watchlist", { plate, reason: "stolen" });
    setPlate("");
  }

  return (
    <div className="body">
      <div className="main" style={{ overflowY: "auto", padding: 18, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, alignContent: "start" }}>
        <div className="card">
          <h3>e-Challans</h3>
          <div className="kpi-row">
            <div className="kpi-box"><div className="label">Total</div><div className="kpi small">{summary?.total ?? 0}</div></div>
            <div className="kpi-box"><div className="label">Paid</div><div className="kpi small">{summary?.paid ?? 0}</div></div>
            <div className="kpi-box"><div className="label">Fines</div><div className="kpi small">{formatInr(summary?.total_fine_inr ?? 0)}</div></div>
          </div>
          <div style={{ marginTop: 10 }}>
            <button onClick={issue}>Issue challans from violations</button>
            {msg && <span className="muted" style={{ marginLeft: 8 }}>{msg}</span>}
          </div>
          <div className="list" style={{ marginTop: 10 }}>
            {challans.slice(0, 6).map((c) => (
              <div className="row" key={c.id}>
                <div>{c.plate}<div className="meta">{c.violation_type} · evidence ✓ {c.evidence_sha256?.slice(0, 8)}</div></div>
                <span className="badge" style={{ background: "var(--panel2)" }}>{formatInr(c.fine_inr)}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h3>Stolen / blacklist watchlist</h3>
          <div style={{ display: "flex", gap: 8 }}>
            <input value={plate} onChange={(e) => setPlate(e.target.value)} placeholder="Plate e.g. KA01AB1234" style={{ flex: 1 }} />
            <button onClick={addWatch}>Add</button>
          </div>
          <div className="list" style={{ marginTop: 10 }}>
            {watchlist.map((w) => (
              <div className="row" key={w.plate}><div>{w.plate}</div><span className="badge" style={{ background: "var(--red)", color: "#000" }}>{w.reason}</span></div>
            ))}
            {!watchlist.length && <div className="muted">No watchlisted plates.</div>}
          </div>
        </div>

        <div className="card">
          <h3>Driver-behavior scoring</h3>
          <div className="list">
            {scores.map((s) => (
              <div className="row" key={s.track_id}>
                <div>{s.track_id}<div className="meta">brake {s.harsh_braking} · weave {s.weaving}</div></div>
                <span className="badge" style={{ background: s.rating === "high" ? "var(--red)" : s.rating === "medium" ? "var(--amber)" : "var(--green)", color: "#000" }}>{s.risk_score}</span>
              </div>
            ))}
            {!scores.length && <div className="muted">No driver data yet.</div>}
          </div>
        </div>

        <div className="card">
          <h3>Pedestrian near-misses</h3>
          <div className="list">
            {nearMiss.slice(0, 8).map((n, i) => (
              <div className="row" key={i}>
                <div>{n.vru_class} ↔ {n.vehicle_track}<div className="meta">{n.distance_m} m @ {n.vehicle_speed_kph} km/h</div></div>
                <span className="badge" style={{ background: "var(--amber)", color: "#000" }}>{n.severity}</span>
              </div>
            ))}
            {!nearMiss.length && <div className="muted">No near-misses detected.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
