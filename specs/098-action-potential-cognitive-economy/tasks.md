# Tasks: 模块 4 行动势能与认知经济

## Phase 1: 协议与测试骨架

- [ ] T001 确认 `ActionPotential` 是否通过 metadata 承载 `recommended_depth`，或最小扩展 domain dataclass。
- [ ] T002 新增 `tests/os_runtime/test_action_potential.py` 的 recommended depth 限定值测试。
- [ ] T003 新增 `tests/os_runtime/test_cognitive_economy.py` 的路径枚举/建议对象测试。

## Phase 2: ActionPotentialEvaluator

- [ ] T004 新增 `agent/os_runtime/engine/action_potential.py`。
- [ ] T005 实现 value/mutual benefit/learning/risk 四类评分与 clamp。
- [ ] T006 实现 `overall_score` 与 `recommended_depth` 规则。
- [ ] T007 为每个评分字段输出 signal/tension/life_state/config evidence。
- [ ] T008 覆盖简单闲聊不触发 continuation。
- [ ] T009 覆盖明确未完成低风险目标可建议 `continue_turn`。
- [ ] T010 覆盖中高风险工具动作降级为审批前置、`sandbox`、`report` 或 `none`。

## Phase 3: CognitiveEconomyController

- [ ] T011 新增 `agent/os_runtime/engine/cognitive_economy.py`。
- [ ] T012 实现 `rule_path`、`auxiliary_small`、`main_model`、`high_reasoning` 建议规则。
- [ ] T013 实现 world compute eligibility，检查配置、登录/token ref、Soul Memory summary、authorization/map。
- [ ] T014 通过 injectable compute/stub 调用 `agent/linz_world/compute.py` 边界并记录 receipt summary。
- [ ] T015 覆盖未登录、缺 token、无 Soul Memory summary、配置禁用时不能选择 `world_compute`。
- [ ] T016 覆盖 receipt rejected/failed 时降级并保留 receipt status。

## Phase 4: 回归

- [ ] T017 运行模块 4 focused tests。
- [ ] T018 运行现有 os_runtime 模块 0/2/3 回归测试。
- [ ] T019 检查 diff 只包含模块 4 实现和测试，不包含模型切换、主循环或工具执行改动。
