# Implementation Tasks: 模块 2：上下文适配与信号解释

## Phase 1: 上下文适配器

- [ ] 1.1 新增 `agent/os_runtime/adapters/context.py`
  - 定义 `ContextAdapter` 与轻量 `ContextSnapshot` 或等价返回结构。
  - 依赖通过构造函数注入，默认读取现有 Linz state、OSRuntimeEventRepository、MemoryManager、ContextEngine、tool registry 和 risk config。
  - **Requirement**: FR-001, FR-002, FR-003

- [ ] 1.2 实现 Linz World 只读投影
  - 读取 identity、authorization map、relationship summary。
  - 生成 `WorldIdentityRef`、authorization metadata、relationship metadata。
  - 未登录、无 map、failed/stale map 时写入 constraints，禁止产生许可语义。
  - **Requirement**: FR-002, FR-004, FR-009

- [ ] 1.3 实现 session/events/memory/context/tools 投影
  - 读取 session id、recent os_runtime events、memory refs、已产出 memory summary、context compression/status、available tools、risk config、resource state。
  - 填充 `TaskContextView` / `AgentContextView` 的字段和 metadata。
  - **Requirement**: FR-002, FR-003, FR-012

- [ ] 1.4 新增 `tests/os_runtime/test_context_adapter.py`
  - 覆盖完整上下文投影、缺失 identity/map、failed/stale map、relationship summary、tool names、memory refs、context summary、resource metadata。
  - 使用 fake 对象，不依赖真实 Linz World、NATS、模型、网络或外部 memory provider。
  - **Requirement**: FR-001, FR-002, FR-003, FR-004, FR-015

## Phase 2: 信号解释器

- [ ] 2.1 新增 `agent/os_runtime/engine/__init__.py`
  - 导出 `SignalInterpreter`，不引入 runtime 副作用。
  - **Requirement**: FR-005, FR-014

- [ ] 2.2 新增 `agent/os_runtime/engine/signals.py`
  - 实现 `SignalInterpreter.interpret()`。
  - 输出 `SignalSet`，保留 event refs、task context、agent context 和 metadata。
  - 固定 signals 顶层键：`needs`、`world_opportunities`、`risks`、`world_authorization`、`relationships`、`resources`、`feedback`、`constraints`。
  - **Requirement**: FR-005, FR-006, FR-007

- [ ] 2.3 实现 needs/world opportunity/relationship/resource/feedback 规则
  - 识别用户明确目标、TODO、standing goal、continuation。
  - 识别 `wsp.mrk.requirement.published`、公开需求广播、任务通知。
  - 表达关系、可用工具、iteration budget、模型/成本状态、工具失败、测试失败、用户打断、judge continue/done、世界结算/租金/交付状态。
  - **Requirement**: FR-010, FR-011, FR-012, FR-013

## Phase 3: 风险与授权 fail-closed

- [ ] 3.1 实现风险分类规则
  - 区分低风险文档任务、代码编辑/文件写入/终端命令、网络发送、外部平台消息、审批敏感动作。
  - 风险信号包含 code、level、reason、evidence_event_ids。
  - **Requirement**: FR-008

- [ ] 3.2 实现世界授权规则
  - 仅信任 `AuthorizationMap`、identity/login/auth state 和 event metadata 中的 subject/event_type。
  - 缺失 map、failed/stale map、无登录、subject/event_type 缺失或不允许时输出 blocked/unknown constraint。
  - 不生成 `OpenIntent`、`PermissionTicket` 或执行许可。
  - **Requirement**: FR-009

- [ ] 3.3 新增 `tests/os_runtime/test_signals.py`
  - 覆盖 deterministic `SignalSet.to_dict()`。
  - 覆盖七类信号、风险分类、authorization allowed/blocked/unknown、自由文本不得授权、反馈和资源信号。
  - **Requirement**: FR-005, FR-006, FR-007, FR-008, FR-009, FR-010, FR-011, FR-012, FR-013

## Phase 4: 集成检查

- [ ] 4.1 运行聚焦测试
  - `pytest tests/os_runtime/test_context_adapter.py tests/os_runtime/test_signals.py`
  - **Requirement**: SC-001

- [ ] 4.2 建议运行 os_runtime 回归
  - `pytest tests/os_runtime`
  - 确认模块 0/1 协议、配置、事件仓库和投影适配器未回归。

- [ ] 4.3 检查 diff 范围
  - 只包含模块 2 adapter、signals engine 和聚焦测试。
  - 不包含 LifeState、Tension、ActionPotential、Prompt 编译、Intent、Arbitration、自动执行或外部发布实现。

## 依赖关系与执行顺序

- Phase 1 是 Phase 2/3 的输入基础。
- Phase 2 的基础 `SignalInterpreter` 可先实现空规则骨架，再按 2.3 与 Phase 3 补齐规则。
- Phase 3 必须在合并前完成，因为授权 fail-closed 是模块 2 的核心边界。
- Phase 4 必须在所有任务完成后执行。

## 后续交接说明

- Builder Agent 应按 Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 实现。
- Reviewer Agent 应在实现前确认信号结构、授权边界和测试场景足够清晰。
- 本任务不允许实现自动行动、裁判、prompt 编译或业务 side effect。
