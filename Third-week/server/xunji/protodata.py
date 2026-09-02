"""proto/data.js 动态生成器——中期原型作业务前端，后端按其数据契约喂真实数据。

proto/ 三件套（prototype.html/css/js）逐字节复制自 midterm/，一处不改；
prototype.html 以相对路径加载 data.js，因此本模块把 /proto/data.js 渲染成
「从真实库映射出的原型十个全局常量」，是唯一的适配层。

映射口径（有损，如实声明）：
- T1 六类 failure_type → FM-* 代号（FM_MAP）；原型的 FM-01~09 九类是产品叙事，
  真实数据只有 T1 六类（docs/05 §F 范围裁定）；
- evidence_grade 三档 → 原型 sufficient/partial/insufficient 三档（GRADE_MAP）；
- span 按 ts 序编为 S1..Sn（原型证据跳转/高亮以此为锚）；
- judge 分数、会话数等原型专有字段：无真实来源的置 null/0，原型自身兜底渲染。
"""
import json
import sqlite3
from datetime import datetime, timezone

from .diagnosis import load_candidates
from .causal import build_graph, path_between
from .diffgen import compare_table, find_baseline

PROJECT = "recon-demo"

FM_MAP = {
    "exception":                 ("FM-EX",  "执行异常",     "规则（异常传播）"),
    "tool_arg_violation":        ("FM-ARG", "工具参数违例", "规则（必填字段、类型校验）"),
    "output_contract_violation": ("FM-CT",  "输出契约违例", "规则（输出契约）"),
    "timeout":                   ("FM-TO",  "超时",         "规则（超时阈值）"),
    "retrieval_empty":           ("FM-RE",  "检索结果为空", "规则（空结果集）"),
    "quality_check_failed":      ("FM-QC",  "质量校验不平", "Diff 对照 + 校验步骤（静默故障）"),
}
GRADE_MAP = {"deterministic": "sufficient", "diff_based": "partial",
             "model_heuristic": "insufficient"}
STEP_TYPE_MAP = {"llm_call": "LLM", "tool_call": "TOOL", "retrieval": "RETRIEVAL",
                 "validation": "GUARDRAIL", "planning": "AGENT", "other": "OTHER"}
SRC_LABEL = {"rule": "规则判定", "diff": "Diff 对照", "model": "模型推断"}


