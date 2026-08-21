"""T1 causal graph: hierarchy edges + data-flow heuristic edges.

范围裁定: state/handoff edges are T2 and are NOT built here. The data-flow
heuristic (upstream output fragment appears verbatim in downstream input)
carries confidence < 1.0 so the aggregation layer can down-weight it; its
false-positive behaviour on real data is a designated retro item.
"""
import json
import sqlite3
from dataclasses import dataclass, field

DATAFLOW_CONFIDENCE = 0.7
MIN_FRAGMENT_LEN = 6  # shorter strings are too common to imply causality


@dataclass
class Graph:
    trace_id: str
    nodes: list[str] = field(default_factory=list)          # span_ids, time-ordered
    edges: list[dict] = field(default_factory=list)          # {src,dst,kind,confidence}
    spans: dict[str, dict] = field(default_factory=dict)     # span_id -> row dict


def _payload_text(conn: sqlite3.Connection, ref: str | None) -> str:
    if not ref:
        return ""
    row = conn.execute("SELECT content FROM payloads WHERE ref=?", (ref,)).fetchone()
    return row["content"] if row else ""


def _fragments(text: str) -> set[str]:
    """Extract matchable value fragments from a JSON payload string."""
    if not text:
        return set()
    frags: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str) and len(node) >= MIN_FRAGMENT_LEN:
            frags.add(node)
        elif isinstance(node, (int, float)) and len(str(node)) >= MIN_FRAGMENT_LEN:
            frags.add(str(node))

    try:
        walk(json.loads(text))
    except (json.JSONDecodeError, TypeError):
        if len(text) >= MIN_FRAGMENT_LEN:
            frags.add(text)
    return frags


def build_graph(conn: sqlite3.Connection, trace_id: str) -> Graph:
    rows = conn.execute(
        "SELECT * FROM spans WHERE trace_id=? ORDER BY ts, span_id", (trace_id,)
    ).fetchall()
    g = Graph(trace_id=trace_id)
    for r in rows:
        g.nodes.append(r["span_id"])
        g.spans[r["span_id"]] = dict(r)

    ids = set(g.nodes)
    for sid in g.nodes:
        parent = g.spans[sid]["parent_span_id"]
        if parent and parent in ids:
            g.edges.append({"src": parent, "dst": sid, "kind": "hierarchy", "confidence": 1.0})

    # Data-flow heuristic, strictly forward in time.
    outputs = {
        sid: _fragments(_payload_text(conn, g.spans[sid]["output_ref"])) for sid in g.nodes
    }
    inputs = {
        sid: _payload_text(conn, g.spans[sid]["input_ref"]) for sid in g.nodes
    }
    for i, src in enumerate(g.nodes):
        if not outputs[src]:
            continue
        for dst in g.nodes[i + 1:]:
            if src == dst or not inputs[dst]:
                continue
            if g.spans[src]["ts"] >= g.spans[dst]["ts"]:
                continue
            if any(frag in inputs[dst] for frag in outputs[src]):
                g.edges.append(
                    {"src": src, "dst": dst, "kind": "dataflow", "confidence": DATAFLOW_CONFIDENCE}
                )
    return g


def upstream_path(g: Graph, span_id: str) -> list[str]:
    """Causal ancestors of span_id (inclusive), ordered by timestamp."""
    incoming: dict[str, list[str]] = {}
    for e in g.edges:
        incoming.setdefault(e["dst"], []).append(e["src"])

    seen: set[str] = set()
    stack = [span_id]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(incoming.get(cur, []))
    return [sid for sid in g.nodes if sid in seen]
