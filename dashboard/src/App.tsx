import { useState } from "react";
import { useNetwork, useLive } from "./hooks";
import CommandCenter from "./components/CommandCenter";
import Commissioner from "./components/Commissioner";
import Citizen from "./components/Citizen";

export default function App() {
  const [view, setView] = useState<"command" | "commissioner" | "citizen">("command");
  const { data: net } = useNetwork();
  const live = useLive();

  return (
    <div className="app">
      <div className="topbar">
        <h1>Traffic-OS <span className="tag">· National Traffic Intelligence OS</span></h1>
        <div className="muted" style={{ fontSize: 12 }}>Detect · Predict · Recommend · Simulate · Optimize</div>
        <div className="spacer" />
        <div className="tabs">
          <div className={`tab ${view === "command" ? "active" : ""}`} onClick={() => setView("command")}>
            Command Center
          </div>
          <div className={`tab ${view === "commissioner" ? "active" : ""}`} onClick={() => setView("commissioner")}>
            Commissioner
          </div>
          <div className={`tab ${view === "citizen" ? "active" : ""}`} onClick={() => setView("citizen")}>
            Citizen
          </div>
        </div>
      </div>
      {view === "command" && <CommandCenter net={net} live={live} />}
      {view === "commissioner" && <Commissioner net={net} />}
      {view === "citizen" && <Citizen net={net} />}
    </div>
  );
}
