# 任务: 实验脚本：共博自制框架阶段验证与 raw transitions 采集

**输入**: `specs/117-experiment-raw-transitions/`  
**前置条件**: spec.md、plan.md、data-model.md、quickstart.md

## 阶段 1: 设置(共享基础设施)

- [ ] T001 创建 `experiment/` package、`experiment/run.py` CLI 入口和 `experiment/results/.gitkeep`。
- [ ] T002 [P] 创建 `tests/experiment/` 测试目录和基础 fixtures。
- [ ] T003 [P] 在 `experiment/config.py` 定义 `ExperimentRunConfig`、phase/mode 参数解析和 run_id 生成。

## 阶段 2: 基础(阻塞前置条件)

- [ ] T004 [P] 在 `experiment/seeds/default_seeds.json` 定义 6 个必需人格种子，并在 `tests/experiment/test_seed_library.py` 覆盖字段完整性。
- [ ] T005 [P] 在 `experiment/events/event_library.json` 定义第 12 节事件和 P0-P5 衍生事件，并在 `tests/experiment/test_event_library.py` 验证正式事件包络。
- [ ] T006 在 `experiment/scenarios/registry.py` 定义 P0-P5 scenario registry，并在 `tests/experiment/test_scenario_registry.py` 验证 P2/P3/P4/P5 覆盖数量。
- [ ] T007 在 `experiment/runtime/base.py` 定义 `RuntimeBackend` 协议和统一 snapshot/transition 返回结构。
- [ ] T008 在 `experiment/collectors/mappings.py` 定义 T/AP/Life/SelfPrompt/OpenIntent/Arbitration 字段映射与缺字段 diagnostics。

**检查点**: seed、event、scenario 和 backend 协议就绪后，用户故事可并行实施。

## 阶段 3: 用户故事 1 - 阶段化运行 P0-P3 机制验证 (优先级: P1)

**目标**: mock 模式可运行 P0-P3，并输出事件级 raw transitions。

**独立测试**: `pytest tests/experiment/test_mock_runtime_transitions.py -k "p0 or p1 or p2 or p3"`

- [ ] T009 [P] [US1] 在 `experiment/runtime/mock_backend.py` 实现 seed 初始化、event apply、tick/decay 和 deterministic delta。
- [ ] T010 [P] [US1] 在 `experiment/collectors/transitions.py` 实现 `TransitionRecord` 构建和 raw chain 收集。
- [ ] T011 [US1] 在 `experiment/run.py` 接入 `--phase P0|P1|P2|P3`、`--repeat` 和 mock backend。
- [ ] T012 [US1] 在 `tests/experiment/test_mock_runtime_transitions.py` 覆盖 P1 repeat=3、tick/decay、方向/幅度/边界 judgement。
- [ ] T013 [US1] 在 `tests/experiment/test_mock_runtime_transitions.py` 覆盖 P2 六类组合的 AP 排序、OpenIntent 来源和 arbitration decision。
- [ ] T014 [US1] 在 `tests/experiment/test_mock_runtime_transitions.py` 覆盖 P3 五类生命状态实验的 before/after delta。

## 阶段 4: 用户故事 2 - P4 持续流自我演化 (优先级: P1)

**目标**: mock 模式可运行 P4 五类持续流，并汇总阈值、偏好、记忆权重变化。

**独立测试**: `pytest tests/experiment/test_mock_runtime_transitions.py -k p4`

- [ ] T015 [P] [US2] 在 `experiment/scenarios/registry.py` 补齐 P4 S1-S5 流的轮次、事件序列和 judgement rules。
- [ ] T016 [US2] 在 `experiment/runtime/mock_backend.py` 增加 threshold/preference/memory delta 生成。
- [ ] T017 [US2] 在 `experiment/reporting/summaries.py` 聚合 P4 evolution summary 和 anomalies。
- [ ] T018 [US2] 在测试中覆盖正反馈、负反馈、规则约束、生存压力、关系记忆五类流。

## 阶段 5: 用户故事 3 - P5 多元神交互实验 (优先级: P1)

