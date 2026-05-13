# 任务: 模块 3 生命状态、张力解释器与张力场内核

**输入**: `specs/097-life-state-tension-field/spec.md`、`plan.md`、`data-model.md`
**前置条件**: Spec Reviewer Agent 审查通过
**测试**: 本 issue 明确要求新增 focused pytest

## 格式: `[ID] [P?] [Story] 描述`

- **[P]**: 可并行，不改同一文件且无直接依赖
- **[Story]**: US1 生命状态、US2 张力解释、US3 张力场

## 阶段 1: 基础协议

- [ ] T001 检查 `agent/os_runtime/domain.py` 现有字段与 spec 差异，最小扩展 `LifeState.health`、`Tension.trend_slope`、`Tension.confidence`、必要 delta/explanation 对象。
- [ ] T002 更新或新增 domain round-trip 测试，验证新增字段 JSON-friendly 且不破坏现有协议。

## 阶段 2: 用户故事 1 - 生命状态可解释更新 (P1)

**目标**: `LifeStateSystem.update()` 能根据信号和反馈输出新状态与 delta。

**独立测试**: `pytest tests/os_runtime/test_life_state.py`

- [ ] T003 [US1] 新增 `tests/os_runtime/test_life_state.py`，覆盖默认初始状态和输入为空的确定性行为。
- [ ] T004 [US1] 新增 `agent/os_runtime/engine/life_state.py`，实现 `LifeStateSystem` 框架、默认阈值、clamp 和 delta 结构。
- [ ] T005 [US1] 实现连续失败、长耗时、连续 continuation 对 `fatigue`、`energy`、`wakefulness`、`restraint` 的影响。
- [ ] T006 [US1] 实现未完成目标、正反馈、机会信号对 `curiosity`、`creative_pressure` 的影响。
- [ ] T007 [US1] 实现长时间无反馈、重复低价值事件、高风险/授权/审批信号对 `silence_pressure`、`boredom`、`restraint`、`life_cycle` 的影响。

## 阶段 3: 用户故事 2 - 张力解释只产出原因与操作 (P1)

**目标**: `TensionInterpreter.interpret()` 识别冲突并生成五类 operation，不修改上一轮 `TensionSet`。

**独立测试**: `pytest tests/os_runtime/test_tension_interpreter.py`

- [ ] T008 [US2] 新增 `tests/os_runtime/test_tension_interpreter.py`，先覆盖未完成目标、高风险授权、输入不可变性和五类 operation。
- [ ] T009 [US2] 新增 `agent/os_runtime/engine/tension_interpreter.py`，实现解释器接口、证据提取和 explanation 输出。
- [ ] T010 [US2] 实现未完成目标、需求/订单、聊天/关系、Soul Memory summary 的 value/social/memory 张力解释规则。
- [ ] T011 [US2] 实现高风险、授权不足、结算失败、租金失败的 constraint/risk 张力解释规则。
- [ ] T012 [US2] 实现重复/相似/低激活/已解决张力对应的 merge/hibernate/eliminate 操作规则。

## 阶段 4: 用户故事 3 - 张力场维护可观测网络 (P2)

**目标**: `TensionFieldEngine.update()` 应用 operation 并输出新 `TensionSet` 与 `TensionNetworkDelta`。

**独立测试**: `pytest tests/os_runtime/test_tension_field.py`

- [ ] T013 [US3] 新增 `tests/os_runtime/test_tension_field.py`，覆盖 generate/update/merge/hibernate/eliminate、传播边和输入不可变性。
- [ ] T014 [US3] 新增 `agent/os_runtime/engine/tension_field.py`，实现引擎接口、copy-on-write 和 delta 输出。
- [ ] T015 [US3] 实现 generate/update 对 intensity、trend、trend_slope、baseline、activation、confidence、evidence 的更新。
- [ ] T016 [US3] 实现 merge/hibernate/eliminate 对 core/dynamic tensions 的处理和 delta 记录。
- [ ] T017 [US3] 实现 propagation_edges/influence_weight 的可解释输出。

## 阶段 5: 集成验证

- [ ] T018 运行 `pytest tests/os_runtime/test_life_state.py tests/os_runtime/test_tension_interpreter.py tests/os_runtime/test_tension_field.py`。
- [ ] T019 运行 `pytest tests/os_runtime/test_domain.py tests/os_runtime/test_signals.py` 回归。
- [ ] T020 检查新增 engine 模块不导入 Hermes 主循环、gateway、tool execution 或 Linz World client。

## 依赖关系与执行顺序

- T001-T002 阻塞所有实现。
- US1 可在 T002 后独立完成。
- US2 依赖 T002 和可用 `LifeState`；不依赖 US3。
- US3 依赖 T002 和 US2 输出的 operation 语义。
- T018-T020 在 US1-US3 完成后执行。

## 并行机会

- T003 与 T008 可并行编写测试框架。
- US1 和 US2 的规则实现可由不同 Builder 并行推进，但都必须基于相同 domain 扩展。
- US3 在 operation 语义稳定后可独立实现。
