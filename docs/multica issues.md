# Multica Issues：基于张力场的 Agent 自驱动实现计划

来源计划：`docs/基于张力场的Agent自驱动实现计划.md`

说明：

- 以下 issue 按计划文档“模块化实施计划”拆分，覆盖 `模块 -1` 到 `模块 11`，并新增 `模块 6.5` 用于常驻完全自驱动 runtime。
- `模块 -1` 已有 spec-kit 拆解：`specs/001-native-linz-identity/`。后续实现应优先遵守该 spec 的范围收敛：不做旧 `linz-world-skill` 身份导入/同步/迁移；注册失败 fail-closed；外部副作用实时刷新授权 map；原始 payload 仅限受限审计。
- 后续模块尚未发现对应 spec 目录，issue 以计划文档为准，适合继续生成 spec/plan/tasks 后再实现。

---

## [Feature]模块 -1：Linz World 原生身份与世界接入

### 仓库

hermes-agent

### 计划文档

`/docs/基于张力场的Agent自驱动实现计划.md`

### 现有拆解

- 已有 spec-kit 文档：`specs/001-native-linz-identity/`
- 已有任务拆解：`specs/001-native-linz-identity/tasks.md`
- 已有分支语境：`feat/88-linz-world-native-identity`

### 目标

基于实现计划完成模块 -1：将 Linz World 从可选 skill 能力迁移为 Hermes Agent 原生世界身份层。每个 Hermes profile 必须拥有稳定的 Linz World original spirit 身份；Agent persona 创建或加载时应幂等注册或复用身份，注册失败时 fail-closed 并提供诊断。

### 范围

- 新增或完善 `agent/linz_world/` 原生模块，覆盖身份、配置、认证、事件目录、事件状态、事件总线、gateway adapter、发布、世界算力、Soul Memory、关系和 runtime bridge。
- 新增或完善 `hermes_cli/linz.py`、`tools/linz_world_tools.py`、`toolsets.py` 和必要 CLI command registry。
- 集成 Hermes profile create/load 与 agent persona bootstrap。
- 保留 Linz World 外部副作用治理边界，默认不启用自驱动、自动监听、自动响应或自动外部发布。

### 关键要求

- 未安装 `linz-world-skill` 时，Hermes 仍能显示和使用原生 Linz World 命令与工具。
- 同一 Hermes profile 重复加载不能重复注册 world identity。
- 注册失败必须阻止 agent persona 进入普通对话状态，并写入 pending/failed 诊断。
- 旧 `linz-world-skill` 本地身份导入、同步和迁移不属于当前 spec 范围。
- 每次发布、世界算力、Soul Memory 写入和关系变更前必须实时刷新授权 map；刷新失败即阻断。
- 世界事件 prompt 注入、普通工具结果和用户默认视图只能显示脱敏摘要。

### 验收标准

- `pytest tests/linz_world` 通过。
- 全新环境不安装 `linz-world-skill`，`hermes linz status` 和内建 `linz_*` 工具仍可发现。
- 同一 Hermes profile 连续加载多次只产生一个 original spirit 身份。
- 未登录、未授权、未知 subject/event_type、禁止结算转账类发布请求均在外部投递前被阻断。
- 重复世界事件不会重复触发 Agent turn，处理失败最多自动重试 3 次后标记 failed。
- 用户可见输出、prompt、普通工具结果和日志摘要中不暴露 token、私钥或完整 restricted payload。

---

## [Feature]模块 0：协议、配置与测试基座

### 仓库

hermes-agent

### 计划文档

`/docs/基于张力场的Agent自驱动实现计划.md`

### 依赖

- 依赖模块 -1 提供 `WorldIdentityRef` 的只读身份视图。
- 不依赖张力场 runtime 接入，不应改变现有行为。

### 目标

冻结 os_runtime 的领域契约和配置基座，明确生命状态、张力、意图、裁判、证据、泡泡和规则结晶对象，避免后续模块重复定义自治语义。

### 范围

- 新增 `agent/os_runtime/domain.py`
- 新增 `agent/os_runtime/config.py`
- 扩展 `hermes_cli/config.py::DEFAULT_CONFIG` 的 `os_runtime` 配置段
- 新增 `tests/os_runtime/test_domain.py`
- 新增 `tests/os_runtime/test_config.py`

