"""Claude Code stream-json → xunji trace contract.

Parses the JSONL event stream from `claude -p ... --output-format stream-json
--verbose` and rebuilds a span tree. Events carry no timestamps, so arrival
order + monotonic clock provide ts (recorded honestly in span attrs).

工具信封约定（接入方工具的结构化输出，非 Claude Code 特性）:
tools may print JSON {"step","input","output","quality","status"} — when
present it supplies step_name / payloads / quality_verdict. Without it the
parser falls back to tool-name heuristics (lower fidelity, still T1-valid).
Unknown event types are tolerated and skipped.
"""
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

TOOL_SCRIPT_RE = re.compile(r"tools[/\\](\w+)\.py")


@dataclass
class ParsedRun:
    trace_id: str
    session_id: str | None = None
    spans: list[dict] = field(default_factory=list)
    raw_events: int = 0
    result_text: str | None = None

    def to_contract(self, resource: dict) -> dict:
        return {"resource": {**resource, "session_id": self.session_id,
                             "run_id": self.trace_id},
                "spans": self.spans}


class StreamParser:
    def __init__(self, trace_id: str | None = None, base_time: datetime | None = None):
        self.run = ParsedRun(trace_id=trace_id or f"tr-{uuid.uuid4().hex[:10]}")
        self._t = base_time or datetime.now(timezone.utc)
        self._seq = 0
        self._root_id = f"{self.run.trace_id}-root"
        self._pending_tools: dict[str, dict] = {}  # tool_use_id -> span draft
        self._root_emitted = False

    def _next_ts(self) -> str:
        self._seq += 1
        return (self._t + timedelta(milliseconds=self._seq * 200)).isoformat()

    def _ensure_root(self):
        if not self._root_emitted:
            self.run.spans.append({
                "trace_id": self.run.trace_id, "span_id": self._root_id,
                "parent_span_id": None, "ts": self._next_ts(),
                "step_type": "planning", "raw_step_type": "claude_code_run",
                "step_name": "agent_run", "execution_status": "running",
            })
            self._root_emitted = True

    def feed_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return  # 宽容：非 JSON 行（CLI 横幅等）直接跳过
        self.run.raw_events += 1
        etype = event.get("type")
        if etype == "system" and event.get("subtype") == "init":
            self.run.session_id = event.get("session_id")
            self._ensure_root()
        elif etype == "assistant":
            self._on_assistant(event)
        elif etype == "user":
            self._on_tool_results(event)
        elif etype == "result":
            self._on_result(event)
        # 其他事件类型（stream_event 等）宽容跳过

    def _on_assistant(self, event: dict) -> None:
        self._ensure_root()
        content = (event.get("message") or {}).get("content") or []
        texts = [b.get("text", "") for b in content if b.get("type") == "text"]
        if texts:
            self.run.spans.append({
                "trace_id": self.run.trace_id,
                "span_id": f"{self.run.trace_id}-llm-{self._seq}",
                "parent_span_id": self._root_id, "ts": self._next_ts(),
                "step_type": "llm_call", "raw_step_type": "assistant_message",
                "step_name": "assistant_message",
                "execution_status": "success",
                "output": {"text": " ".join(texts)[:2000]},
            })
        for block in content:
            if block.get("type") != "tool_use":
                continue
            draft = {
                "trace_id": self.run.trace_id,
                "span_id": f"{self.run.trace_id}-tool-{self._seq}-{len(self._pending_tools)}",
                "parent_span_id": self._root_id, "ts": self._next_ts(),
                "step_type": "tool_call", "raw_step_type": block.get("name", "tool"),
                "step_name": self._guess_step_name(block),
                "execution_status": "running",
                "input": block.get("input"),
            }
            self._pending_tools[block.get("id", draft["span_id"])] = draft

    @staticmethod
    def _guess_step_name(block: dict) -> str:
        cmd = str((block.get("input") or {}).get("command", ""))
        m = TOOL_SCRIPT_RE.search(cmd)
        return m.group(1) if m else block.get("name", "tool")

    def _on_tool_results(self, event: dict) -> None:
        content = (event.get("message") or {}).get("content") or []
        for block in content:
            if block.get("type") != "tool_result":
                continue
            draft = self._pending_tools.pop(block.get("tool_use_id"), None)
            if draft is None:
                continue  # 结果无匹配调用（截断流）→ 跳过，接入侧体检可见
            raw = block.get("content")
            if isinstance(raw, list):
                text = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
            else:
                text = str(raw or "")
            envelope = self._try_envelope(text)
            if envelope:
                draft["step_name"] = envelope.get("step", draft["step_name"])
                draft["input"] = envelope.get("input", draft["input"])
                draft["output"] = envelope.get("output")
                if envelope.get("quality") in ("pass", "failed"):
                    draft["quality_verdict"] = envelope["quality"]
                    draft["step_type"] = ("validation" if envelope["quality"] in ("pass", "failed")
                                          and "validate" in draft["step_name"] else draft["step_type"])
                draft["execution_status"] = ("error" if envelope.get("status") == "error"
                                             else "success")
            else:
                draft["output"] = {"text": text[:2000]}
                draft["execution_status"] = "error" if block.get("is_error") else "success"
            draft["duration_ms"] = 200
            self.run.spans.append(draft)

    @staticmethod
    def _try_envelope(text: str) -> dict | None:
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and "step" in obj:
                    return obj
        return None

    def _on_result(self, event: dict) -> None:
        self._ensure_root()
        ok = event.get("subtype") == "success" and not event.get("is_error")
        self.run.result_text = event.get("result")
        root = self.run.spans[0]
        root["execution_status"] = "success" if ok else "error"
        root["duration_ms"] = event.get("duration_ms")
        # 未闭合的 tool_use（流中断）标记 error 落盘
        for draft in self._pending_tools.values():
            draft["execution_status"] = "error"
            draft["output"] = {"text": "<tool_result missing: stream truncated>"}
            self.run.spans.append(draft)
        self._pending_tools.clear()

    def finish(self) -> ParsedRun:
        if self._pending_tools:
            self._on_result({"subtype": "error"})
        return self.run
