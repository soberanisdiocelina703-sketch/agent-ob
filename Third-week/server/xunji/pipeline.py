"""End-to-end processing pipeline: trace → incident → sync diagnosis → model stage."""
import sqlite3
import threading

from . import db as dbmod
from .diagnosis import run_model_stage, run_sync_diagnosis
from .evaluator import MockEvaluator
from .incidents import detect_incident


def default_evaluator():
    import os

    if os.environ.get("XUNJI_EVALUATOR") == "claude-code":
        from .evaluator import ClaudeCodeEvaluator

        return ClaudeCodeEvaluator()
    delay = float(os.environ.get("XUNJI_MOCK_DELAY", "0"))
    fail = os.environ.get("XUNJI_MOCK_FAIL") == "1"
    return MockEvaluator(delay_s=delay, fail=fail)


def process_trace(conn: sqlite3.Connection, trace_id: str,
                  evaluator=None, model_async: bool = False) -> dict:
    """Returns {incident_id, diagnosis_id} or {} when the trace is healthy."""
    incident_id = detect_incident(conn, trace_id)
    if not incident_id:
        return {}
    incident = dict(conn.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone())
    diagnosis_id = run_sync_diagnosis(conn, incident)
    evaluator = evaluator or default_evaluator()

    if model_async:
        def _bg():
            bg_conn = dbmod.connect()
            try:
                run_model_stage(bg_conn, diagnosis_id, evaluator)
            finally:
                bg_conn.close()

        threading.Thread(target=_bg, daemon=True).start()
    else:
        run_model_stage(conn, diagnosis_id, evaluator)
    return {"incident_id": incident_id, "diagnosis_id": diagnosis_id}