### 关键要求

- 使用 `dataclasses` 或轻量 typed dict，不新增依赖。
- 定义事件来源、张力类型、张力操作、开放行动族、裁判结果、风险等级、泡泡生命周期、规则成熟度 R0-R4。
- 主裁判结果必须是 `auto_execute`、`sandbox_execute`、`require_approval`、`report_only`、`reject`。
- `allow_reply`、`allow_draft`、`allow_sandbox` 等旧字段只能作为迁移别名，不能进入主协议。
- `TaskContextView` 和 `AgentContextView` 只保存投影视图，不复制 SessionDB、memory manager、context engine 或 tool registry。

### 验收标准

- `pytest tests/os_runtime/test_domain.py tests/os_runtime/test_config.py` 通过。
- 所有核心对象支持 JSON round-trip，中文内容、trace id、时间戳和未知 metadata 不丢失。
- 默认 `os_runtime.enabled=false` 时，普通 CLI、gateway、TUI、工具调用和 `/goal` 行为不变。

---

## [Feature]模块 1：外部事件接入与 SessionDB 适配

### 仓库

hermes-agent

### 计划文档

`/docs/基于张力场的Agent自驱动实现计划.md`

### 依赖

- 依赖模块 -1 的 Linz World event state、event bus、gateway adapter 和 runtime bridge。
- 依赖模块 0 的 `OSRuntimeEventRef`、事件来源枚举和配置基座。

### 目标

把 NATS 世界事件、Hermes 元神对话、工具调用、工具结果、模型回复和 continuation 投影为统一自治事件。存储应优先复用 `hermes_state.py::SessionDB` 或同一 profile 下 side tables，避免另建会话存储。

### 范围

- 新增或完善 `agent/os_runtime/adapters/events.py`
- 新增或完善 `agent/os_runtime/adapters/session_store.py`
- 完善 `agent/linz_world/event_state.py`
- 完善 `agent/linz_world/event_bus.py`
- 完善 `agent/linz_world/gateway_adapter.py`
- 新增相关 `tests/linz_world/` 与 `tests/os_runtime/` 覆盖

### 关键要求

- Linz World/NATS raw event 先可靠保存，再进入 Hermes gateway `MessageEvent` 流。
- Agent 处理失败不能让 NATS 等待 LLM 完整处理；失败应转为内部 dispatch status。
- 普通用户消息、assistant response、tool call、tool result、goal continuation、world publish receipt 和 runtime error 都应投影为 `os_runtime` event。
- 禁用 `os_runtime` 时不注册额外工具、不写自治事件、不注入 prompt。
- 工具结果超长时只保存摘要和引用。

### 验收标准

- 启用 `os_runtime.mode=passive` 后，一次普通对话产生可查询自治事件。
- NATS 世界事件进入 Hermes 后可关联 `os_id/soul_id/event_id/nats_sequence/subject/event_type`。
- 重复 NATS event id 或 sequence 不会重复触发 Agent turn。
- `os_runtime.enabled=false` 时不写事件且不改变现有 token prompt。
- 事件存储提供 `append()`、`get()`、`list_recent()`、`list_by_session()`、`list_by_trace()`。

---

## [Feature]模块 2：上下文适配与信号解释

### 仓库

hermes-agent

### 计划文档

`/docs/基于张力场的Agent自驱动实现计划.md`

### 依赖

- 依赖模块 0 的 context/signal 领域对象。
- 依赖模块 1 的 recent os_runtime events。
- 依赖模块 -1 的 identity、authorization map、relationship 和 world event 摘要。

### 目标

把 Linz World 身份/授权/关系/世界消息、现有会话、记忆、上下文压缩、工具边界和自治事件转成张力场可消费的 `TaskContextView` 与 `SignalSet`。该模块不替代 `agent/context_engine.py`。

### 范围

- 新增 `agent/os_runtime/adapters/context.py`
- 新增 `agent/os_runtime/engine/signals.py`
- 新增 `tests/os_runtime/test_context_adapter.py`
- 新增 `tests/os_runtime/test_signals.py`

### 关键要求

