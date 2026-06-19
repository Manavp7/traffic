import { usePoll } from "../hooks";

const AQI_COLOR: Record<string, string> = {
  good: "#22c55e", satisfactory: "#84cc16", moderate: "#eab308",
  poor: "#f97316", "very poor": "#ef4444", severe: "#991b1b",
};

export default function Sustainability() {
  const data = usePoll<any>("/sustainability", 10000).data;
  const aqi = data?.aqi;
  const pricing = data?.pricing;
  const ev = data?.ev;
  const carbon = data?.carbon;

  return (
    <div className="body">
      <div className="main" style={{ overflowY: "auto", padding: 18, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, alignContent: "start" }}>
        <div className="card">
          <h3>Air quality (AQI)</h3>
          <div className="kpi" style={{ color: AQI_COLOR[aqi?.category] || "#fff" }}>{aqi?.aqi ?? "—"}</div>
          <div className="muted">{aqi?.category ?? ""} · {aqi?.advisory ?? ""}</div>
          <div className="muted" style={{ marginTop: 6 }}>Health impact: {aqi?.health_impact_pct_at_risk ?? 0}% at elevated risk</div>
        </div>

        <div className="card">
          <h3>Carbon / net-zero</h3>
          <div className="kpi small">{Math.round(carbon?.co2_kg_per_day ?? 0).toLocaleString()} kg CO₂/day</div>
          <div className="muted">saved {Math.round(carbon?.co2_saved_kg_per_day ?? 0).toLocaleString()} kg/day vs baseline</div>
          <div style={{ marginTop: 8, background: "var(--panel)", borderRadius: 6, height: 10 }}>
            <div style={{ width: `${carbon?.net_zero_progress_pct ?? 0}%`, background: "var(--green)", height: 10, borderRadius: 6 }} />
          </div>
          <div className="muted" style={{ marginTop: 4 }}>{carbon?.net_zero_progress_pct ?? 0}% toward target</div>
        </div>

        <div className="card">
          <h3>Congestion pricing / tolling</h3>
          <div className="kpi-row">
            <div className="kpi-box"><div className="label">Priced roads</div><div className="kpi small">{pricing?.priced_segments ?? 0}</div></div>
            <div className="kpi-box"><div className="label">Avg toll</div><div className="kpi small">₹{pricing?.avg_toll_inr ?? 0}</div></div>
            <div className="kpi-box"><div className="label">Revenue/day</div><div className="kpi small">{pricing?.est_revenue_human ?? "—"}</div></div>
          </div>
          <div className="muted" style={{ marginTop: 6 }}>Est. diversion: {pricing?.est_diversion_pct ?? 0}%</div>
        </div>

        <div className="card">
          <h3>EV charging demand</h3>
          <div className="kpi-row">
            <div className="kpi-box"><div className="label">EV share</div><div className="kpi small">{ev?.ev_share_pct ?? 0}%</div></div>
            <div className="kpi-box"><div className="label">Demand</div><div className="kpi small">{Math.round(ev?.charging_demand_kwh ?? 0).toLocaleString()} kWh</div></div>
            <div className="kpi-box"><div className="label">Peak grid</div><div className="kpi small">{Math.round(ev?.peak_grid_load_kw ?? 0).toLocaleString()} kW</div></div>
          </div>
          {ev?.grid_alert && <div className="muted" style={{ color: "var(--red)", marginTop: 6 }}>⚠ grid load alert</div>}
        </div>
      </div>
    </div>
  );
}
