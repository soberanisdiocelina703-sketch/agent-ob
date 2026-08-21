"""拉取支付流水 → workdir/payments.json。

[注入点 1] stale-source：返回昨日缓存副本（generated_at 落后、少两笔）——
模拟上游缓存未刷新，全程无报错的静默质量故障。
[注入点 2] bad-tool-args：上游导出格式退化（金额为中文字符串），数据被
忠实传递，下游工具因非法参数失败。
两个注入都只发生在数据层；工具逻辑与正常运行完全一致。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import emit, inject_mode, load_data, today, workdir, yesterday


def execute() -> tuple[dict, int]:
    mode = inject_mode()
    if mode == "stale-source":
        source, generated_at = "payments_stale.json", yesterday()
    elif mode == "bad-tool-args":
        source, generated_at = "payments_badtype.json", today()
    else:
        source, generated_at = "payments_fresh.json", today()

    records = load_data(source)["records"]
    snapshot = {"generated_at": generated_at, "records": records}
    (workdir() / "payments.json").write_text(
        json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")

    def safe_total(rs):
        try:
            return round(sum(float(r["amount"]) for r in rs), 2)
        except (TypeError, ValueError):
            return None  # 金额脏数据时如实返回 null，不掩盖

    envelope = {
        "step": "fetch_payments",
        "input": {"source": "payments_gateway", "date": today()},
        "output": {"rows": len(records), "total": safe_total(records),
                   "generated_at": generated_at},
    }
    return envelope, 0


if __name__ == "__main__":
    env, code = execute()
    raise SystemExit(emit(env, code))
