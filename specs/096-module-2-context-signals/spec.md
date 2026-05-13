# 功能规范: 模块 2：上下文适配与信号解释

**功能分支**: `feat/96-module-2-context-signals`
**Spec-Kit 特性目录**: `specs/096-module-2-context-signals`
**创建时间**: 2026-05-13
**状态**: 草稿，待 Spec Reviewer Agent 审查
**输入**: Issue OPE-96；`docs/基于张力场的Agent自驱动实现计划.md` 中“模块 2：上下文适配与信号解释”

## 背景

模块 0 已定义 `TaskContextView`、`AgentContextView`、`SignalSet`、`WorldIdentityRef`、`RiskLevel` 等协议对象；模块 1 已把 Hermes 对话、工具调用、continuation、runtime feedback 与 Linz World 事件投影为可查询的 `os_runtime` events。模块 2 的职责是在这些输入之上生成张力场可消费的上下文视图和信号集合，为后续生命状态、张力解释和意图生成模块提供稳定输入。

本模块不替代 `agent/context_engine.py`，不重写 MemoryManager、SessionDB 或 tool registry，也不从 LLM 自由文本中推断身份、权限或授权许可。它只做只读适配、确定性信号解释和风险/授权约束表达。

## 目标

- 新增 `agent/os_runtime/adapters/context.py`，提供 `ContextAdapter`，从 Linz World state、SessionDB/os_runtime events、MemoryManager prefetch、ContextEngine 状态、tool registry 和风险配置生成 `TaskContextView` / `AgentContextView`。
- 新增 `agent/os_runtime/engine/signals.py`，提供规则版 `SignalInterpreter`，把上下文和 recent events 转为确定性 `SignalSet`。
- 覆盖需求、世界机会、风险、世界授权、关系、资源和反馈七类信号。
- 新增 `tests/os_runtime/test_context_adapter.py` 与 `tests/os_runtime/test_signals.py`，验证上下文投影、确定性、风险分类和授权 fail-closed。

## 非目标

- 不实现 LifeState、TensionInterpreter、TensionFieldEngine、ActionPotential、SelfPrompt、OpenIntent、Arbitration 或自动执行。
- 不触发工具调用、外部消息发送、Linz World 发布、关系写入、memory 写入或 continuation。
- 不新增外部 memory provider，不替换 `agent/context_engine.py` 的压缩逻辑。
- 不把授权 map、身份或权限从 LLM 文本中无约束抽取为事实。
- 不改变 `os_runtime.enabled=false` 时现有对话、工具、gateway、TUI 或 prompt 行为。

## 需求理解

### 用户故事 1 - Builder 可获得张力场输入视图 (优先级: P1)

作为后续张力场 engine，我需要一个只读 `ContextAdapter`，把当前任务、身份、授权状态、关系摘要、会话、近期自治事件、可用工具、风险配置、memory refs 和压缩状态汇总为 `TaskContextView` 与 `AgentContextView`。

**优先级原因**: 后续 LifeState/Tension 模块依赖同一份上下文视图；如果各模块各自读取会话、工具、记忆和 Linz World state，会产生不一致的自治输入。

**独立测试**: 使用 fake repository、fake LinzStateRepository、fake memory/context/tool registry 构造上下文，断言输出字段稳定、只读且不触发外部副作用。

**验收场景**:

1. **给定** 已登录身份、CURRENT 授权 map、关系摘要、session id、memory refs、可用工具和 recent events，**当** 调用 `ContextAdapter.build_context()`，**那么** 返回的 `TaskContextView` / `AgentContextView` 包含对应摘要、约束、recent event ids 和 tool names。
2. **给定** 未登录或缺失授权 map，**当** 构造上下文，**那么** world identity/authorization 状态被标记为 unknown/failed，且约束中包含不可执行外部副作用的原因。

---

### 用户故事 2 - 规则解释器产生确定性 SignalSet (优先级: P1)

