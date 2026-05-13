# 实施计划: 模块 6.5 常驻 Autonomous Runtime Loop

**分支**: `feat/111-autonomous-runtime-loop` | **日期**: 2026-05-13 | **规范**: [spec.md](./spec.md)
**输入**: `specs/111-autonomous-runtime-loop/spec.md`

## 摘要

在现有 Linz World 原生身份、`os_runtime` 模块 1-6 引擎和 assisted continuation 之上，新增常驻 autonomous 编排层。该层负责配置门、状态、scheduler、world event wake、turn hook、SelfPrompt ephemeral 注入和用户观测命令；默认保持低风险、可停止、可审计，不执行真实外部副作用。

## 技术背景

**语言/版本**: Python 3.x，沿用仓库现有运行环境
**主要依赖**: 复用 Hermes 现有模块；不新增必需第三方依赖
**存储**: profile-aware SessionDB side tables / OSRuntimeEventRepository / state meta 适配层
**测试**: pytest
**目标平台**: Hermes CLI、TUI、gateway/runtime
**项目类型**: Python CLI/runtime/gateway 应用
**性能目标**: turn hook 失败不阻塞主对话；scheduler 无无界后台循环；事件重复不重复 wake
**约束条件**: 默认 no external side effects；prompt 注入仅限 ephemeral user context；所有路径 profile-aware
**规模/范围**: 单 profile/session 常驻 runtime 状态；为后续多会话治理留出状态字段但不实现多租户平台化

## 章程检查

- **Profile-Scoped State**: autonomous state、inbox、wake evidence 必须落在当前 Hermes profile/session 作用域，使用现有 profile-aware helper。
- **Native Surfaces Before Optional Skills**: CLI/gateway/runtime 原生支持，不依赖可选 skill。
- **Fail-Closed External Side Effects**: 默认禁止工具副作用和 world publish；显式开启也必须经过 arbiter/policy/catalog/auth/STVB/evidence。
- **Privacy and Audit Separation**: SelfPrompt 注入只包含摘要和 evidence refs，不包含 token/raw payload/restricted audit content。
- **Testable Incremental Delivery**: P1 先交付配置、状态、scheduler、turn hook 和默认低风险 loop；P2 再补 world event wake 和 CLI 可观测面。

## 项目结构

### 文档(此功能)

```text
specs/111-autonomous-runtime-loop/
├── spec.md
├── plan.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── os-runtime-autonomous-cli.md
└── tasks.md
```

### 源代码(仓库根目录)

```text
agent/os_runtime/
├── config.py
├── autonomous_loop.py
├── autonomous_state.py
├── autonomous_scheduler.py
├── world_event_waker.py
├── autonomous_inbox.py
├── turn_hooks.py
├── self_prompt_injector.py
└── adapters/
    └── runtime_queue.py

hermes_cli/
└── os_runtime_autonomous.py

tests/os_runtime/
├── test_autonomous_loop.py
├── test_turn_hooks.py
└── test_world_event_waker.py

tests/gateway/
└── test_os_runtime_autonomous_loop.py
```

**结构决策**: 保持 `os_runtime` 领域层和 adapter 分离。新增文件只做 autonomous 编排，不替代现有 context、memory、tools、SessionDB 或 Linz World adapter。

## 技术方案

### 1. 配置与状态

- 扩展 `OSRuntimeConfig`，增加 `AutonomousRuntimeConfig` dataclass。
- 默认值保持安全：`enabled=false`、`apply_to_all_turns=false`、`inject_self_prompt=false`、`allow_tool_execution=false`、`allow_world_publish=false`。
- `AutonomousRuntimeState` 独立于模块 6 `OSRuntimeState`，避免 `/goal` continuation 状态和常驻 loop 状态互相覆盖。
- 状态字段必须覆盖 spec 中 FR-002，并支持 `to_dict/from_dict` 或 JSON round-trip。

### 2. Scheduler 与 runtime queue

- `AutonomousScheduler` 负责 start/tick/pause/resume/stop 和预算判断。
- `adapters/runtime_queue.py` 负责 profile-aware state/inbox persistence，优先复用现有 SessionDB/OSRuntimeEventRepository 能力。
- 所有 wake 前必须检查：stopped/paused、cooldown_until、max_wakes_per_hour、max_turns_per_wake、fatigue/restraint。
- scheduler 不创建无预算无限循环；后台启动只注册受控 tick/idle 逻辑。

### 3. TurnTensionHook

