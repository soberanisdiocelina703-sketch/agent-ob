# retro-log：实现问题流水（随做随记）

> 格式：日期 | 位置 | 问题 | 临时决定
> 复盘时汇总进 docs/05-技术复盘.md；「设计问题」与「本周简化」分开定性。

- 2026-08-20 | 范围 | state/handoff/memory 语义事件非行业通用约定（OTel GenAI semconv 仅覆盖模型/工具调用级），Claude Code 通用流无法自动获得 | 裁定 T1/T2 分级，T2 只留定义；反哺清单第一条（决策记录见提示词「本周范围裁定」）
- 2026-08-20 | 分支 | git-standards 要求 release→feature 链，但 feature/trace-runs 已存在且为当前分支 | 沿用现分支，提测前补建 release/release_20260827；未新建 worktree（单人开发）
- 2026-08-20 | SDD | Phase 0 PRD 跳过：second-week/docs/05 即 PRD，重写为浪费 | 走「研发主导/快速迭代」路由，spec.md 只裁定第三周实现范围
- 2026-08-20 | schema | docs/08 §8.3 的 regression_cases.suite_id 引用了未定义的 suites 表 | 本地补建最小 suites 表；反哺：docs/08 需补表定义
- 2026-08-20 | schema | docs/08 命名了 incident_status/evidence_grade 字段但未枚举取值（口径含糊） | 本地定义见 enums.py 注释；反哺：PRD/技术方案需锁枚举
