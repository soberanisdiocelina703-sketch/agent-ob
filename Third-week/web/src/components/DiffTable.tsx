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
    <>
      <div className="bd" style={{ paddingBottom: 0 }}>
        <div className="diffhead">
          <div className="dcol base">
            <div className="k">成功基线</div>
            <div className="v mono">{diff.baseline_trace_id}</div>
            <div className="tiny muted">同 Agent 同版本最近一次质量通过</div>
          </div>
          <div className="dcol fail">
            <div className="k">失败运行</div>
            <div className="v mono">{diff.failed_trace_id}</div>
            <div className="tiny muted">当前事故对应的运行</div>
          </div>
        </div>
      </div>
      <table className="dt keydiff" style={{ marginTop: 12 }}>
        <thead>
          <tr>
            <th>步骤</th>
            <th>成功基线</th>
            <th>失败运行</th>
            <th>分歧字段</th>
          </tr>
        </thead>
        <tbody>
          {diff.steps!.map((s) => {
            const diverged = s.divergences.length > 0;
            const first = s.failed.span_id === diff.first_divergence_span_id && diverged;
            return (
              <tr key={s.step_name} className={diverged ? "diverged" : undefined}>
                <td>
                  <b>{s.step_name}</b>
                  {first && (
                    <div><span className="tag t-warn">首分歧</span></div>
                  )}
                </td>
                <td className="mono small basecell">
                  {s.baseline.note ?? fmt(s.baseline.output)?.slice(0, 150)}
                </td>
                <td className="mono small failcell">
                  {s.failed.note ?? fmt(s.failed.output)?.slice(0, 150)}
                </td>
                <td className="mono small">
                  {s.divergences.slice(0, 4).map((d) => (
                    <span key={d.key} className="divkey">
                      {d.key}: {fmt(d.baseline)} → {fmt(d.failed)}
                    </span>
                  ))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}
