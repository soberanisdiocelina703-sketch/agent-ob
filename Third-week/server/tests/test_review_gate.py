import pytest

from xunji import db
from xunji.diagnosis import load_candidates
from xunji.evaluator import MockEvaluator
from xunji.gate import RegressionInvalid, create_regression_case, run_gate
from xunji.ingestion import ingest
from xunji.pipeline import process_trace
from xunji.review import ReviewConflict, ReviewInvalid, submit_review

RES = {"project_id": "recon-demo", "agent_id": "recon-agent", "agent_version": "1.0.0",
       "run_name": "daily-recon"}

GOOD = [
    ("fetch_billing", 1, {"rows": 152, "total": 48210.5, "generated_at": "2026-08-20"}, "success", "pass"),
    ("fetch_payments", 2, {"rows": 152, "total": 48210.5, "generated_at": "2026-08-20"}, "success", "pass"),
    ("reconcile", 4, {"total_billing": 48210.5, "total_payments": 48210.5, "discrepancies": []}, "success", "pass"),
    ("validate_report", 6, {"balanced": True}, "success", "pass"),
]
STALE = [
    ("fetch_billing", 1, {"rows": 152, "total": 48210.5, "generated_at": "2026-08-20"}, "success", "unevaluated"),
    ("fetch_payments", 2, {"rows": 147, "total": 44798.5, "generated_at": "2026-08-19"}, "success", "unevaluated"),
    ("reconcile", 4, {"total_billing": 48210.5, "total_payments": 44798.5,
                      "discrepancies": [{"id": "B9"}]}, "success", "unevaluated"),
    ("validate_report", 6, {"balanced": False}, "success", "failed"),
]


@pytest.fixture()
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def run_trace(conn, trace_id, steps, version="1.0.0", offset=0):
    spans = [{
        "trace_id": trace_id, "span_id": f"{trace_id}-{n}", "parent_span_id": None,
        "ts": f"2026-08-20T08:{offset:02d}:{t:02d}Z", "step_type": "tool_call", "step_name": n,
        "execution_status": st, "quality_verdict": qv, "output": o,
    } for n, t, o, st, qv in steps]
    ingest(conn, {"resource": {**RES, "agent_version": version}, "spans": spans})


@pytest.fixture()
def diagnosed(conn):
    run_trace(conn, "t-base", GOOD)
    run_trace(conn, "t-fail", STALE, offset=1)
    result = process_trace(conn, "t-fail", evaluator=MockEvaluator())
    top = load_candidates(conn, result["diagnosis_id"])[0]
    return conn, result["incident_id"], top


class TestReview:
    def test_confirm_writes_verdict_and_updates_incident(self, diagnosed):
        conn, incident_id, top = diagnosed
        out = submit_review(conn, top["id"], "confirmed", if_match=0,
                            reason_code="上游数据源未刷新")
        assert out["candidate_version"] == 1
        inc = conn.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone()
        assert inc["review_status"] == "confirmed" and inc["incident_status"] == "reviewed"

    def test_stale_if_match_conflicts_409(self, diagnosed):
        conn, _, top = diagnosed
        submit_review(conn, top["id"], "excluded", if_match=0)
        with pytest.raises(ReviewConflict):
            submit_review(conn, top["id"], "confirmed", if_match=0)

    def test_re_review_supersedes_previous_verdict(self, diagnosed):
        """docs/06 用户侧异常：误复核可重新复核，旧结论保留审计链。"""
        conn, _, top = diagnosed
        first = submit_review(conn, top["id"], "excluded", if_match=0)
        submit_review(conn, top["id"], "confirmed", if_match=1)
        old = conn.execute("SELECT * FROM verdicts WHERE id=?", (first["verdict_id"],)).fetchone()
        assert old["superseded_by"] is not None

    def test_invalid_result_rejected(self, diagnosed):
        conn, _, top = diagnosed
        with pytest.raises(ReviewInvalid):
            submit_review(conn, top["id"], "maybe", if_match=0)

    def test_manual_cause_ref_recorded_for_cold_start(self, diagnosed):
        conn, _, top = diagnosed
        submit_review(conn, top["id"], "insufficient", if_match=0,
                      correct_cause_ref="t-fail/t-fail-fetch_payments")
        v = conn.execute("SELECT * FROM verdicts WHERE candidate_id=? AND superseded_by IS NULL",
                        (top["id"],)).fetchone()
        assert v["correct_cause_ref"] == "t-fail/t-fail-fetch_payments"


class TestRegressionAndGate:
    def _confirm(self, diagnosed):
        conn, incident_id, top = diagnosed
        submit_review(conn, top["id"], "confirmed", if_match=0)
        return conn, incident_id

    def test_only_confirmed_incident_converts(self, diagnosed):
        conn, incident_id, _ = diagnosed
        with pytest.raises(RegressionInvalid):
            create_regression_case(conn, incident_id)

    def test_confirmed_incident_packages_invariants(self, diagnosed):
        conn, incident_id = self._confirm(diagnosed)
        out = create_regression_case(conn, incident_id, "对账回归集")
        kinds = {i["kind"] for i in out["invariants"]}
        assert kinds == {"no_recurrence", "quality_pass"}
        inc = conn.execute("SELECT incident_status FROM incidents WHERE id=?",
                           (incident_id,)).fetchone()
        assert inc["incident_status"] == "converted"

    def test_gate_warns_when_failure_recurs(self, diagnosed):
        conn, incident_id = self._confirm(diagnosed)
        out = create_regression_case(conn, incident_id)
        gate = run_gate(conn, out["suite_id"], release="1.0.0", mode="warn")
        assert gate["result"] == "warn"
        assert any(not c["passed"] for c in gate["detail"]["cases"])

    def test_gate_blocks_in_block_mode(self, diagnosed):
        conn, incident_id = self._confirm(diagnosed)
        out = create_regression_case(conn, incident_id)
        assert run_gate(conn, out["suite_id"], "1.0.0", "block")["result"] == "block"

    def test_gate_passes_after_fix(self, diagnosed):
        conn, incident_id = self._confirm(diagnosed)
        out = create_regression_case(conn, incident_id)
        run_trace(conn, "t-fixed", GOOD, version="1.1.0", offset=5)
        gate = run_gate(conn, out["suite_id"], release="1.1.0", mode="warn")
        assert gate["result"] == "pass"

    def test_gate_unknown_suite_invalid(self, conn):
        with pytest.raises(RegressionInvalid):
            run_gate(conn, "suite-ghost", "1.0.0", "warn")
