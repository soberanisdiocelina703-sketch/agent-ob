import type { Evidence } from "../api/types";
import { Icon } from "./Icon";

interface Props {
  evidence: Evidence;
}

/** 证据卡片：支持证据/反证并排呈现（设计原则 2 的落点）。
 * .support/.counter 类保留（测试断言依赖），视觉样式由 .evi/.refute 提供。 */
export function EvidenceCard({ evidence }: Props) {
  const refute = evidence.side === "refute";
  const ref = evidence.span_ref ?? evidence.event_ref ?? "";
  return (
    <div className={`evi ${refute ? "counter refute" : "support"}`}>
      <span className="evid">{refute ? "反证" : "支持证据"}</span>
      <div className="evbody">
        <div className="evmeta">
          <span className="tag t-gray">{evidence.kind}</span>
          <a className="evjump mono" href="#/runs" title="跳转运行记录查看原始步骤">
            {ref}<Icon name="arrowRight" />
          </a>
        </div>
        <div className="evtext mono">{evidence.excerpt}</div>
      </div>
    </div>
  );
}
