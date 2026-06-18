export const API_BASE =
  (import.meta as any).env?.VITE_API_URL || "http://localhost:8000";

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export function post<T = any>(path: string, body: unknown): Promise<T> {
  return api<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export function wsUrl(): string {
  return API_BASE.replace(/^http/, "ws") + "/ws";
}

export function congestionColor(score: number): string {
  if (score < 25) return "#22c55e";
  if (score < 50) return "#eab308";
  if (score < 75) return "#f97316";
  return "#ef4444";
}

export function formatInr(n: number): string {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)} cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)} L`;
  return `₹${Math.round(n).toLocaleString("en-IN")}`;
}

function csvRow(cells: (string | number)[]): string {
  return cells.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",");
}

export function buildReportCsv(
  economics: any,
  breakdown: any[],
  recs: any[]
): string {
  const lines: string[] = ["Traffic-OS Commissioner Report"];
  lines.push("");
  lines.push("Economic Impact (today)");
  lines.push(csvRow(["metric", "value"]));
  const e = economics || {};
  lines.push(csvRow(["cost", e.cost_human ?? ""]));
  lines.push(csvRow(["delay_veh_hours", Math.round(e.delay_veh_h ?? 0)]));
  lines.push(csvRow(["fuel_litres", Math.round(e.fuel_litres ?? 0)]));
  lines.push(csvRow(["co2_kg", Math.round(e.co2_kg ?? 0)]));
  lines.push("");
  lines.push("Top Cost Segments");
  lines.push(csvRow(["segment", "delay_veh_h", "cost_inr"]));
  for (const b of breakdown || []) lines.push(csvRow([b.scope_id, Math.round(b.delay_veh_h), Math.round(b.cost_inr)]));
  lines.push("");
  lines.push("Recommendations");
  lines.push(csvRow(["action", "target", "expected_effect", "rationale"]));
  for (const r of recs || []) lines.push(csvRow([r.action_type, r.target, r.expected_effect, r.rationale || ""]));
  return lines.join("\n");
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
