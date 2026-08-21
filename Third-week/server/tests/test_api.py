"""API-level tests (FastAPI TestClient) — the machine evidence that the
closed loop「入库→事故→诊断→复核→转用例→门禁」works over HTTP."""
import time

import pytest
from fastapi.testclient import TestClient

from xunji import db as dbmod
from xunji.api import app

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


def batch(trace_id, steps, version="1.0.0", offset=0):
    return {"resource": {**RES, "agent_version": version}, "spans": [{
        "trace_id": trace_id, "span_id": f"{trace_id}-{n}", "parent_span_id": None,
        "ts": f"2026-08-20T08:{offset:02d}:{t:02d}Z", "step_type": "tool_call", "step_name": n,
        "execution_status": st, "quality_verdict": qv, "output": o,
    } for n, t, o, st, qv in steps]}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("XUNJI_DB", str(tmp_path / "api.db"))
    dbmod.reset_conn()
    with TestClient(app) as c:
        yield c
    dbmod.reset_conn()


def wait_complete(client, incident_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = client.get(f"/v1/incidents/{incident_id}/diagnosis").json()
        if snap["status"] in ("complete", "failed"):
            return snap
        time.sleep(0.1)
    return snap


@pytest.fixture()
def incident(client):
    assert client.post("/v1/traces", json=batch("t-base", GOOD)).status_code == 202
    resp = client.post("/v1/traces", json=batch("t-fail", STALE, offset=1)).json()
    incident_id = resp["incidents"]["t-fail"]["incident_id"]
    wait_complete(client, incident_id)
    return incident_id


def test_healthy_trace_creates_no_incident(client):
    resp = client.post("/v1/traces", json=batch("t-ok", GOOD)).json()
    assert resp["accepted"] == 4 and resp["incidents"] == {}


def test_full_closed_loop_over_http(client, incident):
    # 诊断快照：Top-1 定位到过期取数步骤
    snap = client.get(f"/v1/incidents/{incident}/diagnosis").json()
    top = snap["candidates"][0]
    assert top["first_fault_span_id"] == "t-fail-fetch_payments"

    # Diff 视图可用且首分歧一致
    diff = client.get(f"/v1/incidents/{incident}/diff").json()
    assert diff["available"] and diff["first_divergence_span_id"] == "t-fail-fetch_payments"

    # 复核确认（If-Match 并发控制）
    r = client.post(f"/v1/candidates/{top['id']}/review",
                    json={"result": "confirmed", "reason_code": "上游缓存未刷新"},
                    headers={"If-Match": str(top["version"])})
    assert r.status_code == 200

    # 转回归用例（仅 confirmed 允许）
    rc = client.post(f"/v1/incidents/{incident}/regression-case",
                     json={"suite_name": "对账回归集"})
    assert rc.status_code == 200
    suite_id = rc.json()["suite_id"]

    # 门禁：旧版本复现 → warn；修复版本 → pass
    warn = client.post(f"/v1/suites/{suite_id}/gate-run",
                       json={"release": "1.0.0", "mode": "warn"}).json()
    assert warn["result"] == "warn"
    client.post("/v1/traces", json=batch("t-fixed", GOOD, version="1.1.0", offset=5))
    ok = client.post(f"/v1/suites/{suite_id}/gate-run",
                     json={"release": "1.1.0", "mode": "warn"}).json()
    assert ok["result"] == "pass"


def test_review_conflict_returns_409(client, incident):
    top = client.get(f"/v1/incidents/{incident}/diagnosis").json()["candidates"][0]
    ok = client.post(f"/v1/candidates/{top['id']}/review", json={"result": "excluded"},
                     headers={"If-Match": str(top["version"])})
    assert ok.status_code == 200
    stale = client.post(f"/v1/candidates/{top['id']}/review", json={"result": "confirmed"},
                        headers={"If-Match": str(top["version"])})
    assert stale.status_code == 409


def test_unconfirmed_regression_returns_422(client, incident):
    r = client.post(f"/v1/incidents/{incident}/regression-case", json={})
    assert r.status_code == 422


def test_trace_list_filters_and_detail(client, incident):
    listed = client.get("/v1/projects/recon-demo/traces",
                        params={"quality_verdict": "failed"}).json()["traces"]
    assert [t["trace_id"] for t in listed] == ["t-fail"]
    detail = client.get("/v1/traces/t-fail").json()
    assert len(detail["spans"]) == 4 and detail["incident_id"] == incident
    assert client.get("/v1/traces/ghost").status_code == 404


def test_incident_list_carries_cluster_info(client, incident):
    incidents = client.get("/v1/projects/recon-demo/incidents").json()["incidents"]
    assert incidents[0]["cluster_title"]


def test_checkup_reports_baseline_coverage(client, incident):
    checkup = client.get("/v1/projects/recon-demo/checkup").json()
    cov = checkup["baseline_coverage"][0]
    assert cov["baseline_available"] is True


def test_sse_stream_emits_snapshot_until_complete(client, incident):
    with client.stream("GET", f"/v1/incidents/{incident}/diagnosis/events") as resp:
        body = ""
        for chunk in resp.iter_text():
            body += chunk
            if "event: snapshot" in body:
                break
    assert "candidates" in body
