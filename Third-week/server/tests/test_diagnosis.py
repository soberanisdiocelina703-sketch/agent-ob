import pytest

from xunji import db
from xunji.causal import build_graph
from xunji.diagnosis import aggregate, load_candidates
from xunji.evaluator import ClaudeCodeEvaluator, MockEvaluator, validate_model_output
from xunji.ingestion import ingest
from xunji.pipeline import process_trace

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
                      "discrepancies": [{"id": "B9", "delta": 3412.0}]}, "success", "unevaluated"),
    ("validate_report", 6, {"balanced": False, "delta": 3412.0}, "success", "failed"),
]


@pytest.fixture()
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def run_trace(conn, trace_id, steps):
    spans = [{
        "trace_id": trace_id, "span_id": f"{trace_id}-{n}", "parent_span_id": None,
        "ts": f"2026-08-20T08:00:{t:02d}Z", "step_type": "tool_call", "step_name": n,
        "execution_status": st, "quality_verdict": qv, "output": o,
    } for n, t, o, st, qv in steps]
    ingest(conn, {"resource": RES, "spans": spans})


def cand(source="rule", span="s1", cause="exception", evidence=None):
    return {"source": source, "cause_type": cause, "summary": f"{source} candidate",
            "first_fault_span_id": span,
            "evidence": evidence if evidence is not None
            else [{"side": "support", "kind": "k", "span_ref": f"t/{span}", "excerpt": "x"}]}


class TestAggregate:
    def test_drops_candidate_without_evidence(self):
        ranked, dropped = aggregate([cand(evidence=[]), cand(span="s2")])
        assert dropped == 1
        assert all(c["first_fault_span_id"] != "s1" or c["evidence"] for c in ranked)

    def test_dedup_merges_same_span_and_cause_keeping_higher_source(self):
        ranked, _ = aggregate([cand("rule", "s1"), cand("diff", "s1")])
        assert len(ranked) == 1
        assert ranked[0]["source"] == "rule"
        assert len(ranked[0]["evidence"]) == 2  # 证据合并不丢

    def test_top3_truncation_and_rank_order(self):
        ranked, _ = aggregate([
            cand("model", "s1", "quality_check_failed"), cand("rule", "s2"),
            cand("diff", "s3", "quality_check_failed"), cand("model", "s4", "timeout"),
        ])
        assert len(ranked) == 3
        assert [c["rank"] for c in ranked] == [1, 2, 3]
        assert ranked[0]["source"] == "rule"  # 确定性优先

    def test_refuting_evidence_lowers_score(self):
        with_refute = cand("model", "s1", evidence=[
            {"side": "support", "kind": "k", "span_ref": "t/s1", "excerpt": "x"},
            {"side": "refute", "kind": "k", "span_ref": "t/s2", "excerpt": "y"},
        ])
        ranked, _ = aggregate([with_refute, cand("model", "s3")])
        assert ranked[0]["first_fault_span_id"] == "s3"

    def test_evidence_grade_mapping(self):
        ranked, _ = aggregate([cand("rule", "s1"), cand("diff", "s2"), cand("model", "s3")])
        grades = {c["source"]: c["evidence_grade"] for c in ranked}
        assert grades == {"rule": "deterministic", "diff": "diff_based",
                          "model": "model_heuristic"}


class TestValidateModelOutput:
    def _graph(self, conn):
        run_trace(conn, "t1", STALE)
        return build_graph(conn, "t1")

    def test_rejects_unknown_span_and_evidence_less(self, conn):
        g = self._graph(conn)
        out = validate_model_output({"candidates": [
            {"first_fault_span_id": "ghost", "summary": "bad",
             "evidence": [{"span_ref": "t1/ghost", "excerpt": "x"}]},
            {"first_fault_span_id": "t1-reconcile", "summary": "no evidence", "evidence": []},
            {"first_fault_span_id": "t1-fetch_payments", "cause_type": "quality_check_failed",
             "summary": "ok", "evidence": [{"span_ref": "t1-fetch_payments", "excerpt": "147"}]},
        ]}, g)
        assert len(out) == 1 and out[0].first_fault_span_id == "t1-fetch_payments"


