# 功能规范: 模块 6.5 常驻 Autonomous Runtime Loop

**功能分支**: `feat/111-autonomous-runtime-loop`
**Spec-Kit feature key**: `111-autonomous-runtime-loop`
**创建时间**: 2026-05-13
**状态**: 草稿
**输入**: Issue OPE-111 与 `docs/基于张力场的Agent自驱动实现计划.md`

## 背景

Hermes 已具备 Linz World 原生身份、世界事件、`os_runtime` 事件投影、生命状态、张力场、行动势能、SelfPrompt、OpenIntent、BoYueArbiter 和模块 6 turn-boundary assisted continuation 的基础。本模块补齐“常驻元神自驱动”入口：Agent/gateway 启动后可由世界事件、tick、内部反馈和生命状态自动 wake；普通 CLI/TUI/gateway 对话也可进入张力场观测与治理，而不要求用户每次输入 `/os_runtime goal`。

## 目标

- 启用 `os_runtime.mode=autonomous_low_risk` 与 `os_runtime.autonomous.enabled=true` 后，Agent/gateway 启动即进入 idle/sleeping 常驻状态。
- 在 `apply_to_all_turns=true` 时，普通用户消息、Linz World MessageEvent、scheduled tick、assistant response、tool result 和 runtime feedback 都投影为 `os_runtime` event，并更新 LifeState/TensionSet/ActionPotential/evidence。
- 在 `inject_self_prompt=true` 时，只向当前轮 user context 注入 ephemeral SelfPrompt，不修改稳定 system prompt 或 prompt cache 前缀。
- 世界事件和 tick 可唤醒 autonomous loop，在无用户 goal 时生成低风险自主 intent，并默认只产生 report、草案、内部反思、evidence package 或审批请求。
- 提供用户可观测命令：`status`、`pause`、`resume`、`stop`、`tick`、`inbox`、`events`、`intents`。

## 非目标

- 不实现默认真实工具副作用、自动外部消息发送、自动 `linz_publish`、删除、支付、权限变更或经济结算。
- 不重写 `AIAgent` 主循环、gateway 主循环、SessionDB、MemoryManager、tool registry、Linz World gateway adapter 或模块 1-6 引擎。
- 不引入新的外部 scheduler/message bus 依赖。
- 不把 SelfPrompt 或张力状态写入长期 system prompt、prompt cache 前缀或普通日志明文。
- 不把模块 -1 的 Linz World original spirit 注册逻辑复制到本模块。

## 需求理解

模块 6.5 交付 Level 2/3 入口：

- Level 2 `tension-observed`：全 turn 事件投影、状态更新和 evidence，不改变模型输入。
- Level 3 `tension-driven`：在配置允许时注入 ephemeral SelfPrompt，并通过张力场影响行动深度、继续/休眠、审批和外部副作用阻断。

默认行为必须保守：`os_runtime.enabled=false` 或 `autonomous.enabled=false` 时，现有 CLI/TUI/gateway/`/goal` 行为不变；hook 失败时普通对话 fail-open，外部副作用 fail-closed。

## 用户场景与测试

### 用户故事 1 - 常驻低风险自治启动 (优先级: P1)

作为启用了 autonomous runtime 的 Hermes 用户，我希望 Agent/gateway 启动后自动进入可观测的 idle/sleeping 常驻状态，而不需要先输入 `/os_runtime goal`。

**优先级原因**: 这是“常驻元神自驱动”的最低可用入口。

**独立测试**: 使用低风险配置启动 runtime/gateway，断言 AutonomousScheduler 初始化状态、预算、cooldown 和状态查询输出。

**验收场景**:

1. **给定** `os_runtime.enabled=true`、`mode=autonomous_low_risk`、`autonomous.enabled=true`，**当** Agent/gateway 启动，**那么** autonomous state 进入 `idle` 或 `sleeping`，且不需要 `/os_runtime goal`。
2. **给定** 已 pause 的 autonomous runtime，**当** 用户执行 resume，**那么** scheduler 恢复 idle/sleeping，预算和 cooldown 仍生效。

### 用户故事 2 - 全 turn 张力观测与 SelfPrompt 注入 (优先级: P1)

作为普通 CLI/TUI/gateway 用户，我希望普通对话在配置开启时进入张力场观测；当允许注入时，当前轮可收到 ephemeral SelfPrompt，但长期系统提示不被污染。

**优先级原因**: 这是 Level 2/3 治理入口，直接影响现有对话兼容性和安全边界。

