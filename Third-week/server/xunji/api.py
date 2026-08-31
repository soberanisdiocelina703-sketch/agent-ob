"""HTTP API layer (FastAPI). Paths/枚举与 second-week/docs/08 §8.2 逐字一致。

鉴权/多租户为本周不做项；SSE 增量通道用轮询式 StreamingResponse 实现，
前端不支持时可降级轮询 GET /diagnosis（spec.md 决策）。
"""
import asyncio
import json
import re
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import db as dbmod
from . import chat
from .diagnosis import load_candidates
from .diffgen import compare_table, find_baseline
from .gate import RegressionInvalid, create_regression_case, run_gate
from .ingestion import ingest
from .pipeline import process_trace
from .review import ReviewConflict, ReviewInvalid, submit_review


@asynccontextmanager
async def lifespan(app: FastAPI):
    dbmod.get_conn()
    yield
    dbmod.reset_conn()


app = FastAPI(title="寻迹 xunji API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173"],
    allow_methods=["*"], allow_headers=["*"],
)


def conn() -> sqlite3.Connection:
    return dbmod.get_conn()


# ---------- 接入 ----------

@app.post("/v1/traces", status_code=202)
def post_traces(payload: dict):
    c = conn()
    result = ingest(c, payload)
    trace_ids = {s.get("trace_id") for s in payload.get("spans", []) if s.get("trace_id")}
    incidents = {}
    for tid in trace_ids:
        outcome = process_trace(c, tid, model_async=True)
        if outcome:
            incidents[tid] = outcome
    return {**result.to_dict(), "incidents": incidents}


@app.get("/v1/projects/{pid}/checkup")
def checkup(pid: str):
    c = conn()
    total = c.execute("SELECT COUNT(*) c FROM spans WHERE project_id=?", (pid,)).fetchone()["c"]
    broken = c.execute(
        "SELECT COUNT(*) c FROM spans WHERE project_id=? AND link_kind='broken_parent'",
        (pid,)).fetchone()["c"]
    traces = c.execute(
        "SELECT COUNT(DISTINCT trace_id) c FROM spans WHERE project_id=?", (pid,)).fetchone()["c"]
    agents = c.execute(
        "SELECT DISTINCT agent_id, agent_version FROM spans WHERE project_id=?", (pid,)).fetchall()
    baseline_ready = []
    for a in agents:
        b = find_baseline(c, pid, a["agent_id"], a["agent_version"], exclude="__none__")
        baseline_ready.append({"agent_id": a["agent_id"], "agent_version": a["agent_version"],
                               "baseline_available": b is not None, "baseline_trace_id": b})
    return {"project_id": pid, "span_count": total, "trace_count": traces,
            "broken_links": broken, "baseline_coverage": baseline_ready}


# ---------- 查询 ----------

@app.get("/v1/projects/{pid}/traces")
def list_traces(pid: str, execution_status: str | None = None,
                quality_verdict: str | None = None, agent: str | None = None,
                limit: int = Query(50, le=200)):
    c = conn()
    rows = c.execute(
        """SELECT trace_id, MIN(ts) started_at, MAX(ts) ended_at, COUNT(*) span_count,
                  MAX(agent_id) agent_id, MAX(agent_version) agent_version,
                  MAX(run_name) run_name,
                  MAX(CASE WHEN execution_status IN ('error','timeout') THEN 1 ELSE 0 END) has_error,
                  MAX(CASE WHEN quality_verdict='failed' THEN 1 ELSE 0 END) has_quality_fail,
                  MAX(CASE WHEN quality_verdict='pass' THEN 1 ELSE 0 END) has_quality_pass
           FROM spans WHERE project_id=? GROUP BY trace_id ORDER BY started_at DESC LIMIT ?""",
        (pid, limit),
    ).fetchall()
    out = []
    for r in rows:
        exec_status = "error" if r["has_error"] else "success"
        # 质量三态：有失败即 failed；有通过判定才算 pass；否则未评估（校验未跑到）
        quality = ("failed" if r["has_quality_fail"]
                   else "pass" if r["has_quality_pass"] else "unevaluated")
        if execution_status and exec_status != execution_status:
            continue
        if quality_verdict and quality != quality_verdict:
            continue
        if agent and r["agent_id"] != agent:
            continue
        inc = c.execute("SELECT id FROM incidents WHERE trace_id=?", (r["trace_id"],)).fetchone()
        out.append({**dict(r), "execution_status": exec_status, "quality_verdict": quality,
                    "incident_id": inc["id"] if inc else None})
    return {"traces": out}


@app.get("/v1/traces/{tid}")
def trace_detail(tid: str):
    c = conn()
    spans = c.execute("SELECT * FROM spans WHERE trace_id=? ORDER BY ts, span_id", (tid,)).fetchall()
    if not spans:
        raise HTTPException(404, f"Trace {tid} 不存在")
    out_spans = []
    for s in spans:
        d = dict(s)
        for key in ("input_ref", "output_ref"):
            if d[key]:
                p = c.execute("SELECT content FROM payloads WHERE ref=?", (d[key],)).fetchone()
                d[key.replace("_ref", "_payload")] = p["content"] if p else None
        out_spans.append(d)
    from .causal import build_graph

    g = build_graph(c, tid)
    inc = c.execute("SELECT id FROM incidents WHERE trace_id=?", (tid,)).fetchone()
    return {"trace_id": tid, "spans": out_spans, "edges": g.edges,
            "incident_id": inc["id"] if inc else None}


