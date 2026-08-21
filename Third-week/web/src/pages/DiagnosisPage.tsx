import { useState } from "react";
import { useParams } from "react-router-dom";
import {
  useDiagnosis, useDiff, useReview, useToRegression,
} from "../hooks/useXunji";
import { StatusTag } from "../components/StatusTag";
import { EvidenceCard } from "../components/EvidenceCard";
import { DiffTable } from "../components/DiffTable";
import type { Candidate } from "../api/types";

/** 诊断工作台：症状 → Top-3 候选 → 证据 → Diff → 复核 → 转用例（事故详情内连续子视图） */
export function DiagnosisPage() {
  const { incidentId = "" } = useParams();
  const { data: diag } = useDiagnosis(incidentId);
  const { data: diff } = useDiff(incidentId);
  const review = useReview(incidentId);
  const toRegression = useToRegression(incidentId);
  const [message, setMessage] = useState<string | null>(null);

  const submitReview = async (c: Candidate, result: string) => {
    setMessage(null);
    try {
      await review.mutateAsync({
        candidateId: c.id, version: c.version, result,
        reason: result === "confirmed" ? "复核人确认" : undefined,
      });
      setMessage(`复核已记录：${result}`);
    } catch (e: unknown) {
      const err = e as { response?: { status?: number } };
      setMessage(
        err.response?.status === 409
          ? "并发冲突：该候选已被他人复核，列表已刷新，请基于最新状态重试"
          : `复核失败：${(e as Error).message}`,
      );
    }
  };

  const confirmed = diag?.candidates.some((c) => c.verdict?.result === "confirmed");

  if (!diag) return <div className="empty">诊断加载中…</div>;
  return (
    <div>
      <div className="card">
        <h3 className="card__title">
          诊断工作台 <span className="mono muted">{incidentId}</span>{" "}
          <StatusTag value={diag.status === "partial" ? "running" : diag.status} />
          {diag.status === "partial" && (
            <span className="muted">（规则结果已出，模型分析进行中…）</span>
          )}
        </h3>
        <div className="muted">
          规则包 {diag.rule_pack_version} · 模型 {diag.model_version ?? "分析中"}
          {diag.failure_reason && (
            <span className="tag tag--warn" style={{ marginLeft: 8 }}>
              降级：{diag.failure_reason}（规则/Diff 候选不受影响）
            </span>
          )}
        </div>
        {message && <p role="status">{message}</p>}

        {!diag.candidates.length ? (
          <div className="empty">
            证据不足：暂无可上屏候选。可在 Diff 区人工比对，或在运行记录中人工指认根因。
          </div>
        ) : (
          diag.candidates.map((c) => (
            <div key={c.id} className={`candidate${c.rank === 1 ? " candidate--top" : ""}`}>
              <div className="candidate__head">
                <span className="candidate__rank">Top {c.rank}</span>
                <StatusTag value={c.source} />
                <StatusTag value={c.evidence_grade} />
                <span className="tag">{c.cause_type}</span>
                {c.verdict && <StatusTag value={c.verdict.result} />}
              </div>
              <div>
                首故障点：<b className="mono">{c.first_fault_span_id}</b> — {c.summary}
              </div>
              {c.evidence.map((e) => (
                <EvidenceCard key={e.id} evidence={e} />
              ))}
              <div style={{ marginTop: 8 }}>
                <button className="btn btn--primary" disabled={review.isPending}
                        onClick={() => submitReview(c, "confirmed")}>
                  确认是根因
                </button>
                <button className="btn btn--danger" disabled={review.isPending}
                        onClick={() => submitReview(c, "excluded")}>
                  排除该原因
                </button>
                <button className="btn" disabled={review.isPending}
                        onClick={() => submitReview(c, "insufficient")}>
                  证据不足
                </button>
              </div>
            </div>
          ))
        )}

        <div style={{ marginTop: 12 }}>
          <button
            className="btn btn--primary"
            disabled={!confirmed || toRegression.isPending}
            title={confirmed ? "" : "仅已确认根因的事故可转回归用例"}
            onClick={async () => {
              const out = await toRegression.mutateAsync("对账回归集");
              setMessage(`已生成回归用例 ${out.case_id}（回归集 ${out.suite_id}）`);
            }}
          >
            一键转回归用例
          </button>
          {!confirmed && <span className="muted"> 需先「确认是根因」</span>}
        </div>
      </div>

      <div className="card">
        <h3 className="card__title">成功 / 失败 Diff</h3>
        {diff ? <DiffTable diff={diff} /> : <div className="empty">加载中…</div>}
      </div>
    </div>
  );
}
