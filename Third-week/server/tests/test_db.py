import sqlite3

import pytest

from xunji import db


@pytest.fixture()
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def test_init_creates_all_tables(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r["name"] for r in rows}
    expected = {
        "spans", "payloads", "events_state", "events_handoff", "events_memory",
        "incidents", "failure_clusters", "diagnoses", "candidates", "evidence",
        "verdicts", "suites", "regression_cases", "gate_runs",
    }
    assert expected <= names


def test_evidence_requires_span_or_event_ref(conn):
    """docs/08 hard constraint: span_ref OR event_ref must exist."""
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO evidence (id, candidate_id, side, kind) VALUES (?,?,?,?)",
            ("e1", "c1", "support", "span_excerpt"),
        )


def test_evidence_accepts_span_ref_only(conn):
    conn.execute(
        "INSERT INTO evidence (id, candidate_id, side, kind, span_ref) VALUES (?,?,?,?,?)",
        ("e1", "c1", "support", "span_excerpt", "t1/s1"),
    )
    assert conn.execute("SELECT COUNT(*) c FROM evidence").fetchone()["c"] == 1


def test_t2_tables_exist_but_stay_empty(conn):
    """范围裁定: T2 tables defined, no write path anywhere in this codebase."""
    for table in ("events_state", "events_handoff", "events_memory"):
        assert conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"] == 0
