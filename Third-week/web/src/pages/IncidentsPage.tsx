import { useIncidents } from "../hooks/useXunji";
import { StatusTag } from "../components/StatusTag";
import type { Incident } from "../api/types";

/** 事故列表：失败模式簇卡片 + 事故表（docs/01 步骤 2） */
export function IncidentsPage() {
  const { data: incidents, isLoading } = useIncidents();

  const clusters = new Map<string, { title: string; count: number; sample: Incident }>();
  for (const i of incidents ?? []) {
    const key = i.cluster_title ?? "未聚类";
    if (!clusters.has(key)) {
      clusters.set(key, { title: key, count: i.cluster_count ?? 1, sample: i });
    }
  }

  return (
    <div className="page-in">
      {clusters.size > 0 && (
        <div className="grid g4 mb10" style={{ marginBottom: 16 }}>
          {[...clusters.values()].slice(0, 4).map((c) => (
            <div key={c.title} className="card cluster">
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <b style={{ fontSize: 13 }}>{c.title}</b>
                <StatusTag value={c.sample.failure_type} />
              </div>
              <div className="cnt" style={{ color: "var(--bad)" }}>
                {c.count}
                <span className="small muted" style={{ fontWeight: 400 }}> 起</span>
              </div>
              <div className="small muted mt10">
                簇由症状签名实时生成，非预设分类
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <div className="taxonomy-note">
          <b>统一口径：</b>故障类型回答「出了什么问题」，症状步骤是失败浮现处——
          <b>不等于根因步骤</b>，根因由诊断工作台给出候选与证据。
        </div>
        <div className="hd">
          <b>事故列表</b>
          <span className="tag t-gray">{incidents?.length ?? 0} 条</span>
        </div>
        {isLoading ? (
          <div className="empty">加载中…</div>
        ) : !incidents?.length ? (
          <div className="empty">暂无事故 — 一切正常，或先执行 npm run demo-offline 灌入演示数据</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>事故 ID</th><th>失败模式簇</th><th>故障类型</th><th>症状步骤</th>
                <th>证据等级</th><th>复核状态</th><th>处置</th>
              </tr>
            </thead>
            <tbody>
              {incidents.map((i) => (
                <tr key={i.id} className="click"
                    onClick={() => (location.hash = `#/incidents/${i.id}`)}>
                  <td className="mono"><b>{i.id}</b></td>
                  <td>
                    {i.cluster_title}
                    <div className="small muted">簇内 {i.cluster_count} 起</div>
                  </td>
                  <td><StatusTag value={i.failure_type} /></td>
                  <td className="mono small">{i.symptom_span_id}</td>
                  <td><StatusTag value={i.evidence_grade} /></td>
                  <td><StatusTag value={i.review_status} /></td>
                  <td><a href={`#/incidents/${i.id}`}>诊断 →</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
