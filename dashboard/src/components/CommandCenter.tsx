import MapView from "./MapView";
import Copilot from "./Copilot";
import { usePoll, type Live } from "../hooks";
import { congestionColor } from "../api";

const LEVEL = (s: number) => (s < 25 ? "free" : s < 50 ? "moderate" : s < 75 ? "heavy" : "severe");

export default function CommandCenter({ net, live }: { net?: any; live: Live }) {
  const summary = usePoll<any>("/intelligence/summary", 5000).data;
  const hotspots = usePoll<any[]>("/intelligence/hotspots?n=6", 6000).data || [];
  const bottlenecks = usePoll<any[]>("/intelligence/bottlenecks?n=4", 6000).data || [];
  const recs = usePoll<any[]>("/recommendations?n=6", 8000).data || [];

  return (
    <div className="body">
      <div className="sidebar left">
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
        <Copilot />
      </div>
    </div>
  );
}
