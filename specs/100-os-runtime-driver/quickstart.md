# Quickstart: 模块 6：自治 Runtime Driver

## 前置配置

在临时 Hermes profile 的 config 中启用：

```yaml
os_runtime:
  enabled: true
  mode: assisted
  max_continuation_turns: 3
  allow_auto_continuation: true
  allow_tool_execution: false
```

## 手动验证流程

1. 启动 Hermes CLI 或 TUI。
2. 执行 `/os_runtime status`，应显示无 active goal 或 passive/off 状态。
3. 执行 `/os_runtime passive`，发送一条普通消息，确认不会自动 continuation。
4. 执行 `/os_runtime goal 写一份三段式发布说明草案`。
5. 观察 assisted continuation：应在低风险草案任务中继续，直到完成或预算耗尽。
6. 在 continuation 排队期间执行 `/os_runtime pause`，确认 pending os_runtime continuation 被取消。
7. 执行 `/os_runtime clear`，确认状态清理。

## 测试命令

```bash
pytest tests/os_runtime/test_driver.py
pytest tests/hermes_cli/test_os_runtime_command.py
pytest tests/gateway/test_os_runtime_continuation.py
pytest tests/tui_gateway/test_os_runtime_continuation.py
pytest tests/gateway/test_goal_status_notice.py tests/tui_gateway/test_goal_command.py
```

## 期望结果

- passive 模式不继续。
- assisted 低风险目标会产生普通 user-role continuation prompt。
- pause/clear 可取消 queued synthetic continuation。
- `os_runtime.enabled=false` 时 `/goal` 回归保持不变。
- Linz World 消息不会导致默认 world publish。
