import { usePoll } from "../hooks";
import { formatInr, congestionColor, getRole } from "../api";

export default function National() {
  const data = usePoll<any>("/national", 10000).data;

  if (getRole() !== "commissioner") {
    return (
      <div className="body"><div className="main" style={{ padding: 40 }}>
        <div className="card"><h3>Access restricted</h3>
          <div className="muted">The National rollup requires the Commissioner role.</div></div>
      </div></div>
    );
  }

  const cities = data?.cities || [];

  return (
    <div className="body">
      <div className="main" style={{ overflowY: "auto", padding: 18, display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="card">
          <h3>National rollup</h3>
          {data?.status === "warming" ? (
            <div className="muted">Warming city simulations…</div>
          ) : (
            <div className="kpi-row">
              <div className="kpi-box"><div className="label">Cities</div><div className="kpi small">{data?.city_count ?? 0}</div></div>
              <div className="kpi-box"><div className="label">National cost / day</div><div className="kpi small" style={{ color: "var(--red)" }}>{data?.national_cost_human ?? "—"}</div></div>
              <div className="kpi-box"><div className="label">Avg congestion</div><div className="kpi small" style={{ color: congestionColor(data?.national_avg_congestion ?? 0) }}>{(data?.national_avg_congestion ?? 0).toFixed(0)}/100</div></div>
              <div className="kpi-box"><div className="label">Severe segments</div><div className="kpi small">{data?.total_severe ?? 0}</div></div>
            </div>
          )}
        </div>

        <div className="card">
          <h3>Cities</h3>
          <div className="list">
            {cities.map((c: any) => (
              <div className="row" key={c.id}>
                <div>{c.name}<div className="meta">{c.segments} segments · {c.severe} severe</div></div>
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <span className="badge" style={{ background: congestionColor(c.avg_congestion), color: "#000" }}>{c.avg_congestion.toFixed(0)}</span>
                  <span className="badge" style={{ background: "var(--panel2)" }}>{formatInr(c.cost_inr)}</span>
                </div>
              </div>
            ))}
            {!cities.length && <div className="muted">No city data yet.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
