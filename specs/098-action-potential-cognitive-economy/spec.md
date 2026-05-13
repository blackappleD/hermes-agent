# 功能规范: 模块 4 行动势能与认知经济

**功能分支**: `098-action-potential-cognitive-economy`
**Spec-Kit 特性目录**: `specs/098-action-potential-cognitive-economy`
**创建时间**: 2026-05-13
**状态**: 草稿，待 Reviewer Agent 审查
**输入**: Issue OPE-98；`docs/基于张力场的Agent自驱动实现计划.md`；模块 -1、0、2、3 既有 spec 与当前代码上下文

## 背景

Hermes Agent 已有 Linz World 原生身份与世界算力边界、`agent/os_runtime/domain.py` 协议对象、上下文信号生成、生命状态系统、张力解释器和张力场内核。模块 4 的职责是在这些输入之上判断“是否值得行动、行动到什么深度、是否需要更强模型或更多预算”。

本模块只输出建议，不切换主模型，不自动执行工具，不发布世界事件，不改写 Hermes 主循环。后续模块会继续接入 Prompt 编译、意图生成、裁判和执行闭环。

## 目标

- 新增 `ActionPotentialEvaluator`，基于 `LifeState`、`TensionSet`、`SignalSet`、任务上下文和可选 intent 候选，输出价值势能、互利势能、学习势能、风险成本、总分和建议行动深度。
- 新增 `CognitiveEconomyController`，基于行动势能、生命状态、张力和配置，建议 `rule_path`、`auxiliary_small`、`main_model`、`world_compute`、`high_reasoning` 之一。
- 让简单闲聊、明确未完成目标、高风险工具动作、未登录 Linz World、缺失 Soul Memory summary 等场景有确定性建议。
- 所有评分字段必须能追踪到 signal、tension、life_state 或配置阈值。

## 非目标

- 不实现 Prompt 编译、开放式意图生成、博约裁判器、工具执行、审批票据或自驱动 continuation。
- 不修改 `run_agent.py` 主循环，不接入真实模型路由，不强制切换 `agent/auxiliary_client.py` 或 reasoning config。
- 不直接调用外部工具或发布 Linz World 事件。
- 不把 `world_compute` 当作裸模型 API；只能通过 `agent/linz_world/compute.py` 的治理入口建议或调用，并记录 receipt。

## 需求理解

### 用户故事 1 - 行动势能可解释评分 (优先级: P1)

作为 Builder Agent，我需要一个纯规则的行动势能评估器，使每个候选行动都能得到价值、互利、学习、风险和总体分数，并能解释推荐深度。

**优先级原因**: 这是后续 continuation、裁判和模型预算选择的基础。

**独立测试**: 仅实现 `agent/os_runtime/engine/action_potential.py` 与 `tests/os_runtime/test_action_potential.py`，使用手写 `LifeState`、`TensionSet`、`SignalSet` 验证评分。

**验收场景**:

1. **给定** 简单闲聊且无活跃目标/张力，**当** 评估行动势能，**那么** `overall_score` 低且 `recommended_depth=none` 或 `report`，不会建议自驱动 continuation。
2. **给定** 明确未完成低风险目标和活跃 unsatisfied goal 张力，**当** 评估行动势能，**那么** value/learning 分数上升，risk 低，`recommended_depth=continue_turn` 或 `draft`。
3. **给定** 高风险工具动作、授权未知或审批需求，**当** 评估行动势能，**那么** `risk_cost` 上升，推荐深度降级为 `sandbox`、`report` 或 `none`，不得直接建议 `tool`。

### 用户故事 2 - 认知经济建议模型/预算路径 (优先级: P1)

作为 Runtime 集成者，我需要一个只产出建议的认知经济控制器，使系统能判断何时走规则路径、小模型、主模型、世界算力或高 reasoning，而不在本 issue 中实际切换模型。

**优先级原因**: 模块 4 的目标不仅是“是否行动”，也包括“值得花多少认知预算”。

**独立测试**: 仅实现 `agent/os_runtime/engine/cognitive_economy.py` 与 `tests/os_runtime/test_cognitive_economy.py`，用 stubbed world compute 调用验证建议和 receipt 记录边界。

**验收场景**:

