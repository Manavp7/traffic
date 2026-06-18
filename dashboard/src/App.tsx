import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { setRole, getRole } from "./api";
import { useNetwork, useLive } from "./hooks";
import CommandCenter from "./components/CommandCenter";
import Commissioner from "./components/Commissioner";
import Citizen from "./components/Citizen";
import Analytics from "./components/Analytics";
import ThreeTwin from "./components/ThreeTwin";

type View = "command" | "commissioner" | "analytics" | "twin" | "citizen";

export default function App() {
  const [view, setView] = useState<View>("command");
  const [role, setRoleState] = useState(getRole());
  const qc = useQueryClient();
  const { data: net } = useNetwork();
  const live = useLive();

  function changeRole(r: string) {
    setRole(r);
    setRoleState(r);
    qc.invalidateQueries();
  }

  return (
    <div className="app">
      <div className="topbar">
        <h1>Traffic-OS <span className="tag">· National Traffic Intelligence OS</span></h1>
        <div className="muted" style={{ fontSize: 12 }}>Detect · Predict · Recommend · Simulate · Optimize</div>
        <div className="spacer" />
        <select value={role} onChange={(e) => changeRole(e.target.value)} title="Role (RBAC)"
                style={{ marginRight: 10 }}>
          <option value="commissioner">Commissioner</option>
          <option value="operator">Operator</option>
        </select>
        <div className="tabs">
          <div className={`tab ${view === "command" ? "active" : ""}`} onClick={() => setView("command")}>
            Command Center
          </div>
          <div className={`tab ${view === "commissioner" ? "active" : ""}`} onClick={() => setView("commissioner")}>
            Commissioner
          </div>
          <div className={`tab ${view === "analytics" ? "active" : ""}`} onClick={() => setView("analytics")}>
            Analytics
          </div>
          <div className={`tab ${view === "twin" ? "active" : ""}`} onClick={() => setView("twin")}>
            3D Twin
          </div>
          <div className={`tab ${view === "citizen" ? "active" : ""}`} onClick={() => setView("citizen")}>
            Citizen
          </div>
        </div>
      </div>
      {view === "command" && <CommandCenter net={net} live={live} />}
      {view === "commissioner" && <Commissioner net={net} />}
      {view === "analytics" && <Analytics />}
      {view === "twin" && <div className="body"><div className="main"><ThreeTwin net={net} live={live} /></div></div>}
      {view === "citizen" && <Citizen net={net} />}
    </div>
  );
}
