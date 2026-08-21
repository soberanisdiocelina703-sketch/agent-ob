"""校验对账报告（质量结论产生处；无注入点）。

balanced 判定：账单与流水总额差 < 0.01 且流水笔数与账单一致。
质量结论通过信封 quality 字段声明——接入方自报质量口径（类似退出码约定）。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import emit, workdir


def execute() -> tuple[dict, int]:
    wd = workdir()
    report = json.loads((wd / "report.json").read_text(encoding="utf-8"))
    billing = json.loads((wd / "billing.json").read_text(encoding="utf-8"))
    payments = json.loads((wd / "payments.json").read_text(encoding="utf-8"))

    delta = round(report["total_billing"] - report["total_payments"], 2)
    balanced = abs(delta) < 0.01 and len(billing["records"]) == len(payments["records"])
    envelope = {
        "step": "validate_report",
        "input": {"report": "report.json",
                  "billing_rows": len(billing["records"]),
                  "payment_rows": len(payments["records"])},
        "output": {"balanced": balanced, "delta": delta,
                   "payments_generated_at": payments.get("generated_at")},
        "quality": "pass" if balanced else "failed",
    }
    return envelope, 0


if __name__ == "__main__":
    env, code = execute()
    raise SystemExit(emit(env, code))
