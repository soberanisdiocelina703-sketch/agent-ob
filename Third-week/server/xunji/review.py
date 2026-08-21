"""Review submission with optimistic concurrency (If-Match on candidate version).

复核枚举与 verdicts 表在 API/DB 保持一致（docs/08 硬约束）；correct_cause_ref
允许在候选全错/证据不足时人工指认真因（冷启动兜底）。
"""
import sqlite3
import uuid
from datetime import datetime, timezone

from .enums import IncidentStatus, ReviewResult


class ReviewConflict(Exception):
    """Candidate was reviewed concurrently; client must refetch (HTTP 409)."""


class ReviewInvalid(Exception):
    pass


def submit_review(conn: sqlite3.Connection, candidate_id: str, result: str,
                  if_match: int, reason_code: str | None = None,
                  correct_cause_ref: str | None = None,
                  decided_by: str = "demo-user") -> dict:
    try:
        result = ReviewResult(result).value
    except ValueError as exc:
        raise ReviewInvalid(f"result 必须是 {[r.value for r in ReviewResult]} 之一") from exc

    cand = conn.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone()
    if cand is None:
        raise ReviewInvalid(f"候选 {candidate_id} 不存在")
    if cand["version"] != if_match:
        raise ReviewConflict(
            f"候选已被并发复核（当前版本 {cand['version']}，请求基于 {if_match}）")

    verdict_id = f"v-{uuid.uuid4().hex[:8]}"
    prev = conn.execute(
        "SELECT id FROM verdicts WHERE candidate_id=? AND superseded_by IS NULL",
        (candidate_id,),
    ).fetchone()
    if prev:
        conn.execute("UPDATE verdicts SET superseded_by=? WHERE id=?", (verdict_id, prev["id"]))

    conn.execute(
        """INSERT INTO verdicts (id, candidate_id, result, reason_code, correct_cause_ref,
           decided_by, decided_at) VALUES (?,?,?,?,?,?,?)""",
        (verdict_id, candidate_id, result, reason_code, correct_cause_ref, decided_by,
         datetime.now(timezone.utc).isoformat()),
    )
    new_version = cand["version"] + 1
    conn.execute("UPDATE candidates SET version=? WHERE id=?", (new_version, candidate_id))

    incident = conn.execute(
        """SELECT i.* FROM incidents i JOIN diagnoses d ON d.incident_id = i.id
           WHERE d.id=?""", (cand["diagnosis_id"],),
    ).fetchone()
    if incident:
        conn.execute(
            "UPDATE incidents SET review_status=?, incident_status=? WHERE id=?",
            (result, IncidentStatus.REVIEWED.value, incident["id"]),
        )
    conn.commit()
    return {"verdict_id": verdict_id, "candidate_version": new_version, "result": result}
