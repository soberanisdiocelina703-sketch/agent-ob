"""生成对账报告 → workdir/report.json（无注入点；broken-contract 时在此崩溃）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import emit, workdir


def execute() -> tuple[dict, int]:
    wd = workdir()
    recon = json.loads((wd / "recon.json").read_text(encoding="utf-8"))
    try:
        report = {
            "total_billing": recon["total_billing"],
            "total_payments": recon["total_payments"],
            "discrepancy_count": len(recon["discrepancies"]),  # 契约缺字段时 KeyError
            "discrepancies": recon["discrepancies"],
        }
    except KeyError as exc:
        envelope = {"step": "write_report",
                    "input": {"recon_file": "recon.json", "present_keys": list(recon)},
                    "output": {"error": f"核对结果缺少必需字段: {exc}"}, "status": "error"}
        return envelope, 1

    path = wd / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    envelope = {
        "step": "write_report",
        "input": {"recon_file": "recon.json"},
        "output": {"report_path": str(path), "total_billing": report["total_billing"],
                   "total_payments": report["total_payments"],
                   "discrepancy_count": report["discrepancy_count"]},
    }
    return envelope, 0


if __name__ == "__main__":
    env, code = execute()
    raise SystemExit(emit(env, code))
