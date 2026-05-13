# 实施计划: 模块 3 生命状态、张力解释器与张力场内核

**分支**: `097-life-state-tension-field` | **日期**: 2026-05-13 | **规范**: `specs/097-life-state-tension-field/spec.md`
**输入**: 来自 `/specs/097-life-state-tension-field/spec.md` 的功能规范

## 摘要

在现有 `agent/os_runtime` 协议对象和 `SignalSet` 生成基础上，实现模块 3 的三个纯领域内核：`LifeStateSystem`、`TensionInterpreter`、`TensionFieldEngine`。实现必须保持事件解释、生命状态变更和张力网络维护三层分离，并通过 focused pytest 覆盖连续失败、未完成目标、高风险授权、张力操作五态和网络传播。

## 技术背景

**语言/版本**: Python 3.11
**主要依赖**: Python 标准库、现有 `agent.os_runtime.domain` dataclass/Enum 协议对象
**存储**: N/A，本模块不持久化状态
**测试**: pytest
**目标平台**: Hermes Agent Python runtime
**项目类型**: Python CLI/runtime library
**性能目标**: 规则计算为内存内确定性操作，单次 update/interpret 不应依赖 I/O 或模型调用
**约束条件**: 不导入主循环、gateway、tool execution、Linz World client；不执行外部副作用
**规模/范围**: 3 个 engine 模块、3 个 focused test 文件、必要时最小扩展 domain 协议字段

## 章程检查

- **Profile-Scoped State**: 通过。本模块不写入运行期状态；只消费调用方传入的 `SignalSet`、`LifeState`、`TensionSet`。
- **Native Surfaces Before Optional Skills**: 通过。新增能力在 `agent/os_runtime/engine/`，不依赖 optional skill。
- **Fail-Closed External Side Effects**: 通过。不做外部调用；授权未知/失败只提升 restraint/constraint。
- **Privacy and Audit Separation**: 通过。只保留 event id、signal key、摘要化 evidence，不要求存储 raw token 或完整私密 payload。
- **Testable Incremental Delivery**: 通过。按生命状态、解释器、张力场三个独立可测故事拆分。

## 项目结构

### 文档(此功能)

```
specs/097-life-state-tension-field/
├── spec.md
├── plan.md
├── data-model.md
├── quickstart.md
└── tasks.md
```

### 源代码(仓库根目录)

```
agent/os_runtime/
├── domain.py
└── engine/
    ├── life_state.py
    ├── tension_interpreter.py
    └── tension_field.py

tests/os_runtime/
├── test_life_state.py
├── test_tension_interpreter.py
└── test_tension_field.py
```

**结构决策**: 使用现有 `agent/os_runtime/engine/`，避免新增 parallel runtime、session store 或外部集成层。

## 关键设计

### LifeStateSystem

- 输入: `SignalSet`、上一轮 `LifeState | None`、可选 `execution_feedback`。
- 输出: 新 `LifeState` 和 `LifeStateDelta` 或等价可审计 delta。
- 规则:
  - 连续失败、长耗时、连续 continuation 提高 `fatigue`，降低 `energy`/`wakefulness`。
  - 未完成高价值目标、正反馈、机会信号提高 `curiosity`/`creative_pressure`。
  - 长时间无反馈提高 `silence_pressure`，重复低价值事件提高 `boredom`。
  - 高风险、授权未知、审批需求、结算失败提高 `restraint`。
  - `generated_intent_count` 到达阈值后进入 cooldown 或提高 restraint。
- 数值字段应 clamp 到稳定范围，默认 0.0-1.0；计数字段保持非负。

### TensionInterpreter

- 输入: `OSRuntimeEventRef`、`SignalSet`、`TaskContextView`、`LifeState`、上一轮 `TensionSet`。
- 输出: `TensionInterpretation`，其中包含 `TensionOperation[]`、detected conflicts、evidence、explanation。
- 只解释原因，不改写 `previous_tensions`。
- 规则优先识别:
  - 未完成目标 -> unsatisfied goal update/generate。
  - 高风险/授权不足/结算失败 -> value vs risk / constraint conflict。
  - 需求/订单 -> value/creative pressure。
  - 聊天/关系 -> social/relationship tension。
  - Soul Memory summary -> core value baseline influence。
  - 重复/相似/已解决张力 -> merge/hibernate/eliminate。

### TensionFieldEngine

- 输入: 上一轮 `TensionSet`、`TensionOperation[]`、`SignalSet`、`LifeState`。
- 输出: 新 `TensionSet` 和 `TensionNetworkDelta`。
- 应用规则:
  - `generate`: 创建 dynamic tension，必要时可标记 core tension。
  - `update`: 调整 intensity、trend、trend_slope、activation、baseline、confidence、evidence。
  - `merge`: 合并重复或高度相关张力，保留来源 evidence。
  - `hibernate`: 降低 activation 并记录 hibernated tension。
  - `eliminate`: 移除已解决/证伪张力并记录原因。
- propagation edges 使用简单可解释权重，不引入复杂图算法。

## 修改范围

- 新增 `agent/os_runtime/engine/life_state.py`
- 新增 `agent/os_runtime/engine/tension_interpreter.py`
- 新增 `agent/os_runtime/engine/tension_field.py`
- 新增 `tests/os_runtime/test_life_state.py`
- 新增 `tests/os_runtime/test_tension_interpreter.py`
- 新增 `tests/os_runtime/test_tension_field.py`
- 允许最小更新 `agent/os_runtime/domain.py` 来补齐 `health`、`trend_slope`、`confidence`、`propagation_edges`、delta 类型或 explanation 类型。

## 风险与取舍

- **协议字段缺口**: 现有 domain 对象不完全覆盖白皮书字段。取舍是最小扩展 domain，不引入第二套对象。
- **信号 key 不统一**: 首版兼容 `signals` 和 `metadata` 中的明确 key，但不做模型解释。
- **网络传播过度复杂**: 首版采用直接边和权重，满足审计与展示，不追求完整图推理。
- **授权语义边界**: 授权变化只影响 restraint/constraint，不调用 Linz World API。

## 验收标准

- 连续失败提高 `fatigue`/`restraint` 并降低行动倾向。
- 未完成目标形成稳定张力。
- 高风险动作形成“价值收益 vs 风险约束”张力。
- 解释器说明事件触发的价值冲突，以及张力为何 update/generate/merge/hibernate/eliminate。
- 张力网络展示核心张力、动态张力、基线、激活度、趋势、信心、证据和传播边。
- 世界授权变化影响后续 action potential 所需输入，而不是只作为提示文本。

## 测试计划

- `pytest tests/os_runtime/test_life_state.py`
- `pytest tests/os_runtime/test_tension_interpreter.py`
- `pytest tests/os_runtime/test_tension_field.py`
- `pytest tests/os_runtime/test_domain.py tests/os_runtime/test_signals.py`

## 后续交接说明

Builder Agent 应按 tasks.md 顺序实现，先补齐协议字段和 delta 对象，再实现 LifeStateSystem、TensionInterpreter、TensionFieldEngine。不要实现模块 4+，不要接入外部副作用，不要改 Hermes 主循环。Spec Reviewer Agent 应重点审查本计划是否充分约束分层职责和测试覆盖。
