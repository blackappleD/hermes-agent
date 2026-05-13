# 实施计划: 模块 4 行动势能与认知经济

**分支**: `098-action-potential-cognitive-economy` | **日期**: 2026-05-13 | **规范**: `specs/098-action-potential-cognitive-economy/spec.md`
**输入**: 来自 `/specs/098-action-potential-cognitive-economy/spec.md` 的功能规范

## 摘要

在模块 3 生命状态与张力场输出之上，实现两个纯领域/建议层模块：`ActionPotentialEvaluator` 负责计算价值势能、互利势能、学习势能、风险成本、总分和建议行动深度；`CognitiveEconomyController` 负责建议认知预算路径。首版只输出建议，不切换主模型、不自动调用工具、不发布世界事件。world compute 必须 fail-closed，并通过 `agent/linz_world/compute.py` 的 governed 入口与 receipt 边界验证。

## 技术背景

**语言/版本**: Python 3.11
**主要依赖**: Python 标准库、现有 `agent.os_runtime.domain` dataclass/Enum 协议对象、`agent.linz_world.compute` governed compute 入口
**存储**: N/A；本模块不新增持久化，receipt 由 Linz World state repository 负责
**测试**: pytest
**目标平台**: Hermes Agent Python runtime
**项目类型**: Python CLI/runtime library
**性能目标**: 规则评估为内存内确定性操作；默认路径不得依赖网络或模型调用
**约束条件**: 不导入或改写 `run_agent.py` 主循环；不执行工具；不真实切换模型；world compute 必须可 stub、可拒绝、可降级
**规模/范围**: 2 个 engine 模块、2 个 focused test 文件、必要时最小 domain 协议扩展

## 章程检查

- **Profile-Scoped State**: 通过。本模块不直接写 profile；world compute receipt 由现有 Linz World repository 管理。
- **Native Surfaces Before Optional Skills**: 通过。实现落在 `agent/os_runtime/engine/`，复用原生 `agent/linz_world/compute.py`，不依赖 optional skill。
- **Fail-Closed External Side Effects**: 通过。行动势能不执行副作用；world compute 未满足登录、token、授权、summary 或配置条件时必须降级。
- **Privacy and Audit Separation**: 通过。禁止裸 token/api key 输入；评分 evidence 只记录 signal/tension/config 摘要和 receipt id/status。
- **Testable Incremental Delivery**: 通过。`action_potential.py` 与 `cognitive_economy.py` 可分别用 focused pytest 验证。

## 项目结构

### 文档(此功能)

```
specs/098-action-potential-cognitive-economy/
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
    ├── action_potential.py
    └── cognitive_economy.py

tests/os_runtime/
├── test_action_potential.py
└── test_cognitive_economy.py
```

**结构决策**: 使用现有 `agent/os_runtime/engine/`。不新增 runtime driver、session store、gateway adapter 或 model router。

## 关键设计

### ActionPotentialEvaluator

- 输入: `SignalSet`、`LifeState`、`TensionSet`、可选候选 action/intent metadata。
- 输出: `ActionPotential` 或兼容对象，包含 `recommended_depth` 和 per-score evidence。
- 评分方向:
  - `value_potential`: 未完成目标、需求/订单、活跃 high-intensity unsatisfied goal/value/creative tensions 提升。
  - `mutual_benefit_potential`: 关系、聊天、订单协作、用户明确收益和 Linz World mutual benefit 信号提升。
  - `learning_potential`: 不确定性、memory resonance、新任务类型、正向探索机会提升。
  - `risk_cost`: risk、authorization、approval、settlement、rent、tool side effect、高 restraint/fatigue 提升。
  - `overall_score`: 收益加权减风险，clamp 到 0.0-1.0。
