import { useMemo, useState } from "react";
import { api, post } from "../api";
import { usePoll } from "../hooks";

const TYPES = ["accident", "pothole", "blockage"];

export default function Citizen({ net }: { net?: any }) {
  const summary = usePoll<any>("/intelligence/summary", 8000).data;
  const reports = usePoll<any[]>("/reports", 8000).data || [];
  const junctions: any[] = net?.junctions || [];
  const jById = useMemo(() => Object.fromEntries(junctions.map((j) => [j.id, j])), [junctions]);

  const [rtype, setRtype] = useState("pothole");
  const [loc, setLoc] = useState("");
  const [note, setNote] = useState("");
  const [sent, setSent] = useState("");

  const [origin, setOrigin] = useState("");
  const [dest, setDest] = useState("");
  const [route, setRoute] = useState<any>(null);
  const [routeErr, setRouteErr] = useState("");

  async function submit() {
    const j = jById[loc] || junctions[0];
    if (!j) return;
    const id = `C-${Date.now()}`;
    await post("/reports", {
      id, ts: new Date().toISOString(), type: rtype, lat: j.lat, lon: j.lon, note,
    });
    setSent(`Report ${id} submitted. Thank you!`);
    setNote("");
  }

  async function findRoute() {
    setRouteErr("");
    setRoute(null);
    try {
      const r = await api(`/intelligence/travel-time?origin=${origin || junctions[0]?.id}&destination=${dest || junctions[junctions.length - 1]?.id}`);
      setRoute(r);
    } catch {
      setRouteErr("No route found between those points.");
    }
  }

  return (
    <div className="body">
      <div className="main" style={{ overflowY: "auto", padding: 18, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, alignContent: "start" }}>
        <div className="card">
          <h3>Live traffic</h3>
          <div className="kpi">{(summary?.avg_congestion ?? 0).toFixed(0)}/100</div>
          <div className="muted">{summary?.level ?? "—"} · {summary?.severe ?? 0} severe spots citywide</div>
        </div>

        <div className="card">
          <h3>Route suggestion</h3>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <select value={origin} onChange={(e) => setOrigin(e.target.value)}>
              <option value="">From…</option>
              {junctions.slice(0, 80).map((j) => <option key={j.id} value={j.id}>{j.name}</option>)}
            </select>
            <select value={dest} onChange={(e) => setDest(e.target.value)}>
              <option value="">To…</option>
              {junctions.slice(0, 80).map((j) => <option key={j.id} value={j.id}>{j.name}</option>)}
            </select>
            <button onClick={findRoute}>Find route</button>
          </div>
          {route && (
            <div style={{ marginTop: 10 }} className="kpi-row">
              <div className="kpi-box"><div className="label">Now</div><div className="kpi small">{Math.round(route.current_s / 60)} min</div></div>
              <div className="kpi-box"><div className="label">Free-flow</div><div className="kpi small">{Math.round(route.free_flow_s / 60)} min</div></div>
              <div className="kpi-box"><div className="label">Delay</div><div className="kpi small" style={{ color: "var(--amber)" }}>+{Math.round(route.delay_s / 60)} min</div></div>
            </div>
          )}
          {routeErr && <div className="muted" style={{ marginTop: 8 }}>{routeErr}</div>}
        </div>

        <div className="card">
          <h3>Report an issue</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <select value={rtype} onChange={(e) => setRtype(e.target.value)}>
              {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <select value={loc} onChange={(e) => setLoc(e.target.value)}>
              <option value="">Nearest junction…</option>
              {junctions.slice(0, 80).map((j) => <option key={j.id} value={j.id}>{j.name}</option>)}
            </select>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Describe the issue…" rows={3} />
            <button onClick={submit}>Submit report</button>
            {sent && <div className="muted">{sent}</div>}
          </div>
        </div>

        <div className="card">
          <h3>Recent citizen reports</h3>
          <div className="list">
            {reports.slice(0, 8).map((r) => (
              <div className="row" key={r.id}>
                <div>{r.type}<div className="meta">{r.note || "—"}</div></div>
                <span className="badge" style={{ background: "var(--panel2)" }}>{r.status}</span>
              </div>
            ))}
            {!reports.length && <div className="muted">No reports yet.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