def _parse_ts(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fmt_ts(iso: str | None) -> str:
    dt = _parse_ts(iso)
    return dt.strftime("%m-%d %H:%M") if dt else "—"


def _fmt_dur(ms: float | None) -> str:
    if ms is None:
        return "—"
    return f"{ms:.0f}ms" if ms < 1000 else f"{ms / 1000:.1f}s"


def _age_hours(iso: str | None) -> int:
    dt = _parse_ts(iso)
    if not dt:
        return 1
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(1, int((datetime.now(timezone.utc) - dt).total_seconds() // 3600))


def _fm_code(failure_type: str | None) -> str:
    return FM_MAP.get(failure_type or "", ("FM-EX",))[0]


def _excerpt(content: str | None, n: int = 90) -> str:
    if not content:
        return ""
    return content[:n].replace("\n", " ")


def _sid_map(conn: sqlite3.Connection, trace_id: str) -> dict[str, str]:
    rows = conn.execute(
        "SELECT span_id FROM spans WHERE trace_id=? ORDER BY ts, span_id", (trace_id,)
    ).fetchall()
    return {r["span_id"]: f"S{i + 1}" for i, r in enumerate(rows)}


def _latest_diagnosis(conn: sqlite3.Connection, incident_id: str):
    d = conn.execute(
        "SELECT * FROM diagnoses WHERE incident_id=? ORDER BY started_at DESC LIMIT 1",
        (incident_id,)).fetchone()
    if d is None:
        return None, []
    return d, load_candidates(conn, d["id"])


def _incident_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT i.*, fc.title cluster_title, fc.count_24h cluster_count
           FROM incidents i LEFT JOIN failure_clusters fc ON fc.id = i.cluster_id
           WHERE i.project_id=? ORDER BY i.created_at DESC""", (PROJECT,)).fetchall()


def build_failure_types(conn: sqlite3.Connection, incidents: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for i in incidents:
        counts[i["fm"]] = counts.get(i["fm"], 0) + 1
    top = max(counts.values()) if counts else 0
    out = []
    for ftype, (code, name, path) in FM_MAP.items():
        n = counts.get(code, 0)
        out.append({"code": code, "key": ftype.upper(), "name": name, "path": path,
                    "count": n, "trend": 0, "sessions": n, "stage": "T1 已实现",
                    "hero": bool(n and n == top)})
    return out


def build_traces(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT trace_id, MIN(ts) started, MAX(ts) ended, COUNT(*) n,
                  MAX(agent_version) ver, MAX(run_name) run,
                  MAX(CASE WHEN execution_status IN ('error','timeout') THEN 1 ELSE 0 END) has_err,
                  MAX(CASE WHEN quality_verdict='failed' THEN 1 ELSE 0 END) qfail,
                  MAX(CASE WHEN quality_verdict='pass' THEN 1 ELSE 0 END) qpass
           FROM spans WHERE project_id=? GROUP BY trace_id
           ORDER BY started DESC LIMIT 100""", (PROJECT,)).fetchall()
    out = []
    for r in rows:
        inc = conn.execute("SELECT id FROM incidents WHERE trace_id=?",
                           (r["trace_id"],)).fetchone()
        t0, t1 = _parse_ts(r["started"]), _parse_ts(r["ended"])
        dur = (t1 - t0).total_seconds() * 1000 if t0 and t1 else None
        out.append({
            "id": r["trace_id"],
            "exec": "failed" if r["has_err"] else "success",
            "quality": "fail" if r["qfail"] else "pass" if r["qpass"] else "unknown",
            "run": r["run"] or "—", "ver": r["ver"] or "—",
            "at": _fmt_ts(r["started"]), "steps": r["n"], "dur": _fmt_dur(dur),
            "incident": inc["id"] if inc else None, "judge": None,
        })
    return out


def build_incidents(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for i in _incident_rows(conn):
        sids = _sid_map(conn, i["trace_id"])
        _, cands = _latest_diagnosis(conn, i["id"])
        top = cands[0] if cands else None
        fault_span = None
        if top and top["first_fault_span_id"]:
            fault_span = conn.execute(
                "SELECT * FROM spans WHERE trace_id=? AND span_id=?",
                (i["trace_id"], top["first_fault_span_id"])).fetchone()
        sym_span = conn.execute(
            "SELECT * FROM spans WHERE trace_id=? AND span_id=?",
            (i["trace_id"], i["symptom_span_id"])).fetchone() if i["symptom_span_id"] else None
        code, name, _ = FM_MAP.get(i["failure_type"], ("FM-EX", "执行异常", ""))
        out.append({
            "id": i["id"], "fm": code, "at": _fmt_ts(i["created_at"]),
            "run": (sym_span["run_name"] if sym_span else None) or "—",
            "trace": i["trace_id"],
            "symptom": f"{name} · {(sym_span['step_name'] if sym_span else '—')}",
            "symptomStep": (f"{sids.get(i['symptom_span_id'], '—')} "
                            f"{STEP_TYPE_MAP.get(sym_span['step_type'], 'OTHER') if sym_span else '—'}"),
            "faultStep": sids.get(top["first_fault_span_id"], "—") if top else "—",
            "faultType": (STEP_TYPE_MAP.get(fault_span["step_type"], "OTHER")
                          if fault_span else "OTHER"),
            "faultName": (fault_span["step_name"] if fault_span else "待诊断"),
            "evidence": GRADE_MAP.get(i["evidence_grade"] or "", "insufficient"),
            "review": {"unreviewed": "pending", "confirmed": "confirmed",
                       "excluded": "excluded"}.get(i["review_status"], "pending"),
            "sessions": i["cluster_count"] or 1, "age": _age_hours(i["created_at"]),
            "hero": i["failure_type"] == "quality_check_failed" or (i["cluster_count"] or 1) >= 2,
        })
    return out


def build_spans(conn: sqlite3.Connection, incidents: list[dict]) -> dict[str, list[dict]]:
    marks: dict[str, dict[str, str]] = {}  # trace → {span_id: fault|symptom}
    for i in _incident_rows(conn):
        m = marks.setdefault(i["trace_id"], {})
        if i["symptom_span_id"]:
            m[i["symptom_span_id"]] = "symptom"
        _, cands = _latest_diagnosis(conn, i["id"])
        if cands and cands[0]["first_fault_span_id"]:
            m[cands[0]["first_fault_span_id"]] = "fault"

    out: dict[str, list[dict]] = {}
    trace_ids = [r["trace_id"] for r in conn.execute(
        "SELECT DISTINCT trace_id FROM spans WHERE project_id=?", (PROJECT,))]
    for tid in trace_ids:
        rows = conn.execute(
            "SELECT * FROM spans WHERE trace_id=? ORDER BY ts, span_id", (tid,)).fetchall()
        spans = []
        for n, s in enumerate(rows):
            payload = ""
            if s["output_ref"]:
                p = conn.execute("SELECT content FROM payloads WHERE ref=?",
                                 (s["output_ref"],)).fetchone()
                payload = _excerpt(p["content"] if p else "")
            mark = marks.get(tid, {}).get(s["span_id"])
            st = (mark or ("bad" if s["execution_status"] in ("error", "timeout")
                           else "warn" if s["quality_verdict"] == "failed" else "ok"))
            note = None
            if mark == "fault":
                note = "首故障点：诊断 Top-1 候选定位于此步骤"
            elif mark == "symptom":
                note = "症状点：失败在此步骤浮现（不等于根因）"
            elif s["link_kind"] == "broken_parent":
                note = "断链：父 span 缺失，已降级挂载"
            spans.append({
                "id": f"S{n + 1}", "ind": 1 if s["parent_span_id"] else 0,
                "type": STEP_TYPE_MAP.get(s["step_type"], "OTHER"),
                "name": (s["step_name"] or "—") + (f" · {payload}" if payload else ""),
                "dur": _fmt_dur(s["duration_ms"]), "st": st,
                **({"note": note} if note else {}),
            })
        out[tid] = spans
    return out


def build_diagnoses(conn: sqlite3.Connection) -> dict[str, dict]:
    out = {}
    for i in _incident_rows(conn):
        d, cands = _latest_diagnosis(conn, i["id"])
        if d is None or not cands:
            continue
        sids = _sid_map(conn, i["trace_id"])
        names = {r["span_id"]: r["step_name"] for r in conn.execute(
            "SELECT span_id, step_name FROM spans WHERE trace_id=?", (i["trace_id"],))}
        top = cands[0]
        fault_sid = sids.get(top["first_fault_span_id"], "—")
        sym_sid = sids.get(i["symptom_span_id"], "—")
        gap = abs(int(sym_sid[1:]) - int(fault_sid[1:])) \
            if fault_sid.startswith("S") and sym_sid.startswith("S") else 0

        def _sid_of_ref(ref: str | None) -> str:
            return sids.get((ref or "").split("/")[-1], "—")

        cand_objs, e_n, c_n = [], 0, 0
        for c in cands:
            support, refute = [], []
            for e in c["evidence"]:
                item = {"kind": e["kind"], "from": SRC_LABEL.get(c["source"], "模型推断"),
                        "span": _sid_of_ref(e["span_ref"]), "text": e["excerpt"] or ""}
                if e["side"] == "refute":
                    c_n += 1
                    refute.append({**item, "id": f"C{c_n}",
                                   "impact": "反证削弱该候选，复核时需一并权衡"})
                else:
                    e_n += 1
                    support.append({**item, "id": f"E{e_n}"})
            cand_objs.append({
                "rank": c["rank"], "source": c["source"],
                "grade": GRADE_MAP.get(c["evidence_grade"], "insufficient"),
                "faultStep": sids.get(c["first_fault_span_id"]),
                "title": c["summary"], "support": support, "refute": refute,
            })
        causal_path = top["causal_path"] or []
        # 展示路径现场重算：首故障 → …dataflow 中间节点… → 症状（存量数据
        # 落库的旧口径路径可能从根 span 起步，展示时统一纠正）
        if top["first_fault_span_id"] and i["symptom_span_id"]:
            g = build_graph(conn, i["trace_id"])
            causal_path = path_between(g, top["first_fault_span_id"], i["symptom_span_id"])
        causal = [f"{sids.get(s, '—')} {names.get(s, s)}" for s in causal_path]
        if not causal:
            causal = [f"{fault_sid} {names.get(top['first_fault_span_id'], '首故障')}",
                      f"{sym_sid} {names.get(i['symptom_span_id'], '症状')}"]
        # 故障即症状：单节点即完整路径，不复制成假两节点
        out[i["id"]] = {
            "rulePack": d["rule_pack_version"] or "—",
            "model": d["model_version"] or "—",
            "faultStep": fault_sid, "symptomStep": sym_sid, "gap": gap,
            "causal": causal, "candidates": cand_objs,
            "gaps": ["补充采集该步骤的输入输出 payload", "累积同 Agent 成功基线以启用 Diff"],
        }
    return out


def _cell_text(cell: dict) -> str:
    return (cell.get("note")
            or _excerpt(json.dumps(cell.get("output"), ensure_ascii=False), 160) or "—")


def build_diffs(conn: sqlite3.Connection) -> dict[str, dict]:
    out = {}
    for i in _incident_rows(conn):
        span0 = conn.execute("SELECT * FROM spans WHERE trace_id=? LIMIT 1",
                             (i["trace_id"],)).fetchone()
        if not span0:
            continue
        baseline = find_baseline(conn, span0["project_id"], span0["agent_id"],
                                 span0["agent_version"], exclude=i["trace_id"])
        if not baseline:
            continue
        table = compare_table(conn, i["trace_id"], baseline)
        sids = _sid_map(conn, i["trace_id"])
        dims, same_kept = [], 0
        for row in table["steps"]:
            same = not row["divergences"]
            if same and same_kept >= 3:
                continue
            if same:
                same_kept += 1
            sid = sids.get(row["failed"]["span_id"] or "", "—")
            dims.append({
                "dim": row["step_name"], "step": f"{sid} {row['step_name']}", "same": same,
                "base": _cell_text(row["baseline"]), "fail": _cell_text(row["failed"]),
                "keys": [{"k": d["key"], "b": str(d["baseline"]), "f": str(d["failed"])}
                         for d in row["divergences"][:6]],
            })
            if len(dims) >= 8:
                break
        out[i["id"]] = {"baseline": baseline, "failed": i["trace_id"],
                        "firstDiv": sids.get(table["first_divergence_span_id"] or "", "—"),
                        "dims": dims}
    return out


def _inv_text(inv: dict) -> str:
    if inv.get("kind") == "no_recurrence":
        step = inv.get("fault_step_name") or "—"
        return f"no_recurrence: 步骤 {step} 不得再出现 {inv.get('failure_type')}（源 {inv.get('source_incident')}）"
    return f"{inv.get('kind')}: {inv.get('description', json.dumps(inv, ensure_ascii=False))}"


def build_suites(conn: sqlite3.Connection, fm_of: dict[str, str]) -> list[dict]:
    out = []
    for s in conn.execute("SELECT * FROM suites WHERE project_id=?", (PROJECT,)):
        cases = []
        for c in conn.execute("SELECT * FROM regression_cases WHERE suite_id=?", (s["id"],)):
            cases.append({
                "id": c["id"], "from": c["incident_id"],
                "fm": fm_of.get(c["incident_id"], "FM-EX"),
                "status": "active" if c["review_status"] == "active" else "pending",
                "inv": [_inv_text(v) for v in json.loads(c["invariants"])],
                "snapshot": f"输入引用 {c['input_ref'] or '—'} · Trace 快照 {c['context_snapshot_ref']}",
            })
        out.append({"id": s["id"], "name": s["name"], "cases": cases})
    if not out:  # 原型 openCaseModal 依赖 SUITES 非空
        out.append({"id": "SUITE-DEFAULT", "name": "默认回归集", "cases": []})
    return out


def build_gate_runs(conn: sqlite3.Connection, fm_of: dict[str, str]) -> list[dict]:
    case_inc = {c["id"]: c["incident_id"] for c in conn.execute(
        "SELECT id, incident_id FROM regression_cases")}
    out = []
    for r in conn.execute("SELECT * FROM gate_runs ORDER BY created_at DESC LIMIT 5"):
        detail = json.loads(r["detail"])
        cases = detail.get("cases", [])
        passed = sum(1 for c in cases if c.get("passed"))
        out.append({
            "id": r["id"], "release": r["release"], "at": _fmt_ts(r["created_at"]),
            "mode": r["mode"], "result": r["result"],
            "total": len(cases), "passed": passed, "failed": len(cases) - passed, "blocked": 0,
            "detail": [{
                "case": c.get("case_id", "—"),
                "fm": fm_of.get(case_inc.get(c.get("case_id", ""), ""), "FM-EX"),
                "result": "pass" if c.get("passed") else "fail",
                "why": (c.get("violations") or [{}])[0].get("detail", "全部不变量通过"),
            } for c in cases],
        })
    if not out:  # 原型 renderGate 无条件读 GATE_RUNS[0]
        out.append({"id": "—", "release": "—", "at": "—", "mode": "warn", "result": "pass",
                    "total": 0, "passed": 0, "failed": 0, "blocked": 0, "detail": []})
    return out


def build_case_presets(conn: sqlite3.Connection, suites: list[dict]) -> dict[str, dict]:
    suite_id = suites[0]["id"]
    out = {}
    for i in _incident_rows(conn):
        first = conn.execute(
            "SELECT * FROM spans WHERE trace_id=? ORDER BY ts LIMIT 1", (i["trace_id"],)
        ).fetchone()
        input_text = "—"
        if first and first["input_ref"]:
            p = conn.execute("SELECT content FROM payloads WHERE ref=?",
                             (first["input_ref"],)).fetchone()
            input_text = _excerpt(p["content"] if p else "", 140) or "—"
        _, cands = _latest_diagnosis(conn, i["id"])
        fault_name = "首故障步骤"
        if cands and cands[0]["first_fault_span_id"]:
            fs = conn.execute("SELECT step_name FROM spans WHERE trace_id=? AND span_id=?",
                              (i["trace_id"], cands[0]["first_fault_span_id"])).fetchone()
            fault_name = (fs["step_name"] if fs else fault_name) or fault_name
        out[i["id"]] = {
            "caseId": f"REG-{i['id'].split('-')[-1]}", "suite": suite_id,
            "input": input_text,
            "snapshot": f"Trace {i['trace_id']} 全量 span 快照（复核确认后由后端真实生成）",
            "inv": [f"no_recurrence: 步骤 {fault_name} 不得再出现 {i['failure_type']}",
                    "quality_pass: 同工作流运行的质量结论不得为 failed"],
        }
    return out


def build_checkup(conn: sqlite3.Connection) -> list[dict]:
    total = conn.execute("SELECT COUNT(*) c FROM spans WHERE project_id=?",
                         (PROJECT,)).fetchone()["c"]
    with_out = conn.execute(
        "SELECT COUNT(*) c FROM spans WHERE project_id=? AND output_ref IS NOT NULL",
        (PROJECT,)).fetchone()["c"]
    broken = conn.execute(
        "SELECT COUNT(*) c FROM spans WHERE project_id=? AND link_kind='broken_parent'",
        (PROJECT,)).fetchone()["c"]
    agents = conn.execute(
        "SELECT DISTINCT agent_id, agent_version FROM spans WHERE project_id=?",
        (PROJECT,)).fetchall()
    no_baseline = [a for a in agents if find_baseline(
        conn, PROJECT, a["agent_id"], a["agent_version"], exclude="__none__") is None]
    cov = round(with_out / total * 100, 1) if total else 0.0
    return [
        {"key": "coverage", "name": "采集完整度", "value": f"{cov}%",
         "status": "ok" if cov >= 80 else "warn",
         "detail": f"{total} 条 span 中 {with_out} 条携带输出 payload"},
        {"key": "broken", "name": "断链检测", "value": f"{broken} 处",
         "status": "ok" if broken == 0 else "warn",
         "detail": "父 span 缺失的步骤已降级为根节点挂载，不影响诊断但会削弱因果推导",
         **({"fix": ["在上报侧确保 parent_span_id 随上下文透传",
                     "参考 sdk/xunji_sdk 的 stream-json 解析路径"]} if broken else {})},
        {"key": "dup", "name": "重复上报", "value": "0%", "status": "ok",
         "detail": "接入层按 (trace_id, span_id) 幂等去重，重复上报不产生脏数据"},
        {"key": "baseline", "name": "基线覆盖", "value": f"{len(agents) - len(no_baseline)}/{len(agents)} 个 Agent",
         "status": "ok" if not no_baseline else "warn",
         "detail": "有成功基线的 Agent 才能启用 Diff 对照定位",
         **({"fix": [f"为 {a['agent_id']}@{a['agent_version']} 积累一次质量通过的运行"
                     for a in no_baseline[:3]]} if no_baseline else {})},
    ]


def render_data_js(conn: sqlite3.Connection) -> str:
    incidents = build_incidents(conn)
    fm_of = {i["id"]: i["fm"] for i in incidents}
    suites = build_suites(conn, fm_of)
    parts = {
        "FAILURE_TYPES": build_failure_types(conn, incidents),
        "TRACES": build_traces(conn),
        "INCIDENTS": incidents,
        "SPANS": build_spans(conn, incidents),
        "DIAGNOSES": build_diagnoses(conn),
        "DIFFS": build_diffs(conn),
        "SUITES": suites,
        "GATE_RUNS": build_gate_runs(conn, fm_of),
        "CASE_PRESETS": build_case_presets(conn, suites),
        "CHECKUP": build_checkup(conn),
        "STATS": {},  # 仅答辩稿使用，原型不消费
    }
    now = datetime.now(timezone.utc).isoformat()
    body = "\n".join(
        f"const {name} = {json.dumps(value, ensure_ascii=False)};"
        for name, value in parts.items())
    return (f"/* 由寻迹后端实时生成于 {now} — 数据全部来自真实库，"
            f"契约与 midterm/data.js 对齐 */\n{body}\n")