class TestClaudeCodeEvaluator:
    def test_parses_runner_output_and_validates(self, conn):
        run_trace(conn, "t1", STALE)
        g = build_graph(conn, "t1")
        fake = ('{"result": "分析如下 {\\"candidates\\": [{\\"first_fault_span_id\\": '
                '\\"t1-fetch_payments\\", \\"cause_type\\": \\"quality_check_failed\\", '
                '\\"summary\\": \\"stale data\\", \\"evidence\\": [{\\"span_ref\\": '
                '\\"t1-fetch_payments\\", \\"excerpt\\": \\"generated_at 2026-08-19\\"}]}]}"}')
        ev = ClaudeCodeEvaluator(runner=lambda prompt: fake)
        out = ev.evaluate(conn, g, "t1-validate_report")
        assert len(out) == 1 and out[0].first_fault_span_id == "t1-fetch_payments"

    def test_garbage_output_yields_no_candidates_not_crash(self, conn):
        run_trace(conn, "t1", STALE)
        g = build_graph(conn, "t1")
        ev = ClaudeCodeEvaluator(runner=lambda prompt: "not json at all")
        assert ev.evaluate(conn, g, "t1-validate_report") == []


class TestEndToEnd:
    def test_stale_source_diagnosed_at_fetch_payments(self, conn):
        """核心验收：静默质量故障 → Top 候选定位到过期取数步骤。"""
        run_trace(conn, "t-base", GOOD)
        run_trace(conn, "t-fail", STALE)
        result = process_trace(conn, "t-fail", evaluator=MockEvaluator())
        assert result, "quality failed trace must create incident"
        cands = load_candidates(conn, result["diagnosis_id"])
        assert cands, "diagnosis must produce candidates"
        assert cands[0]["first_fault_span_id"] == "t-fail-fetch_payments"
        assert cands[0]["evidence_grade"] == "diff_based"
        diag = conn.execute("SELECT status FROM diagnoses WHERE id=?",
                            (result["diagnosis_id"],)).fetchone()
        assert diag["status"] == "complete"

    def test_healthy_trace_creates_no_incident(self, conn):
        run_trace(conn, "t-ok", GOOD)
        assert process_trace(conn, "t-ok") == {}

    def test_model_failure_does_not_block_rule_and_diff_results(self, conn):
        """docs/06 G-4：模型超时后规则/Diff 候选仍在，状态 complete + 原因记录。"""
        run_trace(conn, "t-base", GOOD)
        run_trace(conn, "t-fail", STALE)
        result = process_trace(conn, "t-fail", evaluator=MockEvaluator(fail=True))
        cands = load_candidates(conn, result["diagnosis_id"])
        assert cands and cands[0]["source"] == "diff"
        diag = conn.execute("SELECT * FROM diagnoses WHERE id=?",
                            (result["diagnosis_id"],)).fetchone()
        assert diag["status"] == "complete"
        assert "model:" in (diag["failure_reason"] or "")

    def test_no_baseline_cold_start_yields_insufficient_but_not_crash(self, conn):
        run_trace(conn, "t-fail", STALE)  # 无任何成功基线
        result = process_trace(conn, "t-fail", evaluator=MockEvaluator())
        diag = conn.execute("SELECT * FROM diagnoses WHERE id=?",
                            (result["diagnosis_id"],)).fetchone()
        assert diag is not None  # 诊断对象存在，前端可展示「证据不足」态

    def test_incident_symptom_is_last_failed_span(self, conn):
        run_trace(conn, "t-fail", STALE)
        process_trace(conn, "t-fail", evaluator=MockEvaluator())
        inc = conn.execute("SELECT * FROM incidents WHERE trace_id='t-fail'").fetchone()
        assert inc["symptom_span_id"] == "t-fail-validate_report"
        assert inc["failure_type"] == "quality_check_failed"

    def test_same_signature_joins_same_cluster(self, conn):
        run_trace(conn, "t-f1", STALE)
        run_trace(conn, "t-f2", [(n, t, o, s, q) for n, t, o, s, q in STALE])
        process_trace(conn, "t-f1", evaluator=MockEvaluator())
        process_trace(conn, "t-f2", evaluator=MockEvaluator())
        clusters = conn.execute("SELECT id, count_24h FROM failure_clusters").fetchall()
        assert len(clusters) == 1 and clusters[0]["count_24h"] == 2
