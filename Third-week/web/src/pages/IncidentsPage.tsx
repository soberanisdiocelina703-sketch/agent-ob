import { useIncidents } from "../hooks/useXunji";
import { StatusTag } from "../components/StatusTag";

/** 事故列表：失败模式簇 + 事故（docs/01 步骤 2） */
export function IncidentsPage() {
  const { data: incidents, isLoading } = useIncidents();
  return (
    <div className="card">
      <h3 className="card__title">事故列表（按失败模式聚类）</h3>
      {isLoading ? (
        <div className="empty">加载中…</div>
      ) : !incidents?.length ? (
        <div className="empty">暂无事故 — 一切正常，或先灌入演示数据</div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>事故</th><th>失败模式簇</th><th>簇内计数</th><th>故障类型</th>
              <th>症状步骤</th><th>复核状态</th><th>证据等级</th><th></th>
            </tr>
          </thead>
          <tbody>
            {incidents.map((i) => (
              <tr key={i.id}>
                <td className="mono">{i.id}</td>
                <td>{i.cluster_title}</td>
                <td>{i.cluster_count}</td>
                <td><span className="tag tag--danger">{i.failure_type}</span></td>
                <td className="mono">{i.symptom_span_id}</td>
                <td><StatusTag value={i.review_status} /></td>
                <td><StatusTag value={i.evidence_grade} /></td>
                <td><a href={`#/incidents/${i.id}`}>诊断 →</a></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
