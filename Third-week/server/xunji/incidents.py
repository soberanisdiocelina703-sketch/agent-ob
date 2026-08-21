"""Incident detection from ingested traces.

Symptom span = where the failure *surfaced* (最后一个失败步骤); the whole
product premise is that this is usually NOT the root cause — diagnosis finds
that separately.
"""
import sqlite3
import uuid
from datetime import datetime, timezone

from .clustering import assign_cluster
from .enums import FailureType


def detect_incident(conn: sqlite3.Connection, trace_id: str) -> str | None:
    existing = conn.execute("SELECT id FROM incidents WHERE trace_id=?", (trace_id,)).fetchone()
    if existing:
        return existing["id"]

    quality_failed = conn.execute(
        """SELECT * FROM spans WHERE trace_id=? AND quality_verdict='failed'
           ORDER BY ts DESC LIMIT 1""", (trace_id,)).fetchone()
    exec_failed = conn.execute(
        """SELECT * FROM spans WHERE trace_id=? AND execution_status IN ('error','timeout')
           ORDER BY ts DESC LIMIT 1""", (trace_id,)).fetchone()

    symptom = quality_failed or exec_failed
    if symptom is None:
        return None

    if quality_failed and not exec_failed:
        failure_type = FailureType.QUALITY_CHECK_FAILED.value
    elif symptom["execution_status"] == "timeout":
        failure_type = FailureType.TIMEOUT.value
    else:
        failure_type = FailureType.EXCEPTION.value

    cluster_id = assign_cluster(
        conn, symptom["project_id"], symptom["agent_id"], symptom["step_name"], failure_type)

    incident_id = f"inc-{uuid.uuid4().hex[:8]}"
    conn.execute(
        """INSERT INTO incidents
           (id, tenant_id, project_id, trace_id, cluster_id, failure_type, symptom_span_id,
            execution_status, quality_verdict, incident_status, review_status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (incident_id, symptom["tenant_id"], symptom["project_id"], trace_id, cluster_id,
         failure_type, symptom["span_id"], symptom["execution_status"],
         symptom["quality_verdict"], "open", "unreviewed",
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return incident_id
