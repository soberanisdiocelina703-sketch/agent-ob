import json

import httpx

from xunji_sdk.parser import StreamParser
from xunji_sdk.reporter import report


def lines_for_tool(tool_id, command, result_text, is_error=False):
    return [
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "执行下一步"},
            {"type": "tool_use", "id": tool_id, "name": "Bash",
             "input": {"command": command}},
        ]}}),
        json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": tool_id, "is_error": is_error,
             "content": [{"type": "text", "text": result_text}]},
        ]}}),
    ]


INIT = json.dumps({"type": "system", "subtype": "init", "session_id": "sess-42"})
DONE = json.dumps({"type": "result", "subtype": "success", "result": "对账完成",
                   "duration_ms": 5000})


def parse(lines):
    p = StreamParser(trace_id="t1")
    for line in lines:
        p.feed_line(line)
    return p.finish()


def test_envelope_tool_span_gets_step_name_payloads_and_quality():
    envelope = json.dumps({"step": "validate_report", "input": {"report": "r.json"},
                           "output": {"balanced": False, "delta": 3412.0},
                           "quality": "failed"})
    run = parse([INIT, *lines_for_tool("tu1", "python tools/validate_report.py", envelope), DONE])
    tool = [s for s in run.spans if s["step_type"] in ("tool_call", "validation")][0]
    assert tool["step_name"] == "validate_report"
    assert tool["quality_verdict"] == "failed"
    assert tool["output"] == {"balanced": False, "delta": 3412.0}
    assert tool["parent_span_id"] == run.spans[0]["span_id"]  # 挂在 root 下


def test_plain_tool_result_uses_command_heuristic_and_text_output():
    run = parse([INIT, *lines_for_tool("tu1", "python tools/fetch_billing.py", "152 rows ok"), DONE])
    tool = [s for s in run.spans if s["step_type"] == "tool_call"][0]
    assert tool["step_name"] == "fetch_billing"
    assert tool["output"]["text"] == "152 rows ok"
    assert tool["execution_status"] == "success"


def test_is_error_result_marks_span_error():
    run = parse([INIT, *lines_for_tool("tu1", "python tools/reconcile.py",
                                       "Traceback ...", is_error=True), DONE])
    tool = [s for s in run.spans if s["step_type"] == "tool_call"][0]
    assert tool["execution_status"] == "error"


def test_truncated_stream_closes_pending_tools_as_error():
    lines = [INIT, json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "tu9", "name": "Bash",
         "input": {"command": "python tools/reconcile.py"}}]}})]
    run = parse(lines)  # 无 tool_result、无 result 事件
    tool = [s for s in run.spans if s["step_type"] == "tool_call"][0]
    assert tool["execution_status"] == "error"


def test_non_json_and_unknown_events_tolerated():
    run = parse(["Claude Code v2 banner", INIT,
                 json.dumps({"type": "stream_event", "whatever": 1}), DONE])
    assert run.spans[0]["execution_status"] == "success"  # root 正常闭合


def test_llm_text_becomes_llm_call_span():
    run = parse([INIT, json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "分析：数据已经取全"}]}}), DONE])
    llm = [s for s in run.spans if s["step_type"] == "llm_call"]
    assert llm and "数据已经取全" in llm[0]["output"]["text"]


def test_reporter_posts_contract_to_server():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(202, json={"accepted": 2, "incidents": {}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    run = parse([INIT, DONE])
    out = report(run.to_contract({"project_id": "recon-demo", "agent_id": "a"}),
                 server="http://test", client=client)
    assert captured["url"] == "http://test/v1/traces"
    assert captured["body"]["resource"]["project_id"] == "recon-demo"
    assert out["accepted"] == 2


def test_connect_writes_posttooluse_hook(tmp_path):
    from xunji_sdk.cli import main

    assert main(["connect", "--project", "recon-demo", "--dir", str(tmp_path)]) == 0
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    hook = settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert "xunji_sdk.hook_reporter" in hook and "recon-demo" in hook
