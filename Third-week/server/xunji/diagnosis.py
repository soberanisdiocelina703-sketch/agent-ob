"""Diagnosis aggregation: merge rule/diff/model candidates, enforce evidence,
rank, truncate Top-3, persist.

调用时序（docs/08 §8.4）: run_sync_diagnosis() 同步返回规则+Diff 结果先渲染；
run_model_stage() 异步补充模型候选；模型失败不阻塞（status 仍 complete，
failure_reason 记录原因）。
"""
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone

from .causal import build_graph, upstream_path
from .diffgen import find_baseline, generate_diff_finding
from .enums import CandidateSource, DiagnosisStatus, EvidenceGrade
from .evaluator import EvaluatorError
from .rules import evaluate_rules, load_rulepack

log = logging.getLogger("xunji.diagnosis")

SCORE_BASE = {
    CandidateSource.RULE.value: 1.0,
    CandidateSource.DIFF.value: 0.75,
    CandidateSource.MODEL.value: 0.4,
}
GRADE_BY_SOURCE = {
    CandidateSource.RULE.value: EvidenceGrade.DETERMINISTIC.value,
    CandidateSource.DIFF.value: EvidenceGrade.DIFF_BASED.value,
    CandidateSource.MODEL.value: EvidenceGrade.MODEL_HEURISTIC.value,
}
TOP_N = 3
# 多样性截断（docs/05 问题 3 的 V2 修复，决策记录见 docs/06-反馈迭代闭环.md）：
# 同一 first_fault_span 至多 MAX_PER_SPAN 席，防止多规则命中同一下游步骤时
# 把指向上游源头的异构候选挤出 Top-N；rule/diff 各保底一席（若池中存在）。
# model_heuristic 不参与保底——低置信补充解释只补空位，不得挤占确定性/对照证据。
MAX_PER_SPAN = 2
GUARANTEED_SOURCES = (CandidateSource.RULE.value, CandidateSource.DIFF.value)


def _rank_key(c: dict) -> tuple:
    return (-c["raw_score"], c.get("fault_ts") or "￿")


def _select_diverse(pool: list[dict]) -> list[dict]:
    """从按分数排好序的候选池中选出 Top-N，施加 span/来源多样性约束。"""
    selected: list[dict] = []
    for c in pool:
        if len(selected) >= TOP_N:
            break
        same_span = sum(1 for s in selected
                        if s["first_fault_span_id"] == c["first_fault_span_id"])
        if same_span >= MAX_PER_SPAN:
            continue
        selected.append(c)

    for source in GUARANTEED_SOURCES:
        if any(c["source"] == source for c in selected):
            continue
        entrant = next((c for c in pool if c["source"] == source), None)
        if entrant is None:
            continue
        if len(selected) < TOP_N:
            selected.append(entrant)
            continue
        # 让位者：从队尾（分数最低）找「其来源已占多席」的候选；
        # 各来源都只剩一席时保底不成立（不挤掉某来源的唯一代表）
        victim = next((s for s in reversed(selected)
                       if sum(1 for x in selected if x["source"] == s["source"]) > 1),
                      None)
        if victim is not None:
            selected[selected.index(victim)] = entrant

    return sorted(selected, key=_rank_key)


def aggregate(raw_candidates: list[dict]) -> tuple[list[dict], int]:
    """raw: {source, cause_type, summary, first_fault_span_id, evidence, causal_path}
    Returns (ranked top-N, dropped_no_evidence_count)."""
    dropped = 0
    valid: list[dict] = []
    for c in raw_candidates:
        evidence = [e for e in c.get("evidence", []) if e.get("span_ref") or e.get("event_ref")]
        if not evidence:
            dropped += 1
            log.warning("dropping evidence-less candidate: %s", c.get("summary"))
            continue
        support = sum(1 for e in evidence if e.get("side") == "support")
        refute = sum(1 for e in evidence if e.get("side") == "refute")
        c = dict(c, evidence=evidence)
        c["raw_score"] = SCORE_BASE[c["source"]] + 0.05 * support - 0.1 * refute
        c["evidence_grade"] = GRADE_BY_SOURCE[c["source"]]
        valid.append(c)

    merged: dict[tuple, dict] = {}
    for c in valid:
        key = (c["first_fault_span_id"], c["cause_type"])
        if key in merged:
            keep = merged[key] if merged[key]["raw_score"] >= c["raw_score"] else c
            drop = c if keep is merged[key] else merged[key]
            keep["evidence"] = keep["evidence"] + drop["evidence"]
            merged[key] = keep
        else:
            merged[key] = c

    ranked = _select_diverse(sorted(merged.values(), key=_rank_key))
    for i, c in enumerate(ranked):
        c["rank"] = i + 1
    return ranked, dropped


