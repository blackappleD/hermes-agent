# 任务: 模块 6.5 常驻 Autonomous Runtime Loop

**输入**: `specs/111-autonomous-runtime-loop/`
**前置条件**: spec.md、plan.md、data-model.md、contracts/os-runtime-autonomous-cli.md
**测试要求**: 本模块涉及常驻循环、prompt 注入和副作用边界，必须包含单元与 gateway 回归测试。

## 阶段 1: 配置与状态基础

- [ ] T001 [P] 扩展 `agent/os_runtime/config.py`，新增 `AutonomousRuntimeConfig`、默认值、from_dict/to_dict，并保持未知字段兼容。
- [ ] T002 [P] 新增 `agent/os_runtime/autonomous_state.py`，实现 `AutonomousRuntimeState`、`AutonomousWakeRecord`、状态枚举和 JSON round-trip。
- [ ] T003 [P] 在 `tests/os_runtime/test_config.py` 或新测试中覆盖 autonomous 配置默认关闭、显式开启、布尔 coercion 和危险默认值。
- [ ] T004 [P] 新增 `tests/os_runtime/test_autonomous_loop.py` 的状态 round-trip、transition 和默认安全字段测试。

## 阶段 2: Runtime queue、inbox 与 scheduler

- [ ] T005 新增 `agent/os_runtime/adapters/runtime_queue.py`，复用 profile-aware SessionDB/OSRuntimeEventRepository 保存 state、wake record 和 inbox item。
- [ ] T006 新增 `agent/os_runtime/autonomous_inbox.py`，实现 enqueue、claim、mark handled/skipped/failed、event_id/sequence_key dedupe。
- [ ] T007 新增 `agent/os_runtime/autonomous_scheduler.py`，实现 start、tick、pause、resume、stop、cooldown、wake budget、max_turns_per_wake。
- [ ] T008 在 `tests/os_runtime/test_autonomous_loop.py` 覆盖 scheduler cooldown、budget、pause/resume/stop、stopped tick 诊断和无无限循环。

## 阶段 3: Turn hook 与 SelfPrompt 注入 (P1)

- [ ] T009 新增 `agent/os_runtime/self_prompt_injector.py`，只向当前轮 user context 注入脱敏 ephemeral SelfPrompt。
- [ ] T010 新增 `agent/os_runtime/turn_hooks.py`，实现 `TurnTensionHook.before_turn()` 的 human_request/world_event/runtime_tick 投影和可选 injection。
- [ ] T011 扩展 `agent/os_runtime/turn_hooks.py`，实现 `TurnTensionHook.after_turn()` 的 assistant_response/tool_result/runtime_feedback 投影和 evidence 更新。
- [ ] T012 在 `tests/os_runtime/test_turn_hooks.py` 覆盖 `apply_to_all_turns=false` 不影响普通对话。
- [ ] T013 在 `tests/os_runtime/test_turn_hooks.py` 覆盖 `inject_self_prompt=false` 只观测不改变模型输入。
- [ ] T014 在 `tests/os_runtime/test_turn_hooks.py` 覆盖 `inject_self_prompt=true` 只修改当前 user context，system prompt 和 prompt cache prefix 不变。
- [ ] T015 在 `tests/os_runtime/test_turn_hooks.py` 覆盖 hook 异常时普通对话 fail-open、外部副作用 fail-closed。
- [ ] T016 在 `tests/os_runtime/test_turn_hooks.py` 覆盖 token/raw payload/restricted audit content 不进入 injection。

## 阶段 4: Autonomous loop 与 world event wake (P2)

- [ ] T017 新增 `agent/os_runtime/autonomous_loop.py`，实现 `run_once(wake_reason, event_ref=None)`，串联 context/signals/life/tension/action/self_prompt/intent/arbiter。
- [ ] T018 在 `agent/os_runtime/autonomous_loop.py` 中实现无用户 goal 的低风险 intent 生成和默认 report/draft/require_approval 决策边界。
- [ ] T019 新增 `agent/os_runtime/world_event_waker.py`，只消费已持久化 Linz World event ref，完成 dedupe、inbox 入队和 scheduler wake。
- [ ] T020 在 `tests/os_runtime/test_autonomous_loop.py` 覆盖 tick/manual/world_event wake 的完整链路和 evidence 字段。
- [ ] T021 在 `tests/os_runtime/test_world_event_waker.py` 覆盖持久化后 wake、重复 event 不重复 wake、默认不 `linz_publish`。

## 阶段 5: CLI 与 gateway/runtime 接入 (P2)

- [ ] T022 新增或扩展 `hermes_cli/os_runtime_autonomous.py`，提供 status/pause/resume/stop/tick/inbox/events/intents 命令服务。
- [ ] T023 将 autonomous 命令接入现有 `hermes_cli/os_runtime.py` 或 CLI parser，保持已有 `/goal` 命令兼容。
- [ ] T024 扩展 gateway/runtime 启动 hook，按 `start_on_agent_load`、`start_with_gateway` 启动 scheduler。
- [ ] T025 扩展 CLI/TUI/gateway/Linz turn 边界 hook，按 `apply_to_all_turns` 调用 `TurnTensionHook`。
- [ ] T026 在 `tests/gateway/test_os_runtime_autonomous_loop.py` 覆盖 gateway 启动 idle/sleeping、disabled config 行为不变、普通 turn 投影和 manual tick。

## 阶段 6: 安全、回归与文档校验

- [ ] T027 [P] 补充默认禁止 tool execution/world publish 的负向测试，显式允许时断言仍需 arbiter/policy/catalog/auth/STVB/evidence。
- [ ] T028 [P] 运行并修复 `pytest tests/os_runtime`。
- [ ] T029 [P] 运行并修复 `pytest tests/gateway/test_os_runtime_continuation.py tests/gateway/test_os_runtime_autonomous_loop.py`。
- [ ] T030 检查实现 diff，确认未重写主循环、未新增必需第三方依赖、未修改与本模块无关业务文件。

## 依赖关系与执行顺序

- 阶段 1 阻塞所有后续阶段。
- 阶段 2 依赖阶段 1。
- 阶段 3 可在阶段 2 的 queue 基础完成后开始，是普通 turn 治理 MVP。
- 阶段 4 依赖阶段 2，并复用阶段 3 的 evaluation/injection 能力。
- 阶段 5 依赖阶段 2-4。
- 阶段 6 在功能完成后执行。

## 并行机会

- T001-T004 可并行。
- T012-T016 可在 T009-T011 初版完成后并行。
- T027-T029 可并行运行，但修复需按失败归属回到对应阶段。

## Builder 交接约束

- 不要实现默认真实外部副作用。
- 不要把 SelfPrompt 写入 system prompt 或 prompt cache 前缀。
- 不要重写 `AIAgent` 或 gateway 主循环。
- 若发现现有模块 -1 或模块 1-6 接口不足，先最小扩展 adapter；如影响范围超过本 spec，评论 BLOCKED 请求 Planner 更新。
