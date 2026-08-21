interface Props {
  value: string | null | undefined;
}

const MAP: Record<string, { cls: string; label: string }> = {
  success: { cls: "t-ok", label: "成功" },
  error: { cls: "t-bad", label: "错误" },
  timeout: { cls: "t-bad", label: "超时" },
  running: { cls: "t-gray", label: "运行中" },
  pass: { cls: "t-ok", label: "通过" },
  failed: { cls: "t-bad", label: "不通过" },
  unevaluated: { cls: "t-gray", label: "未评估" },
  deterministic: { cls: "t-rule", label: "规则判定" },
  diff_based: { cls: "t-brand", label: "基线对照" },
  model_heuristic: { cls: "t-model", label: "模型推断" },
  rule: { cls: "t-rule", label: "规则" },
  diff: { cls: "t-brand", label: "Diff" },
  model: { cls: "t-model", label: "模型" },
  warn: { cls: "t-warn", label: "警告" },
  block: { cls: "t-bad", label: "阻断" },
  confirmed: { cls: "t-ok", label: "已确认" },
  excluded: { cls: "t-bad", label: "已排除" },
  insufficient: { cls: "t-warn", label: "证据不足" },
  unreviewed: { cls: "t-warn", label: "待复核" },
  complete: { cls: "t-ok", label: "诊断完成" },
  partial: { cls: "t-warn", label: "模型分析中" },
  pending: { cls: "t-gray", label: "排队中" },
  tool_arg_violation: { cls: "t-bad", label: "工具参数违例" },
  output_contract_violation: { cls: "t-warn", label: "输出契约违例" },
  exception: { cls: "t-bad", label: "异常" },
  retrieval_empty: { cls: "t-warn", label: "检索为空" },
  quality_check_failed: { cls: "t-warn", label: "质量校验不平" },
};

export function StatusTag({ value }: Props) {
  if (!value) return <span className="tag t-gray">—</span>;
  const m = MAP[value] ?? { cls: "t-gray", label: value };
  return <span className={`tag ${m.cls}`}>{m.label}</span>;
}
