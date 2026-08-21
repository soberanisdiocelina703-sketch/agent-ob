import type { DiffView } from "../api/types";

/** 成功/失败字段级对比表（提示词允许的 Diff 保底形态） */
export function DiffTable({ diff }: { diff: DiffView }) {
  if (!diff.available) {
    return (
      <div className="empty">
        {diff.message ?? "暂无可比成功基线；累积一次成功运行后 Diff 将启用"}
      </div>
    );
  }
  const fmt = (v: unknown) =>
    typeof v === "string" ? v : JSON.stringify(v, null, 0);
  return (
    <table className="table">
      <thead>
        <tr>
          <th>步骤</th>
          <th>成功基线（{diff.baseline_trace_id}）</th>
          <th>失败运行（{diff.failed_trace_id}）</th>
          <th>分歧字段</th>
        </tr>
      </thead>
      <tbody>
        {diff.steps!.map((s) => {
          const diverged = s.divergences.length > 0;
          const first = s.failed.span_id === diff.first_divergence_span_id && diverged;
          return (
            <tr key={s.step_name}>
              <td>
                {s.step_name} {first && <span className="tag tag--warn">首分歧</span>}
              </td>
              <td className="mono">{s.baseline.note ?? fmt(s.baseline.output)?.slice(0, 160)}</td>
              <td className={`mono${diverged ? " diff-cell--diverged" : ""}`}>
                {s.failed.note ?? fmt(s.failed.output)?.slice(0, 160)}
              </td>
              <td className="mono">
                {s.divergences.slice(0, 4).map((d) => (
                  <div key={d.key}>
                    {d.key}: {fmt(d.baseline)} → {fmt(d.failed)}
                  </div>
                ))}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
