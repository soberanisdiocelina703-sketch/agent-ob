interface Props {
  value: string | null | undefined;
  kind?: "exec" | "quality" | "grade" | "source" | "gate";
}

const MAP: Record<string, { cls: string; label: string }> = {
  success: { cls: "tag--success", label: "成功" },
  error: { cls: "tag--danger", label: "错误" },
  timeout: { cls: "tag--danger", label: "超时" },
  running: { cls: "tag", label: "运行中" },
  pass: { cls: "tag--success", label: "通过" },
  failed: { cls: "tag--danger", label: "未通过" },
  unevaluated: { cls: "tag", label: "未评估" },
  deterministic: { cls: "tag--success", label: "规则判定" },
  diff_based: { cls: "tag--info", label: "基线对照" },
  model_heuristic: { cls: "tag--warn", label: "模型推断" },
  rule: { cls: "tag--success", label: "规则" },
  diff: { cls: "tag--info", label: "Diff" },
  model: { cls: "tag--warn", label: "模型" },
  warn: { cls: "tag--warn", label: "警告" },
  block: { cls: "tag--danger", label: "阻断" },
  confirmed: { cls: "tag--success", label: "已确认" },
  excluded: { cls: "tag--danger", label: "已排除" },
  insufficient: { cls: "tag--warn", label: "证据不足" },
  unreviewed: { cls: "tag", label: "待复核" },
};

export function StatusTag({ value }: Props) {
  if (!value) return <span className="tag">—</span>;
  const m = MAP[value] ?? { cls: "tag", label: value };
  return <span className={`tag ${m.cls}`}>{m.label}</span>;
}
