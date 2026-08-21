import pytest

from xunji import db
from xunji.causal import build_graph
from xunji.ingestion import ingest
from xunji.rules import evaluate_rules, load_rulepack

RESOURCE = {"project_id": "recon-demo", "agent_id": "a1", "agent_version": "1", "run_name": "r"}


@pytest.fixture()
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def span(sid, ts, **over):
    s = {
        "trace_id": "t1", "span_id": sid, "parent_span_id": None,
        "ts": f"2026-08-20T08:00:{ts:02d}Z", "step_type": "tool_call",
        "step_name": sid, "execution_status": "success",
    }
    s.update(over)
    return s


def findings_for(conn, symptom="validate"):
    g = build_graph(conn, "t1")
    return evaluate_rules(conn, g, symptom, load_rulepack("recon-demo"))


def test_arg_schema_violation_on_non_numeric_amount(conn):
    ingest(conn, {"resource": RESOURCE, "spans": [
        span("reconcile", 3, input={
            "billing": [{"id": "B1", "amount": 320.0}],
            "payments": [{"id": "P1", "amount": "三百二十元"}],
        }),
        span("validate", 6, execution_status="error"),
    ]})
    hits = [f for f in findings_for(conn) if f.rule_id == "R-ARG-001"]
    assert len(hits) == 1
    assert hits[0].cause_type == "tool_arg_violation"
    assert hits[0].first_fault_span_id == "reconcile"
    assert hits[0].evidence and hits[0].evidence[0]["span_ref"] == "t1/reconcile"


def test_arg_schema_passes_on_valid_input(conn):
    ingest(conn, {"resource": RESOURCE, "spans": [
        span("reconcile", 3, input={"billing": [{"amount": 320.0}], "payments": [{"amount": 320}]}),
    ]})
    assert not [f for f in findings_for(conn) if f.rule_id == "R-ARG-001"]


def test_arg_schema_flags_missing_required_key(conn):
    ingest(conn, {"resource": RESOURCE, "spans": [
        span("reconcile", 3, input={"billing": []}),  # payments 缺失
    ]})
    hits = [f for f in findings_for(conn) if f.rule_id == "R-ARG-001"]
    assert hits and "payments" in hits[0].summary


def test_output_contract_flags_missing_field(conn):
    ingest(conn, {"resource": RESOURCE, "spans": [
        span("reconcile", 3, output={"total_billing": 100, "total_payments": 90}),  # 缺 discrepancies
    ]})
    hits = [f for f in findings_for(conn) if f.rule_id == "R-OUT-001"]
    assert hits and hits[0].cause_type == "output_contract_violation"
    assert "discrepancies" in hits[0].summary


def test_output_contract_flags_unparseable_output(conn):
    ingest(conn, {"resource": RESOURCE, "spans": [
        span("reconcile", 3, output="not json {{{"),
    ]})
    assert [f for f in findings_for(conn) if f.rule_id == "R-OUT-001"]


def test_exception_propagation_picks_earliest_failure_on_path(conn):
    """核心主张的代码化：报错步骤（晚）不等于根因步骤（早）。"""
    ingest(conn, {"resource": RESOURCE, "spans": [
        span("fetch", 1, execution_status="error", output={"err": "boom-upstream-XYZ123"}),
        span("recon", 4, input={"err": "boom-upstream-XYZ123"}, execution_status="error"),
        span("validate", 6, execution_status="error"),
    ]})
    hits = [f for f in findings_for(conn) if f.rule_id == "R-EXC-001"]
    assert len(hits) == 1
    assert hits[0].first_fault_span_id == "fetch"


def test_retrieval_empty_rule(conn):
    ingest(conn, {"resource": RESOURCE, "spans": [
        span("fetch_payments", 1, step_type="retrieval", output={"rows": []}),
        span("validate", 6, execution_status="error"),
    ]})
    hits = [f for f in findings_for(conn) if f.rule_id == "R-RET-001"]
    assert hits and hits[0].cause_type == "retrieval_empty"


def test_no_findings_on_clean_trace(conn):
    ingest(conn, {"resource": RESOURCE, "spans": [
        span("reconcile", 3,
             input={"billing": [{"amount": 1}], "payments": [{"amount": 1}]},
             output={"total_billing": 1, "total_payments": 1, "discrepancies": []}),
    ]})
    assert findings_for(conn) == []
