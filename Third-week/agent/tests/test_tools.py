"""Tool-level tests: envelope shapes + all three injection effects.

Runs the real tool chain in-process against a tmp workdir.
"""
import importlib
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS))


@pytest.fixture()
def chain(tmp_path, monkeypatch):
    monkeypatch.setenv("XUNJI_WORKDIR", str(tmp_path))
    monkeypatch.delenv("XUNJI_INJECT", raising=False)

    def run(step: str, inject: str = "none"):
        monkeypatch.setenv("XUNJI_INJECT", inject)
        mod = importlib.import_module(step)
        return mod.execute()

    return run


def test_normal_chain_balances_and_passes(chain):
    for step in ("fetch_billing", "fetch_payments", "reconcile", "write_report"):
        env, code = chain(step)
        assert code == 0, f"{step} failed: {env}"
    env, code = chain("validate_report")
    assert env["quality"] == "pass"
    assert env["output"]["balanced"] is True and env["output"]["delta"] == 0


def test_stale_source_silent_quality_failure(chain):
    """注入点 1：全程无 error，仅质量结论 failed —— 静默故障形态。"""
    chain("fetch_billing")
    env_pay, code = chain("fetch_payments", inject="stale-source")
    assert code == 0
    assert env_pay["output"]["rows"] == 10  # 少两笔
    for step in ("reconcile", "write_report"):
        _, code = chain(step, inject="stale-source")
        assert code == 0  # 中间步骤全部"成功"
    env, code = chain("validate_report", inject="stale-source")
    assert code == 0
    assert env["quality"] == "failed"
    assert env["output"]["delta"] == 8453.25


def test_broken_contract_fails_downstream_not_at_source(chain):
    """注入点 3：契约缺字段在 reconcile，报错却发生在下游 write_report。"""
    chain("fetch_billing")
    chain("fetch_payments", inject="broken-contract")
    env_recon, code = chain("reconcile", inject="broken-contract")
    assert code == 0  # 缺陷步骤自身不报错
    assert "discrepancies" not in env_recon["output"]
    env_report, code = chain("write_report", inject="broken-contract")
    assert code == 1 and env_report["status"] == "error"
    assert "discrepancies" in env_report["output"]["error"]


def test_bad_tool_args_faithfully_propagated_then_rejected(chain, tmp_path):
    """注入点 2：脏数据被忠实传递，reconcile 因非法金额参数失败。"""
    import json

    chain("fetch_billing")
    env_pay, code = chain("fetch_payments", inject="bad-tool-args")
    assert code == 0
    assert env_pay["output"]["total"] is None  # 不掩盖脏数据
    snapshot = json.loads((tmp_path / "payments.json").read_text(encoding="utf-8"))
    assert any(isinstance(r["amount"], str) for r in snapshot["records"])
    env_recon, code = chain("reconcile", inject="bad-tool-args")
    assert code == 1 and env_recon["status"] == "error"
    # 信封 input 中必须能看到非法参数（规则 R-ARG-001 的判定材料）
    assert any(isinstance(r["amount"], str) for r in env_recon["input"]["payments"])
