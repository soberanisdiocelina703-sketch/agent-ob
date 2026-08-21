import type { Evidence } from "../api/types";

interface Props {
  evidence: Evidence;
}

/** 证据卡片：支持证据/反证并排呈现，左侧色条区分（设计原则 2 的落点） */
export function EvidenceCard({ evidence }: Props) {
  const refute = evidence.side === "refute";
  const ref = evidence.span_ref ?? evidence.event_ref ?? "";
  return (
    <div className={`evi ${refute ? "counter" : "support"}`}>
      <div className="ei">{refute ? "⚖" : "🔎"}</div>
      <div style={{ minWidth: 0 }}>
        <div className="meta">
          {refute ? "反证" : "支持证据"} · {evidence.kind} ·{" "}
          <span className="ref mono">{ref}</span>
        </div>
        <pre>{evidence.excerpt}</pre>
      </div>
    </div>
  );
}
