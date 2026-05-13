# 功能规范: 模块 5 SelfPrompt、OpenIntent 与 BoYueArbiter

**功能分支**: `099-module-5-selfprompt-openintent-arbiter`
**创建时间**: 2026-05-13
**状态**: 草稿
**输入**: OPE-99、`docs/基于张力场的Agent自驱动实现计划.md`、现有 `agent/os_runtime` 协议与前序模块 specs

## 背景

Hermes Agent 已有 `agent/os_runtime/domain.py` 中的 `SelfPrompt`、`OpenIntent`、`ArbitrationResult` 等协议对象，以及模块 2/3 的上下文、信号、生命状态、张力解释和张力场基础。OPE-99 是计划文档中的模块 5，目标是把张力状态和行动势能转成可解释的开放意图，并在任何执行前通过 BoYueArbiter 与后续 policy 边界裁判。

当前仓库尚未看到模块 4 的 `agent/os_runtime/engine/action_potential.py` spec/实现落地，但 `ActionPotential` 协议对象已存在。本模块应设计为消费模块 4 产出的 `ActionPotential`，不在本 issue 里重新实现行动势能计算。

## 目标

- 新增 `SelfPromptCompiler`，把 `TaskContextView`、`LifeState`、`TensionSet`、`TensionExplanation`、`ActionPotential`、规则/记忆/约束/环境输入编译为结构化 `SelfPrompt`。
- 通过 `pre_llm_call` hook 将自治上下文作为 ephemeral context 注入当前 user message，不修改 Hermes 稳定 system prompt，不破坏 prompt cache。
- 新增 `OpenIntentGenerator`，首版以规则路径生成固定 schema `OpenIntent`；LLM JSON 路径解析失败时必须回退规则路径，且不得执行行动。
- 新增 `BoYueArbiter`，把 intent 裁决为 `auto_execute`、`sandbox_execute`、`require_approval`、`report_only`、`reject` 五类主结果。
- 明确 Linz World publish 的治理边界：必须同时通过 Arbiter、PolicyEngine、`linz_world.event_catalog` 和 authorization map。

## 非目标

- 不实现模块 4 的 `ActionPotentialEvaluator`、认知经济路由或 action potential 计算。
- 不实现模块 6 的自治 runtime driver、无限循环或自动 continuation 调度。
- 不重写 Hermes system prompt、主循环、工具执行框架、Linz World publisher 或 event catalog。
- 不让 LLM 自由决定 subject/event_type、权限、身份或最终执行许可。
- 不在本模块执行外部副作用；本模块只生成 prompt、intent、裁判结果和可供后续 policy 使用的约束。

## 用户场景与测试 *(必填)*

### 用户故事 1 - 结构化 SelfPrompt 编译 (优先级: P1)

作为 Builder Agent，我需要一个不会修改稳定 system prompt 的编译器，把生命状态、张力解释、行动势能、记忆范围、约束和环境转成当前轮可注入的自我提示。

**优先级原因**: 没有可追溯的 `SelfPrompt`，后续开放意图无法解释 `open_space`、`target_direction` 和 `why_now` 的来源。

**独立测试**: 仅实现 `agent/os_runtime/engine/prompt_compiler.py` 与 `tests/os_runtime/test_prompt_compiler.py`，使用 fake context/life/tension/action potential 输入验证输出。

**验收场景**:

1. **给定** 明确的 task context、life state、tension explanation 和 action potential，**当** 编译 `SelfPrompt`，**那么** 输出包含 `state_summary`、`tension_summary`、`potential_summary`、`memory_scope`、`constraint_scope`、`environment_scope`、`open_space`、`target_direction`。
2. **给定** prompt cache 已依赖稳定 system prompt，**当** 通过 hook 注入自治上下文，**那么** stable system prompt 不变，ephemeral context 只进入当前 user message 或等价当前轮上下文。
3. **给定** 存在授权未知、高风险或缺少 event catalog 的约束，**当** 编译 prompt，**那么** `constraint_scope` 明确保留 fail-closed 原因。

---

### 用户故事 2 - 开放意图规则优先生成 (优先级: P1)

作为 Builder Agent，我需要 `OpenIntentGenerator` 从 `SelfPrompt` 和 `ActionPotential` 生成可解释 intent，并在 LLM JSON 失败时安全回退规则路径且不执行行动。

