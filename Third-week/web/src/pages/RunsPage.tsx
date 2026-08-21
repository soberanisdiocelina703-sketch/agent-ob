import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTraceDetail, useTraces } from "../hooks/useXunji";
import { StatusTag } from "../components/StatusTag";

/** 运行记录：成功与失败并存；失败可跳事故（docs/01 步骤 1A） */
export function RunsPage() {
  const [params, setParams] = useSearchParams();
  const quality = params.get("quality_verdict") ?? "";
  const { data: traces, isLoading } = useTraces(
    quality ? { quality_verdict: quality } : undefined,
  );
  const [selected, setSelected] = useState<string | null>(null);
  const { data: detail } = useTraceDetail(selected);

  return (
    <div>
      <div className="card">
        <h3 className="card__title">运行记录</h3>
        <label>
          质量结论：
          <select
            value={quality}
            onChange={(e) =>
              setParams(e.target.value ? { quality_verdict: e.target.value } : {})
            }
          >
            <option value="">全部</option>
            <option value="pass">通过</option>
            <option value="failed">未通过</option>
          </select>
        </label>
        {isLoading ? (
          <div className="empty">加载中…</div>
        ) : !traces?.length ? (
          <div className="empty">暂无运行数据 — 执行 npm run demo-run 或 demo-offline</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Trace</th><th>Agent</th><th>版本</th><th>执行</th>
                <th>质量</th><th>步骤数</th><th>事故</th>
              </tr>
            </thead>
            <tbody>
              {traces.map((t) => (
                <tr key={t.trace_id} onClick={() => setSelected(t.trace_id)}>
                  <td className="mono">{t.trace_id}</td>
                  <td>{t.agent_id}</td>
                  <td>{t.agent_version}</td>
                  <td><StatusTag value={t.execution_status} /></td>
                  <td><StatusTag value={t.quality_verdict} /></td>
                  <td>{t.span_count}</td>
                  <td>
                    {t.incident_id ? (
                      <a href={`#/incidents/${t.incident_id}`}>{t.incident_id}</a>
                    ) : ("—")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {detail && (
        <div className="card">
          <h3 className="card__title">
            Trace 详情：<span className="mono">{detail.trace_id}</span>
            {detail.incident_id && (
              <a href={`#/incidents/${detail.incident_id}`} style={{ marginLeft: 12 }}>
                → 打开诊断工作台
              </a>
            )}
          </h3>
          <table className="table">
            <thead>
              <tr><th>步骤</th><th>类型</th><th>执行</th><th>质量</th><th>输出摘录</th></tr>
            </thead>
            <tbody>
              {detail.spans.map((s) => (
                <tr key={s.span_id} id={`span-${s.span_id}`}>
                  <td>
                    {s.step_name}
                    {s.link_kind === "broken_parent" && (
                      <span className="tag tag--warn">断链</span>
                    )}
                  </td>
                  <td className="muted">{s.step_type}</td>
                  <td><StatusTag value={s.execution_status} /></td>
                  <td><StatusTag value={s.quality_verdict} /></td>
                  <td className="mono">{(s.output_payload ?? "").slice(0, 120)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