**目标**: 支持多 seed 并行或准并行注入事件，比较差异化响应和关系变化。

**独立测试**: `pytest tests/experiment/test_mock_runtime_transitions.py -k p5`

- [ ] T019 [P] [US3] 在 `experiment/scenarios/registry.py` 补齐 P5 M1-M6 场景和参与 seed。
- [ ] T020 [US3] 在 `experiment/runtime/mock_backend.py` 为多 seed 维护隔离状态和关系状态。
- [ ] T021 [US3] 在 `experiment/collectors/transitions.py` 记录每个 seed 的 AP 排序、intent、arbitration 和 relationship delta。
- [ ] T022 [US3] 在 `experiment/reporting/summaries.py` 输出 P5 seed comparison、协作/竞争/求助/拒绝/评价行为统计。
- [ ] T023 [US3] 在测试中覆盖 M1-M6 至少各一条差异化响应断言。

## 阶段 6: 用户故事 4 - 可分析、安全的实验结果 (优先级: P2)

**目标**: 输出稳定 JSONL/CSV/JSON，并保证 redaction。

**独立测试**: `pytest tests/experiment/test_result_writer.py tests/experiment/test_redaction.py`

- [ ] T024 [P] [US4] 在 `experiment/reporting/writer.py` 实现 `manifest.json`、`events.jsonl`、`transitions.jsonl` streaming 写入。
- [ ] T025 [P] [US4] 在 `experiment/reporting/summaries.py` 实现 `summary.json`、`summary.csv`、`anomalies.json`。
- [ ] T026 [US4] 在 `experiment/reporting/writer.py` 复用现有 redaction/hash/bounded summary，必要时提供 fallback。
- [ ] T027 [US4] 在 `tests/experiment/test_result_writer.py` 覆盖 `--phase all --mode mock` 输出文件和字段。
- [ ] T028 [US4] 在 `tests/experiment/test_redaction.py` 覆盖 token、api_key、password、private_key、authorization、restricted payload。

## 阶段 7: Runtime backend 与回归

- [ ] T029 在 `experiment/runtime/os_runtime_backend.py` 实现 runtime capability check，覆盖配置、profile/session、登录/权限、查询能力、evidence repository。
- [ ] T030 在 `experiment/runtime/os_runtime_backend.py` 接入正式事件包络注入或只读查询边界；能力不足时返回 blocked diagnostics。
- [ ] T031 如缺少只读查询入口，新增最小 `agent/os_runtime/adapters/experiment.py`，只读聚合 LifeState/TensionSet/ActionPotential/SelfPrompt/OpenIntent/Arbitration/Evidence，不改变决策语义。
- [ ] T032 为 runtime backend blocked/success 路径补充测试，真实服务依赖必须 mock/stub。
- [ ] T033 运行 quickstart 中的 tests/experiment 聚焦测试和 os_runtime domain/evidence/driver 回归。

## 依赖关系与执行顺序

- 阶段 1 -> 阶段 2 -> 阶段 3 是关键路径。
- 阶段 4 和阶段 5 依赖阶段 3 的 mock backend 与 transition collector。
- 阶段 6 可在阶段 3 后并行推进，但最终需覆盖 P4/P5 输出。
- 阶段 7 最后实施；不得为了 runtime backend 修改核心 runtime 决策。

## 并行机会

- T004/T005/T006 可由不同 Builder 并行准备 seed、event、scenario。
- T024/T025 可与 P4/P5 场景实现并行，只要 `TransitionRecord` schema 已稳定。
- T029/T030 可在 mock 全链路通过后由熟悉 os_runtime/Linz World 的 Builder 单独实现。

## 注意事项

- 所有实现代码放在 `experiment/` 或必要的只读 adapter；不要修改 `docs/`。
- 不提交真实 `experiment/results/<run_id>/` 输出，只保留 `.gitkeep` 或测试 fixtures。
- runtime 模式不得静默回退 mock；blocked 必须在 manifest/summary 中可见。
- 敏感字段泄漏测试必须先写并失败，再实现 redaction。
