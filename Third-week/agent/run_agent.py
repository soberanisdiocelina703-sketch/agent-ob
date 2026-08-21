"""Demo agent driver: run the reconciliation workload via local Claude Code CLI
with xunji bypass collection.

同一 task_prompt.md 用于正常与全部注入运行 —— 差异只来自 XUNJI_INJECT 环境
变量（工具/数据层），这是 Demo 诚实性的硬规则。
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).parent
ROOT = AGENT_DIR.parent

INJECT_MODES = ("none", "stale-source", "broken-contract", "bad-tool-args")


def run(inject: str, server: str, archive: str | None = None,
        agent_version: str = "1.0.0") -> int:
    workdir = AGENT_DIR / "workdir"
    if workdir.exists():
        shutil.rmtree(workdir)

    env = {**os.environ, "XUNJI_INJECT": inject,
           "XUNJI_WORKDIR": str(workdir),
           "PYTHONPATH": str(ROOT / "sdk")}
    prompt = (AGENT_DIR / "task_prompt.md").read_text(encoding="utf-8")

    cmd = [
        sys.executable, "-m", "xunji_sdk.cli", "run",
        "--project", "recon-demo", "--agent-id", "recon-agent",
        "--agent-version", agent_version, "--run-name", "daily-recon",
        "--server", server,
    ]
    if archive:
        cmd += ["--archive", archive]
    cmd += [
        "--",
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose",
        "--allowedTools", "Bash", "--max-turns", "25",
    ]
    print(f"[agent] inject={inject} version={agent_version} → claude -p (真实执行)")
    return subprocess.call(cmd, cwd=str(AGENT_DIR), env=env)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--inject", choices=INJECT_MODES, default="none")
    p.add_argument("--server", default="http://127.0.0.1:8756")
    p.add_argument("--archive")
    p.add_argument("--agent-version", default="1.0.0")
    args = p.parse_args()
    return run(args.inject, args.server, args.archive, args.agent_version)


if __name__ == "__main__":
    raise SystemExit(main())