- `before_turn()` 输入普通 message、Linz MessageEvent 或 tick ref，输出包含 projection result、最新状态、可选 SelfPrompt injection、diagnostics。
- `after_turn()` 输入 assistant response/tool result/runtime feedback，写回 projection/evidence 并更新状态。
- `apply_to_all_turns=false` 时不影响普通对话。
- hook 异常对普通对话 fail-open；外部副作用没有有效 arbitration/evidence 时 fail-closed。

### 4. SelfPromptInjector

- 复用现有 `SelfPromptCompiler` 结构，但注入层负责脱敏、缩减和 placement。
- 只修改当前轮 user message metadata 或等价 ephemeral user context。
- 明确禁止修改 system message、stable prompt cache prefix、长期 profile prompt。
- 注入字段白名单：state/tension/action 摘要、open_space、target_direction、constraints、evidence_refs。

### 5. AutonomousRuntimeLoop

- `run_once(wake_reason, event_ref=None)` 读取 inbox 或 event_ref，构建 context/signals/life/tension/action/self_prompt/intent/arbitration。
- 无用户 goal 时，允许 intent generator 使用事件、生命状态和张力生成低风险 intent。
- 默认只允许 `report_only`、草案、内部反思、evidence package 或 `require_approval`。
- 每次 wake 写入 evidence：wake reason、event id、LifeState、top tensions、ActionPotential、OpenIntent、ArbitrationResult、action summary、stop reason。

### 6. WorldEventWaker

- 只订阅/消费已由 Linz World gateway adapter 持久化的事件引用。
- 基于 event_id、sequence_key 或 payload hash 去重。
- 入队后触发 scheduler wake；重复事件返回 skipped，不重复 wake。

### 7. CLI 与 gateway/runtime 接入

- `hermes_cli/os_runtime_autonomous.py` 提供 `status|pause|resume|stop|tick|inbox|events|intents` 命令服务。
- gateway/runtime 启动 hook 按 `start_with_gateway` 或 `start_on_agent_load` 启动 scheduler。
- CLI/TUI/gateway turn 边界接入 `TurnTensionHook`，但必须受配置门控制。

## 数据与契约

- 数据模型见 [data-model.md](./data-model.md)。
- CLI contract 见 [contracts/os-runtime-autonomous-cli.md](./contracts/os-runtime-autonomous-cli.md)。
- 不新增 HTTP API contract；本模块的外部接口是 Python service/CLI/gateway hook。

## 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| autonomous loop 自激 | cooldown、wake budget、max turns、pause/stop、fatigue/restraint、dedupe |
| 普通聊天回归 | 默认关闭、apply_to_all_turns 门控、hook fail-open、gateway/CLI 回归测试 |
| Prompt 污染 | SelfPromptInjector 只写 ephemeral user context，测试 system prompt 和 cache 不变 |
| 敏感信息泄露 | 注入白名单、redaction、负向测试 token/raw payload/audit content |
| 外部副作用越权 | 默认禁止；显式允许也必须走 arbiter/policy/catalog/auth/STVB/evidence |
| 状态不可诊断 | status/inbox/events/intents 命令和每次 wake evidence |

## 复杂度跟踪

| 违规 | 为什么需要 | 拒绝更简单替代方案的原因 |
| --- | --- | --- |
| 新增 scheduler/loop/inbox 编排层 | 模块 6 只处理 assisted continuation，无法表达常驻 wake、预算和 inbox | 直接扩展 `/goal` state 会混淆用户显式目标与无 goal autonomous wake |
| 新增 turn hook/injector | 普通对话需要进入张力观测并可选注入 ephemeral SelfPrompt | 只在 driver after_turn 处理无法覆盖 before_turn SelfPrompt 和 fail-open/fail-closed 边界 |

## 验收与测试映射

- SC-001/SC-008: `tests/os_runtime/test_autonomous_loop.py` 和 `tests/gateway/test_os_runtime_autonomous_loop.py`
- SC-002/SC-004/SC-010: `tests/os_runtime/test_turn_hooks.py`、现有 gateway disabled config 回归
- SC-003: `tests/os_runtime/test_turn_hooks.py` 中 SelfPromptInjector/system prompt 不变断言
- SC-005/SC-006/SC-007/SC-009: `tests/os_runtime/test_world_event_waker.py` 与 autonomous loop fake chain 测试

## 后续交接

Builder Agent 应先实现数据模型、配置和纯单元测试，再接入 gateway/CLI。任何需要新增持久化 schema 的地方都必须保持 profile-aware，并在测试中使用临时 HERMES_HOME 或 fake repository。
