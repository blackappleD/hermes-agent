# 功能规范: 模块 3 生命状态、张力解释器与张力场内核

**功能分支**: `097-life-state-tension-field`
**创建时间**: 2026-05-13
**状态**: 草稿
**输入**: OPE-97、`docs/基于张力场的Agent自驱动实现计划.md`、`docs/plans/基于张力场的元神运行时框架技术白皮书.md`

## 背景

Hermes Agent 已经存在 `agent/os_runtime/domain.py`、`agent/os_runtime/engine/signals.py` 和上下文适配器，模块 0/2 的协议对象与 `SignalSet`、`TaskContextView` 投影视图已可作为后续内核输入。本功能是计划文档中的模块 3，目标是在不改写 Hermes 主循环、不执行外部副作用的前提下，补齐白皮书 C/D/A 三个内核：生命状态更新、张力变化解释、张力场网络维护。

当前 issue 明确要求事件解释、生命状态更新和张力网络维护分层。`TensionInterpreter` 只能解释张力变化原因并生成操作；`TensionFieldEngine` 只应用操作并维护 core/dynamic tensions、baseline、activation、trend、confidence、evidence 和 propagation edges。

## 目标

- 提供可测试的 `LifeStateSystem.update()`，根据 `SignalSet`、上一轮 `LifeState` 和执行反馈输出新的 `LifeState` 与可解释 delta。
- 提供只负责解释原因的 `TensionInterpreter.interpret()`，输出 `TensionInterpretation`、`TensionOperation[]` 和解释证据，不直接修改 `TensionSet`。
- 提供 `TensionFieldEngine.update()`，把 `TensionOperation[]` 应用于上一轮 `TensionSet`，维护核心张力、动态张力、网络传播边、休眠/淘汰结果和可审计 delta。
- 让 Linz World 需求、订单、授权、结算、聊天、关系和 Soul Memory summary 等信号能够影响张力解释和后续行动倾向。

## 非目标

- 不实现模块 4 之后的行动势能、Prompt 编译、意图生成、裁判、工具执行或自动自驱动循环。
- 不修改 Hermes `run_agent.py` 主循环、工具执行路径、gateway/NATS 接入或 Linz World 原生身份模块。
- 不引入模型自由解释作为首版规则来源；参数先使用常量或配置默认值。
- 不进行外部发布、授权刷新、结算调用或其他外部副作用。

## 用户场景与测试 *(必填)*

### 用户故事 1 - 生命状态可解释更新 (优先级: P1)

作为 Builder Agent，我需要根据规则化信号更新元神的生命状态，使连续失败、长时间无反馈、高风险信号和正向任务反馈能稳定影响后续行动倾向。

**优先级原因**: 生命状态是张力解释和后续行动势能的基础；没有它无法验证“连续失败降低行动倾向”的核心验收标准。

**独立测试**: 仅实现 `agent/os_runtime/engine/life_state.py` 和 `tests/os_runtime/test_life_state.py` 即可独立验证。

**验收场景**:

1. **给定** 上一轮生命状态为 active 且 `generated_intent_count` 接近阈值，**当** 输入连续失败和高风险审批信号，**那么** `fatigue`、`restraint` 上升，`energy`、`wakefulness` 下降，并返回包含证据的 delta。
2. **给定** 存在明确未完成目标和正向反馈，**当** 更新生命状态，**那么** `curiosity` 或 `creative_pressure` 上升，且不会绕过高风险 restraint。
3. **给定** 长时间无交互或重复低价值事件，**当** 更新生命状态，**那么** `silence_pressure` 或 `boredom` 上升，并可能进入 cooldown/recovering。

---

### 用户故事 2 - 张力解释只产出原因与操作 (优先级: P1)

作为 Builder Agent，我需要一个不会直接改写张力状态的解释器，使每个事件触发的价值冲突、操作类型、证据和可读解释都能被审计。

**优先级原因**: 这是防止“原因解释”和“状态变更”混在一起的核心边界。

**独立测试**: 仅实现 `agent/os_runtime/engine/tension_interpreter.py` 和 `tests/os_runtime/test_tension_interpreter.py`，使用现有 `SignalSet`、`TaskContextView`、`LifeState`、`TensionSet` 构造输入。

**验收场景**:

1. **给定** 明确未完成目标信号，**当** 调用 `interpret()`，**那么** 输出 unsatisfied goal 相关 `generate` 或 `update` 操作，包含 event id、冲突值域、证据和 explanation。
2. **给定** 高风险动作和授权不足信号，**当** 调用 `interpret()`，**那么** 输出“价值收益 vs 风险约束”冲突和 risk/constraint 相关操作。
3. **给定** 已解决、重复或低激活张力，**当** 调用 `interpret()`，**那么** 可输出 `merge`、`hibernate` 或 `eliminate`，但上一轮 `TensionSet` 对象内容不被修改。

---

### 用户故事 3 - 张力场维护可观测网络 (优先级: P2)

作为 Builder Agent，我需要 `TensionFieldEngine` 独立维护张力集合和传播边，使核心/动态张力的强度、趋势、基线、激活度、信心和证据可追踪。

