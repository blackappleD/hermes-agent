# 实施计划: 模块 5 SelfPrompt、OpenIntent 与 BoYueArbiter

**分支**: `099-module-5-selfprompt-openintent-arbiter` | **日期**: 2026-05-13 | **规范**: `specs/099-module-5-selfprompt-openintent-arbiter/spec.md`
**输入**: 来自 `/specs/099-module-5-selfprompt-openintent-arbiter/spec.md` 的功能规范

## 摘要

实现模块 5 的三个执行前决策组件：`SelfPromptCompiler` 将上下文/生命状态/张力/行动势能编译为结构化临时 prompt；`OpenIntentGenerator` 规则优先生成开放意图并安全处理 LLM JSON fallback；`BoYueArbiter` 以博/约/合评分把 intent 限定为五类主 decision，并与 PolicyEngine、event catalog、authorization map 共同约束 Linz World publish 和工具执行。

## 技术背景

**语言/版本**: Python 3.11
**主要依赖**: Python 标准库、现有 `agent.os_runtime.domain` dataclass/Enum 协议对象、现有 plugin hook 约定、后续模块 4 `ActionPotential` 输入
**存储**: N/A，本模块不持久化状态
**测试**: pytest
**目标平台**: Hermes Agent Python runtime
**项目类型**: Python CLI/runtime library
**性能目标**: 规则编译、intent 生成和 arbiter 裁判为内存内确定性操作；默认不做 I/O
**约束条件**: 不改 stable system prompt；不调用真实网络/工具/发布；LLM JSON 失败必须回退且不得执行；外部副作用 fail-closed
**规模/范围**: 3 个 engine 模块、3 个 focused test 文件、必要时最小 domain/hook adapter 扩展

## 章程检查

- **Profile-Scoped State**: 通过。本模块不写 profile state；只消费调用方传入的 context、tension、action potential、authorization/catalog 摘要。
- **Native Surfaces Before Optional Skills**: 通过。新增能力在 `agent/os_runtime/engine/`，Linz World publish 依赖原生 `agent/linz_world` catalog/auth，不依赖 optional skill。
- **Fail-Closed External Side Effects**: 通过。裁判只产出 decision；缺 policy、catalog、authorization 或 approval 时不允许工具执行/世界发布。
- **Privacy and Audit Separation**: 通过。SelfPrompt 只包含摘要、scope、evidence refs 和 constraints，不要求 token/raw payload 进入 prompt。
- **Testable Incremental Delivery**: 通过。prompt compiler、intent generator、arbiter 三个故事可独立用 fake 输入测试。

## 项目结构

### 文档(此功能)

```text
specs/099-module-5-selfprompt-openintent-arbiter/
├── spec.md
├── plan.md
└── tasks.md
```

### 源代码(仓库根目录)

```text
agent/os_runtime/
├── domain.py
└── engine/
    ├── prompt_compiler.py
    ├── intent_generator.py
    └── arbiter.py

tests/os_runtime/
├── test_prompt_compiler.py
├── test_intent_generator.py
└── test_arbiter.py
```

**结构决策**: 使用现有 `agent/os_runtime/engine/` 放纯领域决策逻辑，hook adapter 保持薄集成，不新增 runtime driver 或并行工具执行框架。

## 修改范围

- 新增 `agent/os_runtime/engine/prompt_compiler.py`
- 新增 `agent/os_runtime/engine/intent_generator.py`
- 新增 `agent/os_runtime/engine/arbiter.py`
- 新增 `tests/os_runtime/test_prompt_compiler.py`
- 新增 `tests/os_runtime/test_intent_generator.py`
- 新增 `tests/os_runtime/test_arbiter.py`
- 允许最小更新 `agent/os_runtime/domain.py` 补齐 `SelfPrompt.open_space`、`SelfPrompt.target_direction`、`OpenIntent.open_space`、`OpenIntent.target_direction`、Arbitration 细分评分字段或 metadata helper。
- 允许最小 hook adapter/export 更新，暴露 `pre_llm_call` ephemeral context 注入和 `pre_tool_call` arbiter/policy 检查入口。

## 关键设计

### SelfPromptCompiler

- 输入: `TaskContextView`、`AgentContextView | None`、`LifeState`、`TensionSet`、`TensionExplanation | TensionInterpretation metadata`、`ActionPotential`、memory refs、constraint set、environment state、available tools、rule crystals。
- 输出: `SelfPrompt`，必须包含 state/tension/potential summary、memory/constraint/environment scope、`OpenSpace`、`TargetDirection` 和 evidence refs。
- 编译规则:
  - `state_summary`: life cycle、energy/fatigue/wakefulness/restraint 等摘要。
  - `tension_summary`: high activation/core/dynamic tensions、解释摘要和 evidence。
  - `potential_summary`: value/mutual benefit/learning/risk/overall。
  - `open_space`: 来自可用 action family、tools、constraints、risk config。
  - `target_direction`: 来自 active goal、highest tension、potential rationale 和 stop/success condition。
