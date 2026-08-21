"""Trace ingestion: contract validation, normalization, degradation handling.

Degradation policy (second-week/docs/06 数据侧): broken parent links and
unknown step types are flagged and kept; only spans missing identity fields
(trace_id / span_id / ts) are dropped — each drop returns a warning so the
接入方 can fix instrumentation.
"""
import json
import sqlite3
from dataclasses import dataclass, field

from .enums import ExecutionStatus, QualityVerdict, StepType

REQUIRED_FIELDS = ("trace_id", "span_id", "ts")


@dataclass
class Warning_:
    span_id: str | None
    code: str
    message: str


@dataclass
class IngestResult:
    accepted: int = 0
    dropped: int = 0
    warnings: list[Warning_] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "dropped": self.dropped,
            "warnings": [w.__dict__ for w in self.warnings],
        }


def _store_payload(conn: sqlite3.Connection, ref: str, content) -> str | None:
    if content is None:
        return None
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    conn.execute("INSERT OR REPLACE INTO payloads (ref, content) VALUES (?,?)", (ref, text))
    return ref


def _valid_enum(value, enum_cls, default):
    try:
        return enum_cls(value).value
    except (ValueError, TypeError):
        return default


def ingest(conn: sqlite3.Connection, payload: dict) -> IngestResult:
    resource = payload.get("resource") or {}
    spans = payload.get("spans") or []
    result = IngestResult()

    batch_ids = {s.get("span_id") for s in spans if s.get("span_id")}

    for span in spans:
        missing = [f for f in REQUIRED_FIELDS if not span.get(f)]
        if missing:
            result.dropped += 1
            result.warnings.append(
                Warning_(span.get("span_id"), "missing_required", f"missing fields: {missing}")
            )
            continue

        trace_id, span_id = span["trace_id"], span["span_id"]
        exists = conn.execute(
            "SELECT 1 FROM spans WHERE trace_id=? AND span_id=?", (trace_id, span_id)
        ).fetchone()
        if exists:
            result.dropped += 1
            result.warnings.append(Warning_(span_id, "duplicate_span", "kept first occurrence"))
            continue

        link_kind = "normal"
        parent = span.get("parent_span_id")
        if parent:
            parent_known = parent in batch_ids or conn.execute(
                "SELECT 1 FROM spans WHERE trace_id=? AND span_id=?", (trace_id, parent)
            ).fetchone()
            if not parent_known:
                link_kind = "broken_parent"
                result.warnings.append(
                    Warning_(span_id, "broken_parent", f"parent {parent} not found")
                )

        step_type = _valid_enum(span.get("step_type"), StepType, StepType.OTHER.value)
        input_ref = _store_payload(conn, f"{trace_id}/{span_id}/in", span.get("input"))
        output_ref = _store_payload(conn, f"{trace_id}/{span_id}/out", span.get("output"))

        conn.execute(
            """INSERT INTO spans (
                 tenant_id, project_id, trace_id, span_id, parent_span_id, ts, duration_ms,
                 conversation_id, session_id, run_id, root_run_id, parent_run_id, attempt,
                 agent_id, agent_version, workflow_name, run_name, span_kind,
                 gen_ai_operation_name, raw_step_type, step_type, step_name,
                 execution_status, quality_verdict, input_ref, output_ref, attrs, link_kind
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                resource.get("tenant_id", "demo"),
                resource.get("project_id", "default"),
                trace_id,
                span_id,
                parent,
                span["ts"],
                span.get("duration_ms"),
                resource.get("conversation_id"),
                resource.get("session_id"),
                resource.get("run_id"),
                resource.get("root_run_id"),
                resource.get("parent_run_id"),
                span.get("attempt", 0),
                resource.get("agent_id"),
                resource.get("agent_version"),
                resource.get("workflow_name"),
                resource.get("run_name"),
                span.get("span_kind"),
                span.get("gen_ai_operation_name"),
                span.get("raw_step_type"),
                step_type,
                span.get("step_name"),
                _valid_enum(span.get("execution_status"), ExecutionStatus, ExecutionStatus.SUCCESS.value),
                _valid_enum(span.get("quality_verdict"), QualityVerdict, QualityVerdict.UNEVALUATED.value),
                input_ref,
                output_ref,
                json.dumps(span.get("attrs") or {}, ensure_ascii=False),
                link_kind,
            ),
        )
        result.accepted += 1

    conn.commit()
    return result