**优先级原因**: 开放意图是执行前最后一个语义决策层，必须能解释为什么现在行动、行动属于什么 family、成功/停止条件是什么。

**独立测试**: 仅实现 `agent/os_runtime/engine/intent_generator.py` 与 `tests/os_runtime/test_intent_generator.py`，mock LLM JSON 成功、非法 JSON 和缺失字段场景。

**验收场景**:

1. **给定** 高 value/learning 且低 risk 的 `ActionPotential`，**当** 走规则路径生成 intent，**那么** intent 包含 action family、action type、why_now、open_space、target_direction、tools_needed、success_condition、stop_condition。
2. **给定** LLM 返回非法 JSON、未知 action family 或缺少必填字段，**当** 生成 intent，**那么** 系统回退规则 intent，标记 fallback reason，且不输出执行许可。
3. **给定** LLM 尝试自造 Linz World subject/event_type，**当** 解析 intent，**那么** 该字段不被采信，intent 只能携带需要 catalog 校验的候选 metadata。

---

### 用户故事 3 - BoYueArbiter 执行前裁判 (优先级: P1)

作为 Builder Agent，我需要裁判器把开放意图裁决为有限的主结果，并对高风险、缺授权、缺 catalog 或越界工具调用 fail-closed。

**优先级原因**: 这是阻止开放意图直接进入工具执行或世界发布的核心安全边界。

**独立测试**: 仅实现 `agent/os_runtime/engine/arbiter.py` 与 `tests/os_runtime/test_arbiter.py`，用 fake policy/event catalog/authorization map 验证裁判。

**验收场景**:

1. **给定** 低风险草案或自然语言回复 intent，**当** 裁判，**那么** 可返回 `report_only`、`sandbox_execute` 或在明确配置允许时 `auto_execute`。
2. **给定** 高风险、外部副作用、未知工具、授权缺失或 catalog 未确认 intent，**当** 裁判，**那么** 返回 `require_approval` 或 `reject`，不返回执行许可。
3. **给定** Linz World publish intent，**当** subject/event_type 不在 `linz_world.event_catalog` 或 authorization map 不允许，**那么** 裁判必须 reject 或 require approval，不能直接进入工具执行。

### 边界情况

- 模块 4 未完成或 `ActionPotential` 缺少 recommended depth 时，本模块实现必须使用明确默认值并记录 diagnostics，不重新计算 action potential。
- `SelfPrompt` 输入缺少 tension explanation 或 memory refs 时，编译器必须输出空范围/约束摘要，而不是抛出非业务异常。
- LLM JSON 路径超时、非法 JSON、未知 enum、缺必填字段或包含非 catalog publish 字段时，必须回退规则路径并标记不允许执行。
- 迁移期别名 `allow_reply`、`allow_draft`、`allow_sandbox`、`allow_tool`、`allow_world_publish` 只能进入兼容 metadata，不得成为新 evidence 的主裁判结果。
- `auto_execute` 只允许低风险、无外部副作用、策略明确允许的 intent；高风险 intent 不得直接进入工具执行。

## 需求 *(必填)*

### 功能需求

