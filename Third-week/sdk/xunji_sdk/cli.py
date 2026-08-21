"""xunji CLI: `run` (wrap claude -p, live-parse stream-json) and `connect`
(write PostToolUse hooks into .claude/settings.json for零代码旁路上报).

Usage:
  python -m xunji_sdk.cli run --project recon-demo --agent-id recon-agent \
      --agent-version 1.0.0 [--archive fixtures/raw/x.jsonl] -- claude -p "..." \
      --output-format stream-json --verbose
  python -m xunji_sdk.cli connect --project recon-demo [--dir .]
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .parser import StreamParser
from .reporter import DEFAULT_SERVER, report


def cmd_run(args, extra: list[str]) -> int:
    if not extra:
        print("error: `--` 之后必须给出被包装的命令（如 claude -p ...）", file=sys.stderr)
        return 2
    parser = StreamParser()
    archive = Path(args.archive) if args.archive else None
    if archive:
        archive.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        extra, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", env={**os.environ},
    )
    raw_lines = []
    assert proc.stdout is not None
    for line in proc.stdout:
        raw_lines.append(line)
        parser.feed_line(line)
    proc.wait()
    if archive:
        archive.write_text("".join(raw_lines), encoding="utf-8")

    run = parser.finish()
    contract = run.to_contract({
        "project_id": args.project, "agent_id": args.agent_id,
        "agent_version": args.agent_version, "run_name": args.run_name,
    })
    if not run.spans:
        print(f"error: 未解析到任何 span（原始事件 {run.raw_events} 条）；"
              f"被包装命令 stderr: {proc.stderr.read()[:500] if proc.stderr else ''}",
              file=sys.stderr)
        return 1
    outcome = report(contract, server=args.server)
    print(json.dumps({"trace_id": run.trace_id, "spans": len(run.spans),
                      "accepted": outcome.get("accepted"),
                      "incidents": outcome.get("incidents")}, ensure_ascii=False))
    return proc.returncode or 0


def cmd_connect(args) -> int:
    settings_path = Path(args.dir) / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    hook_cmd = (f"{sys.executable} -m xunji_sdk.hook_reporter "
                f"--project {args.project} --server {args.server}")
    hooks = settings.setdefault("hooks", {})
    hooks["PostToolUse"] = [{
        "matcher": "*",
        "hooks": [{"type": "command", "command": hook_cmd}],
    }]
    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print(f"hooks written to {settings_path}（每次工具调用旁路上报到 {args.server}）")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    extra: list[str] = []
    if "--" in argv:
        idx = argv.index("--")
        argv, extra = argv[:idx], argv[idx + 1:]

    p = argparse.ArgumentParser(prog="xunji")
    sub = p.add_subparsers(dest="cmd", required=True)
    runp = sub.add_parser("run", help="包装并旁路采集一次 claude -p 执行")
    runp.add_argument("--project", required=True)
    runp.add_argument("--agent-id", required=True)
    runp.add_argument("--agent-version", default="1.0.0")
    runp.add_argument("--run-name", default="adhoc")
    runp.add_argument("--server", default=DEFAULT_SERVER)
    runp.add_argument("--archive", help="原始 stream-json 存档路径")
    conn = sub.add_parser("connect", help="向 .claude/settings.json 写入旁路上报 hooks")
    conn.add_argument("--project", required=True)
    conn.add_argument("--server", default=DEFAULT_SERVER)
    conn.add_argument("--dir", default=".")

    args = p.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args, extra)
    return cmd_connect(args)


if __name__ == "__main__":
    raise SystemExit(main())