def _persist(conn: sqlite3.Connection, diagnosis_id: str, candidates: list[dict]) -> None:
    """UPSERT 候选：保留既有 candidate ID 和 version，避免孤儿化已提交的 verdicts。"""
    # 查出既有候选建 ID 映射：(span, cause) → (id, version)
    existing_map = {}
    for row in conn.execute(
        "SELECT id, first_fault_span_id, cause_type, version FROM candidates WHERE diagnosis_id=?",
        (diagnosis_id,)
    ):
        key = (row["first_fault_span_id"], row["cause_type"])
        existing_map[key] = (row["id"], row["version"])

    # 删除即将被替换的候选的证据（会重建），保留候选本身以维持 ID 稳定
    cids_to_update = [existing_map[k][0] for k in existing_map]
    if cids_to_update:
        placeholders = ",".join("?" * len(cids_to_update))
        conn.execute(f"DELETE FROM evidence WHERE candidate_id IN ({placeholders})", cids_to_update)

    # 删除不在新排名中的候选（降级出 Top-3 的）
    new_keys = {(c["first_fault_span_id"], c["cause_type"]) for c in candidates}
    for key, (cid, _) in existing_map.items():
        if key not in new_keys:
            conn.execute("DELETE FROM evidence WHERE candidate_id=?", (cid,))
            conn.execute("DELETE FROM candidates WHERE id=?", (cid,))

    # UPSERT 候选：既有的 UPDATE（保留 version），新的 INSERT（version=0）
    for c in candidates:
        key = (c["first_fault_span_id"], c["cause_type"])
        if key in existing_map:
            cid, version = existing_map[key]
            c["id"] = cid  # 保留既有 ID
            conn.execute(
                """UPDATE candidates SET rank=?, summary=?, raw_score=?, evidence_grade=?,
                   source=?, causal_path=? WHERE id=?""",
                (c["rank"], c["summary"], c["raw_score"], c["evidence_grade"], c["source"],
                 json.dumps(c.get("causal_path", [])), cid),
            )
        else:
            cid = f"cand-{uuid.uuid4().hex[:8]}"
            c["id"] = cid
            conn.execute(
                """INSERT INTO candidates (id, diagnosis_id, rank, cause_type, summary, raw_score,
                   evidence_grade, source, first_fault_span_id, causal_path, version)
                   VALUES (?,?,?,?,?,?,?,?,?,?,0)""",
                (cid, diagnosis_id, c["rank"], c["cause_type"], c["summary"], c["raw_score"],
                 c["evidence_grade"], c["source"], c["first_fault_span_id"],
                 json.dumps(c.get("causal_path", []))),
            )

        # 重建证据（已删旧证据）
        for e in c["evidence"]:
            conn.execute(
                """INSERT INTO evidence (id, candidate_id, side, kind, span_ref, event_ref,
                   excerpt, weight) VALUES (?,?,?,?,?,?,?,?)""",
                (f"ev-{uuid.uuid4().hex[:8]}", c["id"], e.get("side", "support"),
                 e.get("kind", "span_excerpt"), e.get("span_ref"), e.get("event_ref"),
                 e.get("excerpt", ""), e.get("weight", 1.0)),
            )
    conn.commit()


