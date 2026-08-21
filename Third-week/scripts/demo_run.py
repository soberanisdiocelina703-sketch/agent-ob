"""`npm run demo-run` — 真实态：现场执行示例 Agent（正常 + 注入）。

顺序：正常运行（建立基线）→ stale-source（静默质量故障）→ broken-contract。
每次运行都是本机 Claude Code CLI 真实执行，Trace 实时入库、诊断现场计算。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")

SEQUENCE = ["none", "stale-source", "broken-contract"]


def main() -> int:
    modes = sys.argv[1:] or SEQUENCE
    for mode in modes:
        print(f"\n=== 真实执行 inject={mode} ===")
        rc = subprocess.call([PY, str(ROOT / "agent" / "run_agent.py"),
                              "--inject", mode], cwd=ROOT)
        if rc != 0:
            print(f"运行失败（inject={mode}）；确认已登录 Claude Code CLI，"
                  f"或改用 npm run demo-offline")
            return rc
    print("\n完成。打开 http://localhost:5173 查看事故与诊断（现场计算结果）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
