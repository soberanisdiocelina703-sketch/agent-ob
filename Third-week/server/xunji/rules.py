"""T1 rule engine: declarative rulepacks (YAML) + generic rule kinds.

Rule kinds are product code; rule *instances* (which steps carry which
contracts) are接入方 configuration — this split keeps business node names out
of product taxonomy (second-week/docs/05 三层口径 requirement).
"""
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .causal import Graph, upstream_path
from .enums import FailureType

RULEPACK_DIR = Path(__file__).parent / "rulepacks"


@dataclass
class Finding:
    rule_id: str
    cause_type: str
    first_fault_span_id: str
    summary: str
    evidence: list[dict] = field(default_factory=list)  # {side, kind, span_ref, excerpt}


def load_rulepack(project_id: str) -> dict:
    """Default pack merged with the project pack when one exists."""
    pack = yaml.safe_load((RULEPACK_DIR / "default.yaml").read_text(encoding="utf-8"))
    project_file = RULEPACK_DIR / f"{project_id}.yaml"
    if project_file.exists():
        project = yaml.safe_load(project_file.read_text(encoding="utf-8"))
        pack["rules"] = pack["rules"] + project["rules"]
        pack["version"] = f"{pack['version']}+{project['version']}"
    return pack


def _payload(conn: sqlite3.Connection, ref: str | None):
    if not ref:
        return None
    row = conn.execute("SELECT content FROM payloads WHERE ref=?", (ref,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["content"])
    except json.JSONDecodeError:
        return row["content"]  # non-JSON payload kept as raw string


def _matches(span: dict, match: dict | None) -> bool:
    if not match:
        return True
    return all(span.get(k) == v for k, v in match.items())


def _non_numeric_paths(node, fields: list[str], path="") -> list[str]:
    bad: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else k
            if k in fields and not isinstance(v, (int, float)):
                bad.append(p)
            bad.extend(_non_numeric_paths(v, fields, p))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            bad.extend(_non_numeric_paths(v, fields, f"{path}[{i}]"))
    return bad


def _ev(span_ref: str, excerpt: str, kind: str) -> dict:
    return {"side": "support", "kind": kind, "span_ref": span_ref, "excerpt": excerpt[:500]}


def _rule_arg_schema(conn, g: Graph, rule: dict) -> list[Finding]:
    findings = []
    for sid in g.nodes:
        span = g.spans[sid]
        if not _matches(span, rule.get("match")):
            continue
        data = _payload(conn, span["input_ref"])
        if not isinstance(data, dict):
            continue
        ref = f"{g.trace_id}/{sid}"
        missing = [k for k in rule.get("required", []) if k not in data]
        if missing:
            findings.append(Finding(
                rule["id"], FailureType.TOOL_ARG_VIOLATION.value, sid,
                f"步骤 {span['step_name']} 入参缺少必填键: {missing}",
                [_ev(ref, json.dumps({"present": list(data)}, ensure_ascii=False), "arg_missing")],
            ))
            continue
        bad = _non_numeric_paths(data, rule.get("numeric_fields", []))
        if bad:
            findings.append(Finding(
                rule["id"], FailureType.TOOL_ARG_VIOLATION.value, sid,
                f"步骤 {span['step_name']} 入参数值字段非法: {bad[:5]}",
                [_ev(ref, json.dumps(bad[:5], ensure_ascii=False), "arg_type")],
            ))
    return findings


def _rule_output_contract(conn, g: Graph, rule: dict) -> list[Finding]:
    findings = []
    for sid in g.nodes:
        span = g.spans[sid]
        if not _matches(span, rule.get("match")):
            continue
        data = _payload(conn, span["output_ref"])
        ref = f"{g.trace_id}/{sid}"
        if not isinstance(data, dict):
            findings.append(Finding(
                rule["id"], FailureType.OUTPUT_CONTRACT_VIOLATION.value, sid,
                f"步骤 {span['step_name']} 输出不是合法 JSON 对象",
                [_ev(ref, str(data)[:200], "output_format")],
            ))
            continue
        missing = [k for k in rule.get("required_fields", []) if k not in data]
        if missing:
            findings.append(Finding(
                rule["id"], FailureType.OUTPUT_CONTRACT_VIOLATION.value, sid,
                f"步骤 {span['step_name']} 输出缺少契约字段: {missing}",
                [_ev(ref, json.dumps({"present": list(data)}, ensure_ascii=False), "output_missing")],
            ))
    return findings


def _rule_exception_propagation(conn, g: Graph, rule: dict, symptom: str | None) -> list[Finding]:
    scope = upstream_path(g, symptom) if symptom and symptom in g.spans else g.nodes
    failed = [sid for sid in scope
              if g.spans[sid]["execution_status"] in ("error", "timeout")]
    # 因果边稀疏时（症状步骤无入边），回退到全 Trace 时间序——比漏掉上游失败诚实
    if failed in ([], [symptom]):
        failed = [sid for sid in g.nodes
                  if g.spans[sid]["execution_status"] in ("error", "timeout")]
    if not failed:
        return []
    first = failed[0]  # scope 已按时间排序 → 最早失败步骤，而非最后报错处
    span = g.spans[first]
    cause = (FailureType.TIMEOUT if span["execution_status"] == "timeout"
             else FailureType.EXCEPTION).value
    out = _payload(conn, span["output_ref"])
    ev = [_ev(f"{g.trace_id}/{first}",
              json.dumps(out, ensure_ascii=False) if out is not None else span["execution_status"],
              "error_output")]
    later = [s for s in failed[1:]]
    if later:
        ev.append(_ev(f"{g.trace_id}/{later[-1]}",
                      f"下游 {len(later)} 个步骤随之失败: {later}", "propagation"))
    return [Finding(rule["id"], cause, first,
                    f"因果路径上最早失败步骤为 {span['step_name']}（其后 {len(later)} 步连带失败）", ev)]


def _rule_retrieval_empty(conn, g: Graph, rule: dict) -> list[Finding]:
    findings = []
    for sid in g.nodes:
        span = g.spans[sid]
        if not _matches(span, rule.get("match")):
            continue
        data = _payload(conn, span["output_ref"])
        rows = data.get("rows") if isinstance(data, dict) else data
        if rows == [] or rows == 0:
            findings.append(Finding(
                rule["id"], FailureType.RETRIEVAL_EMPTY.value, sid,
                f"步骤 {span['step_name']} 返回空结果",
                [_ev(f"{g.trace_id}/{sid}", json.dumps(data, ensure_ascii=False), "empty_result")],
            ))
    return findings


_KINDS = {
    "arg_schema": lambda conn, g, rule, symptom: _rule_arg_schema(conn, g, rule),
    "output_contract": lambda conn, g, rule, symptom: _rule_output_contract(conn, g, rule),
    "exception_propagation": _rule_exception_propagation,
    "retrieval_empty": lambda conn, g, rule, symptom: _rule_retrieval_empty(conn, g, rule),
}


def evaluate_rules(conn: sqlite3.Connection, g: Graph, symptom_span_id: str | None,
                   rulepack: dict) -> list[Finding]:
    findings: list[Finding] = []
    for rule in rulepack.get("rules", []):
        handler = _KINDS.get(rule.get("kind"))
        if handler is None:
            continue  # 未知规则种类宽容跳过（规则包可先行于引擎版本发布）
        findings.extend(handler(conn, g, rule, symptom_span_id))
    return findings