- `ContextAdapter` 读取 Linz World identity、authorization map、relationship summary、session、recent events、available tools、risk config 和 memory refs。
- 复用 `agent/context_engine.py`、`agent/memory_manager.py`、`tools.registry` 和 `SessionDB`。
- 首版 `SignalInterpreter` 使用确定性规则，不直接生成行动。
- SignalSet 至少覆盖需求、世界机会、风险、世界授权、关系、资源和反馈信号。
- 不从 LLM 文本中无约束抽取权限、身份或授权。

### 验收标准

- 相同事件输入得到确定性 `SignalSet`。
- 低风险文档任务、代码编辑任务、外部消息任务能区分风险等级。
- 世界事件不会绕过授权 map 进入可执行 intent。
- 未登录或无授权 map 的 world side effect 只产生风险/约束信号，不产生执行许可。

---

## [Feature]模块 3：生命状态、张力解释器与张力场内核

### 仓库

hermes-agent

### 计划文档

`/docs/基于张力场的Agent自驱动实现计划.md`

### 依赖

- 依赖模块 0 的 `LifeState`、`TensionOperation`、`TensionSet` 等协议对象。
- 依赖模块 2 的 `SignalSet` 与 `TaskContextView`。

### 目标

实现白皮书的 `LifeStateSystem`、`TensionInterpreter` 与 `TensionFieldEngine`。事件解释、生命状态更新和张力网络维护必须分层，避免把原因解释和状态变更混在一起。

### 范围

- 新增 `agent/os_runtime/engine/life_state.py`
- 新增 `agent/os_runtime/engine/tension_interpreter.py`
- 新增 `agent/os_runtime/engine/tension_field.py`
- 新增 `tests/os_runtime/test_life_state.py`
- 新增 `tests/os_runtime/test_tension_interpreter.py`
- 新增 `tests/os_runtime/test_tension_field.py`

### 关键要求

- `LifeStateSystem.update()` 输入 `SignalSet`、上一状态和执行反馈，输出可解释 delta。
- 首版字段覆盖 `energy`、`fatigue`、`health`、`wakefulness`、`curiosity`、`boredom`、`creative_pressure`、`social_hunger`、`silence_pressure`、`restraint`、`life_cycle`、`recovery_cycle`、`generated_intent_count`。
- `TensionInterpreter` 只解释张力变化原因，不直接修改张力状态。
- `TensionOperation` 必须覆盖 `update`、`generate`、`merge`、`hibernate`、`eliminate`。
- `TensionFieldEngine` 维护 core/dynamic tensions、baseline、activation、trend、confidence、evidence 和 propagation edges。
- Linz World 需求、订单、授权、结算、聊天、关系和 Soul Memory summary 都应能影响张力解释。

### 验收标准

- 连续失败会提高 fatigue/restraint 并降低行动倾向，而不是无限重试。
- 明确未完成目标形成稳定张力。
- 高风险动作形成“价值收益 vs 风险约束”张力。
- 张力解释器能说明事件触发了哪些价值冲突，以及张力为何更新、生成、合并、休眠或淘汰。
- 张力网络能展示核心张力、动态张力、基线、激活度和传播边。
- 世界授权变化会影响后续 action potential，而不是只作为提示文本。

---

## [Feature]模块 4：行动势能与认知经济

### 仓库

hermes-agent

### 计划文档

`/docs/基于张力场的Agent自驱动实现计划.md`

### 依赖

- 依赖模块 3 的 LifeState 和 TensionSet。
- 依赖模块 -1 的 world compute client。
- 依赖模块 0 的 `ActionPotential` 协议对象。

### 目标

决定“是否值得行动、行动到什么深度、是否需要更强模型或更多预算”。首版只输出建议，不直接切换主模型。

### 范围

- 新增 `agent/os_runtime/engine/action_potential.py`
- 新增 `agent/os_runtime/engine/cognitive_economy.py`
- 新增 `tests/os_runtime/test_action_potential.py`
- 新增 `tests/os_runtime/test_cognitive_economy.py`

### 关键要求

