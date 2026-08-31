"""E2E smoke (offline态): 真实录制 fixtures 回放走通完整闭环——
入库 → 事故 → 诊断 → 复核 → 转用例 → 门禁。

这是「Demo 可运行」的机器证据（提示词任务 5）；同时如实断言三类注入的
首故障点命中位置，DEMO.md 的命中实录以此为准。
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xunji import db as dbmod
from xunji.api import app

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load(mode: str) -> dict:
    return json.loads((FIXTURES / f"{mode}.contract.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os

    os.environ["XUNJI_DB"] = str(tmp_path_factory.mktemp("e2e") / "e2e.db")
    dbmod.reset_conn()
    with TestClient(app) as c:
        yield c
    dbmod.reset_conn()
    os.environ.pop("XUNJI_DB", None)


def diagnosis_of(client, incident_id):
    import time

    for _ in range(50):
        snap = client.get(f"/v1/incidents/{incident_id}/diagnosis").json()
        if snap["status"] in ("complete", "failed"):
            return snap
        time.sleep(0.1)
    return snap


def step_of(client, trace_id, span_id):
    detail = client.get(f"/v1/traces/{trace_id}").json()
    return next(s["step_name"] for s in detail["spans"] if s["span_id"] == span_id)


def test_01_baseline_ingests_clean(client):
    r = client.post("/v1/traces", json=load("normal")).json()
    assert r["accepted"] == 12 and r["incidents"] == {}


def test_02_stale_source_diff_locates_fetch_payments(client):
    r = client.post("/v1/traces", json=load("stale-source")).json()
    inc = r["incidents"]["fx-stale-source"]["incident_id"]
    snap = diagnosis_of(client, inc)
    top = snap["candidates"][0]
    assert step_of(client, "fx-stale-source", top["first_fault_span_id"]) == "fetch_payments"
    assert top["source"] == "diff"  # 全程无报错，规则沉默，Diff 是主路径


def test_03_broken_contract_rule_locates_reconcile_not_crash_site(client):
    r = client.post("/v1/traces", json=load("broken-contract")).json()
    inc = r["incidents"]["fx-broken-contract"]["incident_id"]
    snap = diagnosis_of(client, inc)
    steps = [step_of(client, "fx-broken-contract", c["first_fault_span_id"])
             for c in snap["candidates"]]
    assert steps[0] == "reconcile"       # 缺陷源头（deterministic）
    assert "write_report" in steps        # 报错处仅是候选之一——报错≠根因


def test_04_bad_tool_args_rule_names_the_field(client):
    r = client.post("/v1/traces", json=load("bad-tool-args")).json()
    inc = r["incidents"]["fx-bad-tool-args"]["incident_id"]
    snap = diagnosis_of(client, inc)
    arg_cands = [c for c in snap["candidates"] if c["cause_type"] == "tool_arg_violation"]
    assert arg_cands and "amount" in arg_cands[0]["summary"]
    # V2（反馈迭代闭环）：聚合多样性保底后，指向注入点（数据源退化处）的
    # Diff 候选必须进 Top-3——V1 曾被三条同分规则候选挤出（命中实录 2/3）
    steps = [step_of(client, "fx-bad-tool-args", c["first_fault_span_id"])
             for c in snap["candidates"]]
    assert "fetch_payments" in steps


def test_05_review_convert_gate_closes_the_loop(client):
    incidents = client.get("/v1/projects/recon-demo/incidents").json()["incidents"]
    stale_inc = next(i for i in incidents if i["trace_id"] == "fx-stale-source")
    top = client.get(f"/v1/incidents/{stale_inc['id']}/diagnosis").json()["candidates"][0]

    r = client.post(f"/v1/candidates/{top['id']}/review",
                    json={"result": "confirmed", "reason_code": "上游缓存未刷新"},
                    headers={"If-Match": str(top["version"])})
    assert r.status_code == 200

    rc = client.post(f"/v1/incidents/{stale_inc['id']}/regression-case",
                     json={"suite_name": "对账回归集"}).json()
    suite = rc["suite_id"]

    warn = client.post(f"/v1/suites/{suite}/gate-run",
                       json={"release": "1.0.0", "mode": "warn"}).json()
    assert warn["result"] == "warn"  # 故障版本仍在线 → 警告

    fixed = load("normal")
    fixed["resource"]["agent_version"] = "1.1.0"  # 仅版本标签变化，数据为真实录制
    for s in fixed["spans"]:
        s["trace_id"] = "fx-fixed"
        s["span_id"] = s["span_id"].replace("fx-normal", "fx-fixed")
        if s.get("parent_span_id"):
            s["parent_span_id"] = s["parent_span_id"].replace("fx-normal", "fx-fixed")
    client.post("/v1/traces", json=fixed)
    ok = client.post(f"/v1/suites/{suite}/gate-run",
                     json={"release": "1.1.0", "mode": "warn"}).json()
    assert ok["result"] == "pass"
