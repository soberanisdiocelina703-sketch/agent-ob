import { useState } from "react";
import { useGateRun, useSuites } from "../hooks/useXunji";
import { StatusTag } from "../components/StatusTag";
import { Icon } from "../components/Icon";

/** 回归集与门禁：用例清单 + gate-run（默认警告不阻断，docs/12 决策） */
export function GatePage() {
  const { data: suites, isLoading } = useSuites();
  const gate = useGateRun();
  const [release, setRelease] = useState("1.0.0");
  const [mode, setMode] = useState("warn");
  const [last, setLast] = useState<{ result: string; detail: unknown } | null>(null);

  return (
    <div className="page-in">
      {isLoading ? (
        <div className="empty">加载中…</div>
      ) : !suites?.length ? (
        <div className="card">
          <div className="empty">
            <Icon name="shield" className="lg" />
            暂无回归集
            <span className="tiny">在诊断工作台「确认是根因」后一键转回归用例即可创建</span>
          </div>
        </div>
      ) : (
        suites.map((s) => (
          <div key={s.id} className="card mb16">
            <div className="hd">
              <b>{s.name}</b>
              <span className="mono small muted">{s.id}</span>
              <span className="tag t-brand">{s.cases.length} 条用例</span>
              <span className="small muted">来自已确认根因的事故</span>
            </div>
            <div className="bd">
              <div className="filters" style={{ marginBottom: "var(--s3)" }}>
                <label className="small muted" htmlFor={`rel-${s.id}`}>评估版本</label>
                <input id={`rel-${s.id}`} aria-label="版本" value={release}
                       style={{ flex: "0 1 120px" }}
                       onChange={(e) => setRelease(e.target.value)} />
                <select aria-label="模式" value={mode}
                        onChange={(e) => setMode(e.target.value)}>
                  <option value="warn">warn（警告不阻断）</option>
                  <option value="block">block（阻断）</option>
                </select>
                <button className="btn pri" disabled={gate.isPending}
                  onClick={async () => {
                    const out = await gate.mutateAsync({ suiteId: s.id, release, mode });
                    setLast({ result: out.result, detail: out.detail });
                  }}>
                  <Icon name="shield" />运行门禁
                </button>
                {last && (
                  <span>
                    本次结论：<StatusTag value={last.result} />
                  </span>
                )}
              </div>

              {s.cases.length > 0 && (
                <div className="invlist" style={{ marginBottom: "var(--s3)" }}>
                  {s.cases.map((c) => (
                    <div key={c.id} className="caseitem">
                      <div className="citop">
                        <span className="mono small"><b>{c.id}</b></span>
                        <span className="tag t-gray mono">{c.incident_id}</span>
                      </div>
                      <div className="inv mono">{c.invariants}</div>
                    </div>
                  ))}
                </div>
              )}

              {s.recent_runs.length > 0 && (
                <table className="dt keydiff">
                  <thead>
                    <tr><th>门禁运行</th><th>版本</th><th>模式</th><th>结论</th><th>时间</th></tr>
                  </thead>
                  <tbody>
                    {s.recent_runs.map((r) => (
                      <tr key={r.id}>
                        <td className="mono">{r.id}</td>
                        <td className="mono small">{r.release}</td>
                        <td className="small">{r.mode}</td>
                        <td><StatusTag value={r.result} /></td>
                        <td className="muted small mono">
                          {r.created_at.slice(0, 19).replace("T", " ")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        ))
      )}
      {last && (
        <div className="card page-in">
          <div className="hd"><b>最近一次门禁明细</b></div>
          <div className="bd">
            <pre className="mono small" style={{ whiteSpace: "pre-wrap", color: "var(--text-2)" }}>
              {JSON.stringify(last.detail, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