@app.get("/v1/projects/{pid}/incidents")
def list_incidents(pid: str, review_status: str | None = None):
    c = conn()
    sql = """SELECT i.*, fc.title cluster_title, fc.count_24h cluster_count
             FROM incidents i LEFT JOIN failure_clusters fc ON fc.id = i.cluster_id
             WHERE i.project_id=?"""
    params: list = [pid]
    if review_status:
        sql += " AND i.review_status=?"
        params.append(review_status)
    rows = c.execute(sql + " ORDER BY i.created_at DESC", params).fetchall()
    return {"incidents": [dict(r) for r in rows]}


@app.get("/v1/incidents/{iid}/diagnosis")
def diagnosis_snapshot(iid: str):
    c = conn()
    diag = c.execute(
        "SELECT * FROM diagnoses WHERE incident_id=? ORDER BY started_at DESC LIMIT 1", (iid,)
    ).fetchone()
    if diag is None:
        raise HTTPException(404, f"事故 {iid} 无诊断记录")
    candidates = load_candidates(c, diag["id"])
    for cand in candidates:
        latest = c.execute(
            "SELECT * FROM verdicts WHERE candidate_id=? AND superseded_by IS NULL",
            (cand["id"],)).fetchone()
        cand["verdict"] = dict(latest) if latest else None
    return {"diagnosis_id": diag["id"], "status": diag["status"],
            "rule_pack_version": diag["rule_pack_version"],
            "model_version": diag["model_version"],
            "failure_reason": diag["failure_reason"], "candidates": candidates}


@app.get("/v1/incidents/{iid}/diagnosis/events")
async def diagnosis_events(iid: str, request: Request):
    """SSE：推送诊断状态直至 complete/failed（轮询库实现，接口契约同 docs/08）。"""

    async def stream():
        for _ in range(60):  # 最长 30s，覆盖模型阶段超时窗口
            if await request.is_disconnected():
                return
            try:
                snapshot = diagnosis_snapshot(iid)
            except HTTPException:
                yield f"event: error\ndata: {json.dumps({'error': 'not_found'})}\n\n"
                return
            yield f"event: snapshot\ndata: {json.dumps(snapshot, ensure_ascii=False, default=str)}\n\n"
            if snapshot["status"] in ("complete", "failed"):
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/v1/incidents/{iid}/diff")
def incident_diff(iid: str, baseline: str | None = None):
    c = conn()
    incident = c.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()
    if incident is None:
        raise HTTPException(404, f"事故 {iid} 不存在")
    tid = incident["trace_id"]
    if not baseline:
        span0 = c.execute("SELECT * FROM spans WHERE trace_id=? LIMIT 1", (tid,)).fetchone()
        baseline = find_baseline(c, span0["project_id"], span0["agent_id"],
                                 span0["agent_version"], exclude=tid) if span0 else None
    if not baseline:
        return {"available": False, "reason": "no_baseline",
                "message": "暂无可比成功基线；累积一次成功运行后 Diff 将启用"}
    return {"available": True, **compare_table(c, tid, baseline)}


# ---------- 对话演示 ----------

class ChatBody(BaseModel):
    question: str
    session_id: str | None = None  # 上一轮返回的 claude_session_id → 多轮续接


@app.post("/v1/chat/messages", status_code=202)
def post_chat_message(body: ChatBody):
    """手动输入的问题 → 后台 `xunji run` 包装真实执行，返回 job_id 供轮询。"""
    question = body.question.strip()
    if not question:
        raise HTTPException(422, "问题不能为空")
    if body.session_id and not re.fullmatch(r"[0-9a-fA-F-]{8,64}", body.session_id):
        raise HTTPException(422, "session_id 格式非法")
    import os

    server = os.getenv("XUNJI_SELF_URL", "http://127.0.0.1:8756")
    return {"job_id": chat.submit(question, server, body.session_id)}


@app.get("/v1/chat/messages/{job_id}")
def get_chat_message(job_id: str):
    job = chat.get_job(job_id)
    if job is None:
        raise HTTPException(404, f"对话任务 {job_id} 不存在")
    return job


# ---------- 复核 / 回归 / 门禁 ----------

class ReviewBody(BaseModel):
    result: str
    reason_code: str | None = None
    correct_cause_ref: str | None = None
    decided_by: str = "demo-user"


@app.post("/v1/candidates/{cid}/review")
def post_review(cid: str, body: ReviewBody, if_match: int = Header(alias="If-Match")):
    try:
        return submit_review(conn(), cid, body.result, if_match, body.reason_code,
                             body.correct_cause_ref, body.decided_by)
    except ReviewConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ReviewInvalid as exc:
        raise HTTPException(422, str(exc)) from exc


class RegressionBody(BaseModel):
    suite_name: str = "默认回归集"


@app.post("/v1/incidents/{iid}/regression-case")
def post_regression(iid: str, body: RegressionBody):
    try:
        return create_regression_case(conn(), iid, body.suite_name)
    except RegressionInvalid as exc:
        raise HTTPException(422, str(exc)) from exc


class GateBody(BaseModel):
    release: str
    mode: str = "warn"


@app.post("/v1/suites/{sid}/gate-run")
def post_gate_run(sid: str, body: GateBody):
    try:
        return run_gate(conn(), sid, body.release, body.mode)
    except RegressionInvalid as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, f"mode 必须是 warn|block: {exc}") from exc


@app.get("/v1/suites")
def list_suites():
    c = conn()
    suites = c.execute("SELECT * FROM suites").fetchall()
    out = []
    for s in suites:
        cases = c.execute("SELECT * FROM regression_cases WHERE suite_id=?", (s["id"],)).fetchall()
        runs = c.execute(
            "SELECT * FROM gate_runs WHERE suite_id=? ORDER BY created_at DESC LIMIT 5",
            (s["id"],)).fetchall()
        out.append({**dict(s), "cases": [dict(x) for x in cases],
                    "recent_runs": [dict(x) for x in runs]})
    return {"suites": out}
