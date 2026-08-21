import pytest

from xunji import db
from xunji.causal import build_graph, upstream_path
from xunji.ingestion import ingest

RESOURCE = {"project_id": "p1", "agent_id": "a1", "agent_version": "1", "run_name": "r"}


@pytest.fixture()
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def span(sid, parent, ts, inp=None, out=None, **over):
    s = {
        "trace_id": "t1", "span_id": sid, "parent_span_id": parent,
        "ts": f"2026-08-20T08:00:{ts:02d}Z", "step_type": "tool_call",
        "step_name": sid, "execution_status": "success",
        "input": inp, "output": out,
    }
    s.update(over)
    return s


def test_hierarchy_edges_from_parent_ids(conn):
    ingest(conn, {"resource": RESOURCE, "spans": [span("root", None, 0), span("child", "root", 1)]})
    g = build_graph(conn, "t1")
    assert {"src": "root", "dst": "child", "kind": "hierarchy", "confidence": 1.0} in g.edges


def test_dataflow_edge_when_output_appears_in_downstream_input(conn):
    ingest(conn, {"resource": RESOURCE, "spans": [
        span("fetch", None, 0, out={"batch_ref": "PAY-20260820-XK"}),
        span("recon", None, 5, inp={"payments": "PAY-20260820-XK"}),
    ]})
    g = build_graph(conn, "t1")
    flows = [e for e in g.edges if e["kind"] == "dataflow"]
    assert flows and flows[0]["src"] == "fetch" and flows[0]["dst"] == "recon"
    assert flows[0]["confidence"] < 1.0  # 启发式边必须带低于确定边的置信


def test_no_dataflow_edge_for_short_common_fragments(conn):
    ingest(conn, {"resource": RESOURCE, "spans": [
        span("a", None, 0, out={"ok": True, "n": 1}),
        span("b", None, 5, inp={"ok": True, "n": 2}),
    ]})
    g = build_graph(conn, "t1")
    assert not [e for e in g.edges if e["kind"] == "dataflow"]


def test_dataflow_never_points_backwards_in_time(conn):
    ingest(conn, {"resource": RESOURCE, "spans": [
        span("late", None, 9, out={"token": "SHARED-FRAGMENT-1"}),
        span("early", None, 1, inp={"token": "SHARED-FRAGMENT-1"}),
    ]})
    g = build_graph(conn, "t1")
    assert not [e for e in g.edges if e["kind"] == "dataflow"]


def test_broken_parent_span_still_in_graph(conn):
    ingest(conn, {"resource": RESOURCE, "spans": [span("orphan", "ghost", 3)]})
    g = build_graph(conn, "t1")
    assert "orphan" in g.nodes
    assert not [e for e in g.edges if e["kind"] == "hierarchy"]


def test_upstream_path_returns_causal_ancestors_time_ordered(conn):
    ingest(conn, {"resource": RESOURCE, "spans": [
        span("fetch", None, 0, out={"ref": "DATA-FRAGMENT-99"}),
        span("recon", None, 3, inp={"ref": "DATA-FRAGMENT-99"}, out={"report": "RPT-778899"}),
        span("validate", None, 6, inp={"report": "RPT-778899"}),
        span("unrelated", None, 2),
    ]})
    g = build_graph(conn, "t1")
    path = upstream_path(g, "validate")
    assert path == ["fetch", "recon", "validate"]
