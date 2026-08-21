"""Trajectory evaluator interface + Mock and Claude Code implementations.

§8.4 分工：模型只处理语义问题，且输出必须是结构化证据引用 —
validate_model_output() enforces that; free text without span refs is dropped
before it can reach the aggregation layer.
"""
import json
import subprocess
import time
from dataclasses import dataclass, field

from .causal import Graph
from .enums import FailureType

MODEL_TIMEOUT_S = 30  # §8.4 时序：模型异步、30s 超时、失败不阻塞


class EvaluatorError(Exception):
    pass


@dataclass
class EvalCandidate:
    cause_type: str
    summary: str
    first_fault_span_id: str
    evidence: list[dict] = field(default_factory=list)
    confidence: float = 0.5


class MockEvaluator:
    """Heuristic stand-in for offline mode; simulates latency and failure paths."""

    model_version = "mock-heuristic-v1"

    def __init__(self, delay_s: float = 0.0, fail: bool = False):
        self.delay_s = delay_s
        self.fail = fail

    def evaluate(self, conn, graph: Graph, symptom_span_id: str | None,
                 baseline_trace_id: str | None = None) -> list[EvalCandidate]:
        if self.fail:
            raise EvaluatorError("simulated model timeout")
        if self.delay_s:
            time.sleep(self.delay_s)
        if not symptom_span_id or symptom_span_id not in graph.spans:
            return []
        symptom = graph.spans[symptom_span_id]
        evidence = [{
            "side": "support", "kind": "model_reasoning",
            "span_ref": f"{graph.trace_id}/{symptom_span_id}",
            "excerpt": f"替代解释：症状步骤 {symptom['step_name']} 自身逻辑缺陷",
        }]
        if baseline_trace_id:
            # 基线对照反证：基线中同一步骤行为一致 → 削弱「症状步骤自身有错」
            evidence.append({
                "side": "refute", "kind": "baseline_consistency",
                "span_ref": f"{baseline_trace_id}/{symptom_span_id.replace(graph.trace_id, baseline_trace_id)}",
                "excerpt": "成功基线中该步骤对相同形态输入行为一致，更可能是上游数据问题",
            })
        return [EvalCandidate(
            cause_type=FailureType.QUALITY_CHECK_FAILED.value,
            summary=f"替代解释：{symptom['step_name']} 步骤自身逻辑缺陷（模型推断）",
            first_fault_span_id=symptom_span_id,
            evidence=evidence,
            confidence=0.35,
        )]


def validate_model_output(raw: dict, graph: Graph) -> list[EvalCandidate]:
    """Reject candidates whose refs don't resolve — 说不出证据的结论不许上屏."""
    valid_causes = {f.value for f in FailureType}
    out: list[EvalCandidate] = []
    for c in raw.get("candidates", []):
        span_id = c.get("first_fault_span_id")
        if span_id not in graph.spans:
            continue
        evidence = [e for e in c.get("evidence", [])
                    if e.get("span_ref", "").split("/")[-1] in graph.spans and e.get("excerpt")]
        if not evidence:
            continue
        out.append(EvalCandidate(
            cause_type=c.get("cause_type") if c.get("cause_type") in valid_causes
            else FailureType.QUALITY_CHECK_FAILED.value,
            summary=str(c.get("summary", ""))[:300],
            first_fault_span_id=span_id,
            evidence=[{"side": e.get("side", "support"), "kind": "model_reasoning",
                       "span_ref": f"{graph.trace_id}/{e['span_ref'].split('/')[-1]}",
                       "excerpt": str(e["excerpt"])[:500]} for e in evidence],
            confidence=0.5,
        ))
    return out


class ClaudeCodeEvaluator:
    """Real semantic diagnosis via local `claude -p` (needs logged-in CLI).

    runner is injectable for tests; production default shells out.
    """

    model_version = "claude-code-cli"

    def __init__(self, runner=None, timeout_s: int = MODEL_TIMEOUT_S):
        self.runner = runner or self._run_cli
        self.timeout_s = timeout_s

    def _build_prompt(self, conn, graph: Graph, symptom_span_id: str | None) -> str:
        lines = []
        for sid in graph.nodes:
            s = graph.spans[sid]
            out = ""
            if s["output_ref"]:
                row = conn.execute("SELECT content FROM payloads WHERE ref=?",
                                   (s["output_ref"],)).fetchone()
                out = (row["content"] if row else "")[:200]
            lines.append(f"- span_id={sid} step={s['step_name']} status={s['execution_status']} "
                         f"quality={s['quality_verdict']} output={out}")
        causes = ", ".join(f.value for f in FailureType)
        return (
            "你是 Agent 执行链诊断器。以下是一次失败运行的步骤（时间序）：\n"
            + "\n".join(lines)
            + f"\n症状步骤: {symptom_span_id}\n"
            f"请找出最早的故障步骤并给出证据。只输出 JSON："
            f'{{"candidates":[{{"first_fault_span_id":"<span_id>","cause_type":"<{causes} 之一>",'
            f'"summary":"...","evidence":[{{"span_ref":"<span_id>","side":"support|refute",'
            f'"excerpt":"引用的具体输出内容"}}]}}]}}\n'
            "说不出具体证据就不要给候选。"
        )

    def _run_cli(self, prompt: str) -> str:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=self.timeout_s, encoding="utf-8",
        )
        if proc.returncode != 0:
            raise EvaluatorError(f"claude CLI exit {proc.returncode}: {proc.stderr[:200]}")
        return proc.stdout

    def evaluate(self, conn, graph: Graph, symptom_span_id: str | None,
                 baseline_trace_id: str | None = None) -> list[EvalCandidate]:
        prompt = self._build_prompt(conn, graph, symptom_span_id)
        try:
            stdout = self.runner(prompt)
        except subprocess.TimeoutExpired as exc:
            raise EvaluatorError("claude CLI timeout") from exc
        try:
            envelope = json.loads(stdout)
            text = envelope.get("result", "") if isinstance(envelope, dict) else ""
            start, end = text.find("{"), text.rfind("}")
            payload = json.loads(text[start:end + 1]) if start != -1 else {}
        except (json.JSONDecodeError, ValueError):
            return []  # 模型输出不可解析 → 视为无候选，不阻塞（G-4）
        return validate_model_output(payload, graph)