**独立测试**: 直接调用 `TurnTensionHook.before_turn()` 与 `after_turn()`，覆盖 `inject_self_prompt=true/false`、异常 fail-open、system prompt 不变和 evidence 写入。

**验收场景**:

1. **给定** `apply_to_all_turns=true`、`inject_self_prompt=false`，**当** 用户发送普通消息，**那么** 写入 `human_request` 事件并更新状态，但模型输入不变。
2. **给定** `inject_self_prompt=true`，**当** before_turn 生成 SelfPrompt，**那么** 只在当前 user message metadata 或等价 ephemeral user context 注入摘要、约束和 evidence refs。
3. **给定** hook 内部异常，**当** 普通对话继续，**那么** 主对话不崩溃；若本轮涉及外部副作用，则该副作用必须被阻断或要求审批。

### 用户故事 3 - 世界事件和 tick 唤醒 (优先级: P2)

作为 Linz World original spirit，我希望持久化且去重后的世界事件或 scheduler tick 能唤醒 autonomous loop，并完成张力场链路，默认只生成低风险结果。

**优先级原因**: 这是从 assisted continuation 到真正 autonomous wake 的核心增量。

**独立测试**: 用 fake Linz MessageEvent 和 fake clock 驱动 `WorldEventWaker`、`AutonomousInbox`、`AutonomousRuntimeLoop.run_once()`，断言 dedupe、预算、intent、arbitration 和 evidence。

**验收场景**:

1. **给定** 一条已持久化的合法 Linz World 事件，**当** WorldEventWaker 处理，**那么** 事件只入队一次并触发 `wake(reason=world_event)`。
2. **给定** 没有用户 goal，**当** loop 因 world event 或 tick 运行，**那么** 仍执行 context -> signals -> life -> tension -> action potential -> self prompt -> intent -> arbitration 链路。
3. **给定** 默认配置，**当** arbiter 产出 world reply 机会，**那么** 只能生成 report、草案或 require_approval，不自动 `linz_publish`。

### 用户故事 4 - 用户可观测控制面 (优先级: P2)

作为用户，我希望能查看 autonomous 状态、收件箱、事件、intent，并能 pause/resume/stop/tick。

**优先级原因**: 常驻能力必须可停、可查、可诊断。

**独立测试**: 调用 CLI command handler 或其服务层，验证 status/pause/resume/stop/tick/inbox/events/intents 的输出和状态变化。

**验收场景**:

1. **给定** runtime 已启动，**当** 用户执行 `hermes os-runtime autonomous status`，**那么** 输出 status、loop_id、last_wake_reason、预算、cooldown 和 last arbitration 摘要。
2. **给定** runtime 已停止，**当** 用户执行 tick，**那么** 命令返回明确诊断而不是启动无预算后台循环。

## 需求

### 功能需求

- **FR-001**: 系统必须扩展 `OSRuntimeConfig` 支持 `autonomous` 配置段，字段覆盖 enabled、start_on_agent_load、start_with_gateway、apply_to_all_turns、pre_turn_evaluation、post_turn_evaluation、inject_self_prompt、respond_to_world_events、tick_interval_seconds、idle_cooldown_seconds、max_turns_per_wake、max_wakes_per_hour、allow_tool_execution、allow_world_publish、require_approval_for_world_publish。
- **FR-002**: 系统必须新增 `AutonomousRuntimeState`，记录 status、loop_id、profile/session、level、last_wake_reason、last_wake_event_id、last_turn_event_id、last_tick_at、wakes_used、max_wakes_per_hour、cooldown_until、last_intent_id、last_arbitration、last_action_summary 和 paused_reason。
- **FR-003**: `AutonomousScheduler` 必须支持 start、tick、idle cooldown、hourly wake budget、per-wake max turns、pause、resume、stop，并禁止无预算无限循环。
- **FR-004**: `TurnTensionHook.before_turn()` 必须将普通用户消息、Linz World MessageEvent 和 scheduled tick 投影为 `os_runtime` event，并构建 context/signals/life/tension/action/self_prompt。
- **FR-005**: `TurnTensionHook.after_turn()` 必须将 assistant response、tool result 和 runtime feedback 投影回 `os_runtime`，并更新 LifeState/TensionSet/ActionPotential/evidence。
- **FR-006**: `SelfPromptInjector` 必须只注入当前轮 ephemeral user context，内容限定为张力摘要、open_space、target_direction、约束和 evidence refs。
- **FR-007**: `SelfPromptInjector` 不得暴露 token、raw payload、restricted audit content、authorization header、private key 或未脱敏世界事件原文。
- **FR-008**: `AutonomousRuntimeLoop.run_once()` 必须串联模块 1-5 现有组件，在无用户 goal 时也能由事件、生命状态、张力和行动势能生成低风险 OpenIntent。
- **FR-009**: `WorldEventWaker` 必须只在 Linz World raw event 已持久化并去重后唤醒 loop；重复 event 不得重复 wake。
- **FR-010**: 默认 autonomous 行动必须限制为 `report_only`、低风险草案/内部反思/evidence package 或 `require_approval`。
- **FR-011**: 默认不得执行真实工具副作用、正式 world publish、外部消息、删除、支付或权限操作。
- **FR-012**: 当配置显式允许 world publish 时，仍必须通过 BoYueArbiter、PolicyEngine、Linz event catalog、authorization map、STVBGuard 和 evidence receipt。
- **FR-013**: Hook 失败必须 fail-open 保持普通对话可用；涉及外部副作用时必须 fail-closed 或 require_approval。
- **FR-014**: 系统必须提供 `hermes os-runtime autonomous status|pause|resume|stop|tick|inbox|events|intents` 可观测命令。
- **FR-015**: `os_runtime.enabled=false` 或 `autonomous.enabled=false` 时，普通 CLI、gateway、TUI 和模块 6 `/goal` 行为必须保持不变。

