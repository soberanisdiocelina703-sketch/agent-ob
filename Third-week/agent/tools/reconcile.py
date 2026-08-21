"""逐项核对账单与流水 → workdir/recon.json。

[注入点 3] broken-contract：输出信封与中间文件均缺失 discrepancies 字段
（模拟本步骤自身的契约缺陷），下游 write_report 数步之后才失败。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import emit, inject_mode, workdir


def execute() -> tuple[dict, int]:
    wd = workdir()
    billing = json.loads((wd / "billing.json").read_text(encoding="utf-8"))
    payments = json.loads((wd / "payments.json").read_text(encoding="utf-8"))

    envelope_input = {"billing": billing["records"], "payments": payments["records"]}

    try:
        total_billing = round(sum(float(r["amount"]) for r in billing["records"]), 2)
        total_payments = round(sum(float(r["amount"]) for r in payments["records"]), 2)
    except (TypeError, ValueError) as exc:
        envelope = {"step": "reconcile", "input": envelope_input,
                    "output": {"error": f"金额字段无法解析: {exc}"}, "status": "error"}
        return envelope, 1

    paid = {r["order_id"] for r in payments["records"]}
    discrepancies = [{"order_id": r["order_id"], "amount": r["amount"], "reason": "未见支付流水"}
                     for r in billing["records"] if r["order_id"] not in paid]

    output = {"total_billing": total_billing, "total_payments": total_payments}
    if inject_mode() != "broken-contract":
        output["discrepancies"] = discrepancies

    (wd / "recon.json").write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    return {"step": "reconcile", "input": envelope_input, "output": output}, 0


if __name__ == "__main__":
    env, code = execute()
    raise SystemExit(emit(env, code))