作为后续张力解释器，我需要 `SignalInterpreter` 基于确定性规则把 recent events 与上下文转成 `SignalSet`，相同输入必须得到相同输出，且信号不直接代表行动。

**优先级原因**: 模块 2 是事件进入张力场前的最后一层解释；若输出不稳定或含行动许可，会破坏后续裁判和授权边界。

**独立测试**: 固定输入事件顺序、时间和上下文，重复调用解释器，断言 `SignalSet.to_dict()` 完全一致。

**验收场景**:

1. **给定** 相同 recent events 和上下文，**当** 连续两次解释，**那么** `SignalSet` 内容完全一致。
2. **给定** 用户明确目标、TODO 或 standing goal 事件，**当** 解释，**那么** 输出需求信号，但不生成 intent 或 permission ticket。

---

### 用户故事 3 - 风险、授权与关系边界 fail-closed (优先级: P2)

作为 Hermes 用户和 Linz World 审计者，我需要低风险文档任务、代码编辑任务、终端/文件写入、网络发送、外部平台消息和世界发布类事件被区分风险等级，并且缺失授权时只产生风险/约束信号。

**优先级原因**: 信号层如果把 world event 或外部消息误判为可执行许可，后续自治模块可能绕过 authorization map。

**独立测试**: 构造低风险文档、代码编辑、外部消息、world publish/event receipt、无授权 map 等输入，断言风险等级与授权信号符合预期。

**验收场景**:

1. **给定** 文档摘要任务事件，**当** 解释风险，**那么** 输出低风险或信息类风险信号。
2. **给定** 文件写入、终端命令或代码编辑事件，**当** 解释风险，**那么** 输出高于低风险的本地变更风险信号。
3. **给定** 外部平台消息或 world publish 意图相关事件，**当** 授权 map 缺失或不允许 subject/event_type，**那么** 输出 `world_authorization` constraint，不输出执行许可。

---

### 用户故事 4 - 反馈与资源状态可被后续模块消费 (优先级: P3)

作为后续自治 driver，我需要工具失败、测试失败、用户打断、judge continue/done、世界结算/租金/交付状态、剩余 iteration budget、模型/成本状态和可用工具被表达为资源/反馈信号。

**独立测试**: 构造 runtime_feedback、tool_result failure、test failure、judge 状态、resource metadata 和 tool registry 输入，断言 `signals["feedback"]` 与 `signals["resources"]` 字段存在且稳定。

## 修改范围

- `agent/os_runtime/adapters/context.py`
- `agent/os_runtime/engine/__init__.py`
- `agent/os_runtime/engine/signals.py`
- `tests/os_runtime/test_context_adapter.py`
- `tests/os_runtime/test_signals.py`

## 建议方案

采用只读 adapter + 规则解释器两层结构：

- `ContextAdapter` 负责收集现有系统状态并投影为 `TaskContextView` / `AgentContextView`，所有依赖通过构造函数注入，测试使用 fake 对象。
- `SignalInterpreter` 只消费 `TaskContextView`、`AgentContextView`、`OSRuntimeEvent`/`OSRuntimeEventRef` 和可选授权/风险上下文，输出 `SignalSet`。
- 信号数据放在 `SignalSet.signals` 的结构化 dict 中，固定顶层键：`needs`、`world_opportunities`、`risks`、`world_authorization`、`relationships`、`resources`、`feedback`、`constraints`。
- 规则以 event_type、EventSource、metadata、tool name、subject/event_type、risk config 和 authorization map 为依据；身份/授权不得从自由文本解析。

## 功能需求

