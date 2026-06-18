import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { usePoll } from "../hooks";
import { congestionColor } from "../api";

export default function Analytics() {
  const ts = usePoll<any[]>("/analytics/timeseries?hours=48", 20000).data || [];
  const profile = usePoll<any>("/analytics/profile", 30000).data || { hourly: [], daily: [] };

  const tsData = ts.map((d) => ({
    t: new Date(d.ts).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit" }),
    congestion: d.congestion,
    speed: d.speed,
  }));

  return (
    <div className="body">
      <div className="main" style={{ overflowY: "auto", padding: 18, display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="card">
          <h3>Network congestion — last 48h</h3>
          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={tsData}>
                <XAxis dataKey="t" tick={{ fill: "#9aa7c7", fontSize: 10 }} minTickGap={40} />
                <YAxis domain={[0, 100]} tick={{ fill: "#9aa7c7", fontSize: 11 }} />
                <Tooltip contentStyle={{ background: "#141a2e", border: "1px solid #2a3357" }} />
                <Line type="monotone" dataKey="congestion" stroke="#4f8cff" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <h3>Diurnal profile — average congestion by hour of day</h3>
          <div style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={profile.hourly}>
                <XAxis dataKey="hour" tick={{ fill: "#9aa7c7", fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fill: "#9aa7c7", fontSize: 11 }} />
                <Tooltip contentStyle={{ background: "#141a2e", border: "1px solid #2a3357" }} />
                <Bar dataKey="congestion">
                  {profile.hourly.map((d: any, i: number) => (
                    <Cell key={i} fill={congestionColor(d.congestion)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <h3>Daily average congestion</h3>
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={profile.daily}>
                <XAxis dataKey="date" tick={{ fill: "#9aa7c7", fontSize: 10 }} minTickGap={20} />
                <YAxis domain={[0, 100]} tick={{ fill: "#9aa7c7", fontSize: 11 }} />
                <Tooltip contentStyle={{ background: "#141a2e", border: "1px solid #2a3357" }} />
                <Bar dataKey="congestion" fill="#4f8cff" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
