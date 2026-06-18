import { useState } from "react";
import { useNetwork, useLive } from "./hooks";
import CommandCenter from "./components/CommandCenter";
import Commissioner from "./components/Commissioner";

export default function App() {
  const [view, setView] = useState<"command" | "commissioner">("command");
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
        </div>
      </div>
      {view === "command" ? <CommandCenter net={net} live={live} /> : <Commissioner net={net} />}
    </div>
  );
}
