# 任务: 模块 5 SelfPrompt、OpenIntent 与 BoYueArbiter

**输入**: `specs/099-module-5-selfprompt-openintent-arbiter/spec.md`、`plan.md`
**前置条件**: Spec Reviewer Agent 审查通过；模块 4 的 `ActionPotential` 输入协议可用
**测试**: 本 issue 明确要求新增 focused pytest

## 格式: `[ID] [P?] [Story] 描述`

- **[P]**: 可并行，不改同一文件且无直接依赖
- **[Story]**: US1 SelfPrompt、US2 OpenIntent、US3 BoYueArbiter

## 阶段 1: 基础协议与依赖确认

- [x] T001 检查模块 4 `ActionPotential` 可用性；若 `action_potential.py` 未合并，使用现有 `ActionPotential` dataclass 作为输入协议并记录 implementation blocker。
- [x] T002 最小更新 `agent/os_runtime/domain.py`，为 `SelfPrompt`/`OpenIntent` 补齐 `open_space`、`target_direction`，并为 `ArbitrationResult` 支持博/约/合细分评分字段或 metadata helper。
- [x] T003 更新或新增 domain round-trip 测试，验证新增字段 JSON-friendly 且不破坏现有 protocol 对象。

## 阶段 2: 用户故事 1 - 结构化 SelfPrompt 编译 (P1)

**目标**: `SelfPromptCompiler.compile()` 输出可追溯 SelfPrompt，并可通过 ephemeral context 注入当前轮。

**独立测试**: `pytest tests/os_runtime/test_prompt_compiler.py`

- [x] T004 [US1] 新增 `tests/os_runtime/test_prompt_compiler.py`，覆盖完整输入、缺省输入、约束保留和 evidence refs。
- [x] T005 [US1] 新增 `agent/os_runtime/engine/prompt_compiler.py`，实现 `SelfPromptCompiler` 接口、输入 DTO 兼容和 JSON-friendly 输出。
- [x] T006 [US1] 实现 state/tension/potential summary 编译规则，覆盖 `LifeState`、`TensionSet`、`TensionExplanation`、`ActionPotential`。
- [x] T007 [US1] 实现 memory/constraint/environment scope、`OpenSpace`、`TargetDirection` 生成规则。
- [x] T008 [US1] 实现或暴露薄 `pre_llm_call` adapter，测试 stable system prompt 不变且 SelfPrompt 进入 ephemeral context。

## 阶段 3: 用户故事 2 - 开放意图规则优先生成 (P1)

**目标**: `OpenIntentGenerator.generate()` 默认走规则路径，LLM JSON 失败安全回退。

**独立测试**: `pytest tests/os_runtime/test_intent_generator.py`

- [x] T009 [US2] 新增 `tests/os_runtime/test_intent_generator.py`，覆盖规则路径、LLM JSON 成功、非法 JSON、未知 enum、缺必填字段。
- [x] T010 [US2] 新增 `agent/os_runtime/engine/intent_generator.py`，实现 generator 接口、schema 校验和 action family enum 映射。
- [x] T011 [US2] 实现规则路径：根据 `ActionPotential`、`OpenSpace`、`TargetDirection`、constraints 和 available tools 生成固定 schema intent。
- [x] T012 [US2] 实现可选 LLM JSON 解析路径；非法 JSON 或 schema 失败时回退规则路径并记录 `fallback_reason`。
- [x] T013 [US2] 增加 subject/event_type 防伪造测试，证明 LLM 输出不能绕过 `linz_world.event_catalog`。

## 阶段 4: 用户故事 3 - BoYueArbiter 执行前裁判 (P1)

**目标**: `BoYueArbiter.arbitrate()` 输出五类主 decision，并 fail-closed 阻断高风险和缺治理条件的 intent。

**独立测试**: `pytest tests/os_runtime/test_arbiter.py`

- [x] T014 [US3] 新增 `tests/os_runtime/test_arbiter.py`，覆盖五类 decision、博/约/合评分、高风险阻断和 approval 需求。
- [x] T015 [US3] 新增 `agent/os_runtime/engine/arbiter.py`，实现 arbiter 接口、评分结构和有限 decision 输出。
- [x] T016 [US3] 实现低风险 report/sandbox/auto 规则，以及高风险、未知工具、外部副作用默认 require approval/reject 规则。
- [x] T017 [US3] 实现 PolicyEngine、event catalog、authorization map 的 fake preflight 接口适配和 fail-closed 判定。
- [x] T018 [US3] 实现或暴露薄 `pre_tool_call` adapter，测试超出裁判范围、缺 approval、缺 catalog 或缺 authorization 的工具调用被阻断。

## 阶段 5: 集成验证

- [x] T019 运行 `pytest tests/os_runtime/test_prompt_compiler.py tests/os_runtime/test_intent_generator.py tests/os_runtime/test_arbiter.py`。
- [x] T020 运行 `pytest tests/os_runtime/test_domain.py tests/os_runtime/test_signals.py tests/os_runtime/test_life_state.py tests/os_runtime/test_tension_interpreter.py tests/os_runtime/test_tension_field.py` 回归。
- [x] T021 检查新增 engine 模块默认不调用网络、真实 LLM、真实工具、真实 Linz World 服务或外部发布。

## 依赖关系与执行顺序

- T001-T003 阻塞所有实现。
- US1 可在 T003 后独立完成。
- US2 依赖 US1 产出的 `SelfPrompt` schema 和可用 `ActionPotential` 输入。
- US3 依赖 US2 的 `OpenIntent` schema。
- T019-T021 在 US1-US3 完成后执行。

## 并行机会

- T004、T009、T014 可并行编写测试框架。
- T005-T007 可与 T010-T012 在 schema 稳定后部分并行，但同一 domain 字段变更需先完成 T002。
- T017 的 fake policy/catalog/auth preflight 可与 T015 的 arbiter 框架并行。
