# 数据模型: 模块 6.5 常驻 Autonomous Runtime Loop

## AutonomousRuntimeConfig

配置来源为 `os_runtime.autonomous`，默认关闭。

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| enabled | bool | false | 是否启用常驻 autonomous runtime |
| start_on_agent_load | bool | false | Agent/profile 加载时是否启动 scheduler |
| start_with_gateway | bool | false | gateway/runtime 启动时是否启动 scheduler |
| apply_to_all_turns | bool | false | 普通 CLI/TUI/gateway turn 是否进入张力 hook |
| pre_turn_evaluation | bool | true | 是否执行 before_turn |
| post_turn_evaluation | bool | true | 是否执行 after_turn |
| inject_self_prompt | bool | false | 是否注入当前轮 ephemeral SelfPrompt |
| respond_to_world_events | bool | true | 是否允许世界事件 wake |
| tick_interval_seconds | int | 30 | scheduler tick 间隔；0 表示禁用周期 tick |
| idle_cooldown_seconds | int | 60 | wake 后休眠冷却 |
| max_turns_per_wake | int | 3 | 单次 wake 最多推进轮数 |
| max_wakes_per_hour | int | 20 | 每小时 wake 预算 |
| allow_tool_execution | bool | false | 是否允许 autonomous tool execution |
| allow_world_publish | bool | false | 是否允许 autonomous world publish 候选 |
| require_approval_for_world_publish | bool | true | world publish 是否必须审批 |

## AutonomousRuntimeState

每个 profile/session 保存一份可序列化状态。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| status | enum | `stopped | idle | sleeping | evaluating | acting | paused | failed` |
| loop_id | string | 当前 loop 实例标识 |
| profile_id | string | 当前 Hermes profile 标识 |
| session_id | string | 当前 session 标识 |
| level | enum | `tension_observed | tension_driven` |
| last_wake_reason | string | `world_event | tick | manual_tick | turn_feedback | internal_feedback` |
| last_wake_event_id | string | 最近一次 wake 来源事件 |
| last_turn_event_id | string | 最近一次 turn 投影事件 |
| last_tick_at | timestamp | 最近一次 tick 时间 |
| wakes_used | int | 当前小时已用 wake 数 |
| max_wakes_per_hour | int | 当前预算上限 |
| cooldown_until | timestamp | 下次允许 wake 时间 |
| last_intent_id | string | 最近 OpenIntent id |
| last_arbitration | object | 最近 ArbitrationResult 摘要 |
| last_action_summary | string | 最近行动摘要 |
| paused_reason | string | pause/stop/failure 原因 |

## AutonomousInboxItem

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| item_id | string | inbox item id |
| event_id | string | 去重事件 id |
| wake_reason | string | wake reason |
| source | string | `linz_world | runtime_feedback | tick | manual` |
| event_ref | object | 已持久化事件引用，不包含 raw secret |
| status | enum | `queued | processing | handled | skipped | failed` |
| attempts | int | 处理次数 |
| last_error | string | 最近错误摘要 |
| created_at | timestamp | 入队时间 |
| updated_at | timestamp | 更新时间 |

## AutonomousWakeRecord

每次 wake 生成 evidence record。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| wake_id | string | wake record id |
| loop_id | string | loop id |
| wake_reason | string | wake 来源 |
| event_id | string | 来源事件 |
| started_at | timestamp | 开始时间 |
| stopped_at | timestamp | 结束时间 |
| stop_reason | string | `completed | budget_exhausted | cooldown | paused | rejected | error` |
| life_state_ref | string | LifeState evidence ref |
| top_tensions | list | 张力摘要 |
| action_potential_ref | string | ActionPotential ref |
| self_prompt_ref | string | SelfPrompt ref |
| intent_ref | string | OpenIntent ref |
| arbitration_ref | string | ArbitrationResult ref |
| action_summary | string | 生成的 report/草案/审批摘要 |

## TurnTensionEvaluation

before/after turn 返回给调用侧的短生命周期对象。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| status | string | `skipped | observed | injected | error` |
| event_id | string | 投影事件 |
| self_prompt_id | string | 可选 SelfPrompt |
| injection_applied | bool | 是否改变当前轮 user context |
| fail_open | bool | 是否因错误保持普通对话继续 |
| side_effect_allowed | bool | 外部副作用是否允许；错误时必须 false |
| diagnostics | object | 脱敏诊断 |

## 状态转换

```text
stopped -> idle         # start
idle -> evaluating      # wake accepted
sleeping -> evaluating  # wake accepted after cooldown
evaluating -> acting    # intent/arbitration allows report/draft/internal action
evaluating -> sleeping  # no action or cooldown
acting -> sleeping      # action/evidence recorded
idle|sleeping|evaluating|acting -> paused   # user pause
paused -> idle          # user resume
any -> stopped          # user stop
any -> failed           # unrecoverable state error
failed -> idle          # explicit resume/reset only
```
