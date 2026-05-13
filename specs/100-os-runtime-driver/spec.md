# 功能规范: 模块 6：自治 Runtime Driver

**功能分支**: `100-os-runtime-driver`  
**Issue 分支**: `feat/100-os-runtime-driver`  
**创建时间**: 2026-05-13  
**状态**: 草稿  
**输入**: Issue OPE-100「[Feature]模块 6：自治 Runtime Driver」与 `docs/基于张力场的Agent自驱动实现计划.md`

## 背景

Hermes 已有 `/goal` 跨轮 continuation、gateway/TUI 队列、profile-scoped config、SessionDB side tables，以及模块 0-5 的 os_runtime 领域对象、事件投影、上下文信号、生命状态、张力场、行动势能、SelfPrompt、OpenIntent 和 BoYueArbiter。当前模块 6 的职责是把这些能力串成可暂停、可审计、可预算限制的 Runtime Driver，而不是新增无限后台循环或重写 Agent 主循环。

## 目标

- 新增 `agent/os_runtime/driver.py`，提供 `OSRuntimeState` 与 `OSRuntimeDriver.evaluate_after_turn()`。
- 新增 `hermes_cli/os_runtime.py`，承载 CLI/slash command 解析和状态操作。
- 扩展 `/os_runtime status|passive|goal|pause|resume|clear|tick`。
- 在 gateway 和 TUI turn 边界接入 os_runtime continuation hook。
- 保持 `os_runtime.enabled=false` 时 `/goal` 与现有交互不变。
- 首版支持 `passive` 与 `assisted`，只允许状态记录、意图记录、低风险自然语言或草案 continuation。

## 非目标

- 不实现 `autonomous_low_risk` 的工具执行、world publish、permission ticket 或 receipt 执行链；这些属于后续模块 7。
- 不迁移 `/goal` 的存储格式为破坏性新格式；可复用或并行维护，但必须兼容现有 `/goal` 行为。
- 不把 continuation prompt 写入 system prompt。
- 不新增后台定时 daemon 或无用户可控停止条件的自治循环。
- 不默认发布 Linz World 正式事件。

## 需求理解

模块 6 应把每个 turn 结束后的 recent event 投影为张力场决策：读取事件、组装 context/signals、更新 life/tension、计算 action potential、编译 self prompt、生成 open intent、执行 arbitration，最后决定是否把一个普通 user-role continuation prompt 放回 CLI/gateway/TUI 队列。`passive` 模式只记录状态与 intent；`assisted` 模式可在低风险文档/草案任务中继续，但必须受预算、完成态、用户打断、pause/clear 和裁判拒绝约束。

## 用户场景与测试

### 用户故事 1 - 被动观察自治状态 (优先级: P1)

用户开启 `os_runtime` 的 passive 模式后，希望 Hermes 在每轮结束后记录张力、势能、intent 与 arbitration 摘要，但不自动发起下一轮。

**优先级原因**: 这是所有后续 assisted continuation 的审计和安全基础。  
**独立测试**: 在临时 profile 中启用 `os_runtime.enabled=true, mode=passive`，模拟一次 turn 后调用 driver，断言状态与事件写入，且 `should_continue=false`。

**验收场景**:

1. **给定** passive 模式与 recent event，**当** `evaluate_after_turn()` 运行，**那么** `OSRuntimeState` 保存 last tension/action/self_prompt/intent/arbitration 指针且不返回 continuation。
2. **给定** `os_runtime.enabled=false`，**当** 现有 `/goal` 运行，**那么** 行为与当前 `GoalManager` 保持一致。

### 用户故事 2 - 辅助模式自动继续低风险目标 (优先级: P1)

用户通过 `/os_runtime goal <text>` 设置低风险文档或草案目标后，希望 Hermes 在 assistant turn 结束后自动继续少量轮次，直到目标完成、预算耗尽、用户打断或裁判拒绝。

**优先级原因**: 这是本模块的核心交付价值。  
**独立测试**: 用 fake engine/adapters 构造 low-risk `AUTO_EXECUTE` 或 `REPORT_ONLY` arbitration，断言 assisted 模式产生普通 user-role continuation prompt，并正确增加 `turns_used`。

**验收场景**:

1. **给定** assisted 模式、未完成低风险文档目标与剩余预算，**当** turn 结束，**那么** driver 返回 continuation prompt，gateway/TUI 将其放入同一 session 队列。
2. **给定** 预算耗尽、完成、pause、clear、用户打断或裁判 `reject/require_approval/sandbox_execute`，**当** turn 结束，**那么** 不产生 continuation，并记录 `paused_reason` 或最终状态。

