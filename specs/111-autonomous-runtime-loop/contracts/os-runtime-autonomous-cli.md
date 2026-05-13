# CLI Contract: os-runtime autonomous

## Command Namespace

```text
hermes os-runtime autonomous <command>
```

## Commands

### status

返回 autonomous runtime 当前状态。

必须包含：

- status
- loop_id
- profile_id/session_id
- last_wake_reason
- last_wake_event_id
- wakes_used/max_wakes_per_hour
- cooldown_until
- last_intent_id
- last_arbitration summary
- paused_reason

### pause

将状态切换为 `paused`，记录 paused_reason。已 queued inbox item 不删除。

### resume

从 `paused` 恢复到 `idle`；不得绕过 cooldown 或 wake budget。

### stop

将状态切换为 `stopped`，停止 scheduler 后续 wake。不得删除 evidence。

### tick

手动触发一次 `manual_tick` wake。若 stopped/paused/cooldown/budget 不允许，返回明确诊断，不启动无预算循环。

### inbox

列出 autonomous inbox item：item_id、event_id、source、status、attempts、created_at、last_error。

### events

列出相关 `os_runtime` event 摘要，默认不输出 raw payload 或 restricted audit content。

### intents

列出最近 OpenIntent/ArbitrationResult 摘要：intent id、action family/type、decision、risk、requires approval、evidence ref。

## 安全输出规则

- 不输出 token、Authorization header、private key、raw Linz payload、restricted audit content。
- 长文本必须摘要化并用 evidence/content ref 指向受控存储。
- publish/tool side effect 状态只能显示裁判和 receipt 摘要，不显示敏感参数。