- Hook 集成只把 SelfPrompt 放进当前轮 ephemeral context，不修改 stable system prompt。

### OpenIntentGenerator

- 默认规则路径:
  - 高 risk 或 restraint 高 -> `report_only` 候选方向，action family 可为 `rest`、`learn` 或 `communicate`。
  - 高 value/learning 且低 risk -> 依据 tool/context 选择 `communicate`、`create`、`learn`、`collaborate` 等。
  - 需要新能力但当前无工具 -> `new_tool` 或 `new_skill`，不得直接执行不存在工具。
- LLM JSON 路径:
  - 只作为候选生成器，必须 strict JSON/schema/enum validation。
  - 解析失败、缺字段、未知 enum、subject/event_type 越权时回退规则路径。
  - 回退结果 metadata 记录 `fallback_reason`，且不生成执行许可。
- Intent 必填: action_family、action_type、why_now、open_space、target_direction、tools_needed、proposed_new_tools、proposed_new_skills、success_condition、stop_condition。

### BoYueArbiter

- 输入: `OpenIntent`、`SelfPrompt`、`ActionPotential`、risk config、available tools、policy preflight、event catalog preflight、authorization summary。
- 输出: `ArbitrationResult`，主 decision 只允许:
  - `auto_execute`
  - `sandbox_execute`
  - `require_approval`
  - `report_only`
  - `reject`
- 评分维度:
  - 博: innovation_score、opportunity_score、expansion_value。
  - 约: risk_score、permission_level、compliance_fit、trust_impact。
  - 合: mutual_benefit_score、long_term_net_value、ecosystem_gain。
- 判定原则:
  - 低风险、无外部副作用、policy allow 可进入 report/sandbox/auto。
  - 中高风险、写文件、终端、外部平台消息、世界发布默认 require approval 或 reject。
  - 未知工具、缺 catalog、缺 authorization、LLM 自造 subject/event_type reject。
  - `allow_*` 旧字段只能作为兼容 metadata。

### Linz World Publish Boundary

- publish intent 不是独立 decision。
- 即便 arbiter 给出 `auto_execute` 或 `sandbox_execute`，执行前仍必须同时满足:
  - `PolicyEngine` allow。
  - `linz_world.event_catalog` 确认 subject/event_type/payload。
  - authorization map 明确允许。
  - 需要审批的场景已有有效 approval。
- 任一缺失都 fail-closed。

## 风险与取舍

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 模块 4 未合并 | Builder 无法获得真实 `ActionPotentialEvaluator` | 本模块只消费 `ActionPotential` 协议；实现前确认模块 4 或使用测试夹具 |
| domain 字段缺口 | `open_space`/`target_direction` 无法直接 round-trip | 做最小 domain 扩展并补 domain 测试 |
| hook 数据结构差异 | prompt 注入可能误改 system prompt | 用薄 adapter 和测试固定 stable system prompt 不变 |
| LLM JSON 越权 | 自造 action/catelog/subject 导致副作用 | strict schema + catalog/auth/policy fail-closed |
| 裁判阈值过宽或过窄 | 低风险行动被阻断或高风险误放行 | 首版规则偏保守，测试覆盖高风险直接执行禁止 |

## 验收标准

- `SelfPrompt` 输出 state/tension/potential/memory/constraint/environment/open_space/target_direction，且 evidence 可追溯。
- `pre_llm_call` 注入 ephemeral context 时 stable system prompt 不变。
- `OpenIntent` 每次都包含 action family、action type、why_now、open_space、target_direction、tools_needed、新工具/技能提议、success/stop condition。
- LLM JSON 失败或非法时回退规则路径，不输出执行许可。
- `BoYueArbiter` 主 decision 只出现五类新结果。
- 高风险 intent、缺 policy、缺 catalog、缺 authorization 不会直接进入工具执行。
- Linz World publish 不能使用 LLM 自造 subject/event_type，必须走 catalog 和 authorization map。

## 测试计划

1. `pytest tests/os_runtime/test_prompt_compiler.py`
2. `pytest tests/os_runtime/test_intent_generator.py`
3. `pytest tests/os_runtime/test_arbiter.py`
4. 回归: `pytest tests/os_runtime/test_domain.py tests/os_runtime/test_signals.py tests/os_runtime/test_life_state.py tests/os_runtime/test_tension_interpreter.py tests/os_runtime/test_tension_field.py`

## 后续交接说明

Builder Agent 应先处理 domain 最小字段补齐，再实现 `SelfPromptCompiler`、`OpenIntentGenerator`、`BoYueArbiter`，最后接薄 hook adapter。不要实现模块 4 的 action potential evaluator，不要实现模块 6 driver，不要执行真实工具或世界发布。Spec Reviewer Agent 应重点审查模块 4 依赖、prompt cache 边界、LLM fallback 和 publish fail-closed 规则。