### 用户故事 3 - Gateway/TUI 可控队列集成 (优先级: P2)

gateway 或 TUI 用户希望 `/os_runtime` 与 `/goal` 一样可被暂停、清除、用户消息抢占，并且 Linz World 消息只触发 assisted continuation，不自动发布正式事件。

**优先级原因**: continuation 进入用户界面队列后才具备实际可用性，且必须避免后台自发外部副作用。  
**独立测试**: 在 gateway 和 TUI 测试中注入 pending os_runtime continuation，断言 pause/clear 会移除 synthetic continuation，但保留普通用户消息。

**验收场景**:

1. **给定** gateway/TUI 已排队 os_runtime continuation，**当** 用户发送 `/os_runtime pause` 或 `/os_runtime clear`，**那么** queued synthetic continuation 被取消。
2. **给定** Linz World 消息进入 assisted 模式，**当** driver 决策继续，**那么** 只生成自然语言/草案 continuation，不调用 publish。

### 边界情况

- `os_runtime.enabled=false`：不注册新 hook，不写 driver state，不影响 `/goal`。
- `mode=passive`：允许记录 intent/arbitration，但 `should_continue` 必须为 false。
- `mode=assisted`：只允许 `REPORT_ONLY`，或低风险、无工具、无 world publish 的 `AUTO_EXECUTE` continuation。
- `turns_used >= max_turns`：暂停并记录 `paused_reason=turn budget exhausted`。
- 用户打断：真实用户消息优先；queued synthetic continuation 必须可清理。
- 裁判拒绝或需要审批：停止 continuation，不降级为隐式执行。
- recent event 缺失或 engine 异常：fail closed，记录 runtime feedback，不继续。

## 需求

### 功能需求

- **FR-001**: 系统必须新增 `OSRuntimeState`，字段至少包含 `status`、`goal`、`turns_used`、`max_turns`、`last_tension_interpretation_id`、`last_action_potential_id`、`last_self_prompt_id`、`last_intent_id`、`last_arbitration`、`last_world_event_id`、`paused_reason`。
- **FR-002**: 系统必须提供 profile-scoped state persistence，不使用全局隐式状态。
- **FR-003**: `OSRuntimeDriver.evaluate_after_turn()` 必须串联 recent event、context/signals、life/tension、action potential、self prompt、intent、arbitration。
- **FR-004**: driver 必须返回结构化 decision，包含 `status`、`should_continue`、`continuation_prompt`、`reason`、`message` 与可追溯 id。
- **FR-005**: `passive` 模式必须只记录状态和 intent，不继续。
- **FR-006**: `assisted` 模式必须只允许低风险自然语言或草案 continuation，不允许工具执行、world publish 或其他外部副作用。
- **FR-007**: continuation prompt 必须作为普通 user-role 消息进入现有队列。
- **FR-008**: `/os_runtime` 命令必须支持 `status|passive|goal|pause|resume|clear|tick`。
- **FR-009**: gateway 和 TUI continuation hook 必须可被用户打断、暂停或清除。
- **FR-010**: `os_runtime.enabled=false` 时不得改变 `/goal` 原有行为。

### 关键实体

- **OSRuntimeState**: 每个 session/profile 的自治运行状态和最近证据指针。
- **OSRuntimeDecision**: driver 的 turn 后决策结果，用于 CLI/gateway/TUI 决定是否排队 continuation。
- **ContinuationPrompt**: 普通 user-role 文本，携带 goal、why_now、success/stop condition 的安全摘要。
- **Runtime Hook Context**: gateway/TUI/CLI 在 turn 边界传给 driver 的 session、source、final_response 和 latest event refs。

## 建议方案

沿用 `/goal` 的预算、pause/resume/clear 和队列模式，但把 judge 决策替换为 os_runtime 决策链。`hermes_cli/os_runtime.py` 负责命令层状态操作；`agent/os_runtime/driver.py` 负责纯领域决策和 state 持久化；gateway/TUI 在当前 `/goal` hook 附近新增 os_runtime hook，并用相同 FIFO/pending-input 机制排队普通 user-role continuation。实现时优先依赖现有 `OSRuntimeConfig`、`OSRuntimeEventRepository`、`ContextAdapter`、`SignalInterpreter`、`LifeStateSystem`、`TensionInterpreter`、`TensionFieldEngine`、`ActionPotentialEvaluator`、`SelfPromptCompiler`、`OpenIntentGenerator`、`BoYueArbiter`。