def run_sync_diagnosis(conn: sqlite3.Connection, incident: dict) -> str:
    """Rules + Diff, synchronous. Returns diagnosis_id with status=partial."""
    diagnosis_id = f"diag-{uuid.uuid4().hex[:8]}"
    rulepack = load_rulepack(incident["project_id"])
    conn.execute(
        """INSERT INTO diagnoses (id, incident_id, status, rule_pack_version, started_at)
           VALUES (?,?,?,?,?)""",
        (diagnosis_id, incident["id"], DiagnosisStatus.PENDING.value, rulepack["version"],
         datetime.now(timezone.utc).isoformat()),
    )
    g = build_graph(conn, incident["trace_id"])
    symptom = incident["symptom_span_id"]

    raw: list[dict] = []
    for f in evaluate_rules(conn, g, symptom, rulepack):
        raw.append({
            "source": CandidateSource.RULE.value, "cause_type": f.cause_type,
            "summary": f.summary, "first_fault_span_id": f.first_fault_span_id,
            "evidence": f.evidence,
            "fault_ts": g.spans.get(f.first_fault_span_id, {}).get("ts"),
            "causal_path": upstream_path(g, symptom) if symptom in g.spans else [],
        })

    span0 = g.spans.get(g.nodes[0]) if g.nodes else None
    baseline = None
    if span0:
        baseline = find_baseline(conn, span0["project_id"], span0["agent_id"],
                                 span0["agent_version"], exclude=incident["trace_id"])
    finding, diff_reason = generate_diff_finding(conn, g, baseline)
    if finding:
        raw.append({
            "source": CandidateSource.DIFF.value, "cause_type": finding.cause_type,
            "summary": finding.summary, "first_fault_span_id": finding.first_fault_span_id,
            "evidence": finding.evidence,
            "causal_path": upstream_path(g, symptom) if symptom in g.spans else [],
        })

    ranked, dropped = aggregate(raw)
    _persist(conn, diagnosis_id, ranked)
    conn.execute(
        "UPDATE diagnoses SET status=?, failure_reason=? WHERE id=?",
        (DiagnosisStatus.PARTIAL.value,
         None if finding else f"diff:{diff_reason}", diagnosis_id),
    )
    if ranked:
        conn.execute("UPDATE incidents SET evidence_grade=? WHERE id=?",
                     (ranked[0]["evidence_grade"], incident["id"]))
    conn.commit()
    return diagnosis_id


def run_model_stage(conn: sqlite3.Connection, diagnosis_id: str, evaluator) -> None:
    """Async model stage; failure never blocks the page (docs/06 G-4)."""
    diag = conn.execute("SELECT * FROM diagnoses WHERE id=?", (diagnosis_id,)).fetchone()
    incident = conn.execute("SELECT * FROM incidents WHERE id=?",
                            (diag["incident_id"],)).fetchone()
    g = build_graph(conn, incident["trace_id"])
    span0 = g.spans.get(g.nodes[0]) if g.nodes else None
    baseline = None
    if span0:
        baseline = find_baseline(conn, span0["project_id"], span0["agent_id"],
                                 span0["agent_version"], exclude=incident["trace_id"])
    try:
        model_candidates = evaluator.evaluate(conn, g, incident["symptom_span_id"], baseline)
        failure_reason = diag["failure_reason"]
    except EvaluatorError as exc:
        model_candidates = []
        failure_reason = f"model:{exc}"

    existing = load_candidates(conn, diagnosis_id)
    raw = [dict(c, evidence=c["evidence"]) for c in existing]
    for mc in model_candidates:
        raw.append({
            "source": CandidateSource.MODEL.value, "cause_type": mc.cause_type,
            "summary": mc.summary, "first_fault_span_id": mc.first_fault_span_id,
            "evidence": mc.evidence, "causal_path": [],
        })
    ranked, _ = aggregate(raw)
    _persist(conn, diagnosis_id, ranked)
    conn.execute(
        "UPDATE diagnoses SET status=?, model_version=?, completed_at=?, failure_reason=? WHERE id=?",
        (DiagnosisStatus.COMPLETE.value, getattr(evaluator, "model_version", "?"),
         datetime.now(timezone.utc).isoformat(), failure_reason, diagnosis_id),
    )
    conn.commit()


def load_candidates(conn: sqlite3.Connection, diagnosis_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM candidates WHERE diagnosis_id=? ORDER BY rank", (diagnosis_id,)
    ).fetchall()
    out = []
    for r in rows:
        c = dict(r)
        c["causal_path"] = json.loads(c["causal_path"] or "[]")
        ev = conn.execute("SELECT * FROM evidence WHERE candidate_id=?", (r["id"],)).fetchall()
        c["evidence"] = [dict(e) for e in ev]
        out.append(c)
    return out
