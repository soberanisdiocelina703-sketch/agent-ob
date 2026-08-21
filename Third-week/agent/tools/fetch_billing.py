"""拉取账单明细 → workdir/billing.json（无注入点：账单侧始终新鲜）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import emit, load_data, today, total_of, workdir


def execute() -> tuple[dict, int]:
    data = load_data("billing.json")
    records = data["records"]
    snapshot = {"generated_at": today(), "records": records}
    (workdir() / "billing.json").write_text(
        json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    envelope = {
        "step": "fetch_billing",
        "input": {"source": "billing_api", "date": today()},
        "output": {"rows": len(records), "total": total_of(records),
                   "generated_at": today()},
    }
    return envelope, 0


if __name__ == "__main__":
    env, code = execute()
    raise SystemExit(emit(env, code))