- `ActionPotentialEvaluator` 输出 value potential、mutual benefit potential、learning potential、risk cost、overall score 和 recommended depth。
- `recommended_depth` 限定为 `none`、`report`、`draft`、`continue_turn`、`sandbox`、`tool`、`world_publish`、`bubble`。
- `CognitiveEconomyController` 首版只建议 `rule_path`、`auxiliary_small`、`main_model`、`world_compute`、`high_reasoning`。
- `world_compute` 必须通过 `agent/linz_world/compute.py`，使用登录 token 并记录 receipt。
- 后续再接入 `agent/auxiliary_client.py` 与 reasoning config，不在本 issue 中强制切换模型。

### 验收标准

- 简单闲聊不会触发自驱动 continuation。
- 明确未完成低风险目标可建议 `continue_turn`。
- 中高风险工具动作必须建议审批或 sandbox。
- 未登录或无 Soul Memory summary 时不能选择 `world_compute`。
- 所有评分字段可追踪到 signal、tension 或配置阈值。

---

## [Feature]模块 5：SelfPrompt、OpenIntent 与 BoYueArbiter

### 仓库

hermes-agent

### 计划文档

`/docs/基于张力场的Agent自驱动实现计划.md`

### 依赖

- 依赖模块 4 的 `ActionPotential`。
- 依赖模块 3 的 tension explanation。
- 依赖模块 0 的 `SelfPrompt`、`OpenIntent`、`ArbitrationResult` 协议对象。

### 目标

把张力状态转成可解释的开放意图，并在执行前通过 BoYueArbiter 裁判。

### 范围

- 新增 `agent/os_runtime/engine/prompt_compiler.py`
- 新增 `agent/os_runtime/engine/intent_generator.py`
- 新增 `agent/os_runtime/engine/arbiter.py`
- 新增 `tests/os_runtime/test_prompt_compiler.py`
- 新增 `tests/os_runtime/test_intent_generator.py`
- 新增 `tests/os_runtime/test_arbiter.py`

### 关键要求

- `SelfPromptCompiler` 输出结构化 prompt，不修改 Hermes 稳定 system prompt。
- 通过 `pre_llm_call` hook 注入 ephemeral context，遵守现有 prompt cache 设计。
- SelfPrompt 至少包含 `state_summary`、`tension_summary`、`potential_summary`、`memory_scope`、`constraint_scope`、`environment_scope`、`open_space`、`target_direction`。
- `OpenIntentGenerator` 首版规则路径优先；LLM JSON 路径解析失败必须回退规则路径且不得执行行动。
- `OpenIntent` 必须包含 action family、action type、why_now、open_space、target_direction、tools_needed、proposed_new_tools、proposed_new_skills、success_condition、stop_condition。
- `BoYueArbiter` 主结果仅允许 `auto_execute`、`sandbox_execute`、`require_approval`、`report_only`、`reject`。
- Linz World publish 必须同时通过 Arbiter、PolicyEngine、event catalog 和 authorization map。

### 验收标准

- 每个自动 continuation 都能解释 `why_now`、`success_condition`、`stop_condition`。
- 每个 intent 都能追溯到 `open_space` 和 `target_direction`。
- LLM 生成非法 JSON 时不会执行行动。
- 高风险 intent 不会直接进入工具执行。
- LLM 不能凭空构造 subject/event_type，必须走 `linz_world.event_catalog`。

---

## [Feature]模块 6：自治 Runtime Driver

### 仓库

hermes-agent

### 计划文档

`/docs/基于张力场的Agent自驱动实现计划.md`

### 依赖

- 依赖模块 1 到模块 5 的事件、上下文、信号、张力、势能、SelfPrompt、Intent 和 Arbiter。
- 依赖现有 `/goal` continuation 集成点。

### 目标

把 `/goal` 的跨轮 continuation 升级为张力场驱动的自驱动循环。首版支持 passive 和 assisted 模式，允许低风险自然语言或草案 continuation。

### 范围

- 新增 `agent/os_runtime/driver.py`
- 新增 `hermes_cli/os_runtime.py`
- 扩展 CLI/slash 命令：`/os_runtime status|passive|goal|pause|resume|clear|tick`
- 集成 gateway continuation hook
- 集成 TUI continuation hook
- 新增 `tests/os_runtime/test_driver.py`
- 新增 `tests/hermes_cli/test_os_runtime_command.py`
- 新增 `tests/gateway/test_os_runtime_continuation.py`
- 新增 `tests/tui_gateway/test_os_runtime_continuation.py`

