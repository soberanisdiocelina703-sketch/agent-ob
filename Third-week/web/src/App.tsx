import { useState } from "react";
import { NavLink, Route, HashRouter, Routes, Navigate, useLocation } from "react-router-dom";
import { RunsPage } from "./pages/RunsPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { DiagnosisPage } from "./pages/DiagnosisPage";
import { GatePage } from "./pages/GatePage";

const TITLES: [string, string][] = [
  ["/incidents/", "诊断工作台"],
  ["/incidents", "事故列表"],
  ["/gate", "回归集与门禁"],
  ["/runs", "运行记录"],
];

function Topbar() {
  const { pathname } = useLocation();
  const title = TITLES.find(([p]) => pathname.startsWith(p))?.[1] ?? "运行记录";
  return (
    <div className="topbar">
      <div className="crumb">
        对账 Agent（演示环境）<b>{title}</b>
      </div>
      <div className="userchip">
        <span>演示复核人</span>
        <div className="avatar">寻</div>
      </div>
    </div>
  );
}

function Guide() {
  const [open, setOpen] = useState(true);
  if (!open) return null;
  return (
    <div className="guide">
      <div className="gi">🧭</div>
      <div>
        <b>快速排障：发现 → 诊断 → 复核 → 转用例 → 门禁</b>
        <div className="steps">
          <em>1</em>在「事故列表」点开一条事故 →
          <em>2</em>在「诊断工作台」查看首故障点 Top-3、展开支持证据与反证 →
          <em>3</em>对照下方「成功/失败 Diff」的首分歧 →
          <em>4</em>点「确认是根因」完成复核 →
          <em>5</em>「一键转回归用例」，最后到「回归集与门禁」运行门禁查看结论。
          <span className="small" style={{ color: "#94a3b8" }}>
            （数据来自真实运行，诊断为现场计算）
          </span>
        </div>
      </div>
      <div className="close" onClick={() => setOpen(false)} role="button" aria-label="关闭引导">
        ✕
      </div>
    </div>
  );
}

export function App() {
  return (
    <HashRouter>
      <div className="app">
        <aside className="sidebar">
          <div className="logo">
            <b>寻迹</b>
            <span>Agent 链路诊断平台</span>
          </div>
          <nav className="nav">
            <NavLink to="/runs"><span className="ico">▶</span>运行记录</NavLink>
            <NavLink to="/incidents"><span className="ico">⚠</span>事故列表</NavLink>
            <NavLink to="/gate"><span className="ico">🛡</span>回归集与门禁</NavLink>
          </nav>
          <div className="sb-foot">
            寻迹 0.1.0（第三周 T1）<br />对账 Agent · 演示环境
          </div>
        </aside>
        <main className="main">
          <Topbar />
          <Guide />
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
