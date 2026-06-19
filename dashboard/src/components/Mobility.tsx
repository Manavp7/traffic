import { usePoll } from "../hooks";
import { formatInr } from "../api";

export default function Mobility() {
  const transit = usePoll<any[]>("/transit", 8000).data || [];
  const freight = usePoll<any>("/freight?n=10", 12000).data;

  return (
    <div className="body">
      <div className="main" style={{ overflowY: "auto", padding: 18, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, alignContent: "start" }}>
        <div className="card">
          <h3>Public transport — bus routes</h3>
          <div className="list">
            {transit.map((r) => (
              <div className="row" key={r.id}>
                <div>{r.name}<div className="meta">{r.stops} stops · load {r.passenger_load_pct}%</div></div>
                <span className="badge" style={{ background: r.on_time ? "var(--green)" : "var(--red)", color: "#000" }}>
                  {r.on_time ? "on time" : `+${r.delay_min}m`}
                </span>
              </div>
            ))}
            {!transit.length && <div className="muted">No routes.</div>}
          </div>
        </div>

        <div className="card">
          <h3>Freight fleet</h3>
          {freight ? (
            <>
              <div className="kpi-row">
                <div className="kpi-box"><div className="label">Trucks</div><div className="kpi small">{freight.trucks}</div></div>
                <div className="kpi-box"><div className="label">Distance</div><div className="kpi small">{freight.total_distance_km} km</div></div>
                <div className="kpi-box"><div className="label">Fuel</div><div className="kpi small">{freight.total_fuel_litres} L</div></div>
              </div>
              <div className="kpi-row" style={{ marginTop: 10 }}>
                <div className="kpi-box"><div className="label">Fleet cost</div><div className="kpi small">{formatInr(freight.total_cost_inr)}</div></div>
                <div className="kpi-box"><div className="label">Avg delay</div><div className="kpi small">{freight.avg_delay_min} min</div></div>
              </div>
              <div className="list" style={{ marginTop: 10 }}>
                {(freight.trips || []).slice(0, 6).map((t: any) => (
                  <div className="row" key={t.id}>
                    <div>{t.id}<div className="meta">{(t.distance_m / 1000).toFixed(1)} km · {t.fuel_litres} L</div></div>
                    <span className="badge" style={{ background: "var(--panel2)" }}>{formatInr(t.cost_inr)}</span>
                  </div>
                ))}
              </div>
            </>
          ) : <div className="muted">Planning fleet…</div>}
        </div>
      </div>
    </div>
  );
}