## 修改范围

- 新增：`agent/os_runtime/driver.py`
- 新增：`hermes_cli/os_runtime.py`
- 扩展：`gateway/run.py`
- 扩展：`tui_gateway/server.py`
- 可能扩展：`hermes_cli/commands.py`、`hermes_cli/main.py` 或现有 slash command catalog
- 新增测试：`tests/os_runtime/test_driver.py`
- 新增测试：`tests/hermes_cli/test_os_runtime_command.py`
- 新增测试：`tests/gateway/test_os_runtime_continuation.py`
- 新增测试：`tests/tui_gateway/test_os_runtime_continuation.py`

## 关键设计

- **Fail closed**: driver 任一关键环节异常、裁判非允许、配置关闭、模式不匹配都不继续。
- **状态与证据分离**: state 只保存最近 id 和摘要，详细事件继续落在 os_runtime event side table 或现有领域对象输出。
- **普通 user-role continuation**: gateway/TUI 不新增隐藏 channel，直接复用现有 FIFO，确保用户消息自然抢占。
- **模式门控**: passive 只记录；assisted 只允许低风险无外部副作用 continuation；autonomous_low_risk 只保留状态枚举和拒绝路径，不在本模块放开。
- **兼容 `/goal`**: 新 `/os_runtime` 不破坏 `GoalManager`，且 `os_runtime.enabled=false` 时现有 `/goal` hook 仍按当前逻辑运行。

## 风险与取舍

- `/goal` 与 `/os_runtime goal` 可能同时存在。首版建议互不自动迁移，并在命令输出中提示当前活动状态，避免双 loop。
- 现有模块 0-5 的部分输出可能未持久化完整 id。Builder 可先保存 driver state 的可追踪 metadata，并为缺失 id 生成稳定 runtime id。
- Gateway/TUI 队列清理需要精确识别 synthetic os_runtime continuation，避免误删普通用户消息。
- Linz World 事件进入 assisted continuation 后，必须默认不 publish，避免违反 fail-closed external side effects。

## 验收标准

- **AC-001**: `os_runtime.enabled=false` 时 `/goal` 原有行为不变。
- **AC-002**: passive 模式每轮可记录 state/intent/arbitration，但不会 continuation。
- **AC-003**: assisted 模式能在低风险文档任务中自动继续。
- **AC-004**: 预算耗尽、完成、用户打断、pause/clear、裁判拒绝时必须停止。
- **AC-005**: Linz World 消息可以触发 assisted continuation，但默认不自动发布正式事件。
- **AC-006**: gateway 和 TUI 的 continuation 队列可被用户打断、暂停或清除。
- **AC-007**: continuation prompt 是普通 user-role 消息，不改 system prompt。

## 测试计划

- `pytest tests/os_runtime/test_driver.py`
- `pytest tests/hermes_cli/test_os_runtime_command.py`
- `pytest tests/gateway/test_os_runtime_continuation.py`
- `pytest tests/tui_gateway/test_os_runtime_continuation.py`
- 回归：`pytest tests/gateway/test_goal_status_notice.py tests/tui_gateway/test_goal_command.py`

## 成功标准

### 可衡量的结果

- **SC-001**: 在 passive 模式下 100% driver 决策返回 `should_continue=false`。
- **SC-002**: 在 assisted 低风险 fixture 中，driver 在预算内生成 continuation，并在预算耗尽时暂停。
- **SC-003**: pause/clear 测试能证明 queued os_runtime continuation 被移除且普通用户消息保留。
- **SC-004**: `os_runtime.enabled=false` 的 `/goal` 回归测试全部通过。

## 假设

- 模块 0-5 的 os_runtime 领域对象和 engine API 可作为首版 driver 的直接依赖。
- CLI/gateway/TUI 均可复用 `/goal` 的 session_id 与 queue key 策略。
- 首版不需要真实 LLM 调用来测试 driver，可通过 fake engine/arbiter/adapters 做确定性测试。

## 后续交接说明

Builder Agent 应按 `tasks.md` 的故事顺序实现。先完成 driver state 与 passive 决策，再接 assisted continuation，最后接 gateway/TUI 队列清理。实现期间不要放开工具执行或 world publish；任何外部副作用都应保留到模块 7。
