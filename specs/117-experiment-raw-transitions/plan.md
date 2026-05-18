# 实施计划: 实验脚本：共博自制框架阶段验证与 raw transitions 采集

**分支**: `feat/117-experiment-raw-transitions` | **日期**: 2026-05-18 | **规范**: `specs/117-experiment-raw-transitions/spec.md`  
**输入**: Issue OPE-117 与 `docs/共博自制框架实验准备.md`

## 摘要

新增 `experiment/` 下的可重复实验套件，按 P0-P5 执行人格种子、事件脚本、组合流、持续流和多元神交互验证。实现以 mock backend 为 CI/本地结构验证基础，以 runtime backend 作为真实 os_runtime/Linz World 查询边界；输出统一 transition schema 到 `experiment/results/<run_id>/`，包含 JSONL 原始记录、CSV/JSON 汇总、异常判定和 evidence refs。

## 技术背景

**语言/版本**: Python 3.11+  
**主要依赖**: Python 标准库、现有 `agent.os_runtime` domain/driver/evidence、现有 `agent.linz_world` redaction/event/receipt 相关模块  
**存储**: 文件输出到 `experiment/results/<run_id>/`；测试使用临时目录  
**测试**: pytest  
**目标平台**: 本地 CLI、CI、可选真实 Linz World runtime 环境  
**项目类型**: Python CLI/实验工具  
**性能目标**: mock `--phase all` 在普通开发机上应在数秒级完成；结果文件按 JSONL streaming 写入，避免把全部 transition 强制常驻内存  
**约束条件**: 不修改核心 runtime 决策语义；真实模式 fail closed；普通输出禁止明文秘密  
**规模/范围**: 首版覆盖 6 个 seed、P0-P5 至少 1+10+6+5+5+6 组事件/场景，支持后续扩展事件库

## 章程检查

- **Profile-Scoped State**: 通过。实验结果写入显式 run directory；真实 runtime 读取必须复用 profile-scoped runtime/evidence 状态，不写隐式全局状态。
- **Native Surfaces Before Optional Skills**: 通过。实验工具使用 repo 内 Python package 和现有 OS Runtime/Linz World 原生模块，不依赖 optional skill。
- **Fail-Closed External Side Effects**: 通过。默认 mock；runtime 模式必须显式开启并完成 capability check，缺登录/权限/查询/evidence 能力时停止。
- **Privacy and Audit Separation**: 通过。结果只保存 redacted summary、hash、content_ref、audit_ref、evidence refs；不保存 token、私钥或 restricted raw payload。
- **Testable Incremental Delivery**: 通过。任务按 seed/event/scenario、mock backend、结果 schema、P4/P5、runtime backend 分层，每层有独立 pytest。

## 项目结构

### 文档(此功能)

```
specs/117-experiment-raw-transitions/
├── spec.md
├── plan.md
├── data-model.md
├── quickstart.md
└── tasks.md
```

### 源代码(仓库根目录)

```
experiment/
├── __init__.py
├── run.py
├── config.py
├── seeds/
│   ├── __init__.py
│   └── default_seeds.json
├── events/
│   ├── __init__.py
│   └── event_library.json
├── scenarios/
│   ├── __init__.py
│   └── registry.py
├── runtime/
│   ├── __init__.py
│   ├── base.py
│   ├── mock_backend.py
│   └── os_runtime_backend.py
├── collectors/
│   ├── __init__.py
│   ├── transitions.py
│   └── mappings.py
├── reporting/
│   ├── __init__.py
│   ├── writer.py
│   └── summaries.py
└── results/
    └── .gitkeep

tests/
└── experiment/
    ├── test_event_library.py
    ├── test_seed_library.py
    ├── test_scenario_registry.py
    ├── test_mock_runtime_transitions.py
    ├── test_result_writer.py
    └── test_redaction.py
```

**结构决策**: 选择仓库根目录 `experiment/` 单一 Python package，符合 issue 范围要求；核心 runtime 只被导入或通过薄查询 adapter 读取，不把实验数据放入 `docs/` 或 `agent/os_runtime/`。

## 实施策略

