import pytest

from xunji import db
from xunji.ingestion import ingest


@pytest.fixture()
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def make_span(span_id="s1", parent=None, **over):
    span = {
        "trace_id": "t1",
        "span_id": span_id,
        "parent_span_id": parent,
        "ts": "2026-08-20T08:00:00Z",
        "duration_ms": 120,
        "step_type": "tool_call",
        "raw_step_type": "Bash",
        "step_name": "fetch_billing",
        "execution_status": "success",
        "quality_verdict": "unevaluated",
        "input": {"cmd": "python tools/fetch_billing.py"},
        "output": {"rows": 152},
        "attrs": {},
    }
    span.update(over)
    return span


RESOURCE = {
    "project_id": "recon-demo",
    "agent_id": "recon-agent",
    "agent_version": "1.0.0",
    "run_name": "daily-recon",
}


def test_normal_batch_stored_with_payload_refs(conn):
    result = ingest(conn, {"resource": RESOURCE, "spans": [make_span("s1"), make_span("s2", parent="s1")]})
    assert result.accepted == 2 and result.dropped == 0
    row = conn.execute("SELECT * FROM spans WHERE span_id='s1'").fetchone()
    assert row["project_id"] == "recon-demo"
    assert row["agent_id"] == "recon-agent"
    payload = conn.execute(
        "SELECT content FROM payloads WHERE ref=?", (row["output_ref"],)
    ).fetchone()
    assert "152" in payload["content"]


def test_missing_required_field_drops_span_with_warning(conn):
    bad = make_span("s9")
    del bad["ts"]
    result = ingest(conn, {"resource": RESOURCE, "spans": [make_span("s1"), bad]})
    assert result.accepted == 1 and result.dropped == 1
    assert any(w.code == "missing_required" for w in result.warnings)


def test_broken_parent_is_flagged_not_rejected(conn):
    """docs/06 数据侧异常: 断链 Trace 降级处理而不是崩溃."""
    result = ingest(conn, {"resource": RESOURCE, "spans": [make_span("s2", parent="ghost")]})
    assert result.accepted == 1
    row = conn.execute("SELECT link_kind FROM spans WHERE span_id='s2'").fetchone()
    assert row["link_kind"] == "broken_parent"
    assert any(w.code == "broken_parent" for w in result.warnings)


def test_duplicate_span_keeps_first(conn):
    ingest(conn, {"resource": RESOURCE, "spans": [make_span("s1", step_name="first")]})
    result = ingest(conn, {"resource": RESOURCE, "spans": [make_span("s1", step_name="second")]})
    assert result.dropped == 1
    assert any(w.code == "duplicate_span" for w in result.warnings)
    row = conn.execute("SELECT step_name FROM spans WHERE span_id='s1'").fetchone()
    assert row["step_name"] == "first"


def test_unknown_step_type_maps_to_other(conn):
    ingest(conn, {"resource": RESOURCE, "spans": [make_span("s1", step_type="weird_kind")]})
    row = conn.execute("SELECT step_type, raw_step_type FROM spans WHERE span_id='s1'").fetchone()
    assert row["step_type"] == "other"