- **FR-001**: 系统必须新增 `agent/os_runtime/engine/prompt_compiler.py`，提供 `SelfPromptCompiler.compile(...)`，输出结构化 `SelfPrompt`。
- **FR-002**: `SelfPrompt` 输出必须至少包含 `state_summary`、`tension_summary`、`potential_summary`、`memory_scope`、`constraint_scope`、`environment_scope`、`open_space`、`target_direction`。
- **FR-003**: 编译器必须保留输入证据引用，至少能追溯到 event id、tension id、action potential id 或 context metadata。
- **FR-004**: 系统必须提供 `pre_llm_call` hook 适配入口，把 `SelfPrompt` 作为 ephemeral context 注入当前轮 user context，不修改稳定 system prompt。
- **FR-005**: 系统必须新增 `agent/os_runtime/engine/intent_generator.py`，提供规则优先的 `OpenIntentGenerator.generate(...)`。
- **FR-006**: `OpenIntent` 必须包含 `action_family`、`action_type`、`why_now`、`open_space`、`target_direction`、`tools_needed`、`proposed_new_tools`、`proposed_new_skills`、`success_condition`、`stop_condition`。
- **FR-007**: action family 主集合必须限制为 `communicate`、`learn`、`trade`、`collaborate`、`rest`、`create`、`new_tool`、`new_skill`。
- **FR-008**: LLM JSON 路径解析失败、schema 校验失败或枚举非法时，必须回退规则路径，且不得产生 `PermissionTicket`、`ExecutionReceipt` 或执行许可。
- **FR-009**: 系统必须新增 `agent/os_runtime/engine/arbiter.py`，提供 `BoYueArbiter.arbitrate(...)`。
- **FR-010**: `BoYueArbiter` 主裁判结果只能是 `auto_execute`、`sandbox_execute`、`require_approval`、`report_only`、`reject`。
- **FR-011**: BoYue 评分必须覆盖博：`innovation_score`、`opportunity_score`、`expansion_value`；约：`risk_score`、`permission_level`、`compliance_fit`、`trust_impact`；合：`mutual_benefit_score`、`long_term_net_value`、`ecosystem_gain`。
- **FR-012**: `pre_tool_call` hook 集成必须调用 arbiter/policy 并阻断超出裁判范围、缺 approval、缺 catalog 或缺 authorization 的工具调用。
- **FR-013**: Linz World publish 必须同时通过 `BoYueArbiter`、`PolicyEngine`、`linz_world.event_catalog` 和 authorization map；LLM 不得凭空构造 subject/event_type。
- **FR-014**: 本模块新增测试必须覆盖 `tests/os_runtime/test_prompt_compiler.py`、`tests/os_runtime/test_intent_generator.py`、`tests/os_runtime/test_arbiter.py`。

### 关键实体

- **SelfPrompt**: 当前轮自我提示结构，聚合状态、张力、势能、记忆范围、约束、环境、开放空间和目标方向。
- **OpenSpace**: 当前可行动空间，表达允许考虑的 action families、约束和证据。
- **TargetDirection**: 当前目标方向，表达优先级、成功条件和停止条件。
- **OpenIntent**: 开放行动意图，描述下一步想做什么、为什么现在做、需要工具/新能力与停止边界。
- **BoYueArbiter**: 以博/约/合三组评分裁决 intent 的执行前治理组件。
- **ArbitrationResult**: 裁判结果，包含有限主 decision、risk、评分、理由、审批需求和诊断 metadata。

## 建议方案

按三层实现并保持执行前安全边界：

1. `SelfPromptCompiler` 做纯数据编译，输出 JSON-friendly `SelfPrompt`，并提供 hook adapter 只负责把该结构注入当前轮 ephemeral context。
2. `OpenIntentGenerator` 默认走规则路径：根据 `ActionPotential` 分数、`open_space`、`target_direction`、约束和可用工具生成固定 schema intent。可选 LLM 路径只作为候选解释增强，必须严格 schema 校验。
3. `BoYueArbiter` 对 intent 做有限状态裁判，并把 Linz World publish、工具执行和高风险外部副作用交给 PolicyEngine/event catalog/authorization map 共同确认。

## 修改范围

- 新增 `agent/os_runtime/engine/prompt_compiler.py`
- 新增 `agent/os_runtime/engine/intent_generator.py`
- 新增 `agent/os_runtime/engine/arbiter.py`
- 新增 `tests/os_runtime/test_prompt_compiler.py`
- 新增 `tests/os_runtime/test_intent_generator.py`
- 新增 `tests/os_runtime/test_arbiter.py`
- 允许最小更新 `agent/os_runtime/domain.py`：为 `SelfPrompt`/`OpenIntent` 补齐 `open_space`、`target_direction`，为 `ArbitrationResult` 补齐博/约/合细分评分 metadata 或字段；不得改动无关协议。
- 允许最小更新 hook 注册或 adapter 文件以暴露 `pre_llm_call` / `pre_tool_call` 集成点，但不得修改 Hermes 主循环语义。

## 关键设计

- **Prompt cache 边界**: 稳定 system prompt 不变；自治 prompt 作为当前轮 ephemeral user context 或等价 transient block 注入。
- **规则优先**: 规则路径是首版主路径，LLM JSON 只能增强候选 intent，失败必须回退。
- **Schema 严格校验**: intent/action family/decision 使用 enum 和必填字段校验；未知字段进入 diagnostics，不进入执行许可。
- **有限裁判结果**: 主 decision 字段只允许五类新结果，迁移期 allow_* 只能作为兼容 metadata。
- **Fail-closed 发布**: Linz World publish 必须有 catalog subject/event_type、authorization map allow、policy allow 和 arbiter allow。
- **证据链**: `why_now`、`success_condition`、`stop_condition`、`open_space`、`target_direction` 必须能回溯到 SelfPrompt/ActionPotential/TensionExplanation。

