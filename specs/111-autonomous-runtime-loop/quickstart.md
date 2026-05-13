# Quickstart: 模块 6.5 常驻 Autonomous Runtime Loop

## 配置示例

```yaml
os_runtime:
  enabled: true
  mode: autonomous_low_risk
  autonomous:
    enabled: true
    start_on_agent_load: true
    start_with_gateway: true
    apply_to_all_turns: true
    pre_turn_evaluation: true
    post_turn_evaluation: true
    inject_self_prompt: true
    respond_to_world_events: true
    tick_interval_seconds: 30
    idle_cooldown_seconds: 60
    max_turns_per_wake: 3
    max_wakes_per_hour: 20
    allow_tool_execution: false
    allow_world_publish: false
    require_approval_for_world_publish: true
```

## 手动验证路径

1. 启动 CLI 或 gateway，并确保 `os_runtime.enabled=true`、`mode=autonomous_low_risk`、`autonomous.enabled=true`。
2. 执行 `hermes os-runtime autonomous status`，确认状态为 `idle` 或 `sleeping`。
3. 直接发送普通用户消息，不输入 `/os_runtime goal`。
4. 查询 `hermes os-runtime autonomous events`，确认产生 `human_request` 或 `conversation_turn` 投影事件。
5. 若 `inject_self_prompt=true`，通过测试或调试输出确认当前轮 user context 有 ephemeral SelfPrompt，system prompt 未变。
6. 执行 `hermes os-runtime autonomous tick`，确认产生 `manual_tick` wake evidence。
7. 注入一条已持久化、未重复的 Linz World MessageEvent，确认 `inbox` 出现 item，loop 生成 intent/arbitration/evidence。
8. 确认默认配置下不会自动 `linz_publish`，只生成 report、草案或审批请求。

## 推荐测试命令

```bash
pytest tests/os_runtime
pytest tests/gateway/test_os_runtime_continuation.py tests/gateway/test_os_runtime_autonomous_loop.py
```

如 gateway autonomous 测试文件尚未存在，Builder 应在实现本模块时新增。
