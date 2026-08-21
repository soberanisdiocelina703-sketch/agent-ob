# SPEC：寻迹 T1 通用流诊断最小闭环（第三周）

> 提交状态：已确认
> 核心交付：功能规格与验收标准
> 上游依据：`promot/第三周任务提示词-优化版.md` · `second-week/docs/01/03/05/06/08`
> 迭代：iter03 · 提测日期（假定）：20260827 · 分支：feature/trace-runs

## 1. 一句话定义

为接入寻迹的 Agent（Claude Code 生态：Agent SDK 与 CLI）提供 **T1 通用流诊断闭环**：自动采集运行 Trace → 事故触发 → 规则 + Diff + 模型三路诊断（现场计算，证据强制引用）→ 人工复核 → 转回归用例 → 发布门禁。

## 2. 范围（In Scope，全部 T1）

| # | 能力 | 说明 |
|---|------|------|
| S1 | 接入层 | `xunji run -- claude -p ...` 包装命令解析 stream-json；`xunji connect` 写 hooks；SDK 探针包装 `query()`（同一重建逻辑） |
| S2 | 接入与标准化 | `POST /v1/traces`（契约格式）；断链/字段缺失降级处理 |
| S3 | 因果图（T1 口径） | 父子层级 + 时序 + 数据流启发式（上游输出出现在下游输入），启发式边带置信标记 |
| S4 | 规则引擎 | 3 类规则：工具参数 Schema 违例、步骤输出契约违例、异常与超时传播；声明式配置 + 引擎分离 |
| S5 | Diff 候选生成器 | 与最近兼容成功基线逐步骤对比，首个显著分歧点生成候选（静默故障主诊断路径） |
| S6 | 评估模型 | `Evaluator` 接口；默认启发式 Mock（含超时失败路径）；可选 `ClaudeCodeEvaluator` 子进程调用 `claude -p` |
| S7 | 诊断聚合 | 合并去重、证据加权排序、Top-3 截断、证据等级映射；**无证据候选丢弃并记日志** |
| S8 | 事故与聚类 | 症状签名（agent + 症状步骤 + failure_type + 校验项）自动建簇/归簇 |
| S9 | 复核 | confirmed/excluded/insufficient 三态必选；`correct_cause_ref` 人工指认；If-Match 并发控制（409） |
| S10 | 回归与门禁 | confirmed 事故转回归用例（输入引用 + 不变量）；gate-run 重放输出 pass/warn/block |
| S11 | 前端五页 | 运行记录 / 事故列表 / 诊断工作台（证据卡片 + Diff）/ 复核 / 回归与门禁 |
| S12 | 示例 Agent | 对账场景（读-析-报）；`--inject stale-source|broken-contract|bad-tool-args` 只在工具/数据层 |
| S13 | 双态 Demo | 真实态（现场执行示例 Agent + 现场计算）；离线态（真实录制 fixtures + Mock 回放，供 CI） |

## 3. 明确不做（Out of Scope）

T2 语义增强（state/handoff/memory 采集与相关规则，建表与注解 API 只留定义）；多租户与鉴权；LangGraph/Dify 等其他框架适配；消息队列；ClickHouse/Postgres 真实部署（SQLite 替身，同构契约）；水平扩展。

## 4. 验收标准（对齐提示词自检清单）

1. `demo` 启动全栈；`demo-run` 现场执行示例 Agent（≥1 正常 + 2 注入，含静默质量故障），事故/候选/证据全部运行时计算；
2. 改动注入参数可改变诊断结果；代码库无预写诊断结论（可 grep 验证）；
3. `demo-offline` 无网跑通同一流程；E2E 冒烟自动走通「入库 → 事故 → 诊断 → 复核 → 转用例 → 门禁」；
4. 每条候选携带 span_ref/event_ref，违例候选被丢弃且有测试证明；
5. 规则同步先返回、模型异步增量（SSE）、模型失败不阻塞——三点可演示；
6. 接口路径/字段/枚举与 second-week/docs/08 逐字一致，差异记入 retro-log；
7. `check` 一条命令 lint + 测试全绿；后端核心模块（causal/rules/diagnosis）覆盖率各 ≥80%；
8. 3 类注入故障的 Top-3 命中数如实记录于 DEMO.md（含未命中）；注入点全部标注；
9. T2 表无写入路径；示例 Agent 不使用注解 API。

## 5. 关键决策记录（本阶段）

- 分支沿用已存在的 `feature/trace-runs`（不重建 release/feature 链，提测前补建 release/release_20260827）；
- Phase 0 PRD 跳过：第二周 docs/05 即 PRD，本 spec 只做第三周实现范围的裁定；
- SSE 通道实现为 FastAPI StreamingResponse；前端不支持时降级轮询 `GET /diagnosis`。
