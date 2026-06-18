import { useState } from "react";
import MapView from "./MapView";
import Copilot from "./Copilot";
import SignalControl from "./SignalControl";
import { usePoll, type Live } from "../hooks";
import { congestionColor, post } from "../api";

const ETYPES = ["ambulance", "fire", "police", "disaster"];

const LEVEL = (s: number) => (s < 25 ? "free" : s < 50 ? "moderate" : s < 75 ? "heavy" : "severe");

export default function CommandCenter({ net, live }: { net?: any; live: Live }) {
  const summary = usePoll<any>("/intelligence/summary", 5000).data;
  const hotspots = usePoll<any[]>("/intelligence/hotspots?n=6", 6000).data || [];
  const bottlenecks = usePoll<any[]>("/intelligence/bottlenecks?n=4", 6000).data || [];
  const recs = usePoll<any[]>("/recommendations?n=6", 8000).data || [];
  const alerts = usePoll<any[]>("/alerts", 5000).data || [];

  const sevColor: Record<string, string> = {
    critical: "#ef4444", high: "#f97316", medium: "#eab308",
  };

  // emergency corridor builder
  const [etype, setEtype] = useState("ambulance");
  const [picking, setPicking] = useState(false);
  const [origin, setOrigin] = useState<{ lat: number; lon: number } | null>(null);
  const [corridor, setCorridor] = useState<any>(null);

  async function onMapClick(lat: number, lon: number) {
    if (!picking) return;
    if (!origin) {
      setOrigin({ lat, lon });
      return;
    }
    try {
      const r = await post("/emergency", {
        type: etype, lat: origin.lat, lon: origin.lon, dest_lat: lat, dest_lon: lon,
      });
      setCorridor(r);
    } catch {
      setCorridor(null);
    }
    setOrigin(null);
    setPicking(false);
  }

  return (
    <div className="body">
      <div className="sidebar left">
        {alerts.length > 0 && (
          <div className="card">
            <h3>⚠ Alerts ({alerts.length})</h3>
            <div className="list">
              {alerts.slice(0, 6).map((a, i) => (
                <div className="row" key={i} style={{ borderLeft: `3px solid ${sevColor[a.severity] || "#888"}` }}>
                  <div style={{ fontSize: 12 }}>{a.message}<div className="meta">{a.kind} · {a.severity}</div></div>
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="card">
          <h3>Network status</h3>
          <div className="kpi" style={{ color: congestionColor(summary?.avg_congestion ?? 0) }}>
            {(summary?.avg_congestion ?? 0).toFixed(0)}/100
          </div>
          <div className="muted">{LEVEL(summary?.avg_congestion ?? 0)} · {summary?.severe ?? 0} severe segments</div>
          <div className="kpi-row" style={{ marginTop: 10 }}>
            <div className="kpi-box"><div className="label">Live vehicles</div><div className="kpi small">{live.active_vehicles}</div></div>
            <div className="kpi-box"><div className="label">Weather</div><div className="kpi small">{live.weather}</div></div>
          </div>
        </div>

        <div className="card">
          <h3>Top hotspots</h3>
          <div className="list">
            {hotspots.map((h) => (
              <div className="row" key={h.junction_id}>
                <div>{h.name}<div className="meta">{h.junction_id}</div></div>
                <span className="badge" style={{ background: congestionColor(h.congestion), color: "#000" }}>{h.congestion.toFixed(0)}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h3>Bottlenecks (root cause)</h3>
          <div className="list">
            {bottlenecks.map((b) => (
              <div className="row" key={b.segment_id} style={{ display: "block" }}>
                <div><b>{b.name}</b></div>
                <div className="meta">{b.explanation}</div>
              </div>
            ))}
            {!bottlenecks.length && <div className="muted">No bottlenecks detected.</div>}
          </div>
        </div>
      </div>

      <div className="main">
        <MapView
          net={net}
          congestion={live.congestion}
          vehicles={live.vehicles}
          incidents={live.incidents}
          corridorSegments={corridor?.route_segments}
          onMapClick={onMapClick}
        />
        <div className="stat-overlay">
          <div className="stat-pill"><div className="n">{live.tick}</div><div className="l">tick</div></div>
          <div className="stat-pill"><div className="n">{live.vehicles.length}</div><div className="l">tracked</div></div>
          <div className="stat-pill"><div className="n">{live.incidents.length}</div><div className="l">incidents</div></div>
        </div>
        <div className="legend">
          <div style={{ marginBottom: 6, color: "var(--muted)" }}>Congestion</div>
          {[["free", 10], ["moderate", 40], ["heavy", 60], ["severe", 90]].map(([l, v]) => (
            <div className="item" key={l as string}>
              <span className="swatch" style={{ background: congestionColor(v as number) }} /> {l}
            </div>
          ))}
        </div>
      </div>

      <div className="sidebar">
        <div className="card">
          <h3>AI Recommendations</h3>
          <div className="list">
            {recs.map((r) => (
              <div className="rec" key={r.id}>
                <div className="action">{r.expected_effect}</div>
                <div><span className="chip">{r.action_type}</span><span className="chip">@ {r.target}</span><span className="chip">impact {r.impact_score}</span></div>
                {r.rationale && <div className="why">Why: {r.rationale}</div>}
              </div>
            ))}
            {!recs.length && <div className="muted">No actions needed — traffic flowing.</div>}
          </div>
        </div>
        <div className="card">
          <h3>Emergency Green Corridor</h3>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <select value={etype} onChange={(e) => setEtype(e.target.value)}>
              {ETYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <button onClick={() => { setPicking(true); setOrigin(null); setCorridor(null); }}>
              {picking ? (origin ? "Click destination…" : "Click origin…") : "Plan corridor"}
            </button>
          </div>
          {picking && <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
            Click two points on the map to route an emergency vehicle.
          </div>}
          {corridor && (
            <div style={{ marginTop: 10 }}>
              <div className="kpi-row">
                <div className="kpi-box"><div className="label">Baseline ETA</div><div className="kpi small">{Math.round(corridor.baseline_eta_s)}s</div></div>
                <div className="kpi-box"><div className="label">Corridor ETA</div><div className="kpi small" style={{ color: "var(--green)" }}>{Math.round(corridor.eta_s)}s</div></div>
              </div>
              <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
                {corridor.route_segments.length} segments · {corridor.signals_preempted.length} signals preempted ·
                saves {Math.max(0, Math.round(corridor.baseline_eta_s - corridor.eta_s))}s
                ({Math.round(corridor.distance_m)} m)
              </div>
            </div>
          )}
        </div>
        <SignalControl />
        <Copilot />
      </div>
    </div>
  );
}
