# 任务: 模块 6：自治 Runtime Driver

**输入**: 来自 `specs/100-os-runtime-driver/` 的设计文档  
**前置条件**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/os-runtime-cli.md`

## 阶段 1: Driver 基础与状态

**目的**: 建立 profile/session-scoped state 和 fail-closed decision contract。

- [ ] T001 [P] 在 `tests/os_runtime/test_driver.py` 添加 `OSRuntimeState` JSON round-trip、默认值和 profile/session isolation 测试
- [ ] T002 [P] 在 `tests/os_runtime/test_driver.py` 添加 disabled/passive 模式不 continuation 的测试
- [ ] T003 在 `agent/os_runtime/driver.py` 定义 `OSRuntimeState`、`OSRuntimeDecision` 和状态持久化接口
- [ ] T004 在 `agent/os_runtime/driver.py` 实现 disabled/passive fail-closed 路径

**检查点**: passive/disabled driver 可独立测试，且不会接触 gateway/TUI。

## 阶段 2: 张力场决策链

**目的**: 串联模块 0-5 的 context/signals/life/tension/action/self_prompt/intent/arbitration。

- [ ] T005 [P] 在 `tests/os_runtime/test_driver.py` 用 fake adapters 覆盖 recent event 缺失、engine 异常和 runtime feedback
- [ ] T006 [P] 在 `tests/os_runtime/test_driver.py` 覆盖 low-risk `REPORT_ONLY` 和低风险无工具 `AUTO_EXECUTE` assisted continuation
- [ ] T007 在 `agent/os_runtime/driver.py` 实现 `evaluate_after_turn()` 的 recent event -> context/signals -> life/tension -> action potential -> self prompt -> intent -> arbitration 管线
- [ ] T008 在 `agent/os_runtime/driver.py` 实现 assisted 模式门控：只允许低风险自然语言/草案 continuation
- [ ] T009 在 `agent/os_runtime/driver.py` 实现预算、完成、暂停、裁判拒绝和错误停止原因

**检查点**: driver 能在单元测试中独立决定是否 continuation。

## 阶段 3: `/os_runtime` 命令

**目的**: 提供 CLI/slash command 状态控制面。

- [ ] T010 [P] 在 `tests/hermes_cli/test_os_runtime_command.py` 覆盖 `status|passive|goal|pause|resume|clear|tick`
- [ ] T011 [P] 在 `tests/hermes_cli/test_os_runtime_command.py` 覆盖 config disabled、empty goal、missing session 错误
- [ ] T012 在 `hermes_cli/os_runtime.py` 实现命令解析与 state 操作
- [ ] T013 在 `hermes_cli/commands.py` 和必要 CLI dispatch 位置注册 `/os_runtime`
- [ ] T014 确保 `/os_runtime pause|clear` 返回 surface 可用于清理 pending synthetic continuation 的标记

**检查点**: 命令测试不需要 gateway/TUI 即可通过。

## 阶段 4: Gateway continuation hook

**目的**: 在 gateway turn 边界接入 os_runtime continuation，并保持用户可打断。

- [ ] T015 [P] 在 `tests/gateway/test_os_runtime_continuation.py` 覆盖 assisted continuation 入队为普通 `MessageEvent`
- [ ] T016 [P] 在 `tests/gateway/test_os_runtime_continuation.py` 覆盖 pause/clear 只移除 os_runtime synthetic continuation，不移除普通用户消息
- [ ] T017 [P] 在 `tests/gateway/test_os_runtime_continuation.py` 覆盖 `os_runtime.enabled=false` 时不影响 `/goal`
- [ ] T018 在 `gateway/run.py` 添加 turn 后 os_runtime hook，复用 adapter FIFO
- [ ] T019 在 `gateway/run.py` 添加 os_runtime synthetic continuation 识别与清理 helper

**检查点**: Gateway 可自动继续低风险 assisted prompt，并可被用户命令清理。

## 阶段 5: TUI continuation hook

**目的**: 与 TUI prompt submit 和 `command.dispatch` 集成。

- [ ] T020 [P] 在 `tests/tui_gateway/test_os_runtime_continuation.py` 覆盖 command.dispatch `/os_runtime` 子命令
- [ ] T021 [P] 在 `tests/tui_gateway/test_os_runtime_continuation.py` 覆盖 turn 后 assisted continuation 触发 `_run_prompt_submit`
- [ ] T022 [P] 在 `tests/tui_gateway/test_os_runtime_continuation.py` 覆盖 pause/clear 清理 pending os_runtime followup
- [ ] T023 在 `tui_gateway/server.py` 添加 `/os_runtime` command.dispatch 处理
- [ ] T024 在 `tui_gateway/server.py` 添加 turn 后 os_runtime hook 和 followup dispatch

**检查点**: TUI 行为与 gateway 保持一致。

## 阶段 6: 回归与收口

**目的**: 验证 `/goal` 兼容和文档约束。

- [ ] T025 运行 `pytest tests/os_runtime/test_driver.py tests/hermes_cli/test_os_runtime_command.py`
- [ ] T026 运行 `pytest tests/gateway/test_os_runtime_continuation.py tests/tui_gateway/test_os_runtime_continuation.py`
- [ ] T027 运行 `pytest tests/gateway/test_goal_status_notice.py tests/tui_gateway/test_goal_command.py`
- [ ] T028 检查实现没有放开工具执行或 Linz World publish

## 依赖关系与执行顺序

- 阶段 1 阻塞后续所有阶段。
- 阶段 2 依赖阶段 1。
- 阶段 3 可在阶段 2 完成后开始。
- 阶段 4 和阶段 5 都依赖阶段 2 与阶段 3，可并行实施。
- 阶段 6 依赖所有实现阶段。

## 并行机会

- 标记 `[P]` 的测试任务可并行。
- Gateway 与 TUI hook 可由不同 Builder 并行实现，但必须共享 driver decision contract。

## 实施策略

先让 driver 在纯单元测试中稳定 fail closed，再接命令面，最后接 gateway/TUI。不要在本模块实现工具执行、world publish、permission ticket 或 receipt。