### 关键实体

- **AutonomousRuntimeState**: 当前 profile/session 的常驻自治状态和最近一次 wake/evidence 摘要。
- **AutonomousWake**: 一次由 world event、tick、turn feedback 或 manual tick 触发的运行记录。
- **AutonomousInboxItem**: 等待 autonomous loop 处理的去重事件引用或内部反馈。
- **TurnTensionEvaluation**: before/after turn 的投影、状态更新、SelfPrompt 和裁判摘要。
- **EphemeralSelfPromptInjection**: 当前轮 user context 的短生命周期注入结果。

## 建议方案

- 复用现有 `OSRuntimeDriver`、`EventProjectionAdapter`、`OSRuntimeEventRepository`、`ContextAdapter` 和模块 1-5 engine；新增常驻 loop/scheduler/hook/inbox/injector 作为编排层。
- 配置默认关闭 autonomous；开启后也默认 `allow_tool_execution=false`、`allow_world_publish=false`。
- 将状态和 evidence 写入现有 profile-aware SessionDB side table / state meta 适配层；如果现有 repository 不足，扩展 adapter，不新建全局状态路径。
- gateway/runtime 启动 hook 只负责按配置启动 scheduler；普通 turn hook 按 `apply_to_all_turns` 独立工作，避免把普通对话绑定到后台 loop。
- CLI 命令通过服务层读写 scheduler/state/inbox，不直接操作底层 JSON 或 DB schema。

## 修改范围

- 新增 `agent/os_runtime/autonomous_loop.py`
- 新增 `agent/os_runtime/autonomous_state.py`
- 新增 `agent/os_runtime/autonomous_scheduler.py`
- 新增 `agent/os_runtime/world_event_waker.py`
- 新增 `agent/os_runtime/autonomous_inbox.py`
- 新增 `agent/os_runtime/turn_hooks.py`
- 新增 `agent/os_runtime/self_prompt_injector.py`
- 新增 `agent/os_runtime/adapters/runtime_queue.py`
- 新增或扩展 `hermes_cli/os_runtime_autonomous.py`
- 扩展 `agent/os_runtime/config.py`
- 扩展 gateway/runtime 启动 hook 和 CLI/TUI/gateway/Linz turn 边界 hook
- 新增测试：`tests/os_runtime/test_autonomous_loop.py`、`tests/os_runtime/test_turn_hooks.py`、`tests/os_runtime/test_world_event_waker.py`、`tests/gateway/test_os_runtime_autonomous_loop.py`

## 关键设计

- **状态边界**: `AutonomousRuntimeState` 与模块 6 `OSRuntimeState` 分开，避免 `/goal` assisted continuation 和常驻 loop 互相污染。
- **预算边界**: scheduler 每次 wake 必须检查 paused/stopped、cooldown、hourly budget、per-wake turn limit、fatigue/restraint。
- **Hook 边界**: before_turn/after_turn 不直接执行外部副作用；只投影、评估、注入 ephemeral context 和写 evidence。
- **世界事件边界**: WorldEventWaker 只消费已持久化的 event ref，不直接 ack NATS 或解析 raw inbox；重复 event 基于 event_id/sequence_key 去重。
- **Prompt 边界**: SelfPromptInjector 复用 `SelfPromptCompiler` 产物，但必须输出脱敏、摘要化、当前轮限定的 injection。
- **副作用边界**: 任何工具执行或 world publish 必须走现有 arbiter/policy/authorization/catalog/STVB/evidence receipt 链；默认只产出 report/草案/审批。