- **FR-001**: 系统必须提供 `ContextAdapter.build_context()` 或等价入口，返回 `TaskContextView` 与 `AgentContextView`。
- **FR-002**: `ContextAdapter` 必须读取当前 Linz World identity、authorization map、relationship summary、session 信息、recent os_runtime events、available tools、risk config 和 memory refs。
- **FR-003**: `ContextAdapter` 必须复用现有 `ContextEngine` 状态、`MemoryManager.prefetch_all()` 已产出或显式传入的 memory summary、`tools.registry` 工具定义和 `SessionDB`/`OSRuntimeEventRepository` 查询结果，不新增第二套会话或记忆实现。
- **FR-004**: `ContextAdapter` 在缺少 identity、login session 或 authorization map 时必须 fail-closed，记录 constraints，不得生成任何执行许可。
- **FR-005**: 系统必须提供 `SignalInterpreter.interpret()` 或等价入口，输出 `SignalSet`，并保留输入 event refs、task context 和 agent context。
- **FR-006**: `SignalSet.signals` 必须至少覆盖 `needs`、`world_opportunities`、`risks`、`world_authorization`、`relationships`、`resources`、`feedback` 和 `constraints`。
- **FR-007**: `SignalInterpreter` 首版必须使用确定性规则，不调用 LLM，不依赖网络，不使用当前时间生成不可预测排序。
- **FR-008**: 风险规则必须能区分低风险文档任务、代码编辑/文件写入/终端命令、网络发送、外部平台消息和审批敏感动作。
- **FR-009**: 世界授权规则必须只信任 `AuthorizationMap`/governance 结构化输入；缺失或不允许 subject/event_type 时只输出风险/约束信号。
- **FR-010**: 世界机会规则必须识别 `wsp.mrk.requirement.published`、公开需求广播和任务通知类 world event。
- **FR-011**: 关系规则必须从 Linz relationship records、MessageEvent metadata 或 event source metadata 读取对端/需求发布方/接单方摘要。
- **FR-012**: 资源规则必须表达可用工具、剩余 iteration budget、模型/成本状态和禁用的能力。
- **FR-013**: 反馈规则必须表达工具失败、测试失败、runtime error、用户打断、judge continue/done、世界结算/租金/交付状态。
- **FR-014**: `os_runtime.enabled=false` 时，本模块不得被默认接入主流程；单元测试可直接调用 adapter/interpreter 验证纯函数行为。
- **FR-015**: 测试不得依赖真实 Linz World 服务、NATS、真实模型、网络或外部 memory provider。

## 关键实体

- **ContextAdapter**: 只读适配器，组合 Linz World、SessionDB/os_runtime events、MemoryManager、ContextEngine、tool registry 和 risk config，输出上下文视图。
- **ContextSnapshot**: 建议的轻量内部返回结构，包含 `task_context`、`agent_context`、`recent_events` 和诊断 constraints；也可直接返回 tuple/dict。
- **SignalInterpreter**: 规则解释器，把上下文和事件解释为 `SignalSet`。
- **SignalSet**: 模块 0 协议对象；本模块填充 `event_refs`、`task_context`、`agent_context`、`signals` 和 `metadata`。
- **Authorization Signal**: 对结构化 authorization map 的只读判断，表达 allowed/blocked/unknown 和原因，不产生 permission ticket。
- **Risk Signal**: 对事件和任务表面的风险分级，使用模块 0 `RiskLevel` 值或字符串兼容值。

## 关键设计

- 依赖注入优先：`ContextAdapter` 接受 repository、linz state repository、memory manager、context engine、tool registry、config 等可选参数，默认使用现有全局入口；测试不需要 monkeypatch 大量全局状态。
- 只读投影：adapter 只调用读取方法，如 `get_identity()`、`get_authorization_map()`、`relationships()`、`list_recent()`、`prefetch_all()` 的已产出结果或显式 memory summary；不得写入 state、刷新远端授权或触发 login。
- 稳定排序：recent events、tools、signals 内部列表按 timestamp/event_id/name 等稳定键排序；无 timestamp 时保留输入顺序并在 metadata 标记。
- 信号结构化：每条信号至少包含 `type`、`level` 或 `status`、`reason`、`evidence_event_ids`；authorization/risk/feedback 需带 machine-readable code。
- 授权 fail-closed：world event 可产生机会和关系信号，但只有 authorization map 明确允许时才标记 `status=allowed`；缺失 map、未登录、failed/stale 均标记 constraint。
- 文本解析边界：可以用自由文本识别 TODO、测试失败、文档/代码任务关键词等低风险分类，但身份、权限、授权 subject/event_type 必须来自 metadata 或 AuthorizationMap。