1. 建立 seed/event/scenario registry：先把文档第 5、8-12 节转成结构化数据，并补齐 P0/P3/P4/P5 所需衍生事件。
2. 实现统一 schema 和 mock backend：让 P0-P5 在无外部服务时生成稳定 transitions，先满足 CI 和输出格式。
3. 实现 writer 和 redaction：输出 JSONL/CSV/JSON，保证敏感字段只以摘要/hash/ref 出现。
4. 实现 runtime backend：显式 capability check 后调用或读取 os_runtime/Linz World 状态；能力不足时返回 blocked diagnostics。
5. 补齐 P4/P5 专项汇总：阈值、偏好、记忆权重、关系变化和多 seed 差异比较。

## 关键设计

- **ExperimentRunConfig**: CLI 参数归一化对象，包含 phase、mode、repeat、run_id、results_root、seed filter、runtime profile。
- **RuntimeBackend 协议**: `prepare(seed)`, `apply_event(event, context)`, `tick(duration)`, `snapshot()`, `capabilities()`；mock 和真实 backend 共用返回 schema。
- **TransitionCollector**: 负责把 backend 返回的模块对象映射成分析字段，不把 runtime 内部 dataclass 直接写出。
- **FieldMapping**: 将现有 `LifeState.energy/fatigue/curiosity/restraint`、`TensionSet.core_tensions`、`ActionPotential.value_potential/...` 映射到文档要求的 T/AP/Life 字段；缺字段写 diagnostics。
- **ResultWriter**: streaming 写 `events.jsonl` 与 `transitions.jsonl`，结束时写 `summary.json`、`summary.csv`、`anomalies.json`。
- **Redaction**: 优先复用 `agent.linz_world.redaction.redact_value` 和 `agent.os_runtime.adapters.events.bounded_summary/stable_hash`；不可导入时提供同等本地 fallback。

## Runtime Backend 设计

### Mock Backend

- 使用 seed 的初始生命状态、张力权重和行动阈值初始化状态。
- 基于 event/scenario metadata 中的 expected effects 生成确定性 delta。
- 生成完整 raw transition chain，保证所有输出字段可测。
- 不模拟真实智能，只验证机制方向、边界、排序和输出结构。

### OS Runtime Backend

- 启动前执行 capability check：配置启用、profile/session 可用、Linz World 登录/权限、事件注入或读取能力、evidence repository 可用。
- 注入事件时必须使用正式包络；无法注入时只允许 report blocked，不允许降级成 mock 并标记为 runtime。
- 读取 `LifeState`、`TensionSet`、`ActionPotential`、`SelfPrompt`、`OpenIntent`、`ArbitrationResult`、`EvidencePackage` 或等价快照。
- 只读 adapter 不得改变 runtime 决策语义；任何外部 publish/action 必须由已有 arbitration/permission 约束。

## 输出文件

- `manifest.json`: run_id、phase、mode、commit、开始/结束时间、capability diagnostics、配置摘要。
- `events.jsonl`: redacted 原始事件包络、seed、scenario、repeat/tick 信息。
- `transitions.jsonl`: 每个事件的 before/after/tick state、raw chain、delta、action、judgement、evidence refs。
- `summary.json`: 按阶段/场景/seed 聚合的成功、异常、字段覆盖率和统计。
- `summary.csv`: 便于 notebook/表格分析的扁平汇总。
- `anomalies.json`: 方向错误、爆表、卡死、缺字段、敏感字段泄漏、runtime blocked 等异常。

## 风险与取舍

- **字段命名不一致**: 通过 `collectors/mappings.py` 做稳定输出映射，而不是要求 runtime 改名。
- **真实 runtime 依赖未就绪**: mock backend 仍可交付结构验证；runtime backend 明确 blocked diagnostics。
- **P5 并行状态复杂**: 首版可用准并行事件调度，每个 seed 独立 state；真实并行留给 runtime 能力。
- **输出量增加**: 使用 JSONL streaming 和 bounded summary，避免大 payload 常驻内存或写入完整敏感内容。

## 复杂度跟踪

无章程违规。新增 package 和 backend 抽象是为同时满足 mock CI 与真实 runtime 两种模式；比把逻辑硬编码到单脚本更可测、可扩展。