### 关键要求

- 新建 `OSRuntimeState`，覆盖 status、goal、turns_used、max_turns、last tension/action/self_prompt/intent/arbitration/world_event 和 paused_reason。
- `OSRuntimeDriver.evaluate_after_turn()` 串联 recent event、context/signals、life/tension、action potential、self prompt、intent、arbitration，并返回是否需要 continuation prompt。
- `mode=passive` 只记录状态和 intent，不继续。
- `mode=assisted` 只允许 `report_only` 或无外部副作用的低风险 `auto_execute` continuation。
- continuation prompt 必须是普通 user-role 消息，不改 system prompt。

### 验收标准

- `os_runtime.enabled=false` 时 `/goal` 原有行为不变。
- `assisted` 模式能在低风险文档任务中自动继续。
- 预算耗尽、完成、用户打断、pause/clear、裁判拒绝时必须停止。
- Linz World 消息可以触发 assisted continuation，但默认不自动发布正式事件。
- gateway 和 TUI 的 continuation 队列可被用户打断、暂停或清除。

---

## [Feature]模块 6.5：常驻 Autonomous Runtime Loop 与世界事件自响应

### 仓库

hermes-agent

### 计划文档

`/docs/基于张力场的Agent自驱动实现计划.md`

### 依赖

- 依赖模块 -1 的 Linz World identity、event state、gateway adapter、event catalog 和 authorization map。
- 依赖模块 1 到模块 5 的事件、上下文、信号、生命状态、张力、行动势能、SelfPrompt、OpenIntent 和 BoYueArbiter。
- 依赖模块 6 的 driver state、turn-boundary decision 和 pause/resume/clear 控制语义，但不依赖用户输入 `/os_runtime goal`。

### 目标

实现真正的常驻元神自驱动 runtime：Agent/gateway 启动后可根据世界事件、时间 tick、内部反馈、生命状态、张力场和行动势能自动唤醒，生成 intent 并经裁判后执行低风险自主响应、草案、反思、evidence 或审批请求。该模块不应要求用户每次输入 `/os_runtime goal` 才进入自驱动。

### 范围

- 新增 `agent/os_runtime/autonomous_loop.py`
- 新增 `agent/os_runtime/autonomous_state.py`
- 新增 `agent/os_runtime/autonomous_scheduler.py`
- 新增 `agent/os_runtime/world_event_waker.py`
- 新增 `agent/os_runtime/autonomous_inbox.py`
- 新增 `agent/os_runtime/adapters/runtime_queue.py`
- 新增或扩展 `hermes_cli/os_runtime_autonomous.py`
- 扩展 gateway/runtime 启动 hook，使 autonomous loop 可按配置启动
- 扩展 Linz World event dispatch hook，使 world event 可唤醒 autonomous loop
- 新增 `tests/os_runtime/test_autonomous_loop.py`
- 新增 `tests/os_runtime/test_world_event_waker.py`
- 新增 `tests/gateway/test_os_runtime_autonomous_loop.py`

### 关键要求

- 配置启用形态应支持：

```yaml
os_runtime:
  enabled: true
  mode: autonomous_low_risk
  autonomous:
    enabled: true
    start_on_agent_load: true
    start_with_gateway: true
    respond_to_world_events: true
    tick_interval_seconds: 30
    idle_cooldown_seconds: 60
    max_turns_per_wake: 3
    max_wakes_per_hour: 20
    allow_tool_execution: false
    allow_world_publish: false
    require_approval_for_world_publish: true
```

