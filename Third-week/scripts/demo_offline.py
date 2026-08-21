"""`npm run demo-offline` — 离线态：真实录制 fixtures 回放（无网/无 CLI 可跑）。

fixtures/*.contract.json 由 scripts/convert_fixtures.py 从真实运行录制转换，
不是手造数据。回放后可在前端浏览与复核（诊断仍为现场计算）。
"""
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
SERVER = "http://127.0.0.1:8756"
MODES = ["normal", "stale-source", "broken-contract", "bad-tool-args"]


def main() -> int:
    try:
        httpx.get(f"{SERVER}/v1/projects/recon-demo/checkup", timeout=3)
    except httpx.HTTPError:
        print(f"后端未启动：先执行 npm run demo（{SERVER}）")
        return 1

    for mode in MODES:
        path = ROOT / "fixtures" / f"{mode}.contract.json"
        contract = json.loads(path.read_text(encoding="utf-8"))
        r = httpx.post(f"{SERVER}/v1/traces", json=contract, timeout=30).json()
        inc = r.get("incidents") or {}
        print(f"{mode:16s} accepted={r['accepted']:3d} "
              f"incident={list(inc.values())[0]['incident_id'] if inc else '-'}")
    time.sleep(1.5)  # 等模型异步阶段收尾

    incidents = httpx.get(f"{SERVER}/v1/projects/recon-demo/incidents",
                          timeout=10).json()["incidents"]
    print(f"\n事故 {len(incidents)} 条；诊断摘要：")
    for i in incidents:
        snap = httpx.get(f"{SERVER}/v1/incidents/{i['id']}/diagnosis", timeout=10).json()
        top = snap["candidates"][0] if snap["candidates"] else None
        print(f"- {i['trace_id']}: top1="
              f"{top['first_fault_span_id'] if top else '证据不足'} "
              f"[{top['source'] if top else '-'}]")
    print("\n打开 http://localhost:5173 继续复核 → 转用例 → 门禁。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
