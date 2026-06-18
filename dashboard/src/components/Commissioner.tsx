import { useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { usePoll } from "../hooks";
import { post, formatInr, congestionColor } from "../api";

export default function Commissioner({ net }: { net?: any }) {
  const data = usePoll<any>("/commissioner", 15000).data;
  const economics = usePoll<any>("/economics", 15000).data;
  const segments: any[] = net?.segments || [];

  const [segId, setSegId] = useState("");
  const [op, setOp] = useState("add_flyover");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);

  async function runScenario() {
    const target = segId || segments[0]?.id;
    if (!target) return;
    setRunning(true);
    setResult(null);
    try {
      const r = await post("/planning/scenario", {
        id: `ui-${Date.now()}`,
        name: `${op} on ${target}`,
        edits: [{ op, target, params: op === "widen_lane" ? { delta: 2 } : {} }],
      });
      setResult(r);
    } finally {
      setRunning(false);
    }
  }

  const econ = economics?.summary || {};
  const risk: any[] = data?.accident_risk || [];
  const riskChart = risk.map((r) => ({ name: r.segment_id, risk: r.risk_pct }));

  return (
    <div className="body">
      <div className="sidebar left" style={{ width: 420 }}>
        <div className="card">
          <h3>Economic loss (today)</h3>
          <div className="kpi" style={{ color: "var(--red)" }}>{econ.cost_human || "—"}</div>
          <div className="kpi-row" style={{ marginTop: 10 }}>
            <div className="kpi-box"><div className="label">Vehicle-hours lost</div><div className="kpi small">{Math.round(econ.delay_veh_h || 0).toLocaleString()}</div></div>
            <div className="kpi-box"><div className="label">Fuel (L)</div><div className="kpi small">{Math.round(econ.fuel_litres || 0).toLocaleString()}</div></div>
            <div className="kpi-box"><div className="label">CO₂ (kg)</div><div className="kpi small">{Math.round(econ.co2_kg || 0).toLocaleString()}</div></div>
          </div>
        </div>

        <div className="card">
          <h3>Future congestion (next hour)</h3>
          <div className="kpi" style={{ color: congestionColor(data?.forecast_avg ?? 0) }}>
            {(data?.forecast_avg ?? 0).toFixed(0)}/100
          </div>
          <div className="muted">network-average forecast</div>
        </div>

        <div className="card">
          <h3>Top cost segments</h3>
          <div className="list">
            {(economics?.breakdown || []).slice(0, 6).map((e: any) => (
              <div className="row" key={e.scope_id}>
                <div>{e.scope_id}<div className="meta">{Math.round(e.delay_veh_h)} veh-h lost</div></div>
                <span className="badge" style={{ background: "var(--panel2)" }}>{formatInr(e.cost_inr)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="main" style={{ overflowY: "auto", padding: 18 }}>
        <div className="card" style={{ marginBottom: 16 }}>
          <h3>Accident risk — highest-risk roads</h3>
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={riskChart}>
                <XAxis dataKey="name" tick={{ fill: "#9aa7c7", fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fill: "#9aa7c7", fontSize: 11 }} />
                <Tooltip contentStyle={{ background: "#141a2e", border: "1px solid #2a3357" }} />
                <Bar dataKey="risk">
                  {riskChart.map((r, i) => (
                    <Cell key={i} fill={congestionColor(r.risk)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <h3>Infrastructure What-If Simulator</h3>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
            <select value={op} onChange={(e) => setOp(e.target.value)}>
              <option value="add_flyover">Add flyover</option>
              <option value="widen_lane">Widen lane (+2)</option>
              <option value="close_road">Close road</option>
            </select>
            <select value={segId} onChange={(e) => setSegId(e.target.value)} style={{ minWidth: 220 }}>
              <option value="">(first segment)</option>
              {segments.slice(0, 60).map((s) => (
                <option key={s.id} value={s.id}>{s.id} — {s.name}</option>
              ))}
            </select>
            <button onClick={runScenario} disabled={running}>{running ? "Simulating…" : "Run simulation"}</button>
          </div>
          {result && (
            <div>
              <div style={{ marginBottom: 10 }}>{result.summary}</div>
              <div className="kpi-row">
                {Object.keys(result.baseline_kpis).map((k) => (
                  <div className="kpi-box" key={k}>
                    <div className="label">{k.replace(/_/g, " ")}</div>
                    <div className="kpi small">{Number(result.scenario_kpis[k]).toFixed(1)}</div>
                    <div className="meta" style={{ color: result.deltas[k] <= 0 ? "var(--green)" : "var(--red)" }}>
                      Δ {Number(result.deltas[k]).toFixed(1)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {!result && <div className="muted">Pick an intervention and run a digital-twin simulation to see KPI deltas.</div>}
        </div>
      </div>

      <div className="sidebar">
        <div className="card">
          <h3>Infrastructure & action recommendations</h3>
          <div className="list">
            {(data?.recommendations || []).map((r: any) => (
              <div className="rec" key={r.id}>
                <div className="action">{r.expected_effect}</div>
                <div><span className="chip">{r.action_type}</span><span className="chip">@ {r.target}</span></div>
                {r.rationale && <div className="why">Why: {r.rationale}</div>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