- `AutonomousRuntimeState` 必须记录 status、loop_id、profile/session、last_wake_reason、last_wake_event_id、last_tick_at、wakes_used、cooldown_until、last_intent_id、last_arbitration、last_action_summary 和 paused_reason。
- `AutonomousRuntimeLoop.run_once()` 必须串联模块 1-5 的完整张力场链路，且在没有用户 goal 时也能由世界事件、生命状态和张力场生成低风险 intent。
- `AutonomousScheduler` 必须提供 tick、idle cooldown、wake budget、per-wake max turns、pause/resume/stop，避免无限后台循环。
- `WorldEventWaker` 必须在 Linz World raw event 持久化和去重后才唤醒 autonomous loop；重复 event 不得重复 wake。
- 默认 autonomous 行动只允许 `report_only`、低风险回复/文档草案、内部反思、evidence package 或 `require_approval`。
- 默认不得执行真实工具副作用、不得自动 `linz_publish`、不得发送外部消息、不得删除、支付或改权限。
- 如果配置显式允许 world publish，仍必须通过 BoYueArbiter、PolicyEngine、Linz event catalog、authorization map、STVBGuard 和 evidence receipt。
- 必须提供用户可观测命令：`status`、`pause`、`resume`、`stop`、`tick`、`inbox`、`events`、`intents`。

### 验收标准

- 启用 `os_runtime.mode=autonomous_low_risk` 与 `autonomous.enabled=true` 后，Agent/gateway 启动即进入 idle/sleeping 常驻状态，不需要用户输入 `/os_runtime goal`。
- 注入合法 Linz World 消息事件后，runtime 自动 wake，并完成 context -> signals -> life -> tension -> action potential -> self prompt -> intent -> arbitration 链路。
- 无用户 goal 时，Agent 仍能根据张力场/行动势能/生命状态生成低风险自主 intent。
- 默认配置下，世界事件只生成回复草案、report 或审批请求，不自动发布正式 Linz World 事件。
- tick wake 可在无世界事件时触发内部反思、未完成张力检查或休眠决策。
- cooldown、wake budget、fatigue/restraint、pause/stop 能阻止无限自驱动。
- 每次 wake 都有可查询 evidence：wake reason、event id、LifeState、top tensions、ActionPotential、OpenIntent、ArbitrationResult、action summary 和 stop reason。
- `os_runtime.enabled=false` 或 `autonomous.enabled=false` 时，普通 CLI、gateway、TUI 和 `/goal` 行为不变。

---

## [Feature]模块 7：工具执行适配与证据包

### 仓库

hermes-agent

### 计划文档

`/docs/基于张力场的Agent自驱动实现计划.md`

### 依赖

- 依赖模块 5 的 arbitration 和 permission 结果。
- 依赖模块 6 的 assisted runtime continuation 与模块 6.5 的 autonomous wake。
- 依赖现有 `model_tools.py` post tool hook 和 `run_agent.py` LLM result 信息。

### 目标

复用现有工具执行通道，让所有被允许的自治行动都有 receipt，可审计、可复盘。不得实现第二套 execution gateway。

### 范围

- 新增 `agent/os_runtime/adapters/tools.py`
- 新增 `agent/os_runtime/evidence.py`
- 新增 `agent/os_runtime/adapters/linz_world.py`
- 新增 `tests/os_runtime/test_tools_adapter.py`
- 新增 `tests/os_runtime/test_evidence.py`

### 关键要求

- 在 `domain.py` 中定义或完善 `PermissionTicket` 与 `ExecutionReceipt`。
- `post_tool_call` hook 记录 tool name、args 摘要、result 摘要、duration、session/task/tool_call id、arbitration id 和 permission ticket id。
- `post_llm_call` hook 记录 final response receipt。
- `linz_world.publisher` 发布成功后记录 subject、event_type、event_id、payload 摘要、authorization map version 和 arbitration id。
- `EvidencePackage` 聚合 intent、arbitration、tool receipts、world receipts、final response、tests/commands evidence 和 known risks。
- 首版只记录 evidence，不改变现有工具返回。

### 验收标准

- 每个自治触发的 continuation 至少有一个 evidence package。
- 每个工具 receipt 可回溯到 event id 和 intent id。
- 每个 world publish receipt 可回溯到 Linz World event id。
- 敏感参数需要 redaction，不能明文写 API key、token 或 restricted payload。
- 工具失败和命令失败也会进入 evidence，而不是只记录成功路径。

---

## [Feature]模块 8：演化记忆适配与规则结晶

### 仓库

hermes-agent

### 计划文档

`/docs/基于张力场的Agent自驱动实现计划.md`

### 依赖

