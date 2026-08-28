# 寻迹（第三周）：T1 通用流诊断最小闭环 — 工程实现交付

评分从本文件开始。本周把第二周的产品设计落成**可运行、可测试、可复盘**的工程实现：
真实 Claude Code CLI 驱动的示例 Agent 现场产生 Trace，规则 + Diff + 模型三路诊断现场计算，
复核 → 回归用例 → 发布门禁全闭环。**代码库无任何预写诊断结论。**

## 快速启动

```bash
cd Third-week
python -m venv .venv && .venv/Scripts/pip install -r server/requirements.txt
cd web && npm install && cd ..
npm run demo          # 后端 :8756 + 前端 :5173
npm run demo-run      # 真实态：本机 claude -p 现场执行（需已登录 CLI）
npm run demo-offline  # 离线态：真实录制 fixtures 回放（无网可跑）
npm run check         # ruff + 80 项后端测试 + 覆盖率门槛
```

逐步演示脚本（点什么、看到什么、截图）见 [DEMO.md](DEMO.md)。

## 六项任务索引

| # | 任务 | 交付物 | 检查点 | 状态 |
|---|---|---|---|---|
| 1 | 技术方案设计 | [docs/01](docs/01-技术方案设计.md) · [specs/](specs/iter03-20260827-xunji-t1/) | 实施架构、选型表、目标→Demo 映射、不做项 | 完成 |
| 2 | 接口/数据设计 | [docs/02](docs/02-接口与数据设计.md) · [api/openapi.yaml](api/openapi.yaml) · [schema.sql](server/xunji/schema.sql) | 11 接口字段级契约、12+2 表、枚举对照 | 完成 |
| 3 | 核心功能编码 | [server/](server/) [sdk/](sdk/) [agent/](agent/) [web/](web/) · [docs/03](docs/03-代码结构说明.md) | 接入层→因果→规则→Diff→评估→聚合→复核→门禁→五页前端 | 完成 |
| 4 | 代码质量 | [docs/04](docs/04-测试报告.md) | 84 项测试全绿；后端覆盖率 94%（核心模块 94–100%）；ruff/tsc 零违例 | 完成 |
| 5 | 可运行 Demo | [DEMO.md](DEMO.md) · [e2e/](e2e/) · [fixtures/](fixtures/) | 双态一键运行；E2E 冒烟闭环；命中实录 2/3（含未命中，如实记录） | 完成 |
| 6 | 技术复盘 | [docs/05](docs/05-技术复盘.md) · [retro-log.md](retro-log.md) | 7 项设计问题、8 条反哺清单（T1 收窄居首）、指标可测性 | 完成 |

## 三条硬证据（评分快捷路径）

1. **真实性**：`fixtures/raw/*.jsonl` 是 claude -p 的原始事件流存档；
   `fixtures/*.contract.json` 由它转换（附脚本可重放）；
2. **诊断能力**：`.venv/Scripts/python -m pytest e2e -q` —— 5 步断言在真实录制数据上
   走通「入库→事故→诊断→复核→转用例→门禁」，静默故障定位到过期取数步骤；
3. **诚实性**：DEMO.md §5 如实记录 bad-tool-args 未进 Top-3（2/3），成因与聚合策略
   修改建议在 docs/05 问题 3。

## 范围声明

本周实现范围 = 提示词「T1/T2 分级裁定」的 T1 全集：只依赖任何 Agent 框架都能自动采集的
通用事件流。state/handoff/memory 语义增强（T2）只保留表结构与注解 API 签名，
无写入路径（有测试证明）。与第二周设计的全部出入见 docs/05 反哺清单，第四周统一回改。