1. **给定** 低分、低张力、低风险事件，**当** 生成认知经济建议，**那么** 建议 `rule_path` 或 `auxiliary_small`。
2. **给定** 中高价值且需要主线回答的目标，**当** 生成建议，**那么** 可建议 `main_model`，但不修改当前模型。
3. **给定** 高价值、高不确定性、已登录且存在 Soul Memory summary 的场景，**当** 配置允许 world compute，**那么** 可建议 `world_compute`，并通过 `agent/linz_world/compute.py` 记录 governed receipt。

### 用户故事 3 - 世界算力 fail-closed 边界 (优先级: P2)

作为 Linz World 侧治理维护者，我需要 world compute 只能在身份、登录、Soul Memory summary 和授权条件满足时被建议，否则必须降级。

**优先级原因**: world compute 是外部治理边界，必须比普通本地建议更严格。

**独立测试**: 在 `tests/os_runtime/test_cognitive_economy.py` 中覆盖未登录、缺 token、无 Soul Memory summary、配置禁用和 receipt 失败。

**验收场景**:

1. **给定** 未登录或缺少 token ref，**当** 行动势能很高，**那么** 不选择 `world_compute`，并记录降级 reason。
2. **给定** 无 Soul Memory summary，**当** world compute 原本可能被选择，**那么** 降级为 `main_model` 或 `high_reasoning`。
3. **给定** `agent/linz_world/compute.py` 返回 rejected/failed receipt，**当** 生成建议，**那么** 输出 receipt 摘要并降级，不重试外部调用。

## 修改范围

- 新增 `agent/os_runtime/engine/action_potential.py`
- 新增 `agent/os_runtime/engine/cognitive_economy.py`
- 新增 `tests/os_runtime/test_action_potential.py`
- 新增 `tests/os_runtime/test_cognitive_economy.py`
- 允许最小扩展 `agent/os_runtime/domain.py`，仅用于 `ActionPotential.recommended_depth`、评分 evidence、认知经济建议对象或 metadata 字段；不得引入外部 runtime 依赖。

## 功能需求

- **FR-001**: 系统必须提供 `ActionPotentialEvaluator.evaluate(...)`，输入至少包含 `SignalSet`、`LifeState`、`TensionSet`、可选候选 intent/action metadata，输出 `ActionPotential` 或兼容对象。
- **FR-002**: 输出必须包含 `value_potential`、`mutual_benefit_potential`、`learning_potential`、`risk_cost`、`overall_score`、`recommended_depth`、`rationale` 和 evidence/metadata。
- **FR-003**: `recommended_depth` 必须限定为 `none`、`report`、`draft`、`continue_turn`、`sandbox`、`tool`、`world_publish`、`bubble`。
- **FR-004**: 评分必须综合 active tensions、life_state、task context、signal key、risk/authorization/approval/settlement 等约束信号，并 clamp 到稳定数值范围。
- **FR-005**: 简单闲聊或低价值重复事件不得触发 `continue_turn`、`tool`、`world_publish` 或 `bubble`。
- **FR-006**: 明确未完成低风险目标可建议 `continue_turn` 或 `draft`，但必须仍受 fatigue/restraint/risk 抑制。
- **FR-007**: 中高风险工具动作、授权未知、审批需求或外部副作用必须建议审批前置路径、`sandbox`、`report` 或 `none`，不得直接建议 `tool`。
- **FR-008**: 系统必须提供 `CognitiveEconomyController.recommend(...)`，首版只输出 `rule_path`、`auxiliary_small`、`main_model`、`world_compute`、`high_reasoning` 五类建议之一。
- **FR-009**: `world_compute` 只能通过 `agent/linz_world/compute.py` 的 governed compute 入口；禁止接受裸 token、api key 或 prompt 中的秘密字段。
- **FR-010**: 未登录、token ref 缺失、token secret 不可用、authorization/map 不满足、配置禁用或无 Soul Memory summary 时，不能选择 `world_compute`。
- **FR-011**: 如果执行 world compute 预检或调用，必须记录 receipt 或 rejected/failed 摘要，并把 receipt id/status 放入建议 metadata。
- **FR-012**: 本模块新增测试必须覆盖 `tests/os_runtime/test_action_potential.py` 和 `tests/os_runtime/test_cognitive_economy.py`，且不得依赖真实网络、真实 Linz World 服务或真实模型。

## 关键实体