- 依赖模块 7 的 evidence package。
- 依赖模块 -1 的 Soul Memory 和 relationship 能力。
- 依赖模块 5 的 arbiter，可把 R0/R1 规则作为约束输入。

### 目标

让行动结果、失败摩擦、成功经验、协作证据成为后续张力和裁判输入。演化记忆是自治决策证据层，不替代 `agent/memory_manager.py` 管理的外部 memory provider。

### 范围

- 新增 `agent/os_runtime/adapters/memory.py`
- 新增 `agent/os_runtime/engine/rule_crystallizer.py`
- 完善 `agent/linz_world/memory.py`
- 完善 `agent/linz_world/relationship.py`
- 新增 `tests/os_runtime/test_evolution_memory.py`
- 新增 `tests/os_runtime/test_rule_crystallizer.py`

### 关键要求

- 定义 event log、important event、reflection、tension evolution、rule crystal 的分层。
- `adapters/memory.py` 复用 `MemoryManager` 生命周期入口，从 evidence package 抽取候选演化记忆。
- 高价值 evidence、交付物引用和规则结晶可写入 Linz World Soul Memory sink。
- 世界关系摘要输入关系信号。
- `RuleCrystallizer` 首版只生成 R0/R1，来源包括高频失败、重复审批、重复工具风险和重复成功模式。
- R0/R1 只进入 `RuleMembrane` 与 `BoYueArbiter` 提示/约束，不自动升级为硬规则。

### 验收标准

- 偶发失败不会直接成为硬规则。
- 同类失败达到阈值才生成 R0。
- 规则可以解释来源 evidence。
- 写入 Soul Memory 的内容必须有 `artifact_ref` 和 `sink_reason`。
- R0/R1 规则能影响后续 arbiter 提示或约束，但不会绕过人工确认变成 R2/R3。

---

## [Feature]模块 9：治理、安全与审批

### 仓库

hermes-agent

### 计划文档

`/docs/基于张力场的Agent自驱动实现计划.md`

### 依赖

- 依赖模块 5 的 intent 和 arbiter。
- 依赖模块 7 的 permission ticket 与 evidence。
- 依赖模块 -1 的 Linz World event catalog、authorization map 和 world rules。

### 目标

确保开放意图可控，高风险动作必须降级、审批或拒绝。该模块强化 PolicyEngine、STVBGuard、审批面和 Linz World 世界规则 enforcement。

### 范围

- 新增 `agent/os_runtime/engine/policy.py`
- 新增 `agent/os_runtime/engine/stvb_guard.py`
- 集成 `pre_tool_call` 阻断
- 集成 gateway `/approve` / `/deny`
- 集成 TUI prompts
- 新增 `tests/os_runtime/test_policy.py`
- 新增 `tests/os_runtime/test_stvb_guard.py`

### 关键要求

- `PolicyEngine` 输入 actor、intent、tool、context，输出 permission ticket。
- 风险等级首版覆盖自然语言回复、文档草案、文件写入、终端执行、外部消息、删除、支付、账号/权限操作、Linz World publish 和结算类事件。
- `ec.transfer.*` 禁止 agent 直接发布。
- `STVBGuard` 做底线检查：安全、可信、价值向善、有益共生。
- 自动批准或 yolo 模式下仍必须保留 evidence 和 ticket。
- Linz World 世界规则作为治理输入：未 registry/login/map、未知 subject/event_type、非 JSON object payload 均必须阻断。

### 验收标准

- 未经允许不会自动发送外部消息。
- destructive shell/file 操作必须被裁判为审批或拒绝。
- 任何拒绝都写入 governance event。
- 世界规则拒绝必须写入 governance event，并保留被拒绝的 subject/event_type 摘要。
- 高风险动作在 gateway、TUI 和 CLI 路径上的行为一致。

---

## [Feature]模块 10：观测与用户界面

### 仓库

hermes-agent

### 计划文档

`/docs/基于张力场的Agent自驱动实现计划.md`

### 依赖

- 依赖模块 -1 到模块 9 的状态、事件、intent、arbitration、evidence 和 governance 数据。
- TUI/dashboard 只做辅助视图，不重建主聊天体验。

### 目标

