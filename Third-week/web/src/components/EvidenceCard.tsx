import type { Evidence } from "../api/types";

interface Props {
  evidence: Evidence;
  onJump?: (spanRef: string) => void;
}

/** 证据卡片：支持/反证并排呈现，引用可回跳原始 Span（设计原则 2 的落点） */
export function EvidenceCard({ evidence, onJump }: Props) {
  const refute = evidence.side === "refute";
  const ref = evidence.span_ref ?? evidence.event_ref ?? "";
  return (
    <div className={`evidence-card${refute ? " evidence-card--refute" : ""}`}>
      <div className="evidence-card__meta">
        {refute ? "反证" : "支持证据"} · {evidence.kind} ·{" "}
        {onJump && evidence.span_ref ? (
          <a onClick={() => onJump(evidence.span_ref!)} role="button">
            {ref}
          </a>
        ) : (
          <span>{ref}</span>
        )}
      </div>
      <pre className="evidence-card__excerpt">{evidence.excerpt}</pre>
    </div>
  );
}
