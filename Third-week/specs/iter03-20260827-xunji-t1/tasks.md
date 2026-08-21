# TASKS：可执行任务列表（第三周）

> 上游：[plan.md](plan.md) · 执行方式：TDD（判定逻辑先写测试），每任务完成即提交
> 状态标记：[ ] 待办 · [x] 完成 · [!] 受阻（记 retro-log）

## M1 脚手架与数据层

- [ ] T01 仓库脚手架：根 package.json（demo/check 脚本占位）、server/requirements.txt（锁版本）、.gitignore、venv 说明 — `chore(scaffold)`
- [ ] T02 建表 SQL（观测侧 4 表 + 业务侧 8 表，T2 表标注无写入路径；ClickHouse/PG 目标形态注释）+ db.py 连接与迁移 + 测试 — `feat(db)`
- [ ] T03 枚举字典 enums.py（execution_status/quality_verdict/failure_type/evidence_grade/review_result/gate_*，与 docs/08 逐字一致）+ 测试 — `feat(db)`

## M2 诊断流水线（后端核心，覆盖率≥80%/模块）

- [ ] T04 ingestion：`POST /v1/traces` 契约模型（pydantic）、标准化入库、断链/缺字段降级 + 测试（正常/断链/重复 span/缺字段） — `feat(ingestion)`
- [ ] T05 causal：父子边 + 时序 + 数据流启发式边（输出内容 ≥N 字符片段出现在下游输入；confidence 标记）+ 因果路径查询 + 测试（含断链图） — `feat(causal)`
- [ ] T06 rules：声明式规则配置（YAML）+ 引擎；3 类规则各自测试（命中/不命中/边界） — `feat(rules)`
- [ ] T07 diffgen：基线选择（同 agent+版本+成功）、逐步骤对齐比较、首分歧候选 + 测试（有基线/无基线/不兼容基线） — `feat(diff)`
- [ ] T08 evaluator：接口 + Mock（启发式候选与反证、可配延迟/超时）+ ClaudeCodeEvaluator（子进程，输出结构化校验）+ 测试（Mock 路径、超时路径、违例输出被拒） — `feat(evaluator)`
- [ ] T09 diagnosis：聚合去重、证据加权排序、Top-3 截断、证据等级映射、无证据丢弃 + 测试（丢弃证明、排序稳定性） — `feat(diagnosis)`
- [ ] T10 clustering：症状签名计算 + 建簇/归簇/signature_version + 测试 — `feat(clustering)`

## M3 闭环 API

- [ ] T11 查询 API：traces 列表/详情、incidents 列表、diagnosis 快照 + SSE 增量 + 测试 — `feat(api)`
- [ ] T12 review：三态提交、If-Match 409、correct_cause_ref 人工指认 + 测试（并发冲突） — `feat(review)`
- [ ] T13 regression + gate：confirmed 转用例（输入引用+不变量）、gate-run 重放 pass/warn/block + gate CLI + 测试 — `feat(gate)`

## M4 接入层与示例 Agent

- [ ] T14 sdk：stream-json 解析器（宽容未知事件）、Span 树重建、HTTP 上报、T2 注解 API 空签名 + 测试（真实事件样本） — `feat(sdk)`
- [ ] T15 sdk CLI：`xunji run -- claude -p ...`（子进程+旁路解析+原始流存档）、`xunji connect`（写 hooks 配置）+ 测试 — `feat(sdk)`
- [ ] T16 agent：对账工作负载（任务提示词固定文件）、4 个工具脚本（fetch_billing/fetch_payments/reconcile/validate_report）、注入开关（仅工具/数据层）+ 工具单测 — `feat(agent)`

## M5 数据与 Demo

- [ ] T17 录制脚本 record_fixtures.py：真实运行 1 正常 + 3 注入，转存 fixtures/；离线态回放 loader + 测试 — `feat(fixtures)`
- [ ] T18 E2E 冒烟（API 级）：离线态全流程断言 — `test(e2e)`
- [ ] T19 demo 脚本：demo（起后端+前端）、demo-run（真实态）、demo-offline、check — `chore(demo)`

## M6 前端五页

- [ ] T20 web 脚手架：Vite+React+TS、axios 实例、react-query、路由、布局 — `feat(web)`
- [ ] T21 运行记录页 + Trace 详情（含设为基线）+ 测试 — `feat(web)`
- [ ] T22 事故列表页（簇 + 事故）+ 测试 — `feat(web)`
- [ ] T23 诊断工作台（症状区/候选区/证据卡片/SSE 增量渲染）+ 测试 — `feat(web)`
- [ ] T24 Diff 视图（字段级表格对比保底）+ 复核操作（三态 + 冲突提示）+ 测试 — `feat(web)`
- [ ] T25 回归与门禁页 + 测试 — `feat(web)`

## M7 文档与复盘

- [ ] T26 api/openapi.yaml（11 接口，deferred 标注） — `docs(api)`
- [ ] T27 docs/01 技术方案设计、02 接口与数据设计 — `docs`
- [ ] T28 docs/03 代码结构说明、04 测试报告（真实覆盖率数据） — `docs`
- [ ] T29 DEMO.md（演示脚本 + 命中实录 + 注入点标注）+ README 评分入口 — `docs`
- [ ] T30 docs/05 技术复盘（retro-log 汇总 + 反哺清单，T1 收窄第一条） — `docs(retro)`

## 全程规则

- retro-log.md 随做随记（设计说不清/做不了/有矛盾之处）；
- 每个 P0 判定逻辑的测试先于实现（tdd-workflow）；
- 提交遵循 git-standards：Conventional Commits + AI trailer，不推 main。
