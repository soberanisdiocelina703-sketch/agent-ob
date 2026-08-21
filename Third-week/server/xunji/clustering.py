"""Symptom-signature clustering: clusters grow from ingested data, never preset.

Signature fields (v1): agent_id | symptom step_name | failure_type.
Algorithm versioned via signature_version so re-clustering is possible
(docs/08 failure_clusters.signature_version).
"""
import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone

SIGNATURE_VERSION = 1


def signature(agent_id: str | None, symptom_step_name: str | None, failure_type: str) -> str:
    raw = "|".join([agent_id or "?", symptom_step_name or "?", failure_type])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def assign_cluster(conn: sqlite3.Connection, project_id: str, agent_id: str | None,
                   symptom_step_name: str | None, failure_type: str) -> str:
    sig = signature(agent_id, symptom_step_name, failure_type)
    row = conn.execute(
        "SELECT id FROM failure_clusters WHERE project_id=? AND symptom_signature=?",
        (project_id, sig),
    ).fetchone()
    if row:
        conn.execute("UPDATE failure_clusters SET count_24h = count_24h + 1 WHERE id=?",
                     (row["id"],))
        return row["id"]
    cluster_id = f"fc-{uuid.uuid4().hex[:8]}"
    title = f"{agent_id or '未知Agent'} / {symptom_step_name or '未知步骤'} / {failure_type}"
    conn.execute(
        """INSERT INTO failure_clusters
           (id, project_id, symptom_signature, signature_version, title, count_24h, created_at)
           VALUES (?,?,?,?,?,1,?)""",
        (cluster_id, project_id, sig, SIGNATURE_VERSION, title,
         datetime.now(timezone.utc).isoformat()),
    )
    return cluster_id