- **ActionPotential**: 行动势能评估结果，承载三类收益、风险成本、总分、建议深度、解释和 evidence。
- **RecommendedDepth**: 建议行动深度枚举或常量集合，限定为 issue 指定的八个值。
- **CognitiveEconomyRecommendation**: 认知经济建议，承载 selected_path、reason、budget_hint、receipt summary、降级原因和 evidence。
- **WorldComputeEligibility**: world compute 可用性判断摘要，覆盖登录状态、token ref、Soul Memory summary、授权/配置和 receipt 状态。

## 关键设计

- **纯评估优先**: `ActionPotentialEvaluator` 只做内存内规则评分，不调用模型、不调用工具、不写外部状态。
- **风险先行降级**: `risk_cost`、`LifeState.restraint`、授权未知和审批需求优先限制 `recommended_depth`。
- **可追踪证据**: 每个分数字段都必须在 metadata 中列出贡献来源，例如 `signal:goal`、`tension:unsatisfied_goal`、`life_state:fatigue`、`config:threshold`。
- **建议不切换**: `CognitiveEconomyController` 返回建议对象；真实模型切换、auxiliary client 和 reasoning config 接入留给后续 issue。
- **世界算力治理**: world compute 走 `agent/linz_world/compute.py`，使用登录 token ref 和治理预检；失败时 fail-closed 并给出降级路径。

## 风险与取舍

- **评分权重主观**: 首版使用明确常量和配置阈值，风险是权重不够精细。取舍是先保证确定性与可测性，后续再用 evidence/rules 调整。
- **ActionPotential 协议字段不足**: 当前 `ActionPotential` 没有显式 `recommended_depth`。Builder 可最小扩展 domain 或把它放在 metadata，但测试必须固定输出。
- **world_compute 是否实际调用**: 本 issue 目标是建议。只有在测试中用 stubbed compute 验证 governed receipt 边界；生产路径可先只返回 eligible/recommended 状态，不强制真实调用。
- **与后续裁判重叠**: 本模块只判断深度和预算，不做最终 allow/reject；高风险动作仍必须交给后续 Arbiter/approval。

## 验收标准

- 简单闲聊不会触发自驱动 continuation。
- 明确未完成低风险目标可建议 `continue_turn`。
- 中高风险工具动作必须建议审批前置、`sandbox`、`report` 或 `none`。
- 未登录或无 Soul Memory summary 时不能选择 `world_compute`。
- 所有评分字段可追踪到 signal、tension、life_state 或配置阈值。
- `pytest tests/os_runtime/test_action_potential.py tests/os_runtime/test_cognitive_economy.py` 通过。
- 现有 `pytest tests/os_runtime/test_domain.py tests/os_runtime/test_signals.py tests/os_runtime/test_life_state.py tests/os_runtime/test_tension_interpreter.py tests/os_runtime/test_tension_field.py` 不回归。

## 测试计划

- 单元测试 `ActionPotentialEvaluator` 的闲聊、未完成目标、低风险 continuation、高风险工具、授权未知、疲劳/克制抑制、评分 evidence。
- 单元测试 `recommended_depth` 限定值，确保不输出 issue 未允许的深度。
- 单元测试 `CognitiveEconomyController` 的 `rule_path`、`auxiliary_small`、`main_model`、`high_reasoning` 建议。
- 单元测试 world compute eligibility：未登录、缺 token、无 Soul Memory summary、配置禁用、receipt rejected/failed、receipt published。
- 使用 stub repository/service 替代真实 Linz World 和网络。

## 假设

- 模块 -1 的 `agent/linz_world/compute.py` 已提供 governed compute 入口并拒绝裸 credentials。
- 模块 0 的 `ActionPotential`、`LifeState`、`TensionSet`、`SignalSet` 可作为首版协议基础。
- 模块 3 已提供可用的生命状态和张力网络输出；本模块不负责重新解释张力。

## 后续交接说明

Builder Agent 应先补齐最小协议字段或建议对象，再实现 `ActionPotentialEvaluator`，最后实现 `CognitiveEconomyController`。实现过程中不要接入真实模型切换，不要改主循环，不要实现 Prompt 编译/意图生成/裁判。Spec Reviewer Agent 重点审查 world compute fail-closed 边界、评分证据链和 recommended depth 是否足以约束 Builder。
