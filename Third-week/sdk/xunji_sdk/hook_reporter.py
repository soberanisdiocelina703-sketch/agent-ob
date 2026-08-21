"""PostToolUse hook reporter: stdin JSON → one-span report (零代码 CLI 接入).

Claude Code invokes this per tool call; session_id groups spans into a trace.
Root/llm spans are absent in hook mode — lower fidelity than `xunji run`,
documented in docs/02.
"""
import argparse
import json
import sys
import uuid
from datetime import datetime, timezone

from .parser import StreamParser
from .reporter import DEFAULT_SERVER, report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True)
    p.add_argument("--server", default=DEFAULT_SERVER)
    args = p.parse_args()

    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0  # hook 不阻塞宿主

    session = event.get("session_id") or uuid.uuid4().hex[:8]
    trace_id = f"cc-{session[:12]}"
    tool_input = event.get("tool_input") or {}
    response = event.get("tool_response")
    text = json.dumps(response, ensure_ascii=False) if not isinstance(response, str) else response
    envelope = StreamParser._try_envelope(text or "")

    span = {
        "trace_id": trace_id,
        "span_id": f"{trace_id}-{uuid.uuid4().hex[:8]}",
        "parent_span_id": None,
        "ts": datetime.now(timezone.utc).isoformat(),
        "step_type": "tool_call",
        "raw_step_type": event.get("tool_name", "tool"),
        "step_name": (envelope or {}).get("step")
        or StreamParser._guess_step_name({"name": event.get("tool_name"),
                                          "input": tool_input}),
        "execution_status": "success",
        "input": (envelope or {}).get("input", tool_input),
        "output": (envelope or {}).get("output", {"text": (text or "")[:2000]}),
    }
    if envelope and envelope.get("quality") in ("pass", "failed"):
        span["quality_verdict"] = envelope["quality"]

    try:
        report({"resource": {"project_id": args.project, "agent_id": "cli-session",
                             "agent_version": "unknown", "run_name": "interactive",
                             "session_id": session},
                "spans": [span]}, server=args.server)
    except Exception:
        pass  # 上报失败不影响宿主会话
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
