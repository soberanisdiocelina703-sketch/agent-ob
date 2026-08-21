import pytest

from xunji import db
from xunji.diffgen import find_baseline, generate_diff_finding
from xunji.causal import build_graph
from xunji.ingestion import ingest

RES = {"project_id": "recon-demo", "agent_id": "recon-agent", "agent_version": "1.0.0",
       "run_name": "daily-recon"}


@pytest.fixture()
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def run_trace(conn, trace_id, steps, resource=None):
    """steps: [(step_name, ts_sec, output_dict, status)]"""
    spans = [{
        "trace_id": trace_id, "span_id": f"{trace_id}-{name}", "parent_span_id": None,
        "ts": f"2026-08-20T08:00:{ts:02d}Z", "step_type": "tool_call", "step_name": name,
        "execution_status": status, "output": out,
        "quality_verdict": "pass" if status == "success" else "failed",
    } for name, ts, out, status in steps]
    ingest(conn, {"resource": resource or RES, "spans": spans})


GOOD = [
    ("fetch_billing", 1, {"rows": 152, "total": 48210.5, "generated_at": "2026-08-20"}, "success"),
    ("fetch_payments", 2, {"rows": 152, "total": 48210.5, "generated_at": "2026-08-20"}, "success"),
    ("reconcile", 4, {"total_billing": 48210.5, "total_payments": 48210.5, "discrepancies": []}, "success"),
]
STALE = [
    ("fetch_billing", 1, {"rows": 152, "total": 48210.5, "generated_at": "2026-08-20"}, "success"),
    ("fetch_payments", 2, {"rows": 147, "total": 44798.5, "generated_at": "2026-08-19"}, "success"),
    ("reconcile", 4, {"total_billing": 48210.5, "total_payments": 44798.5,
                      "discrepancies": [{"id": "B9"}]}, "success"),
]


def test_baseline_selection_prefers_latest_compatible_success(conn):
    run_trace(conn, "old", GOOD)
    run_trace(conn, "new", [(n, t + 10, o, s) for n, t, o, s in GOOD])
    assert find_baseline(conn, "recon-demo", "recon-agent", "1.0.0", exclude="x") == "new"


def test_baseline_excludes_failed_and_incompatible_versions(conn):
    bad = [("fetch_billing", 1, {"err": 1}, "error")]
    run_trace(conn, "failed-run", bad)
    run_trace(conn, "other-ver", GOOD, resource={**RES, "agent_version": "2.0.0"})
    assert find_baseline(conn, "recon-demo", "recon-agent", "1.0.0", exclude="x") is None


def test_no_baseline_returns_none_finding_with_reason(conn):
    """冷启动降级：无基线时不硬造候选（spec S5 / docs/06 证据不足分支）。"""
    run_trace(conn, "t-fail", STALE)
    g = build_graph(conn, "t-fail")
    finding, reason = generate_diff_finding(conn, g, baseline_trace_id=None)
    assert finding is None and reason == "no_baseline"


def test_first_divergence_located_at_stale_step_not_symptom(conn):
    """静默故障主张的代码化：分歧首现于取数步骤，而非下游核对/校验。"""
    run_trace(conn, "t-base", GOOD)
    run_trace(conn, "t-fail", STALE)
    g = build_graph(conn, "t-fail")
    finding, _ = generate_diff_finding(conn, g, "t-base")
    assert finding is not None
    assert finding.first_fault_span_id == "t-fail-fetch_payments"
    assert any(e["side"] == "support" and "t-fail/t-fail-fetch_payments" == e["span_ref"]
               for e in finding.evidence)
    # 分歧详情必须同时呈现两侧值（正反对照的物质基础）
    assert "147" in str(finding.evidence) and "152" in str(finding.evidence)


def test_identical_traces_produce_no_finding(conn):
    run_trace(conn, "t-base", GOOD)
    run_trace(conn, "t-same", GOOD)
    g = build_graph(conn, "t-same")
    finding, reason = generate_diff_finding(conn, g, "t-base")
    assert finding is None and reason == "no_divergence"


def test_missing_step_counts_as_divergence(conn):
    run_trace(conn, "t-base", GOOD)
    run_trace(conn, "t-short", GOOD[:1])
    g = build_graph(conn, "t-short")
    finding, _ = generate_diff_finding(conn, g, "t-base")
    assert finding is not None and "fetch_payments" in finding.summary


def test_llm_text_drift_is_not_divergence(conn):
    """真实录制教训（retro 2026-08-21）：assistant 文本每次漂移，不得进对照。"""
    def with_llm(trace_id, text):
        run_trace(conn, trace_id, GOOD)
        ingest(conn, {"resource": RES, "spans": [{
            "trace_id": trace_id, "span_id": f"{trace_id}-llm", "parent_span_id": None,
            "ts": "2026-08-20T08:00:09Z", "step_type": "llm_call",
            "step_name": "assistant_message", "execution_status": "success",
            "output": {"text": text},
        }]})

    with_llm("t-base", "对账完成，一切正常")
    with_llm("t-same", "五步全部执行成功，账实相符")  # 文本不同但业务一致
    g = build_graph(conn, "t-same")
    finding, reason = generate_diff_finding(conn, g, "t-base")
    assert finding is None and reason == "no_divergence"
