"""Regression assets + release gate.

仅 confirmed 事故可转用例（docs/08 契约）；用例打包输入引用 + 不变量。
gate-run 对指定 release 的最新一次运行重放规则包与不变量检查，
默认 warn 不阻断（second-week 设计决策）。
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone

from .causal import build_graph
from .enums import GateMode, GateResult, IncidentStatus, ReviewResult
from .rules import evaluate_rules, load_rulepack


class RegressionInvalid(Exception):
    pass


def _ensure_suite(conn: sqlite3.Connection, project_id: str, name: str) -> str:
    row = conn.execute("SELECT id FROM suites WHERE project_id=? AND name=?",
                       (project_id, name)).fetchone()
    if row:
        return row["id"]
    suite_id = f"suite-{uuid.uuid4().hex[:8]}"
    conn.execute("INSERT INTO suites (id, project_id, name, created_at) VALUES (?,?,?,?)",
                 (suite_id, project_id, name, datetime.now(timezone.utc).isoformat()))
    return suite_id


def create_regression_case(conn: sqlite3.Connection, incident_id: str,
                           suite_name: str = "默认回归集") -> dict:
    incident = conn.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone()
    if incident is None:
        raise RegressionInvalid(f"事故 {incident_id} 不存在")
    if incident["review_status"] != ReviewResult.CONFIRMED.value:
        raise RegressionInvalid("仅允许已确认根因(confirmed)的事故转回归用例")

    confirmed = conn.execute(
        """SELECT c.* FROM candidates c
           JOIN verdicts v ON v.candidate_id = c.id AND v.superseded_by IS NULL
           JOIN diagnoses d ON d.id = c.diagnosis_id
           WHERE d.incident_id=? AND v.result='confirmed' ORDER BY c.rank LIMIT 1""",
        (incident_id,),
    ).fetchone()

    first_span = conn.execute(
        "SELECT * FROM spans WHERE trace_id=? ORDER BY ts LIMIT 1",
        (incident["trace_id"],),
    ).fetchone()
    fault_span = None
    if confirmed and confirmed["first_fault_span_id"]:
        fault_span = conn.execute(
            "SELECT * FROM spans WHERE trace_id=? AND span_id=?",
            (incident["trace_id"], confirmed["first_fault_span_id"]),
        ).fetchone()

    invariants = [{
        "kind": "no_recurrence",
        "failure_type": confirmed["cause_type"] if confirmed else incident["failure_type"],
        "fault_step_name": fault_span["step_name"] if fault_span else None,
        "source_incident": incident_id,
    }, {
        "kind": "quality_pass",
        "description": "同工作流运行的质量结论不得为 failed",
    }]

    suite_id = _ensure_suite(conn, incident["project_id"], suite_name)
    case_id = f"rc-{uuid.uuid4().hex[:8]}"
    conn.execute(
        """INSERT INTO regression_cases
           (id, incident_id, suite_id, input_ref, context_snapshot_ref, invariants, review_status)
           VALUES (?,?,?,?,?,?, 'active')""",
        (case_id, incident_id, suite_id,
         first_span["input_ref"] if first_span else None,
         incident["trace_id"], json.dumps(invariants, ensure_ascii=False)),
    )
    conn.execute("UPDATE incidents SET incident_status=? WHERE id=?",
                 (IncidentStatus.CONVERTED.value, incident_id))
    conn.commit()
    return {"case_id": case_id, "suite_id": suite_id, "invariants": invariants}


def _traces_for_release(conn: sqlite3.Connection, project_id: str,
                        release: str, cap: int = 20) -> list[str]:
    # docs/08 未定义门禁评估范围（记 retro）：取该 release 全部运行（上限 cap），
    # 任一运行违反不变量即视为复现——比只看最新一次诚实
    rows = conn.execute(
        """SELECT trace_id, MAX(ts) latest FROM spans
           WHERE project_id=? AND agent_version=? GROUP BY trace_id
           ORDER BY latest DESC LIMIT ?""",
        (project_id, release, cap),
    ).fetchall()
    return [r["trace_id"] for r in rows]


def _check_case(conn: sqlite3.Connection, case: dict, trace_id: str) -> dict:
    invariants = json.loads(case["invariants"])
    g = build_graph(conn, trace_id)
    project_id = next(iter(g.spans.values()))["project_id"] if g.spans else "default"
    findings = evaluate_rules(conn, g, None, load_rulepack(project_id))
    violated = []
    for inv in invariants:
        if inv["kind"] == "no_recurrence":
            hits = [f for f in findings if f.cause_type == inv["failure_type"]]
            step = inv.get("fault_step_name")
            if step:
                hits = [f for f in hits
                        if g.spans.get(f.first_fault_span_id, {}).get("step_name") == step] or hits
            if hits:
                violated.append({"invariant": inv, "detail": hits[0].summary})
        elif inv["kind"] == "quality_pass":
            failed = conn.execute(
                "SELECT COUNT(*) c FROM spans WHERE trace_id=? AND quality_verdict='failed'",
                (trace_id,),
            ).fetchone()
            if failed["c"]:
                violated.append({"invariant": inv, "detail": "质量校验步骤结论为 failed"})
    return {"case_id": case["id"], "trace_id": trace_id,
            "passed": not violated, "violations": violated}


def run_gate(conn: sqlite3.Connection, suite_id: str, release: str, mode: str) -> dict:
    mode = GateMode(mode).value
    suite = conn.execute("SELECT * FROM suites WHERE id=?", (suite_id,)).fetchone()
    if suite is None:
        raise RegressionInvalid(f"回归集 {suite_id} 不存在")
    cases = conn.execute(
        "SELECT * FROM regression_cases WHERE suite_id=? AND review_status='active'",
        (suite_id,),
    ).fetchall()

    trace_ids = _traces_for_release(conn, suite["project_id"], release)
    results = []
    for case in cases:
        if not trace_ids:
            results.append({"case_id": case["id"], "trace_id": None, "passed": False,
                            "violations": [{"detail": f"release {release} 无可评估运行"}]})
            continue
        per_trace = [_check_case(conn, dict(case), tid) for tid in trace_ids]
        worst = next((r for r in per_trace if not r["passed"]), per_trace[0])
        worst["evaluated_traces"] = len(per_trace)
        results.append(worst)

    failed = [r for r in results if not r["passed"]]
    if not cases:
        result = GateResult.PASS.value
    elif failed:
        result = GateResult.BLOCK.value if mode == GateMode.BLOCK.value else GateResult.WARN.value
    else:
        result = GateResult.PASS.value

    run_id = f"gate-{uuid.uuid4().hex[:8]}"
    detail = {"cases": results, "release": release, "evaluated_traces": trace_ids}
    conn.execute(
        "INSERT INTO gate_runs (id, suite_id, release, mode, result, detail, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (run_id, suite_id, release, mode, result, json.dumps(detail, ensure_ascii=False),
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return {"gate_run_id": run_id, "result": result, "detail": detail}
