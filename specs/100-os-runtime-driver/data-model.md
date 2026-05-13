# 数据模型: 模块 6：自治 Runtime Driver

## OSRuntimeState

Profile-scoped、session-scoped 的 driver 状态。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` | string | Hermes session id |
| `status` | enum | `off`, `passive`, `assisted`, `active`, `paused`, `done`, `cleared` |
| `mode` | string | 当前 config mode，首版支持 `passive`, `assisted` |
| `goal` | string | `/os_runtime goal` 目标文本 |
| `turns_used` | int | 已消耗 continuation/turn 预算 |
| `max_turns` | int | 本轮目标最大 continuation turns |
| `last_tension_interpretation_id` | string | 最近张力解释 id |
| `last_action_potential_id` | string | 最近行动势能 id |
| `last_self_prompt_id` | string | 最近 SelfPrompt id |
| `last_intent_id` | string | 最近 OpenIntent id |
| `last_arbitration` | object | 最近 arbitration 摘要，至少包含 decision/risk/rationale |
| `last_world_event_id` | string | 最近 Linz World event id，如适用 |
| `paused_reason` | string | 暂停原因 |
| `created_at` | string | ISO timestamp |
| `updated_at` | string | ISO timestamp |
| `metadata` | object | 非敏感扩展字段 |

## OSRuntimeDecision

Driver turn 后返回给 surface 的结构。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `status` | string | state 更新后的状态 |
| `should_continue` | bool | 是否应排队 continuation |
| `continuation_prompt` | string/null | 普通 user-role continuation prompt |
| `verdict` | string | `continue`, `done`, `paused`, `rejected`, `skipped`, `error` |
| `reason` | string | 机器可读/短文本原因 |
| `message` | string | 用户可见状态行 |
| `state` | object | 更新后的 state 摘要 |
| `event_id` | string | 触发评估的 recent event id |
| `intent_id` | string | 对应 OpenIntent id |
| `arbitration_id` | string | 对应 arbitration id 或派生 id |

## ContinuationPrompt

必须作为普通 user-role 文本进入队列，不进入 system prompt。

建议内容：

- 当前目标
- why_now 摘要
- success_condition
- stop_condition
- 安全约束：不要执行工具、不要发布 Linz World 正式事件，除非后续模块明确放开

## Synthetic Queue Marker

Gateway/TUI queued event 需要可识别为 os_runtime synthetic continuation。

建议 metadata：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `synthetic` | bool | true |
| `kind` | string | `os_runtime_continuation` |
| `session_id` | string | session id |
| `goal` | string | 目标摘要 |
| `state_id` | string | state or decision id |

## 状态转换

```text
off -> passive
off -> assisted
passive -> assisted
assisted -> paused
assisted -> done
assisted -> cleared
paused -> assisted
paused -> cleared
done -> cleared
```

`active` 作为未来 `autonomous_low_risk` 兼容状态保留；本模块不应把 assisted 自动升级为 active。
