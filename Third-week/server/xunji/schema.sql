-- 寻迹观测 + 业务库建表（Demo 形态：SQLite 单库）
-- 目标形态（second-week/docs/08 §8.3）：观测侧 ClickHouse（按 tenant/project/date 分区，
-- ORDER BY (trace_id, ts)）、业务侧 Postgres。本文件字段与枚举与 docs/08 逐字对齐，
-- 迁移时仅替换 repository 层连接与分区子句。

-- ============ 观测侧（目标：ClickHouse） ============

CREATE TABLE IF NOT EXISTS spans (
  tenant_id      TEXT NOT NULL DEFAULT 'demo',
  project_id     TEXT NOT NULL,
  trace_id       TEXT NOT NULL,
  span_id        TEXT NOT NULL,
  parent_span_id TEXT,
  ts             TEXT NOT NULL,           -- ISO8601；CH 中为 DateTime64
  duration_ms    INTEGER,
  conversation_id TEXT,
  session_id     TEXT,
  run_id         TEXT,
  root_run_id    TEXT,
  parent_run_id  TEXT,
  attempt        INTEGER DEFAULT 0,
  agent_id       TEXT,
  agent_version  TEXT,
  workflow_name  TEXT,
  run_name       TEXT,
  span_kind      TEXT,
  gen_ai_operation_name TEXT,
  raw_step_type  TEXT,                    -- 接入方原始类型
  step_type      TEXT,                    -- 跨框架稳定枚举（enums.StepType）
  step_name      TEXT,                    -- 接入方业务语义，原样保留
  execution_status TEXT,                  -- enums.ExecutionStatus
  quality_verdict  TEXT,                  -- enums.QualityVerdict
  input_ref      TEXT,                    -- payloads.ref（目标形态：对象存储 key）
  output_ref     TEXT,
  attrs          TEXT,                    -- JSON
  link_kind      TEXT,                    -- normal | broken_parent（断链降级标记）
  PRIMARY KEY (trace_id, span_id)
);
CREATE INDEX IF NOT EXISTS idx_spans_project_ts ON spans (project_id, ts);

-- Demo 替身：对象存储 → 本表。ref 即主键。
CREATE TABLE IF NOT EXISTS payloads (
  ref     TEXT PRIMARY KEY,
  content TEXT NOT NULL
);

-- ---- T2 表：仅保留定义，本周无任何写入路径（范围裁定见提示词） ----
CREATE TABLE IF NOT EXISTS events_state (   -- T2
  tenant_id TEXT, project_id TEXT, trace_id TEXT, span_id TEXT, ts TEXT,
  state_key TEXT, before_hash TEXT, after_hash TEXT, diff_ref TEXT,
  writer_span_id TEXT, reader_span_id TEXT, snapshot_version TEXT, snapshot_age_s INTEGER
);
CREATE TABLE IF NOT EXISTS events_handoff ( -- T2
  tenant_id TEXT, project_id TEXT, trace_id TEXT, span_id TEXT, ts TEXT,
  source_span_id TEXT, target_span_id TEXT, contract_version TEXT,
  fields_present TEXT, fields_missing TEXT, payload_ref TEXT, accepted INTEGER, reject_reason TEXT
);
CREATE TABLE IF NOT EXISTS events_memory (  -- T2
  tenant_id TEXT, project_id TEXT, trace_id TEXT, span_id TEXT, ts TEXT,
  memory_id TEXT, version TEXT, op TEXT, source TEXT, retrieval_score REAL, written_at TEXT
);

-- ============ 业务侧（目标：Postgres） ============

CREATE TABLE IF NOT EXISTS incidents (
  id             TEXT PRIMARY KEY,
  tenant_id      TEXT NOT NULL DEFAULT 'demo',
  project_id     TEXT NOT NULL,
  trace_id       TEXT NOT NULL,
  cluster_id     TEXT,
  failure_type   TEXT NOT NULL,            -- enums.FailureType
  symptom_span_id TEXT,
  execution_status TEXT,
  quality_verdict  TEXT,
  incident_status TEXT NOT NULL DEFAULT 'open',   -- enums.IncidentStatus
  review_status   TEXT NOT NULL DEFAULT 'unreviewed',
  evidence_grade  TEXT,
  created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS failure_clusters (
  id                TEXT PRIMARY KEY,
  project_id        TEXT NOT NULL,
  symptom_signature TEXT NOT NULL,
  cause_signature   TEXT,
  signature_version INTEGER NOT NULL DEFAULT 1,
  title             TEXT NOT NULL,
  count_24h         INTEGER NOT NULL DEFAULT 0,
  trend             TEXT DEFAULT 'flat',
  merged_into       TEXT,
  created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clusters_sig ON failure_clusters (project_id, symptom_signature);

CREATE TABLE IF NOT EXISTS diagnoses (
  id               TEXT PRIMARY KEY,
  incident_id      TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'pending',  -- pending|partial|complete|failed
  model_version    TEXT,
  rule_pack_version TEXT,
  started_at       TEXT,
  completed_at     TEXT,
  failure_reason   TEXT
);

CREATE TABLE IF NOT EXISTS candidates (
  id                  TEXT PRIMARY KEY,
  diagnosis_id        TEXT NOT NULL,
  rank                INTEGER NOT NULL,
  cause_type          TEXT NOT NULL,
  summary             TEXT NOT NULL,
  raw_score           REAL NOT NULL,        -- 不直接展示给用户（docs/08 约束）
  evidence_grade      TEXT NOT NULL,        -- enums.EvidenceGrade
  calibration_version TEXT DEFAULT 'v0',
  source              TEXT NOT NULL,        -- rule | diff | model
  first_fault_span_id TEXT,
  causal_path         TEXT,                 -- JSON: [span_id, ...]
  version             INTEGER NOT NULL DEFAULT 0   -- If-Match 并发控制
);

CREATE TABLE IF NOT EXISTS evidence (
  id           TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL,
  side         TEXT NOT NULL,               -- support | refute
  kind         TEXT NOT NULL,
  span_ref     TEXT,
  event_ref    TEXT,
  excerpt      TEXT,
  weight       REAL NOT NULL DEFAULT 1.0,
  CHECK (span_ref IS NOT NULL OR event_ref IS NOT NULL)  -- docs/08 硬约束
);

CREATE TABLE IF NOT EXISTS verdicts (
  id               TEXT PRIMARY KEY,
  candidate_id     TEXT NOT NULL,
  result           TEXT NOT NULL,           -- confirmed | excluded | insufficient
  reason_code      TEXT,
  correct_cause_ref TEXT,                   -- 人工指认真因（冷启动兜底）
  decided_by       TEXT,
  decided_at       TEXT NOT NULL,
  superseded_by    TEXT
);

-- docs/08 未定义 suites 表但 regression_cases.suite_id 引用之（已记 retro-log）
CREATE TABLE IF NOT EXISTS suites (
  id         TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  name       TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS regression_cases (
  id                   TEXT PRIMARY KEY,
  incident_id          TEXT NOT NULL,
  suite_id             TEXT NOT NULL,
  input_ref            TEXT,
  context_snapshot_ref TEXT,
  invariants           TEXT NOT NULL,       -- JSON: [{kind, params, source_evidence}]
  review_status        TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS gate_runs (
  id         TEXT PRIMARY KEY,
  suite_id   TEXT NOT NULL,
  release    TEXT NOT NULL,
  mode       TEXT NOT NULL,                 -- warn | block
  result     TEXT NOT NULL,                 -- pass | warn | block
  detail     TEXT NOT NULL,                 -- JSON: 逐用例结果
  created_at TEXT NOT NULL
);