**优先级原因**: 该引擎把解释器产出的操作变成后续模块可消费的张力网络，是模块 3 的交付闭环。

**独立测试**: 仅实现 `agent/os_runtime/engine/tension_field.py` 和 `tests/os_runtime/test_tension_field.py`，用手写 `TensionOperation[]` 验证更新、合并、休眠、淘汰和传播。

**验收场景**:

1. **给定** `generate` 与 `update` 操作，**当** 更新张力场，**那么** dynamic/core tensions 的 `intensity`、`trend`、`baseline`、`activation`、`confidence` 和 `evidence` 发生可解释变化。
2. **给定** 两个相似张力的 `merge` 操作，**当** 更新张力场，**那么** 输出合并后的张力和 `TensionNetworkDelta` 证据链。
3. **给定** 低强度或已解决张力，**当** 应用 `hibernate` 或 `eliminate`，**那么** 张力不会参与高激活输出，但 delta 仍记录原因。

### 边界情况

- 当 `SignalSet` 缺少某类信号时，系统必须保持确定性默认值，不抛出非业务异常。
- 当上一轮 `LifeState` 或 `TensionSet` 为空时，系统必须使用默认初始状态并记录初始化原因。
- 当操作引用不存在的张力时，`update` 可降级为 `generate` 或记录 rejected operation，行为必须可测试。
- 当事件同时包含价值收益和风险约束时，解释器必须保留两个方向，不可只保留正向收益。
- 当授权状态未知或失败时，必须提高 restraint/constraint，而不是把授权变化只作为提示文本。

## 需求 *(必填)*

### 功能需求

- **FR-001**: 系统必须新增 `agent/os_runtime/engine/life_state.py`，提供 `LifeStateSystem.update(signal_set, previous_state, execution_feedback=None)`，输出新 `LifeState` 和 `LifeStateDelta` 或等价可解释 delta。
- **FR-002**: `LifeState` 首版必须覆盖 `energy`、`fatigue`、`health`、`wakefulness`、`curiosity`、`boredom`、`creative_pressure`、`social_hunger`、`silence_pressure`、`restraint`、`life_cycle`、`recovery_cycle`、`generated_intent_count`。
- **FR-003**: 生命状态更新必须支持时间衰减、恢复周期、连续失败、连续 continuation、长耗时、未完成目标、正反馈、长时间无反馈、重复低价值事件、高风险信号和审批需求。
- **FR-004**: 系统必须新增 `agent/os_runtime/engine/tension_interpreter.py`，提供 `TensionInterpreter.interpret(event_ref, signal_set, task_context, life_state, previous_tensions)`。
- **FR-005**: `TensionInterpreter` 必须只生成 `TensionOperation[]`、`TensionInterpretation` 和可读 explanation，不得直接修改上一轮 `TensionSet`。
- **FR-006**: `TensionOperation` 必须覆盖并测试 `update`、`generate`、`merge`、`hibernate`、`eliminate` 五类操作。
- **FR-007**: 解释器输出必须保留 event id、冲突值域、证据、操作原因和可读 explanation。
- **FR-008**: 系统必须新增 `agent/os_runtime/engine/tension_field.py`，提供 `TensionFieldEngine.update(previous_tensions, operations, signal_set, life_state)`。
- **FR-009**: 张力场必须维护 core/dynamic tensions、baseline、activation、trend、trend_slope、confidence、evidence、propagation_edges 和 influence_weight。
- **FR-010**: 张力场必须支持合并同类张力、低激活休眠、已解决淘汰、高冲突激活，并输出 `TensionNetworkDelta` 或等价可审计结果。
- **FR-011**: Linz World 需求/订单、授权不足、结算失败、租金失败、聊天、关系和 Soul Memory summary 信号必须映射到生命状态或张力解释规则。
- **FR-012**: 本模块新增测试必须覆盖 `tests/os_runtime/test_life_state.py`、`tests/os_runtime/test_tension_interpreter.py`、`tests/os_runtime/test_tension_field.py`。

### 关键实体

- **LifeState**: 元神当前行动状态，包含能量、疲劳、健康、唤醒、好奇、无聊、创造压力、社交饥饿、沉默压力、克制和周期字段。
- **LifeStateDelta**: 一次状态更新的字段变化、原因、证据和状态转移摘要。
- **TensionOperation**: 解释器输出的张力操作，覆盖 update/generate/merge/hibernate/eliminate，不直接改变状态。
- **TensionInterpretation / TensionExplanation**: 事件触发的价值冲突、证据和自然语言解释。
- **TensionSet**: core/dynamic tensions 的集合，以及张力网络元数据。
- **TensionNetworkDelta**: 张力场应用操作后的传播边、激活/休眠/淘汰结果和证据。

## 建议方案

按三层实现，不跨层混合职责：

