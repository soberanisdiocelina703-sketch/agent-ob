import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTraceDetail, useTraces } from "../hooks/useXunji";
import { StatusTag } from "../components/StatusTag";

const KIND_TAG: Record<string, string> = {
  llm_call: "t-model", tool_call: "t-ok", retrieval: "t-brand",
  validation: "t-warn", planning: "t-brand", other: "t-gray",
};
const KIND_LABEL: Record<string, string> = {
  llm_call: "LLM", tool_call: "TOOL", retrieval: "RETR",
  validation: "CHECK", planning: "AGENT", other: "OTHER",
};

/** 运行记录：成功与失败并存；失败可跳事故（docs/01 步骤 1A） */
export function RunsPage() {
  const [params, setParams] = useSearchParams();
  const quality = params.get("quality_verdict") ?? "";
  const { data: traces, isLoading } = useTraces(
    quality ? { quality_verdict: quality } : undefined,
  );
  const [selected, setSelected] = useState<string | null>(null);
  const { data: detail } = useTraceDetail(selected);

  const total = traces?.length ?? 0;
  const succ = traces?.filter((t) => t.execution_status === "success").length ?? 0;
  const qfail = traces?.filter((t) => t.quality_verdict === "failed").length ?? 0;
  const withInc = traces?.filter((t) => t.incident_id).length ?? 0;

  return (
    <div className="page-in">
      <div className="grid g4 mb10">
        <div className="card bd">
          <div className="small muted">运行总数</div>
          <div className="metric">{total}</div>
          <div className="small muted">对账 Agent · 演示数据</div>
        </div>
        <div className="card bd">
          <div className="small muted">执行成功率</div>
          <div className="metric" style={{ color: "var(--ok)" }}>
            {total ? Math.round((succ / total) * 100) : 0}%
          </div>
          <div className="small muted">只表示技术执行状态</div>
        </div>
        <div className="card bd">
          <div className="small muted">质量不通过</div>
          <div className="metric" style={{ color: "var(--warn)" }}>{qfail}</div>
          <div className="small muted">执行成功也可能质量不通过</div>
        </div>
        <div className="card bd">
          <div className="small muted">涉及事故</div>
          <div className="metric" style={{ color: "var(--bad)" }}>{withInc}</div>
          <div className="small muted">点击行进入排障</div>
        </div>
      </div>

      <div className="filters">
        <select
          aria-label="质量结论"
          value={quality}
          onChange={(e) =>
            setParams(e.target.value ? { quality_verdict: e.target.value } : {})
          }
        >
          <option value="">质量结论：全部</option>
          <option value="pass">通过</option>
          <option value="failed">不通过</option>
        </select>
      </div>

      <div className="card">
        <div className="taxonomy-note">
          <b>状态口径：</b>执行状态只描述程序是否完成；质量结论描述业务结果是否正确。
          执行成功但质量不通过的运行同样会进入事故列表。
        </div>
        <div className="hd">
          <b>运行记录</b>
          <span className="tag t-gray">{total} 条</span>
          <span className="small muted">真实 Claude Code 运行 · 每 5s 自动刷新</span>
        </div>
        {isLoading ? (
          <div className="empty">加载中…</div>
        ) : !traces?.length ? (
          <div className="empty">暂无运行数据 — 执行 npm run demo-run 或 demo-offline</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Trace ID</th><th>执行状态</th><th>质量结论</th><th>Agent</th>
                <th>版本</th><th>步骤数</th><th>事故状态</th>
              </tr>
            </thead>
            <tbody>
              {traces.map((t) => (
                <tr key={t.trace_id} className="click" onClick={() => setSelected(t.trace_id)}>
                  <td className="mono"><b>{t.trace_id}</b></td>
                  <td>
                    <span className={`run-status ${t.execution_status === "success" ? "success" : "failed"}`}>
                      {t.execution_status === "success" ? "成功" : "失败"}
                    </span>
                  </td>
                  <td><StatusTag value={t.quality_verdict} /></td>
                  <td>{t.agent_id}</td>
                  <td className="mono small">{t.agent_version}</td>
                  <td>{t.span_count}</td>
                  <td>
                    {t.incident_id ? (
                      <a href={`#/incidents/${t.incident_id}`}>
                        <span className="tag t-bad">{t.incident_id}</span>
                      </a>
                    ) : (
                      <span className="muted small">未立案</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {detail && (
        <div className="card mt16 page-in">
          <div className="hd">
            <b>Trace 详情</b>
            <span className="mono muted small">{detail.trace_id}</span>
            {detail.incident_id && (
              <a href={`#/incidents/${detail.incident_id}`} style={{ marginLeft: "auto" }}>
                打开诊断工作台 →
              </a>
            )}
          </div>
          <div className="bd ttree">
            {detail.spans.map((s) => {
              const bad = s.execution_status !== "success";
              const qbad = s.quality_verdict === "failed";
              return (
                <div key={s.span_id} className={`trow${bad ? " hlbad" : qbad ? " hl" : ""}`}>
                  <span className={`tag kind ${KIND_TAG[s.step_type] ?? "t-gray"}`}>
                    {KIND_LABEL[s.step_type] ?? s.step_type}
                  </span>
                  <span>
                    {s.step_name}
                    {s.link_kind === "broken_parent" && (
                      <span className="tag t-warn" style={{ marginLeft: 6 }}>断链</span>
                    )}
                  </span>
                  <span className="mono muted small" style={{ maxWidth: 520, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {(s.output_payload ?? "").slice(0, 110)}
                  </span>
                  <span className="dur">
                    <StatusTag value={bad ? s.execution_status : s.quality_verdict === "unevaluated" ? "success" : s.quality_verdict} />
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
