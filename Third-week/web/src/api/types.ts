/** API 类型（与 api/openapi.yaml、docs/08 §8.3 对齐） */
export interface TraceSummary {
  trace_id: string;
  started_at: string;
  span_count: number;
  agent_id: string | null;
  agent_version: string | null;
  run_name: string | null;
  execution_status: string;
  quality_verdict: string;
  incident_id: string | null;
}

export interface Span {
  span_id: string;
  parent_span_id: string | null;
  ts: string;
  step_type: string;
  raw_step_type: string | null;
  step_name: string | null;
  execution_status: string;
  quality_verdict: string;
  input_payload?: string | null;
  output_payload?: string | null;
  link_kind: string | null;
}

export interface TraceDetail {
  trace_id: string;
  spans: Span[];
  edges: { src: string; dst: string; kind: string; confidence: number }[];
  incident_id: string | null;
}

export interface Incident {
  id: string;
  trace_id: string;
  failure_type: string;
  symptom_span_id: string | null;
  incident_status: string;
  review_status: string;
  evidence_grade: string | null;
  cluster_title: string | null;
  cluster_count: number | null;
  created_at: string;
}

export interface Evidence {
  id: string;
  side: "support" | "refute";
  kind: string;
  span_ref: string | null;
  event_ref: string | null;
  excerpt: string;
}

export interface Candidate {
  id: string;
  rank: number;
  cause_type: string;
  summary: string;
  evidence_grade: string;
  source: "rule" | "diff" | "model";
  first_fault_span_id: string | null;
  causal_path: string[];
  version: number;
  evidence: Evidence[];
  verdict: { result: string; reason_code: string | null } | null;
}

export interface Diagnosis {
  diagnosis_id: string;
  status: "pending" | "partial" | "complete" | "failed";
  rule_pack_version: string | null;
  model_version: string | null;
  failure_reason: string | null;
  candidates: Candidate[];
}

export interface DiffStep {
  step_name: string;
  failed: { span_id: string | null; output: unknown; note?: string };
  baseline: { span_id: string | null; output: unknown; note?: string };
  divergences: { key: string; baseline: unknown; failed: unknown }[];
}

export interface DiffView {
  available: boolean;
  reason?: string;
  message?: string;
  baseline_trace_id?: string;
  failed_trace_id?: string;
  steps?: DiffStep[];
  first_divergence_span_id?: string | null;
}

export interface Suite {
  id: string;
  name: string;
  cases: { id: string; incident_id: string; invariants: string }[];
  recent_runs: { id: string; release: string; mode: string; result: string; created_at: string }[];
}

export interface ChatJob {
  job_id: string;
  status: "running" | "done" | "error";
  question: string;
  answer: string | null;
  trace_id: string | null;
  span_count: number | null;
  incident_id: string | null;
  error: string | null;
  duration_ms: number | null;
  claude_session_id: string | null;
}