- `recommended_depth` 门槛:
  - `none`: 低分、简单闲聊、重复低价值、强抑制。
  - `report`: 有价值但风险/不确定性高，或需要向用户说明。
  - `draft`: 可生成草案但不继续自动推进。
  - `continue_turn`: 明确未完成低风险目标且生命状态允许。
  - `sandbox`: 工具/外部动作有价值但风险中高。
  - `tool`: 仅低风险、授权明确、后续裁判允许前的建议值。
  - `world_publish`: 仅世界发布候选建议，不在本 issue 执行。
  - `bubble`: 仅复杂协作候选建议，不在本 issue 编排。

### CognitiveEconomyController

- 输入: `ActionPotential`、`SignalSet`、`LifeState`、`TensionSet`、配置、可选 world compute gateway/stub。
- 输出: `CognitiveEconomyRecommendation` 或等价 JSON-friendly 对象。
- 路径规则:
  - `rule_path`: 低分、确定性低价值、风险抑制或无需模型。
  - `auxiliary_small`: 低风险轻量摘要/分类/草案建议。
  - `main_model`: 用户主线回答、需要完整上下文但不需要额外预算。
  - `high_reasoning`: 高价值、高复杂度、高不确定，但 world compute 不可用或不合适。
  - `world_compute`: 高价值、高不确定、已登录、有 token ref、有 Soul Memory summary、授权/配置允许，并能记录 governed receipt。
- 建议对象必须包含 selected path、reason、score snapshot、downgrade reason、receipt summary 和 evidence。

### World Compute Boundary

- 仅通过 `agent.linz_world.compute.invoke_compute()` 或等价 injectable wrapper。
- 不接受 `token`、`api_key`、`secret` 等显式 credential input。
- eligibility 必须检查配置、world identity、login/token ref、Soul Memory summary 和 authorization/map 状态。
- rejected/failed receipt 导致降级为 `main_model` 或 `high_reasoning`，并保留 receipt status。

## 修改范围

- 新增 `agent/os_runtime/engine/action_potential.py`
- 新增 `agent/os_runtime/engine/cognitive_economy.py`
- 新增 `tests/os_runtime/test_action_potential.py`
- 新增 `tests/os_runtime/test_cognitive_economy.py`
- 允许最小更新 `agent/os_runtime/domain.py`，补齐 `recommended_depth`、认知经济建议对象或 metadata 结构。

## 风险与取舍

- **评分权重误导**: 首版固定规则可能不能代表所有业务场景。缓解：所有分数必须有 evidence 和阈值 metadata，后续可调参。
- **模型建议与裁判混淆**: 本模块只建议深度和预算，不做最终执行许可。高风险动作仍交给后续 Arbiter。
- **world compute 调用副作用**: 默认生产路径可只生成 recommendation；测试中通过 stub 验证 governed receipt，不依赖真实服务。
- **domain 扩展范围**: 若新增对象，保持 JSON-friendly dataclass，不引入运行时依赖。

## 验收标准

- 简单闲聊不会触发自驱动 continuation。
- 明确未完成低风险目标可建议 `continue_turn`。
- 中高风险工具动作必须建议审批前置、`sandbox`、`report` 或 `none`。
- 未登录或无 Soul Memory summary 时不能选择 `world_compute`。
- 所有评分字段可追踪到 signal、tension、life_state 或配置阈值。
- `pytest tests/os_runtime/test_action_potential.py tests/os_runtime/test_cognitive_economy.py` 通过。
- 现有模块 0/2/3 os_runtime 测试不回归。

## 测试计划

- `pytest tests/os_runtime/test_action_potential.py`
- `pytest tests/os_runtime/test_cognitive_economy.py`
- `pytest tests/os_runtime/test_domain.py tests/os_runtime/test_signals.py tests/os_runtime/test_life_state.py tests/os_runtime/test_tension_interpreter.py tests/os_runtime/test_tension_field.py`

## 后续交接说明

Builder Agent 应按 tasks.md 顺序实现，先补齐最小 domain 对象，再实现行动势能评分，最后实现认知经济建议和 world compute eligibility/stub 测试。不要接入真实模型切换，不要实现自动 continuation、Prompt 编译、意图生成或裁判执行。
