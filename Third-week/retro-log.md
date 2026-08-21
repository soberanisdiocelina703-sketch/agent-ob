# retro-log：实现问题流水（随做随记）

> 格式：日期 | 位置 | 问题 | 临时决定
> 复盘时汇总进 docs/05-技术复盘.md；「设计问题」与「本周简化」分开定性。

- 2026-08-20 | 范围 | state/handoff/memory 语义事件非行业通用约定（OTel GenAI semconv 仅覆盖模型/工具调用级），Claude Code 通用流无法自动获得 | 裁定 T1/T2 分级，T2 只留定义；反哺清单第一条（决策记录见提示词「本周范围裁定」）
- 2026-08-20 | 分支 | git-standards 要求 release→feature 链，但 feature/trace-runs 已存在且为当前分支 | 沿用现分支，提测前补建 release/release_20260827；未新建 worktree（单人开发）
- 2026-08-20 | SDD | Phase 0 PRD 跳过：second-week/docs/05 即 PRD，重写为浪费 | 走「研发主导/快速迭代」路由，spec.md 只裁定第三周实现范围
- 2026-08-20 | schema | docs/08 §8.3 的 regression_cases.suite_id 引用了未定义的 suites 表 | 本地补建最小 suites 表；反哺：docs/08 需补表定义
- 2026-08-20 | schema | docs/08 命名了 incident_status/evidence_grade 字段但未枚举取值（口径含糊） | 本地定义见 enums.py 注释；反哺：PRD/技术方案需锁枚举
- 2026-08-21 | 接入 | Windows 下 claude 为 .CMD 垫片：多行 prompt 走 argv 被折断（0 事件）；`shutil.which` 才能定位 | xunji run 增加 --stdin-file，prompt 一律走 stdin；反哺：接入文档需写明平台差异
- 2026-08-21 | 接入 | headless `claude -p --allowedTools Bash` 仍被权限墙拦截（"requires approval"），Agent 被拒后真实改变策略（fetch 失败 4 次后转用 Read 翻文件）——真实行为形态是 fixtures 永远造不出的 | 改用 --permission-mode bypassPermissions（受控演示目录）；这条被拒轨迹保留为「异常形态样本」；反哺：接入体检应检测权限配置
- 2026-08-21 | 接入 | bypassPermissions 被会话安全分类器正确拒绝（全局绕过越权）；probe 发现 Windows 下嵌套 Claude Code 的终端工具名是 PowerShell 而非 Bash，窄授权规则须写 PowerShell(python:*) | 双规则并列 PowerShell/Bash；反哺：接入文档与体检必须覆盖「工具名随平台变化」
- 2026-08-21 | diffgen | 真实录制暴露：assistant 文本每次运行必然漂移，Diff 把 llm_call 当首分歧（伪根因） | 对照排除 llm_call/planning 步骤，加回归测试；反哺：docs/08 Diff 设计需写明步骤类型过滤
- 2026-08-21 | gate | docs/08 §8.2 gate-run 未定义评估范围（只说重放回归集）；E2E 实测「只看 release 最新一次运行」会漏掉更早运行中的复现 | 改为评估该 release 全部运行（上限 20），任一违例即不过；反哺：门禁 PRD 需锁定评估窗口口径
