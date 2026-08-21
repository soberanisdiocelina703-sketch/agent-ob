"""Convert recorded raw stream-json archives → contract fixtures.

fixtures/*.contract.json 全部由真实运行录制转换而来（提示词硬规则：
手造数据不得充当夹具）。重放刷新：跑 record 后再执行本脚本。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "sdk"))

from xunji_sdk.parser import StreamParser  # noqa: E402

MODES = {
    "normal": {"agent_version": "1.0.0"},
    "stale-source": {"agent_version": "1.0.0"},
    "broken-contract": {"agent_version": "1.0.0"},
    "bad-tool-args": {"agent_version": "1.0.0"},
}


def convert(mode: str) -> Path | None:
    raw = ROOT / "fixtures" / "raw" / f"{mode}.jsonl"
    if not raw.exists():
        print(f"skip {mode}: 无录制档 {raw}")
        return None
    parser = StreamParser(trace_id=f"fx-{mode}")
    for line in raw.read_text(encoding="utf-8").splitlines():
        parser.feed_line(line)
    run = parser.finish()
    contract = run.to_contract({
        "project_id": "recon-demo", "agent_id": "recon-agent",
        "agent_version": MODES[mode]["agent_version"], "run_name": "daily-recon",
    })
    out = ROOT / "fixtures" / f"{mode}.contract.json"
    out.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{mode}: {len(run.spans)} spans → {out.name}")
    return out


if __name__ == "__main__":
    for mode in MODES:
        convert(mode)
