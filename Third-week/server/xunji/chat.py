"""对话演示后端：把每个手动输入的问题包装成一次 `xunji run` 真实执行。

每个问题起一个后台线程执行 `python -m xunji_sdk.cli run -- claude -p ...`，
Trace 由 SDK 旁路解析并上报回本服务（自采自诊），回答文本从 --archive
存档的 stream-json result 事件中提取。runner 可注入（测试用），
与 evaluator.ClaudeCodeEvaluator 同一模式；真实执行需本机已登录 Claude Code CLI。
"""
import json
import logging
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

log = logging.getLogger("xunji.chat")

ROOT = Path(__file__).resolve().parents[2]
CHAT_TIMEOUT_S = 300
CHAT_MAX_TURNS = 15
CHAT_PROJECT = "recon-demo"
CHAT_AGENT_ID = "chat-demo"


class ChatRunError(Exception):
    pass


def _extract_result_text(archive_path: Path) -> str | None:
    """从 stream-json 存档中取最终 result 事件的回答文本。"""
    try:
        lines = archive_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            return event.get("result")
    return None


def _extract_session_id(archive_path: Path) -> str | None:
    """取本次执行的 claude session_id（多轮对话用 --resume 续接）。

    注意取最后一个事件的 session_id：--resume 会 fork 出新会话 ID，
    续接必须用最新值而非发起时传入的旧值。
    """
    try:
        lines = archive_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("session_id"):
            return event["session_id"]
    return None


def _run_subprocess(question: str, server: str, resume_session: str | None = None) -> dict:
    """真实执行一次被包装的 claude -p，返回 {answer, trace_id, span_count, incident_id,
    claude_session_id}。resume_session 非空时用 --resume 续接既有会话（多轮对话）。"""
    with tempfile.TemporaryDirectory(prefix="xunji-chat-") as tmp:
        qfile = Path(tmp) / "question.md"
        qfile.write_text(question, encoding="utf-8")
        archive = Path(tmp) / "run.jsonl"
        cmd = [
            sys.executable, "-m", "xunji_sdk.cli", "run",
            "--project", CHAT_PROJECT, "--agent-id", CHAT_AGENT_ID,
            "--agent-version", "1.0.0", "--run-name", "chat",
            "--server", server,
            "--stdin-file", str(qfile), "--archive", str(archive),
            "--",
            "claude", "-p", "--output-format", "stream-json", "--verbose",
            "--max-turns", str(CHAT_MAX_TURNS),
        ]
        if resume_session:
            cmd += ["--resume", resume_session]
        import os

        env = {**os.environ, "PYTHONPATH": str(ROOT / "sdk")}
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=CHAT_TIMEOUT_S,
                                  cwd=str(ROOT), env=env)
        except subprocess.TimeoutExpired as exc:
            raise ChatRunError(f"执行超时（>{CHAT_TIMEOUT_S}s）") from exc
        if proc.returncode != 0:
            snippet = (proc.stderr or proc.stdout or "").strip()[:300]
            raise ChatRunError(f"claude 执行失败（exit {proc.returncode}）：{snippet}")

        outcome: dict = {}
        for line in reversed((proc.stdout or "").splitlines()):
            try:
                outcome = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        incidents = outcome.get("incidents") or {}
        incident_id = None
        for v in incidents.values():
            incident_id = (v or {}).get("incident_id")
        return {
            "answer": _extract_result_text(archive) or "（未取到回答文本，见 Trace 详情）",
            "trace_id": outcome.get("trace_id"),
            "span_count": outcome.get("spans"),
            "incident_id": incident_id,
            "claude_session_id": _extract_session_id(archive),
        }


RUNNER = _run_subprocess  # 测试可整体替换（monkeypatch）

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def submit(question: str, server: str, resume_session: str | None = None) -> str:
    """登记任务并起后台线程真实执行；立即返回 job_id 供前端轮询。

    resume_session 为上一轮回答返回的 claude_session_id 时续接同一会话（多轮）。
    """
    job_id = f"chat-{uuid.uuid4().hex[:8]}"
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id, "status": "running", "question": question,
            "answer": None, "trace_id": None, "span_count": None,
            "incident_id": None, "error": None, "duration_ms": None,
            "claude_session_id": None,
        }

    def _work() -> None:
        started = time.monotonic()
        try:
            result = RUNNER(question, server, resume_session)
            patch = {"status": "done", **result}
        except ChatRunError as exc:
            patch = {"status": "error", "error": str(exc)}
        except Exception as exc:  # 兜底：任何意外不留下永久 running 的僵尸任务
            log.exception("chat job %s crashed", job_id)
            patch = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        patch["duration_ms"] = int((time.monotonic() - started) * 1000)
        with _lock:
            _jobs[job_id].update(patch)

    threading.Thread(target=_work, daemon=True).start()
    return job_id


def get_job(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None