## 风险与取舍

- **模块 4 依赖未落地**: 仓库当前未见 `action_potential.py`，Builder 需要先确认模块 4 已合并或提供兼容 `ActionPotential` 输入夹具；本模块不补做模块 4。
- **现有 domain 字段缺口**: 当前 `SelfPrompt`/`OpenIntent` 缺少直接的 `open_space`、`target_direction` 字段；取舍是做最小协议扩展而不是新建并行对象。
- **Hook 接入差异**: 现有 plugin hook 数据结构可能与 engine 纯函数不同；应将 hook adapter 做薄，核心逻辑保持可单测。
- **LLM 候选诱导越权**: 严格 schema、catalog 与 authorization 校验，LLM 输出永远不能成为执行许可来源。
- **裁判过早复杂化**: 首版评分使用透明规则和阈值，不引入训练模型或复杂优化。

## 成功标准 *(必填)*

### 可衡量的结果

- **SC-001**: 每个自动 continuation 候选 intent 都能解释 `why_now`、`success_condition`、`stop_condition`。
- **SC-002**: 每个 intent 都能追溯到 `open_space` 和 `target_direction`。
- **SC-003**: LLM 生成非法 JSON、未知 enum 或缺字段时不会执行行动，并回退规则路径。
- **SC-004**: 高风险 intent 不会直接进入工具执行。
- **SC-005**: Linz World publish intent 无法凭 LLM 自造 subject/event_type 通过，必须走 `linz_world.event_catalog`。
- **SC-006**: 新 evidence 的主裁判结果只出现五类新 decision，不出现旧 allow_* 主字段。

## 验收标准

- `pytest tests/os_runtime/test_prompt_compiler.py tests/os_runtime/test_intent_generator.py tests/os_runtime/test_arbiter.py` 通过。
- 现有 `pytest tests/os_runtime/test_domain.py tests/os_runtime/test_signals.py tests/os_runtime/test_life_state.py tests/os_runtime/test_tension_interpreter.py tests/os_runtime/test_tension_field.py` 不回归。
- 新增 engine 模块默认不调用网络、真实 LLM、真实工具、真实 Linz World 服务或外部发布。
- `pre_llm_call` 测试证明稳定 system prompt 未被修改。
- `pre_tool_call` 或 arbiter 集成测试证明高风险/缺授权/缺 catalog 不会获得执行许可。

## 测试计划

- 单元测试 `SelfPromptCompiler` 完整字段、缺省输入、约束保留、证据引用和 ephemeral context 注入结构。
- 单元测试 `OpenIntentGenerator` 规则路径、LLM JSON 成功、LLM JSON 失败回退、未知 action family、缺必填字段和 subject/event_type 防伪造。
- 单元测试 `BoYueArbiter` 五类 decision、博/约/合评分、低风险草案、高风险工具、审批需求、Linz World publish catalog/auth fail-closed。
- 回归测试 domain round-trip 和前序 os_runtime engine tests。

## 后续交接说明

Builder Agent 应先确认模块 4 的 `ActionPotential` 输入可用，再按 `SelfPromptCompiler` -> `OpenIntentGenerator` -> `BoYueArbiter` 的顺序实现。实现时只做最小 domain 扩展和薄 hook adapter，不要实现 runtime driver，不要执行外部副作用，不要把 LLM 输出当作权限来源。Spec Reviewer Agent 重点审查 prompt cache 边界、LLM fallback、五类裁判结果和 Linz World publish fail-closed 是否足够明确。

## 假设

- 模块 0 提供的协议对象是本功能基础，允许做最小字段补齐。
- 模块 2/3 已能产出 `TaskContextView`、`LifeState`、`TensionSet` 和 `TensionExplanation` 或等价解释 metadata。
- 模块 4 将提供 `ActionPotential`，本模块只消费其分数和 rationale。
- Builder Agent 负责业务代码实现；Planner Agent 本轮只维护 spec-kit artifacts。