1. `LifeStateSystem` 读取 `SignalSet.signals`、`metadata`、`TaskContextView` 和可选执行反馈，使用规则表计算字段 delta，并通过 clamp 保持数值在约定范围内。
2. `TensionInterpreter` 读取事件、信号、任务上下文、生命状态和上一轮张力快照，识别 value/risk/goal/social/memory/constraint 冲突，生成操作和解释，不修改输入对象。
3. `TensionFieldEngine` 复制上一轮 `TensionSet`，按操作顺序应用 generate/update/merge/hibernate/eliminate，计算 trend/baseline/activation/confidence/evidence 和 propagation edges，返回新 `TensionSet` 与 delta。

## 修改范围

- 新增 `agent/os_runtime/engine/life_state.py`
- 新增 `agent/os_runtime/engine/tension_interpreter.py`
- 新增 `agent/os_runtime/engine/tension_field.py`
- 新增 `tests/os_runtime/test_life_state.py`
- 新增 `tests/os_runtime/test_tension_interpreter.py`
- 新增 `tests/os_runtime/test_tension_field.py`
- 如现有 `agent/os_runtime/domain.py` 缺少 `health`、`trend_slope`、`confidence`、`propagation_edges` 或 delta 对象，可做最小协议扩展，但不得引入外部 runtime 依赖。

## 关键设计

- **分层边界**: LifeState 只更新生命状态；Interpreter 只解释原因和操作；FieldEngine 只维护张力集合与网络。
- **规则优先**: 首版规则由常量/配置默认值驱动，禁止把 LLM 自由解释作为状态变更依据。
- **输入不可变**: Interpreter 和 FieldEngine 的测试必须证明上一轮 `TensionSet` 不被原地改写。
- **证据链**: 每个状态 delta、operation、network delta 必须可追溯到 event id、signal key 或 context metadata。
- **行动抑制**: 连续失败、过度 intent、授权未知和高风险信号必须提升 restraint 或降低 wakefulness/energy。

## 风险与取舍

- 现有 `LifeState` 当前缺少 `health`，`Tension` 当前缺少 `trend_slope` 和 `confidence`；Builder 需要做最小 domain 扩展，避免影响无关协议对象。
- 信号字段来自规则化 `SignalSet.signals`，不同来源命名可能不完全统一；首版应兼容明确 key 和 `metadata` 中的来源摘要，同时保持确定性。
- 张力网络传播容易过度设计；首版只要求可解释的边和权重，不要求复杂图算法。
- 授权和结算信号只影响状态/张力，不做真实外部调用，避免越过模块 3 边界。

## 成功标准 *(必填)*

### 可衡量的结果

- **SC-001**: 连续失败测试能证明 `fatigue`、`restraint` 上升，行动倾向相关字段下降或进入 cooldown。
- **SC-002**: 明确未完成目标测试能稳定生成或增强 unsatisfied goal 张力，并保留 event id 与证据。
- **SC-003**: 高风险动作测试能生成“价值收益 vs 风险约束”解释，并提高 restraint 或 constraint 张力。
- **SC-004**: 解释器测试能覆盖 update/generate/merge/hibernate/eliminate 且证明不直接修改 `TensionSet`。
- **SC-005**: 张力场测试能展示 core/dynamic tensions、baseline、activation、trend/trend_slope、confidence、evidence 和 propagation edges。
- **SC-006**: 授权变化测试能证明后续 action potential 所需的 restraint/constraint 输入发生变化，而不只是生成提示文本。

## 验收标准

- `pytest tests/os_runtime/test_life_state.py tests/os_runtime/test_tension_interpreter.py tests/os_runtime/test_tension_field.py` 通过。
- 现有 `pytest tests/os_runtime/test_domain.py tests/os_runtime/test_signals.py` 不回归。
- 新增模块不导入 Hermes 主循环、gateway、tool execution 或外部 Linz World client。
- 所有新对象均支持 JSON-friendly 输出或可被现有 domain 对象承载。

## 测试计划

- 单元测试 `LifeStateSystem` 默认状态、连续失败、未完成目标、正反馈、无反馈、重复低价值事件、高风险授权信号、intent count 阈值。
- 单元测试 `TensionInterpreter` 对目标、风险、授权、结算、聊天/关系、Soul Memory summary、重复/解决张力的解释与五类 operation。
- 单元测试 `TensionFieldEngine` 对 generate/update/merge/hibernate/eliminate、baseline/activation/trend/confidence、propagation edges 和输入不可变性。
- 回归测试现有 domain round-trip 和 SignalSet 生成规则。

## 后续交接说明

Builder Agent 应先扩展缺失的 domain 字段或 delta 对象，再按 LifeStateSystem -> TensionInterpreter -> TensionFieldEngine 的顺序实现。实现过程中不要接入外部副作用，不要实现模块 4+，不要修改主循环。Spec Reviewer Agent 重点审查分层边界、缺失字段扩展范围和验收测试是否足以约束 Builder。

## 假设

- 模块 0/2 已提供的 `LifeState`、`TensionOperation`、`TensionSet`、`SignalSet` 和 `TaskContextView` 是本功能的协议基础。
- `SignalSet.signals` 中允许出现规则化 key，例如失败、目标、风险、授权、结算、关系、聊天、memory summary 相关信号。
- 本 issue 的实现阶段由 Builder Agent 完成，Planner Agent 本轮只维护 spec-kit artifacts。
