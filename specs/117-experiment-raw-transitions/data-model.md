# 数据模型: 实验脚本与 raw transitions

## ExperimentSeed

人格种子配置，用于初始化 mock 状态或选择真实 runtime profile。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `seed_id` | string | yes | 如 `seed_neutral_001` |
| `name` | string | yes | 元神名称 |
| `role` | string | yes | 角色定位 |
| `bo_bias` / `yue_bias` | number | yes | 博/约倾向 |
| `initial_life_state` | object | yes | energy/stability/confidence/credit/trust/curiosity/stress/fatigue 等 |
| `tension_weights` | object | yes | T_value/T_risk 等权重 |
| `action_thresholds` | object | yes | accept_task/ask_clarify/refuse 等阈值 |
| `metadata` | object | no | 阶段适用性、说明、来源文档 |

必须内置：`seed_neutral_001`、`seed_bold_001`、`seed_prudent_001`、`seed_social_001`、`seed_competitive_001`、`seed_fragile_001`。

## ExperimentEvent

正式事件包络与实验 metadata。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `event_id` | string | yes | 稳定事件 id |
| `subject` | string | yes | 正式事件 subject |
| `event_type` | string | yes | 正式事件 type |
| `payload` | object | yes | 业务 payload，写结果前必须 redacted/hash |
| `expected_effects` | object | no | mock backend 使用的预期 T/AP/Life 变化 |
| `tags` | array | no | P0/P1/P2 等标签 |

## ExperimentScenario

阶段实验定义。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `scenario_id` | string | yes | 如 `P2-C2`、`P4-S1` |
| `phase` | enum | yes | P0-P5 |
| `title` | string | yes | 场景名称 |
| `seed_ids` | array | yes | 参与 seed |
| `event_sequence` | array | yes | event ids 或 inline event refs |
| `repeat` | number | no | P1 默认 3 |
| `tick_policy` | object | no | 衰减/自然时间流设置 |
| `judgement_rules` | array | yes | 方向、幅度、边界、异常判定 |

## RuntimeSnapshot

某个 seed 在某个事件前/后/tick 后的状态。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `life_state` | object | energy/stability/confidence/credit/trust/curiosity/stress/fatigue 等 |
| `tension_field` | object | T_value/T_risk/T_consensus/T_creation/T_survival/T_reputation/T_resource/T_governance |
| `action_potential` | object | AP_* 当前值、排序、delta 来源 |
| `self_prompt` | object | 结构化字段、摘要、原因、evidence refs |
| `open_intent` | object | action family/type、why_now、conditions、tools、source scores |
| `arbitration` | object | decision、bo/yue、risk、constraints、approval、permission/evidence refs |
| `memory_evolution` | object | threshold/preference/memory/relationship delta |

## TransitionRecord

`transitions.jsonl` 的核心行格式。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `run_id` | string | 实验 run |
| `phase` / `scenario_id` | string | 阶段和场景 |
| `seed_id` | string | 当前元神 |
| `event` | object | redacted 正式事件包络 |
| `repeat_index` | number | P1 repeat 或流轮次 |
| `before_state` | RuntimeSnapshot | 事件前 |
| `raw_transitions` | array | event -> context/signals -> life_state -> tension_field -> action_potential -> self_prompt -> open_intent -> arbitration -> action/evidence |
| `after_state` | RuntimeSnapshot | 事件后 |
| `tick_state` | RuntimeSnapshot | tick/衰减后，可为空 |
| `delta_summary` | object | T/AP/Life/threshold/preference/memory/relationship delta |
| `actual_action` | object | action family/type/status |
| `stop_reason` | string | 完成、预算、拒绝、blocked 等 |
| `judgement` | object | pass/warn/fail、原因、异常 refs |
| `evidence_refs` | array | evidence/receipt/audit refs |

## ExperimentRunResult

`summary.json` 的顶层结果。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `run_id` | string | 唯一 run id |
| `mode` | enum | mock/runtime |
| `phases` | array | 已运行阶段 |
| `started_at` / `completed_at` | string | ISO 时间 |
| `counts` | object | events/transitions/scenarios/seeds/anomalies |
| `coverage` | object | 必需阶段/场景/字段覆盖率 |
| `capabilities` | object | runtime capability check 结果 |
| `anomalies` | array | 异常摘要 |
| `files` | object | 输出文件相对路径 |
