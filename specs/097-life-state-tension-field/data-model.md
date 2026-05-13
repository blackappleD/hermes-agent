# 数据模型: 模块 3 生命状态、张力解释器与张力场内核

## Existing Protocol Inputs

- `OSRuntimeEventRef`: event id、source、trace/session/timestamp、summary 和 metadata。
- `SignalSet`: event refs、task context、agent context、signals、metadata。
- `TaskContextView`: task/session/user goal/active goal/recent event ids/memory refs/tool names/constraints。
- `LifeState`: 生命状态字段；Builder 需要补齐 `health`。
- `TensionOperation`: 操作类型、tension id/type、delta、reason、evidence、metadata。
- `TensionInterpretation`: event id、detected conflicts、operations、explanation、evidence、metadata。
- `Tension`: 张力字段；Builder 需要补齐 `trend_slope`、`confidence`，并通过 metadata 或字段承载网络信息。
- `TensionSet`: core/dynamic tensions、timestamp、metadata。
- `TensionNetworkDelta`: operations、propagation edges、activated/hibernated tensions、metadata。

## New Or Extended Entities

### LifeStateDelta

Purpose: Record one deterministic life-state transition.

Fields:

- `previous`: Optional `LifeState` snapshot or compact dict.
- `current`: New `LifeState`.
- `changes`: dict from field name to `{before, after, delta}`.
- `reasons`: list of readable rule reasons.
- `evidence`: list of event ids, signal keys, or metadata references.
- `metadata`: rule version, thresholds, lifecycle transition.

### TensionExplanation

Purpose: Keep a readable explanation separate from state mutation.

Fields:

- `event_id`
- `detected_conflicts`
- `operation_reasons`
- `evidence`
- `summary`

This may be represented as an explicit dataclass or as structured metadata inside `TensionInterpretation`, as long as tests can assert the content.

### Tension Propagation Edge

Purpose: Represent explainable influence between tensions.

Fields:

- `source_tension_id`
- `target_tension_id`
- `relation`
- `influence_weight`
- `evidence`

This may remain inside `TensionNetworkDelta.propagation_edges` and/or `TensionSet.metadata`.

## Relationships

- `LifeStateSystem.update()` consumes `SignalSet` and returns `LifeState` plus `LifeStateDelta`.
- `TensionInterpreter.interpret()` consumes `OSRuntimeEventRef`, `SignalSet`, `TaskContextView`, `LifeState`, `TensionSet` and returns `TensionInterpretation` with operations.
- `TensionFieldEngine.update()` consumes `TensionSet`, operations, `SignalSet`, `LifeState` and returns new `TensionSet` plus `TensionNetworkDelta`.

## Validation Rules

- Numeric state fields clamp to stable bounds, normally 0.0 through 1.0.
- `generated_intent_count` must remain non-negative.
- Operation type must be one of update/generate/merge/hibernate/eliminate.
- Evidence lists must not contain raw tokens or unrestricted private payloads.
- Interpreter and field engine must not mutate previous input objects in place.