## 风险与取舍

- **常驻循环失控**: 通过 cooldown、wake budget、max turns、pause/stop、fatigue/restraint 和 dedupe 限制。
- **普通对话回归**: 通过默认关闭、`apply_to_all_turns` 开关、hook fail-open 和现有行为回归测试控制。
- **Prompt 污染**: 只注入 ephemeral user context，测试覆盖 system prompt/prompt cache 不变。
- **敏感信息泄露**: 注入层只允许摘要、约束和 evidence refs，复用 redaction，并增加负向测试。
- **越权发布**: 默认禁止 publish；显式允许时仍需完整治理链，缺任一环节即 fail-closed。
- **状态重复或不可查**: inbox、wake、event、intent 以 trace/evidence refs 关联，CLI 可查询。

## 成功标准

- **SC-001**: 开启 autonomous 配置后，Agent/gateway 启动无需 `/os_runtime goal` 即可查询到 idle/sleeping 常驻状态。
- **SC-002**: 开启 `apply_to_all_turns=true` 后，普通 CLI/TUI/gateway 消息会写入 `os_runtime` event，并更新 LifeState/TensionSet/ActionPotential/evidence。
- **SC-003**: 开启 `inject_self_prompt=true` 后，当前轮 user context 包含 ephemeral SelfPrompt，稳定 system prompt 和 prompt cache 前缀无变化。
- **SC-004**: 关闭 `inject_self_prompt` 时，普通对话只被观测记录，不改变模型输入。
- **SC-005**: 合法 Linz World 消息事件能自动 wake，并完成完整张力链路与 arbitration 记录。
- **SC-006**: 无用户 goal 时，world event 或 tick 能生成低风险 autonomous intent。
- **SC-007**: 默认配置下不会自动发布正式 Linz World 事件或执行外部副作用。
- **SC-008**: cooldown、wake budget、fatigue/restraint、pause/stop 能阻止重复或无限 wake。
- **SC-009**: 每次 wake 可查询 wake reason、event id、LifeState、top tensions、ActionPotential、OpenIntent、ArbitrationResult、action summary 和 stop reason。
- **SC-010**: `os_runtime.enabled=false` 或 `autonomous.enabled=false` 时现有 CLI/gateway/TUI/`/goal` 回归测试通过。

## 测试计划

- 单元测试 `OSRuntimeConfig` autonomous 配置解析、默认值和无效输入。
- 单元测试 `AutonomousRuntimeState` JSON round-trip、status transition、budget/cooldown 字段。
- 单元测试 `AutonomousScheduler` tick、pause/resume/stop、wake budget、idle cooldown、max turns 和 stopped 状态诊断。
- 单元测试 `TurnTensionHook.before_turn/after_turn` 普通消息、world event、tick、assistant response、tool result、runtime feedback 投影。
- 单元测试 `SelfPromptInjector` ephemeral 注入、system prompt 不变、prompt cache 不变、敏感字段脱敏。
- 单元测试 `WorldEventWaker` 持久化后 wake、dedupe、重复 event 不重复入队。
- 单元测试 `AutonomousRuntimeLoop.run_once()` world_event/tick/manual wake、无 goal intent、arbiter 默认 report_only/草案/require_approval。
- gateway 集成测试启动配置、scheduler 状态、普通 turn hook、world event wake 和 disabled config 回归。
- 回归测试优先运行：`pytest tests/os_runtime`、`pytest tests/gateway/test_os_runtime_continuation.py`、`pytest tests/gateway/test_os_runtime_autonomous_loop.py`。

## 后续交接说明

Builder Agent 应按 `tasks.md` 的 P1 -> P2 顺序实现。若实现时发现模块 -1 或模块 1-6 的接口缺失，先在同一 spec 分支评论 BLOCKED 或请求 Planner 更新 spec，不要绕过现有 engine 重新造链路。

## 假设

- 模块 -1 与模块 1-6 的基础能力已按 issue 依赖存在或可被本模块通过 adapter 调用。
- `SessionDB` 或现有 `OSRuntimeEventRepository` 可扩展以保存 autonomous state/inbox/evidence；若需要 schema 变更，必须保持 profile-aware。
- CLI/TUI/gateway 的 turn 边界已有可插入 hook 的位置；本模块只接入，不重写主循环。
