import { useState } from "react";
import { useGateRun, useSuites } from "../hooks/useXunji";
import { StatusTag } from "../components/StatusTag";

/** 回归与门禁：用例清单 + gate-run（默认警告不阻断，docs/12 决策） */
export function GatePage() {
  const { data: suites, isLoading } = useSuites();
  const gate = useGateRun();
  const [release, setRelease] = useState("1.0.0");
  const [mode, setMode] = useState("warn");
  const [lastDetail, setLastDetail] = useState<string | null>(null);

  return (
    <div>
      {isLoading ? (
        <div className="empty">加载中…</div>
      ) : !suites?.length ? (
        <div className="card">
          <div className="empty">
            暂无回归集 — 在诊断工作台确认根因后「一键转回归用例」即可创建
          </div>
        </div>
      ) : (
        suites.map((s) => (
          <div key={s.id} className="card">
            <h3 className="card__title">
              {s.name} <span className="mono muted">{s.id}</span>
            </h3>
            <p className="muted">用例 {s.cases.length} 条（来自已确认根因的事故）</p>
            <div>
              版本：
              <input value={release} onChange={(e) => setRelease(e.target.value)}
                     style={{ width: 90, marginRight: 8 }} />
              模式：
              <select value={mode} onChange={(e) => setMode(e.target.value)}
                      style={{ marginRight: 8 }}>
                <option value="warn">warn（警告不阻断）</option>
                <option value="block">block（阻断）</option>
              </select>
              <button className="btn btn--primary" disabled={gate.isPending}
                onClick={async () => {
                  const out = await gate.mutateAsync({ suiteId: s.id, release, mode });
                  setLastDetail(JSON.stringify(out.detail, null, 2));
                }}>
                运行门禁
              </button>
            </div>
            {s.recent_runs.length > 0 && (
              <table className="table" style={{ marginTop: 10 }}>
                <thead>
                  <tr><th>门禁运行</th><th>版本</th><th>模式</th><th>结论</th><th>时间</th></tr>
                </thead>
                <tbody>
                  {s.recent_runs.map((r) => (
                    <tr key={r.id}>
                      <td className="mono">{r.id}</td>
                      <td>{r.release}</td>
                      <td>{r.mode}</td>
                      <td><StatusTag value={r.result} /></td>
                      <td className="muted">{r.created_at.slice(0, 19)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))
      )}
      {lastDetail && (
        <div className="card">
          <h3 className="card__title">最近一次门禁明细</h3>
          <pre className="mono" style={{ whiteSpace: "pre-wrap" }}>{lastDetail}</pre>
        </div>
      )}
    </div>
  );
}
