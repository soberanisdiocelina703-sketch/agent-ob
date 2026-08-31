import { useState } from "react";
import { useParams } from "react-router-dom";
import {
  useDiagnosis, useDiff, useIncidents, useReview, useToRegression, useTraceDetail,
} from "../hooks/useXunji";
import { StatusTag } from "../components/StatusTag";
import { EvidenceCard } from "../components/EvidenceCard";
import { DiffTable } from "../components/DiffTable";
import { Icon } from "../components/Icon";
import type { Candidate } from "../api/types";

/** 诊断工作台：症状 → Top-3 候选 → 证据 → Diff → 复核 → 转用例 */
export function DiagnosisPage() {
  const { incidentId = "" } = useParams();
  const { data: diag } = useDiagnosis(incidentId);
  const { data: diff } = useDiff(incidentId);
  const { data: incidents } = useIncidents();
  const review = useReview(incidentId);
  const toRegression = useToRegression(incidentId);
  const [message, setMessage] = useState<{ text: string; warn?: boolean } | null>(null);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const incident = incidents?.find((i) => i.id === incidentId);
  const { data: trace } = useTraceDetail(incident?.trace_id ?? null);
  const stepName = (sid: string) =>
    trace?.spans.find((s) => s.span_id === sid)?.step_name ?? sid.split("-").slice(-2).join("-");

  const submitReview = async (c: Candidate, result: string) => {
    setMessage(null);
    try {
      await review.mutateAsync({
        candidateId: c.id, version: c.version, result,
        reason: result === "confirmed" ? "复核人确认" : undefined,
      });
      setMessage({
        text: `复核已记录：${result === "confirmed" ? "确认是根因" : result === "excluded" ? "排除该原因" : "证据不足"}`,
      });
    } catch (e: unknown) {
      const err = e as { response?: { status?: number } };
      setMessage(
        err.response?.status === 409
          ? { text: "并发冲突：该候选已被他人复核，列表已刷新，请基于最新状态重试", warn: true }
          : { text: `复核失败：${(e as Error).message}`, warn: true },
      );
    }
  };

  const confirmed = diag?.candidates.some((c) => c.verdict?.result === "confirmed");

  if (!diag) return <div className="empty">诊断加载中…</div>;
  return (
    <div className="page-in">
      {/* 症状区 */}
      <div className="card sym mb16">
        <div className="hd">
          <b>症状</b>
          {incident && <StatusTag value={incident.failure_type} />}
          <span className="mono small muted">
            {incidentId}{incident && <> · {incident.trace_id}</>}
          </span>
          <span className="sp">
            <StatusTag value={incident?.review_status ?? "unreviewed"} />
          </span>
        </div>
        <div className="bd">
          <div className="symrow">
            <div className="k">症状步骤</div>
            <div className="v" style={{ color: "var(--bad)" }}>
              {incident?.symptom_span_id ?? "—"}
              <span className="tiny muted" style={{ fontWeight: 400 }}>
                （失败浮现处，不等于根因）
              </span>
            </div>
          </div>
          <div className="symrow">
            <div className="k">失败模式簇</div>
            <div className="v">
              {incident?.cluster_title ?? "—"}
              <span className="tiny muted" style={{ fontWeight: 400 }}>
                · 簇内 {incident?.cluster_count ?? 1} 起
              </span>
            </div>
          </div>
          <div className="symrow">
            <div className="k">规则包</div>
            <div className="v mono small">{diag.rule_pack_version}</div>
          </div>
          <div className="symrow">
            <div className="k">诊断状态</div>
            <div className="v"><StatusTag value={diag.status} /></div>
          </div>
        </div>
      </div>

      {/* 候选区 */}
      <div className="card fault mb16">
        <div className="hd">
          <b>候选根因 Top-{diag.candidates.length || 3}</b>
          <span className="small muted">规则同步先出，模型候选异步追加</span>
        </div>
        <div className="bd">
          {diag.status === "partial" && (
            <div className="diagload">
              <Icon name="loader" className="spin" />
              规则/Diff 结果已出；模型分析进行中（超时不阻塞本页）…
            </div>
          )}
          {diag.failure_reason && diag.status === "complete" && (
            <div className="verdictdone warn mb10">
              <Icon name="alert" />
              <div className="small">降级提示：{diag.failure_reason} —— 规则 / Diff 候选不受影响</div>
            </div>
          )}
          {message && (
            <div role="status" className={`verdictdone${message.warn ? " warn" : ""} mb10`}>
              <Icon name={message.warn ? "alert" : "check"} />
              <div className="small">{message.text}</div>
            </div>
          )}

          {!diag.candidates.length ? (
            <div className="empty">
              证据不足：暂无可上屏候选。可在下方 Diff 区人工比对，或在复核中人工指认根因。
            </div>
          ) : (
            diag.candidates.map((c) => {
              const open = !collapsed[c.id];
              return (
                <div key={c.id} className={`cand${open ? " open" : ""}`}>
                  <button
                    type="button"
                    className="candhd"
                    aria-expanded={open}
                    onClick={() => setCollapsed((p) => ({ ...p, [c.id]: open }))}
                  >
                    <span className="rank">{c.rank}</span>
                    <span className="candtitle">
                      <span className="ct mono">{c.first_fault_span_id}</span>
                      <span className="cmetarow">
                        <StatusTag value={c.source} />
                        <StatusTag value={c.evidence_grade} />
                        <StatusTag value={c.cause_type} />
                        {c.verdict && <StatusTag value={c.verdict.result} />}
                      </span>
                    </span>
                    <span className="candtoggle"><Icon name="arrowRight" /></span>
                  </button>
                  <div className="candbody" hidden={!open}>
                    <p className="mt10 mb10">{c.summary}</p>
                    {c.causal_path.length > 1 && (
                      <div className="causal mb10" aria-label="因果传播路径">
                        {c.causal_path.map((sid, i) => (
                          <span key={sid} style={{ display: "contents" }}>
                            {i > 0 && (
                              <span className="carrow" aria-hidden="true">
                                <Icon name="arrowRight" />
                              </span>
                            )}
                            <span
                              className={`cnode${sid === c.first_fault_span_id ? " first" : ""}${sid === incident?.symptom_span_id ? " last" : ""}`}
                            >
                              <span className="cbadge">{i + 1}</span>
                              <span className="ctext mono">{stepName(sid)}</span>
                              <span className="tiny muted">
                                {sid === c.first_fault_span_id ? "首故障点"
                                  : sid === incident?.symptom_span_id ? "症状" : " "}
                              </span>
                            </span>
                          </span>
                        ))}
                      </div>
                    )}
                    {c.evidence.map((e) => (
                      <EvidenceCard key={e.id} evidence={e} />
                    ))}
                    <div className="candfoot">
                      <button className="btn ok sm" disabled={review.isPending}
                              onClick={() => submitReview(c, "confirmed")}>
                        <Icon name="check" />确认是根因
                      </button>
                      <button className="btn bad sm" disabled={review.isPending}
                              onClick={() => submitReview(c, "excluded")}>
                        排除该原因
                      </button>
                      <button className="btn sm" disabled={review.isPending}
                              onClick={() => submitReview(c, "insufficient")}>
                        证据不足
                      </button>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="hd" style={{ borderTop: "1px solid var(--line)", borderBottom: "none" }}>
          <b className="small">复核后沉淀为资产</b>
          <span className="sp">
            {!confirmed && <span className="muted tiny">需先「确认是根因」</span>}
            <button
              className="btn pri sm"
              disabled={!confirmed || toRegression.isPending}
              title={confirmed ? "" : "仅已确认根因的事故可转回归用例"}
              onClick={async () => {
                const out = await toRegression.mutateAsync("对账回归集");
                setMessage({ text: `已生成回归用例 ${out.case_id}（回归集见「回归集与门禁」页）` });
              }}
            >
              一键转回归用例<Icon name="arrowRight" />
            </button>
          </span>
        </div>
      </div>

      {/* Diff 区 */}
      <div className="card">
        <div className="hd">
          <b>成功 / 失败 Diff</b>
          <span className="small muted">与最近一次质量通过的运行逐步骤对比（语言步骤不参与分歧判定）</span>
        </div>
        {diff ? <DiffTable diff={diff} /> : <div className="empty">加载中…</div>}
      </div>
    </div>
  );
}