让用户能理解 Agent 为什么继续、为什么停止、为什么阻断工具，以及当前 Linz World 身份、授权、事件和 os_runtime 状态。

### 范围

- 新增或扩展 `tools/os_runtime_tools.py`
- 完善 `tools/linz_world_tools.py`
- 完善 `hermes_cli/linz.py`
- 新增或完善 `hermes_cli/os_runtime.py`
- 扩展 `hermes_cli/web_server.py` os_runtime API
- 新增 TUI os_runtime 状态摘要组件
- 新增 dashboard React 侧栏或状态组件

### 关键要求

- CLI 查询覆盖 `hermes linz status|map|messages|publish` 和 `hermes os_runtime status|events|tensions|intents|evidence <id>`。
- Agent 工具覆盖 `linz_status`、`linz_map`、`linz_events_recent`、`linz_publish`、`linz_memory_sink`、`linz_relationship`、`linz_compute`、`os_runtime_state`、`os_runtime_tick`、`os_runtime_bubble_show`、`os_runtime_evidence_show`。
- Dashboard API 覆盖 Linz status/map/messages 和 os_runtime state/events/intents/bubbles。
- TUI 只显示状态摘要和最近 intent，不重建 transcript 或 composer。
- UI 失败必须非破坏性处理，不影响主终端/TUI。

### 验收标准

- 用户能看到当前 LifeState、top tensions、last intent、last arbitration。
- 用户能看到最近一次 tension explanation、action potential 摘要、open_space 和 target_direction。
- 用户能看到当前 os_id/soul_id、登录状态、授权 map 摘要、未读世界消息数量。
- 每个自动 continuation 在 UI 中可解释。
- Dashboard 失败不影响主终端/TUI。

---

## [Feature]模块 11：泡泡协议协作运行时（最后实现）

### 仓库

hermes-agent

### 计划文档

`/docs/基于张力场的Agent自驱动实现计划.md`

### 依赖

- 该模块最后实现。
- 依赖 Linz World 原生身份、os_runtime 张力场、事件投影、证据、演化记忆、治理和观测稳定。
- 依赖现有 kanban/delegate 基础设施。

### 目标

将复杂目标拆成 `TaskBubble`、`SkillSlot`、`RuleMembrane`，先映射到现有 kanban/delegate 基础设施，并在需要时映射到 Linz World 市场事件。该模块不阻塞 MVP。

### 范围

- 新增 `agent/os_runtime/bubble/domain.py`
- 新增 `agent/os_runtime/bubble/manager.py`
- 新增 `agent/os_runtime/bubble/slot_broker.py`
- 新增 `agent/os_runtime/bubble/skill_matcher.py`
- 新增 `agent/os_runtime/adapters/kanban.py`
- 新增 `agent/os_runtime/bubble/lifecycle.py`
- 新增 `tests/os_runtime/test_bubble_*.py`

### 关键要求

- `TaskBubbleManager` 基于 action potential、风险/复杂度阈值、工具/能力缺口和用户明确协作需求判断是否需要泡泡。
- 首批能力槽覆盖 `coding`、`api_review`、`qa_regression`、`security_review`、`evidence_pack`、`docs`。
- `AgentSkillMatcher` 首版基于本地 role/toolset/profile 静态表，不做复杂信誉系统。
- `adapters/kanban.py` 将泡泡映射到 board、tasks、task_links、task_comments、assignee/profile 和 evidence comment。
- Linz World market event mapping 覆盖 requirement published、order accepted、handover delivered、handover approved/rejected、settlement requested。
- 不允许直接发布 `ec.transfer.*`。
- 需要执行时优先使用 durable kanban task pipeline，`delegate_task` 只作为短生命周期辅助。

### 验收标准

- 一个复杂代码任务可生成 bubble spec 和 kanban tasks。
- worker 只能修改自己的 kanban task 状态，遵守现有 task ownership 约束。
- evidence package 能汇总各 slot 输出。
- 世界市场事件必须由 bubble/evidence 驱动生成，不能由 LLM 直接拼 payload 发布。
- 泡泡生命周期至少覆盖 `created`、`seeking`、`assembled`、`executing`、`validating`、`dissolved`、`crystallized`。