## 风险与取舍

- **规则过粗风险**: 首版 deterministic rules 可能误分部分任务风险。缓解：规则集中在 `signals.py`，测试覆盖 issue 明确场景，并在 metadata 中保留 evidence。
- **依赖耦合风险**: 直接读取多个 runtime 对象容易耦合主流程。缓解：构造函数注入、只读接口、fake 测试和 no default main-loop 接入。
- **授权误判风险**: world event metadata 不完整时可能被误当可执行。缓解：缺失 subject/event_type 或 map 时一律 unknown/blocked。
- **信号 schema 演进风险**: 后续 LifeState/Tension 可能需要更多字段。缓解：使用 `SignalSet.signals` 中的结构化 dict 与 `metadata` 保留扩展点。
- **memory/context 读取成本风险**: `prefetch_all()` 可能触发 provider 工作。缓解：adapter 优先接受已产出的 memory summary/refs；Builder 若调用 prefetch，必须让测试证明可控且不新增 provider。

## 验收标准

- **SC-001**: `pytest tests/os_runtime/test_context_adapter.py tests/os_runtime/test_signals.py` 通过。
- **SC-002**: 相同 recent events、authorization map、relationship summary、tools 和 memory/context 输入，重复生成的 `SignalSet.to_dict()` 完全一致。
- **SC-003**: 低风险文档任务、代码编辑/文件写入/终端命令、外部消息任务能输出不同风险等级或风险 code。
- **SC-004**: world event 不会绕过 authorization map；未登录、无 map、stale/failed map 或 subject/event_type 不允许时只产生风险/约束信号。
- **SC-005**: `ContextAdapter` 输出包含 identity/map 状态、relationship summary、session id、recent event ids、memory refs、tool names、context summary 和 constraints。
- **SC-006**: 测试证明本模块不调用 LLM、网络、真实 Linz World 服务、真实 NATS 或外部 memory provider。
- **SC-007**: 本模块不修改普通对话、工具执行、prompt 注入、gateway dispatch 或自动 continuation 行为。

## 测试计划

- 新增 `tests/os_runtime/test_context_adapter.py`：
  - fake Linz identity/map/relationships + fake recent events + fake tool registry，断言上下文字段。
  - 未登录、无授权 map、failed/stale map 的 constraints。
  - memory refs、context summary、session id、iteration budget、模型/成本 metadata 的传递。
- 新增 `tests/os_runtime/test_signals.py`：
  - deterministic `SignalSet.to_dict()`。
  - needs/world opportunities/relationships/resources/feedback 七类信号。
  - 文档任务、代码编辑、终端命令、网络发送、外部消息的风险分类。
  - authorization allowed/blocked/unknown 与 subject/event_type 缺失场景。
- 建议回归运行：`pytest tests/os_runtime`，确保模块 0/1 协议和事件适配器未被破坏。

## 假设

- 模块 0 的协议对象和配置已在 Builder 开始前可用。
- 模块 1 的 `OSRuntimeEventRepository`、`OSRuntimeEvent` 和 `EventProjectionAdapter` 已在当前分支基线可导入；如模块 1 尚未合并，Builder 应先同步或基于同一分支完成依赖。
- Linz World `LinzStateRepository` 可读取 identity、authorization map、relationships 和 recent world records。
- 首版信号解释只要求可测试的确定性规则，不追求完整语义理解。

## 后续交接说明

- Builder Agent 应按 `tasks.md` 的阶段实现，先完成 adapter 输出，再实现 SignalInterpreter，最后接测试。
- Builder Agent 不应在本模块接入自动执行、意图生成、裁判或 prompt 编译。
- Reviewer Agent 应重点审查 fail-closed 授权边界、信号确定性、依赖注入可测试性和是否误触碰主流程。
