# 研究: 模块 6：自治 Runtime Driver

## 决策 1: 复用 `/goal` 的队列模式而非新增后台循环

**结论**: os_runtime continuation 应在 turn 结束后产生普通 user-role prompt，并进入现有 CLI/gateway/TUI 队列。  
**依据**: `hermes_cli/goals.py::GoalManager.evaluate_after_turn()` 已覆盖预算、pause/resume/clear 与 continuation prompt；`gateway/run.py::_post_turn_goal_continuation()` 和 `tui_gateway/server.py` 已有 turn 后排队模式。  
**取舍**: 复用队列会让 os_runtime 受当前 session turn 生命周期限制，但这正好满足用户可打断和无后台无限循环的要求。

## 决策 2: Driver 与 surface 解耦

**结论**: `agent/os_runtime/driver.py` 只返回 decision，不直接操作 gateway/TUI 队列。  
**依据**: gateway 和 TUI 有不同 event/submit 机制；领域 driver 直接依赖这些 surface 会增加测试复杂度。  
**取舍**: surface 需要少量 glue code，但 driver 可用 fake adapters 做稳定单测。

## 决策 3: assisted 首版只允许无外部副作用 continuation

**结论**: `REPORT_ONLY` 或低风险、无工具、无 world publish 的 `AUTO_EXECUTE` 才能继续；其他 arbitration decision 停止。  
**依据**: 宪章要求 fail-closed external side effects；issue 明确首版只支持 passive 和 assisted，允许低风险自然语言或草案 continuation。  
**取舍**: 不会覆盖工具执行自动化，但避免模块 6 与模块 7 的 evidence/receipt 边界混杂。

## 决策 4: State 保存指针与摘要，不保存敏感全文

**结论**: `OSRuntimeState` 保存 last_* id、last arbitration 摘要和 paused_reason；详细事件继续由 `OSRuntimeEventRepository` 或后续 evidence 管理。  
**依据**: 宪章要求 privacy and audit separation；现有 `EventProjectionAdapter` 已有 redaction 和 bounded summary。  
**取舍**: 调试时需要跟随 id 查事件，但避免 prompt/log/state 中出现敏感内容。

## 决策 5: `/goal` 兼容优先

**结论**: `os_runtime.enabled=false` 时不改变 `/goal`；`/os_runtime` 与 `/goal` 首版并行存在，不做破坏性迁移。  
**依据**: issue 验收标准明确 `/goal` 原有行为不变。  
**取舍**: 短期可能有两个目标命令，但能降低回归风险。
