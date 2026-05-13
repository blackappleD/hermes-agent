# 功能规范: 模块 0：协议、配置与测试基座

**功能分支**: `feat/89-module-0-protocol-config-test-base`
**Spec-Kit 特性目录**: `specs/089-module-0-protocol-config-test-base`
**创建时间**: 2026-05-12
**状态**: 草稿，待 Reviewer Agent 审查
**输入**: Issue OPE-89；`docs/基于张力场的Agent自驱动实现计划.md` 中“模块 0：协议、配置与测试基座”

## 背景

Hermes 后续会逐步引入 Linz World 原生身份与 `os_runtime` 张力场自治闭环。模块 0 的职责是先冻结张力场领域契约、配置默认值和测试基座，避免后续事件投影、生命状态、张力解释、意图生成、裁判、证据和泡泡协议模块各自重复定义自治语义。

本模块不接入 runtime，不改变普通 CLI、gateway、TUI、工具调用、memory provider 或 `/goal` 行为。它只建立可序列化、可测试、可被后续模块复用的协议层。

## 目标

- 定义 `agent/os_runtime/domain.py` 中的核心领域对象、枚举和 JSON round-trip 边界。
- 定义 `agent/os_runtime/config.py` 中的 `os_runtime` 配置模型与默认值读取逻辑。
- 在 `hermes_cli/config.py::DEFAULT_CONFIG` 增加 `os_runtime` 配置段，默认关闭。
- 增加 `tests/os_runtime/test_domain.py` 和 `tests/os_runtime/test_config.py`，覆盖协议对象、配置默认值和序列化兼容性。

## 非目标

- 不实现 Linz World 原生身份、registry、login、NATS 监听或世界事件发布。
- 不实现事件投影、SessionDB side tables、LifeState 计算、张力解释、行动势能、Prompt 编译、意图生成、裁判执行或 evidence 聚合。
- 不新增后台循环，不自动 continuation，不调用工具，不写入记忆。
- 不创建新的外部依赖或替换 Hermes 现有会话、上下文、记忆、工具基础设施。

## 需求理解

### 用户故事 1 - Builder 可基于统一协议实现后续模块 (优先级: P1)

作为 Builder Agent，我需要一个稳定的 `os_runtime` 协议模块，能够导入领域对象、枚举和配置默认值，从而在后续模块中复用同一套自治语义。

**优先级原因**: 这是后续模块 1-11 的基础；协议不稳定会导致每个模块重复定义字段并产生不兼容数据。

**独立测试**: 运行 `pytest tests/os_runtime/test_domain.py tests/os_runtime/test_config.py`，验证对象可创建、可 JSON round-trip、默认配置为关闭状态。

**验收场景**:

1. **给定** clean checkout，**当** Builder 实现模块 0 并运行单元测试，**那么** 所有核心对象都能完成 JSON round-trip。
2. **给定** 未启用 `os_runtime` 的默认配置，**当** 加载 Hermes 配置，**那么** `os_runtime.enabled=false` 且不触发现有行为变化。

### 用户故事 2 - 后续事件与裁判模块可保留 trace/evidence (优先级: P2)

作为后续事件投影和裁判模块，我需要 `OSRuntimeEventRef`、`ArbitrationResult`、`PermissionTicket`、`ExecutionReceipt`、`EvidencePackage` 等对象保留 trace id、时间戳、未知 metadata 和中文内容。

**独立测试**: 构造带中文文本、ISO 时间戳、trace id、metadata 的对象，序列化后反序列化，断言字段保持不变。

**验收场景**:

1. **给定** 带未知 metadata 的 evidence 对象，**当** round-trip 为 JSON，**那么** metadata 不被丢弃。
2. **给定** 中文 world event 摘要，**当** 写入并读取协议对象，**那么** 中文内容保持原样。

### 用户故事 3 - 配置保持 opt-in 与低风险默认值 (优先级: P3)

作为 Hermes 用户，我需要 `os_runtime` 默认关闭，并且工具执行、自动 continuation、后台 tick 都默认不启用。

**独立测试**: 检查默认配置对象和 `DEFAULT_CONFIG` 中 `os_runtime` 段的默认值。

## 修改范围

- `agent/os_runtime/__init__.py`
- `agent/os_runtime/domain.py`
- `agent/os_runtime/config.py`
- `hermes_cli/config.py`
- `tests/os_runtime/test_domain.py`
- `tests/os_runtime/test_config.py`

## 功能需求

- **FR-001**: 系统必须提供 `agent.os_runtime.domain`，包含模块 0 计划列出的核心对象：`OSRuntimeEventRef`、`WorldIdentityRef`、`TaskContextView`、`AgentContextView`、`SignalSet`、`LifeState`、`TensionInterpretation`、`TensionOperation`、`Tension`、`TensionSet`、`TensionNetworkDelta`、`ActionPotential`、`SelfPrompt`、`OpenSpace`、`TargetDirection`、`OpenIntent`、`ArbitrationResult`、`PermissionTicket`、`ExecutionReceipt`、`BubbleSpec`、`EvidencePackage`、`RuleCrystal`。
- **FR-002**: 系统必须定义事件来源、张力类型、张力操作、开放行动族、裁判结果、风险等级、泡泡生命周期、规则成熟度 R0-R4 等枚举。
- **FR-003**: 裁判结果主枚举必须使用 `auto_execute`、`sandbox_execute`、`require_approval`、`report_only`、`reject`；旧 `allow_reply`、`allow_draft`、`allow_sandbox` 最多作为迁移兼容别名，不进入新协议主枚举。
- **FR-004**: 领域对象必须支持 JSON 序列化/反序列化，并保留中文内容、trace id、时间戳和未知 metadata。
- **FR-005**: `WorldIdentityRef` 必须只是 Linz World 身份的只读引用视图，不负责 registry/login/token 管理。
- **FR-006**: `TaskContextView` 与 `AgentContextView` 必须只保存张力场需要的投影视图，不替代现有 SessionDB、MemoryManager、ContextEngine 或 tool registry。
- **FR-007**: `agent.os_runtime.config` 必须提供默认配置，默认 `enabled=false`，不自动执行工具、不自动后台 tick、不自动 continuation。
- **FR-008**: `hermes_cli/config.py::DEFAULT_CONFIG` 必须增加 `os_runtime` 配置段，但不能 bump config version。
- **FR-009**: 模块 0 必须新增聚焦单元测试，且测试不得依赖外部 Linz World 服务、NATS、真实模型或网络。
- **FR-010**: 模块 0 不得改变现有普通对话、CLI、gateway、TUI、工具调用、memory provider 或 `/goal` 行为。

