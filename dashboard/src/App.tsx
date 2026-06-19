import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { setRole, getRole } from "./api";
import { t, type Lang } from "./i18n";
import { useNetwork, useLive } from "./hooks";
import CommandCenter from "./components/CommandCenter";
import Commissioner from "./components/Commissioner";
import Citizen from "./components/Citizen";
import Analytics from "./components/Analytics";
import ThreeTwin from "./components/ThreeTwin";
import Mobility from "./components/Mobility";
import National from "./components/National";
import Enforcement from "./components/Enforcement";
import Sustainability from "./components/Sustainability";

type View =
  | "command" | "commissioner" | "national" | "analytics"
  | "twin" | "mobility" | "enforcement" | "sustainability" | "citizen";

export default function App() {
  const [view, setView] = useState<View>("command");
  const [lang, setLang] = useState<Lang>("en");
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
        <div className="muted" style={{ fontSize: 12 }}>{t("tagline", lang)}</div>
        <div className="spacer" />
        <select value={lang} onChange={(e) => setLang(e.target.value as Lang)} title="Language"
                style={{ marginRight: 8 }}>
          <option value="en">EN</option>
          <option value="hi">हिंदी</option>
        </select>
        <select value={role} onChange={(e) => changeRole(e.target.value)} title="Role (RBAC)"
                style={{ marginRight: 10 }}>
          <option value="commissioner">Commissioner</option>
          <option value="operator">Operator</option>
        </select>
        <div className="tabs">
          {(["command", "commissioner", "national", "analytics", "twin", "mobility", "enforcement", "sustainability", "citizen"] as View[]).map((v) => (
            <div key={v} className={`tab ${view === v ? "active" : ""}`} onClick={() => setView(v)}>
              {t(v, lang)}
            </div>
          ))}
        </div>
      </div>
      {view === "command" && <CommandCenter net={net} live={live} lang={lang} />}
      {view === "commissioner" && <Commissioner net={net} />}
      {view === "national" && <National />}
      {view === "analytics" && <Analytics />}
      {view === "twin" && <div className="body"><div className="main"><ThreeTwin net={net} live={live} /></div></div>}
      {view === "mobility" && <Mobility />}
      {view === "enforcement" && <Enforcement />}
      {view === "sustainability" && <Sustainability />}
      {view === "citizen" && <Citizen net={net} />}
    </div>
  );
}
