import { NavLink, Route, HashRouter, Routes, Navigate } from "react-router-dom";
import { RunsPage } from "./pages/RunsPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { DiagnosisPage } from "./pages/DiagnosisPage";
import { GatePage } from "./pages/GatePage";

export function App() {
  return (
    <HashRouter>
      <div className="layout">
        <nav className="layout__nav">
          <div className="layout__nav-title">寻迹</div>
          <NavLink to="/runs">运行记录</NavLink>
          <NavLink to="/incidents">事故</NavLink>
          <NavLink to="/gate">回归与门禁</NavLink>
        </nav>
        <main className="layout__main">
          <Routes>
            <Route path="/" element={<Navigate to="/runs" replace />} />
            <Route path="/runs" element={<RunsPage />} />
            <Route path="/incidents" element={<IncidentsPage />} />
            <Route path="/incidents/:incidentId" element={<DiagnosisPage />} />
            <Route path="/gate" element={<GatePage />} />
          </Routes>
        </main>
      </div>
    </HashRouter>
  );
}