## 关键实体

- **OSRuntimeEventRef**: 自治事件引用，承载 event id、source、trace id、session id、时间戳与摘要。
- **WorldIdentityRef**: Linz World 身份只读视图，承载 os_id、soul_id、os_name、account_id 和授权状态摘要。
- **LifeState**: 生命状态快照，覆盖 energy、fatigue、wakefulness、curiosity、boredom、creative_pressure、social_hunger、silence_pressure、restraint、life_cycle、recovery_cycle、generated_intent_count。
- **Tension / TensionSet / TensionNetworkDelta**: 张力、张力集合和网络变化，覆盖 intensity、trend、baseline、activation、propagation_edges 等字段。
- **ActionPotential**: 行动势能评估结果，覆盖 value_potential、mutual_benefit_potential、learning_potential、risk_cost、overall_score。
- **SelfPrompt / OpenIntent**: 后续 Prompt 编译与开放意图生成的协议输出。
- **ArbitrationResult / PermissionTicket / ExecutionReceipt**: 裁判、权限票据与执行回执协议。
- **EvidencePackage / RuleCrystal**: 证据包和规则结晶协议，保留来源 evidence 与成熟度。

## 关键设计

- 使用 `dataclasses`、`Enum` 和标准库 JSON 友好类型，不新增运行时依赖。
- 为对象提供统一的 `to_dict()` / `from_dict()` 或等效辅助函数，避免每个后续模块自写序列化。
- 时间字段使用字符串或标准库可稳定 round-trip 的表示方式；测试必须覆盖时区或 ISO 字符串保留。
- metadata 使用 `dict[str, Any]`，未知字段在 round-trip 中保留；对已知枚举做严格校验。
- 配置段只新增键，不触发行为；所有自动能力默认关闭。

## 风险与取舍

- **对象过度设计风险**: 模块 0 可能一次性定义过多字段。缓解：只覆盖计划文档中列出的 A-G 内核必备字段，并保持对象轻量。
- **后续兼容风险**: 未来模块可能需要新增字段。缓解：保留 metadata 和可选字段，测试未知 metadata 保留。
- **行为漂移风险**: 修改 `DEFAULT_CONFIG` 可能影响现有配置加载。缓解：默认关闭，不 bump version，测试默认值。
- **边界混淆风险**: `WorldIdentityRef` 被误用为 Linz auth 实现。缓解：规范中明确它只读、不含 token、不负责登录。

## 验收标准

- **SC-001**: `pytest tests/os_runtime/test_domain.py tests/os_runtime/test_config.py` 通过。
- **SC-002**: 所有核心领域对象均可完成 JSON round-trip，中文内容、trace id、时间戳和 metadata 不丢失。
- **SC-003**: 默认配置中 `os_runtime.enabled=false`，且自动工具执行、后台 tick、自动 continuation 均未启用。
- **SC-004**: `hermes_cli/config.py::DEFAULT_CONFIG` 新增 `os_runtime` 段但未 bump config version。
- **SC-005**: 本模块不新增外部依赖，不访问网络，不要求 Linz World 服务可用。
- **SC-006**: 现有行为保持不变；至少运行一个配置相关或 import 级别回归测试确认无破坏性导入。

## 测试计划

- 新增 `tests/os_runtime/test_domain.py`，覆盖枚举值、核心对象构造、JSON round-trip、metadata 保留、中文内容保留、裁判结果主枚举。
- 新增 `tests/os_runtime/test_config.py`，覆盖默认配置、从 dict 加载、未知键处理、`DEFAULT_CONFIG` 中 `os_runtime` 段默认关闭。
- 建议回归运行：`pytest tests/os_runtime/test_domain.py tests/os_runtime/test_config.py`。
- 若 Builder 修改 `hermes_cli/config.py` 影响配置加载，再追加运行相关现有配置测试或 import smoke test。

## 假设

- Hermes 当前支持 Python dataclasses 与标准库 typing；模块 0 不引入 Pydantic 等新依赖。
- `hermes_cli/config.py::DEFAULT_CONFIG` 是当前默认配置入口。
- 计划文档中的模块 0 范围优先于后续模块内容；Linz World 原生化由模块 -1 或后续任务处理。

## 后续交接说明

- Builder Agent 应只实现本 spec 的模块 0 范围，不接入 runtime 行为。
- Reviewer Agent 重点审查对象边界是否过度、默认配置是否安全、测试是否覆盖 JSON round-trip。
- 本 spec 被 Reviewer Agent APPROVED 后，再交给 Builder Agent 在同一分支上实现。
