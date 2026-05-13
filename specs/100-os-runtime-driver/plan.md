# 实施计划: 模块 6：自治 Runtime Driver

**分支**: `feat/100-os-runtime-driver` | **日期**: 2026-05-13 | **规范**: `specs/100-os-runtime-driver/spec.md`  
**输入**: 来自 `specs/100-os-runtime-driver/spec.md` 的功能规范

## 摘要

新增 os_runtime driver，把模块 0-5 的事件、上下文、信号、生命状态、张力、势能、SelfPrompt、Intent 与 BoYueArbiter 串成 turn 后决策链。首版只交付 passive 和 assisted：passive 记录状态不继续；assisted 只允许低风险、无外部副作用的自然语言或草案 continuation。Gateway/TUI/CLI 复用 `/goal` 的预算、状态命令和 FIFO 队列集成方式，保证用户可打断、暂停和清除。

## 技术背景

**语言/版本**: Python 3.x，沿用仓库当前运行环境  
**主要依赖**: 标准库、现有 Hermes modules、现有 os_runtime modules；不新增必需依赖  
**存储**: profile-scoped Hermes state，优先复用 `OSRuntimeEventRepository` / `state.db` side tables；driver state 可使用同 profile 下轻量状态存储  
**测试**: pytest  
**目标平台**: Hermes CLI、gateway、TUI gateway  
**项目类型**: Python CLI/runtime/gateway  
**性能目标**: 每个 turn 后的 driver 评估应为同步、短路径、可被 fake engine 单测覆盖；不得引入后台长轮询  
**约束条件**: `os_runtime.enabled=false` 时零行为变化；自动 continuation 必须可预算限制和用户打断  
**规模/范围**: 单 repo，新增 2 个模块、扩展 2 个 runtime hook、4 组测试

## 章程检查

- **Profile-Scoped State**: PASS。driver state 和事件必须以 session/profile 为边界，不写全局目录。
- **Native Surfaces Before Optional Skills**: PASS。`/os_runtime` 是 Hermes 原生命令，不依赖 skill。
- **Fail-Closed External Side Effects**: PASS。assisted 首版不允许工具执行或 world publish；裁判拒绝、审批、异常均停止。
- **Privacy and Audit Separation**: PASS。state 仅保存摘要/id；敏感原文仍由现有 redaction/event repository 处理。
- **Testable Incremental Delivery**: PASS。任务按 passive driver、assisted driver、CLI、gateway/TUI 四个可独立测试切片组织。

## 项目结构

### 文档(此功能)

```text
specs/100-os-runtime-driver/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── os-runtime-cli.md
└── tasks.md
```

### 源代码(仓库根目录)

```text
agent/os_runtime/
├── driver.py
├── config.py
├── domain.py
├── adapters/
└── engine/

hermes_cli/
├── os_runtime.py
├── commands.py
└── main.py

gateway/
└── run.py

tui_gateway/
└── server.py

tests/
├── os_runtime/test_driver.py
├── hermes_cli/test_os_runtime_command.py
├── gateway/test_os_runtime_continuation.py
└── tui_gateway/test_os_runtime_continuation.py
```

**结构决策**: 采用单一 Python 项目布局。driver 只放在 `agent/os_runtime`，命令解析放在 `hermes_cli`，queue hook 分别在 gateway/TUI 现有 `/goal` turn 边界附近扩展。

## 阶段 0 研究结论

- 复用 `/goal` 的状态机语义，但不要把 `/goal` judge 迁入 os_runtime。
- continuation prompt 必须继续走普通 user-role queue，避免 system prompt 污染。
- assisted 首版只允许 `REPORT_ONLY` 或低风险无工具 `AUTO_EXECUTE`；`SANDBOX_EXECUTE`、`REQUIRE_APPROVAL`、`REJECT` 均停止。
- Gateway/TUI 清理逻辑必须能识别 os_runtime synthetic event，避免误删普通用户消息。

## 阶段 1 设计

### Driver

`OSRuntimeDriver.evaluate_after_turn()` 输入 session、final_response、source metadata 和可注入 engine/adapters。输出 `OSRuntimeDecision`：

- disabled/inactive/passive -> `should_continue=false`
- assisted + low-risk allowed -> `should_continue=true`
- budget/paused/done/user interruption/arbitration denied/error -> `should_continue=false`

Driver 负责更新 `OSRuntimeState`，但不直接执行 gateway/TUI queue 操作。

### CLI/slash command

`hermes_cli/os_runtime.py` 提供解析函数，例如 `handle_os_runtime_command(arg, session_id, config)`，供 CLI、gateway 和 TUI 复用。命令行为：

- `status`: 显示状态、目标、turn budget、last arbitration。
- `passive`: 设置 passive 状态。
- `goal <text>`: 设置 assisted 目标并返回 kickoff 文本。
- `pause|resume|clear`: 更新 state；pause/clear 需要调用 surface hook 清理 queued continuation。
- `tick`: 手动执行一次 driver 评估，但仍遵守 mode gates。

### Gateway/TUI

在现有 `/goal` turn 后 hook 附近调用 os_runtime hook。若 decision 允许 continuation，则构造普通 `MessageEvent` 或 TUI prompt submit。pause/clear 需要删除 synthetic os_runtime continuation。

## 复杂度跟踪

| 违规 | 为什么需要 | 拒绝更简单替代方案的原因 |
| --- | --- | --- |
| 无 | 无 | 无 |

## 风险

- 双 loop 风险：`/goal` 和 `/os_runtime goal` 同时激活时可能产生多个 continuation。实现应检查并提示状态，避免隐式互相触发。
- 状态落库风险：若 driver state 与 event repository 分离，必须保持 profile-scoped 和 session-scoped。
- 队列误删风险：pause/clear 只能移除 os_runtime synthetic continuation，不能移除普通用户消息。
- 外部副作用风险：Linz World message 只可触发 assisted continuation，不可默认 publish。

## 验收标准

- `os_runtime.enabled=false` 时 `/goal` 原有测试通过且行为不变。
- passive 模式只记录 state/intent/arbitration，不 continuation。
- assisted 模式低风险文档目标可自动继续。
- 预算耗尽、完成、用户打断、pause/clear、裁判拒绝停止。
- gateway/TUI 队列可清理 os_runtime continuation。
- continuation prompt 是普通 user-role 消息。

## 测试计划

- Unit: `tests/os_runtime/test_driver.py`
- CLI: `tests/hermes_cli/test_os_runtime_command.py`
- Gateway integration: `tests/gateway/test_os_runtime_continuation.py`
- TUI integration: `tests/tui_gateway/test_os_runtime_continuation.py`
- Regression: `tests/gateway/test_goal_status_notice.py`, `tests/tui_gateway/test_goal_command.py`
