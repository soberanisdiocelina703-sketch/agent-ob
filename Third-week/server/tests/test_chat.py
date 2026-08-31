"""对话演示后端：任务生命周期、runner 注入、API 契约。"""
import json
import time

import pytest
from fastapi.testclient import TestClient

from xunji import chat
from xunji.api import app
from xunji.chat import ChatRunError, _extract_result_text, _extract_session_id


def wait_done(job_id: str, timeout_s: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        job = chat.get_job(job_id)
        if job and job["status"] != "running":
            return job
        time.sleep(0.02)
    pytest.fail("chat job 未在超时内结束")


class TestChatJobs:
    def test_提问_runner成功_返回回答与trace(self, monkeypatch):
        monkeypatch.setattr(chat, "RUNNER", lambda q, s, r=None: {
            "answer": f"回答：{q}", "trace_id": "chat-t1",
            "span_count": 3, "incident_id": None, "claude_session_id": "aaaa-bbbb",
        })
        job = wait_done(chat.submit("今天对账平吗", "http://x"))
        assert job["status"] == "done"
        assert job["answer"] == "回答：今天对账平吗"
        assert job["trace_id"] == "chat-t1" and job["span_count"] == 3
        assert job["claude_session_id"] == "aaaa-bbbb"
        assert job["duration_ms"] is not None

    def test_多轮_resume_session透传给runner(self, monkeypatch):
        seen = {}

        def spy(q, s, resume=None):
            seen["resume"] = resume
            return {"answer": "ok", "trace_id": "t", "span_count": 1,
                    "incident_id": None, "claude_session_id": "new-session"}

        monkeypatch.setattr(chat, "RUNNER", spy)
        wait_done(chat.submit("第二轮", "http://x", resume_session="old-session"))
        assert seen["resume"] == "old-session"

    def test_runner失败_状态error且带原因(self, monkeypatch):
        def boom(q, s, r=None):
            raise ChatRunError("claude 执行失败（exit 2）：找不到命令 claude")

        monkeypatch.setattr(chat, "RUNNER", boom)
        job = wait_done(chat.submit("q", "http://x"))
        assert job["status"] == "error"
        assert "找不到命令" in job["error"]

    def test_意外异常_不留僵尸任务(self, monkeypatch):
        monkeypatch.setattr(chat, "RUNNER",
                            lambda q, s, r=None: (_ for _ in ()).throw(RuntimeError("boom")))
        job = wait_done(chat.submit("q", "http://x"))
        assert job["status"] == "error" and "RuntimeError" in job["error"]

    def test_未知任务_返回None(self):
        assert chat.get_job("chat-ghost") is None


class TestExtractResultText:
    def test_从存档取result事件文本_忽略非JSON行(self, tmp_path):
        f = tmp_path / "run.jsonl"
        f.write_text(
            'not json\n'
            + json.dumps({"type": "assistant", "message": {}}) + "\n"
            + json.dumps({"type": "result", "subtype": "success",
                          "result": "两侧一致，差异 0 笔"}) + "\n",
            encoding="utf-8")
        assert _extract_result_text(f) == "两侧一致，差异 0 笔"

    def test_存档缺失_返回None(self, tmp_path):
        assert _extract_result_text(tmp_path / "nope.jsonl") is None

    def test_session取最后一个事件的值_resume会fork新ID(self, tmp_path):
        f = tmp_path / "run.jsonl"
        f.write_text(
            json.dumps({"type": "system", "subtype": "init", "session_id": "old-id"}) + "\n"
            + json.dumps({"type": "result", "result": "ok", "session_id": "forked-id"}) + "\n",
            encoding="utf-8")
        assert _extract_session_id(f) == "forked-id"


class TestChatApi:
    @pytest.fixture()
    def client(self):
        with TestClient(app) as c:
            yield c

    def test_提交与轮询闭环(self, client, monkeypatch):
        monkeypatch.setattr(chat, "RUNNER", lambda q, s, r=None: {
            "answer": "ok", "trace_id": "chat-t2", "span_count": 2,
            "incident_id": "inc-9", "claude_session_id": "cccc-dddd",
        })
        r = client.post("/v1/chat/messages", json={"question": "  报告校验过了吗  "})
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        wait_done(job_id)
        snap = client.get(f"/v1/chat/messages/{job_id}").json()
        assert snap["status"] == "done" and snap["incident_id"] == "inc-9"
        assert snap["claude_session_id"] == "cccc-dddd"
        assert snap["question"] == "报告校验过了吗"  # 已去除首尾空白

    def test_带session_id提交_透传resume(self, client, monkeypatch):
        seen = {}

        def spy(q, s, resume=None):
            seen["resume"] = resume
            return {"answer": "ok", "trace_id": "t", "span_count": 1,
                    "incident_id": None, "claude_session_id": "next"}

        monkeypatch.setattr(chat, "RUNNER", spy)
        r = client.post("/v1/chat/messages",
                        json={"question": "继续", "session_id": "7621d649-1d77"})
        assert r.status_code == 202
        wait_done(r.json()["job_id"])
        assert seen["resume"] == "7621d649-1d77"

    def test_非法session_id_422(self, client):
        r = client.post("/v1/chat/messages",
                        json={"question": "q", "session_id": "--resume; rm -rf"})
        assert r.status_code == 422

    def test_空问题_422(self, client):
        assert client.post("/v1/chat/messages", json={"question": "   "}).status_code == 422

    def test_未知任务_404(self, client):
        assert client.get("/v1/chat/messages/chat-ghost").status_code == 404
