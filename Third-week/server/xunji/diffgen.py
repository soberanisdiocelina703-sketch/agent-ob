"""Success/failure diff candidate generator — primary T1 path for silent failures.

Baseline compatibility (second-week/docs/08 diff?baseline= contract): same
project + agent + agent_version, fully successful, quality not failed. When no
baseline exists the generator degrades to (None, "no_baseline") instead of
guessing — cold-start honesty is part of the product claim.
"""
import json
import sqlite3
from dataclasses import dataclass, field

from .causal import Graph
from .enums import FailureType

# Volatile keys that legitimately differ between runs; comparing them would
# flood the diff with false divergences. Kept deliberately small — timestamps
# like generated_at are NOT here because data freshness is a real signal.
VOLATILE_KEYS = {"run_id", "trace_id", "report_path", "duration_ms"}
NUMERIC_TOLERANCE = 0.001  # relative


@dataclass
class DiffFinding:
    first_fault_span_id: str
    cause_type: str
    summary: str
    evidence: list[dict] = field(default_factory=list)


def find_baseline(conn: sqlite3.Connection, project_id: str, agent_id: str,
                  agent_version: str, exclude: str) -> str | None:
    rows = conn.execute(
        """SELECT trace_id, MAX(ts) latest FROM spans
           WHERE project_id=? AND agent_id=? AND agent_version=? AND trace_id != ?
           GROUP BY trace_id ORDER BY latest DESC""",
        (project_id, agent_id, agent_version, exclude),
    ).fetchall()
    for row in rows:
        bad = conn.execute(
            """SELECT COUNT(*) c FROM spans WHERE trace_id=? AND
               (execution_status IN ('error','timeout') OR quality_verdict='failed')""",
            (row["trace_id"],),
        ).fetchone()
        if bad["c"] == 0:
            return row["trace_id"]
    return None


def _outputs_by_step(conn: sqlite3.Connection, trace_id: str) -> list[tuple[str, str, dict | str | None]]:
    rows = conn.execute(
        "SELECT span_id, step_name, output_ref FROM spans WHERE trace_id=? ORDER BY ts, span_id",
        (trace_id,),
    ).fetchall()
    result = []
    for r in rows:
        content = None
        if r["output_ref"]:
            p = conn.execute("SELECT content FROM payloads WHERE ref=?", (r["output_ref"],)).fetchone()
            if p:
                try:
                    content = json.loads(p["content"])
                except json.JSONDecodeError:
                    content = p["content"]
        result.append((r["span_id"], r["step_name"], content))
    return result


def _diverging_keys(base, cur, path="") -> list[dict]:
    """Structural comparison; returns [{key, baseline, failed}] divergences."""
    divs: list[dict] = []
    if isinstance(base, dict) and isinstance(cur, dict):
        for k in sorted(set(base) | set(cur)):
            if k in VOLATILE_KEYS:
                continue
            p = f"{path}.{k}" if path else k
            if k not in base:
                divs.append({"key": p, "baseline": "<absent>", "failed": _short(cur[k])})
            elif k not in cur:
                divs.append({"key": p, "baseline": _short(base[k]), "failed": "<absent>"})
            else:
                divs.extend(_diverging_keys(base[k], cur[k], p))
    elif isinstance(base, list) and isinstance(cur, list):
        if len(base) != len(cur):
            divs.append({"key": f"{path}.length", "baseline": len(base), "failed": len(cur)})
    elif isinstance(base, (int, float)) and isinstance(cur, (int, float)):
        denom = max(abs(base), 1e-9)
        if abs(base - cur) / denom > NUMERIC_TOLERANCE:
            divs.append({"key": path, "baseline": base, "failed": cur})
    elif base != cur:
        divs.append({"key": path, "baseline": _short(base), "failed": _short(cur)})
    return divs


def _short(v) -> str:
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s[:120]


def generate_diff_finding(conn: sqlite3.Connection, g: Graph,
                          baseline_trace_id: str | None) -> tuple[DiffFinding | None, str]:
    if not baseline_trace_id:
        return None, "no_baseline"

    base_steps = _outputs_by_step(conn, baseline_trace_id)
    fail_steps = _outputs_by_step(conn, g.trace_id)
    base_by_name = {name: (sid, out) for sid, name, out in base_steps}
    fail_names = {name for _, name, _ in fail_steps}

    for span_id, step_name, output in fail_steps:
        if step_name not in base_by_name:
            continue  # 失败链新增步骤不视为首分歧（可能是重试），只比对共有步骤
        base_sid, base_out = base_by_name[step_name]
        divs = _diverging_keys(base_out, output)
        if divs:
            excerpt = json.dumps(divs[:8], ensure_ascii=False)
            evidence = [
                {"side": "support", "kind": "diff_divergence",
                 "span_ref": f"{g.trace_id}/{span_id}", "excerpt": excerpt},
                {"side": "support", "kind": "baseline_ref",
                 "span_ref": f"{baseline_trace_id}/{base_sid}",
                 "excerpt": f"成功基线 {baseline_trace_id} 同名步骤输出"},
            ]
            downstream = [e["dst"] for e in g.edges if e["src"] == span_id and e["kind"] == "dataflow"]
            if downstream:
                evidence.append({
                    "side": "support", "kind": "propagation",
                    "span_ref": f"{g.trace_id}/{downstream[0]}",
                    "excerpt": f"分歧沿数据流传导至下游步骤: {downstream}"})
            return DiffFinding(
                first_fault_span_id=span_id,
                cause_type=FailureType.QUALITY_CHECK_FAILED.value,
                summary=f"步骤 {step_name} 输出与成功基线首次显著分歧（{divs[0]['key']}: "
                        f"{divs[0]['baseline']} → {divs[0]['failed']}）",
                evidence=evidence,
            ), "ok"

    # 共有步骤全部一致 → 检查基线有而失败链缺的步骤
    missing = [name for _, name, _ in base_steps if name not in fail_names]
    if missing:
        last_sid = fail_steps[-1][0] if fail_steps else "?"
        return DiffFinding(
            first_fault_span_id=last_sid,
            cause_type=FailureType.EXCEPTION.value,
            summary=f"失败链缺少基线步骤: {missing}（执行提前中止）",
            evidence=[{"side": "support", "kind": "missing_steps",
                       "span_ref": f"{g.trace_id}/{last_sid}",
                       "excerpt": json.dumps(missing, ensure_ascii=False)}],
        ), "ok"
    return None, "no_divergence"
