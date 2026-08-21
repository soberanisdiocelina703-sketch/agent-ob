"""Enum dictionary — values must match second-week/docs/08 verbatim where defined.

Where docs/08 left values unenumerated (IncidentStatus, EvidenceGrade tiers),
the choices here are recorded in retro-log.md as 口径含糊 feedback items.
"""
from enum import Enum


class StepType(str, Enum):
    """Cross-framework stable step taxonomy (PRD三层口径 middle layer)."""

    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    RETRIEVAL = "retrieval"
    VALIDATION = "validation"
    PLANNING = "planning"
    OTHER = "other"


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    RUNNING = "running"


class QualityVerdict(str, Enum):
    PASS = "pass"
    FAILED = "failed"
    UNEVALUATED = "unevaluated"


class FailureType(str, Enum):
    """T1-determinable failure taxonomy (范围裁定后的词汇表)."""

    TOOL_ARG_VIOLATION = "tool_arg_violation"
    OUTPUT_CONTRACT_VIOLATION = "output_contract_violation"
    EXCEPTION = "exception"
    TIMEOUT = "timeout"
    RETRIEVAL_EMPTY = "retrieval_empty"
    QUALITY_CHECK_FAILED = "quality_check_failed"


class EvidenceGrade(str, Enum):
    """docs/08 named the field but not the values — see retro-log."""

    DETERMINISTIC = "deterministic"  # 规则判定，铁证
    DIFF_BASED = "diff_based"        # 成功基线对照推断
    MODEL_HEURISTIC = "model_heuristic"  # 模型/启发式推断


class CandidateSource(str, Enum):
    RULE = "rule"
    DIFF = "diff"
    MODEL = "model"


class EvidenceSide(str, Enum):
    SUPPORT = "support"
    REFUTE = "refute"


class ReviewResult(str, Enum):
    """Must stay identical in API and DB (docs/08 §8.3 constraint)."""

    CONFIRMED = "confirmed"
    EXCLUDED = "excluded"
    INSUFFICIENT = "insufficient"


class DiagnosisStatus(str, Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    COMPLETE = "complete"
    FAILED = "failed"


class IncidentStatus(str, Enum):
    OPEN = "open"
    REVIEWED = "reviewed"
    CONVERTED = "converted"  # 已转回归用例
    CLOSED = "closed"


class GateMode(str, Enum):
    WARN = "warn"
    BLOCK = "block"


class GateResult(str, Enum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"
