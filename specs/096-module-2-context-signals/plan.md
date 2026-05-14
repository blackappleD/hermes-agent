# 实施计划: 模块 2：上下文适配与信号解释

**分支**: `feat/96-module-2-context-signals`
**日期**: 2026-05-13
**规范**: `specs/096-module-2-context-signals/spec.md`
**输入**: Issue OPE-96；`docs/基于张力场的Agent自驱动实现计划.md`

## 摘要

实现模块 2 的只读上下文适配和确定性信号解释：`ContextAdapter` 汇总 Linz World identity/authorization/relationship、SessionDB/os_runtime recent events、memory/context 摘要、tool registry、risk config 和资源状态，生成 `TaskContextView` / `AgentContextView`；`SignalInterpreter` 基于规则输出稳定 `SignalSet`，覆盖需求、世界机会、风险、世界授权、关系、资源和反馈信号。模块不生成行动、不接入自动执行、不替代现有上下文/记忆/工具基础设施。

## 技术背景

**语言/版本**: Python，沿用仓库当前支持范围。
**主要依赖**: 标准库、`agent.os_runtime.domain/config`、`agent.os_runtime.adapters.session_store`、`agent.linz_world` state/auth/relationship models、`agent.context_engine.ContextEngine`、`agent.memory_manager.MemoryManager`、`tools.registry`、`hermes_state.SessionDB`。
**存储**: 只读消费现有 profile state、SessionDB/os_runtime events 和 Linz state；本模块不新增存储表。
**测试**: pytest，使用 fake repository/state/memory/context/tool registry，不依赖网络、真实 Linz World 服务、真实 NATS、真实模型或外部 memory provider。
**目标平台**: Hermes CLI/gateway/TUI 当前运行环境。
**项目类型**: Python CLI/agent runtime 仓库。
**性能目标**: 单次 context build 只做 bounded recent events 查询和本地对象投影；信号解释为线性规则扫描。
**约束条件**: `os_runtime.enabled=false` 不默认接入主流程；身份、权限和授权只能来自结构化 state/map；输出 `SignalSet` 不得包含 intent、ticket 或执行许可。
**规模/范围**: 模块 2，仅新增 context adapter、signals engine 和聚焦测试。

## 章程检查

- **Profile-Scoped State**: 通过。所有读取绑定当前 Hermes profile 的 Linz state、SessionDB/os_runtime repository 和现有 MemoryManager/ContextEngine。
- **Native Surfaces Before Optional Skills**: 通过。实现落在 `agent/os_runtime`，复用现有 Hermes/Linz/tool registry，不依赖外部 skill。
- **Fail-Closed External Side Effects**: 通过。模块只读，缺失授权 map 或登录状态时输出 constraints，不生成执行许可。
- **Privacy and Audit Separation**: 通过。只消费模块 1 的 bounded summary/ref 和 Linz relationship summary，不读取或泄漏 raw payload/token。
- **Testable Incremental Delivery**: 通过。任务拆分为 adapter、signal rules、风险/授权和集成检查，均可用 fake 对象测试。

## 项目结构

### 文档(此功能)

```text
specs/096-module-2-context-signals/
├── spec.md
├── plan.md
└── tasks.md
```

### 源代码(仓库根目录)

```text
agent/
└── os_runtime/
    ├── adapters/
    │   └── context.py
    └── engine/
        ├── __init__.py
        └── signals.py

tests/
└── os_runtime/
    ├── test_context_adapter.py
    └── test_signals.py
```

**结构决策**: `adapters/context.py` 放只读投影，`engine/signals.py` 放张力场前置解释规则。暂不新增 driver、arbiter、intent 或 prompt compiler。

## 修改范围

- 新增 `agent/os_runtime/adapters/context.py`：
  - 定义 `ContextAdapter` 和必要的轻量 `ContextSnapshot`/输入 DTO。
  - 读取 identity、authorization map、relationships、recent events、session、memory refs、context status、available tools、risk config、resource metadata。
  - 输出 `TaskContextView` 与 `AgentContextView`，并保留 constraints/diagnostics。
- 新增 `agent/os_runtime/engine/__init__.py`：
  - 导出 `SignalInterpreter`，避免 runtime 副作用。
- 新增 `agent/os_runtime/engine/signals.py`：
  - 实现 deterministic rules 和 `SignalSet` 构建。
  - 固定信号顶层键：`needs`、`world_opportunities`、`risks`、`world_authorization`、`relationships`、`resources`、`feedback`、`constraints`。
- 新增 `tests/os_runtime/test_context_adapter.py`。
- 新增 `tests/os_runtime/test_signals.py`。

## 关键设计

### ContextAdapter Contract

建议接口：

```python
snapshot = ContextAdapter(...).build_context(
    session_id=session_id,
    user_goal=user_goal,
    active_goal=active_goal,
    task_id=task_id,
    memory_summary=memory_summary,
    memory_refs=memory_refs,
    resource_state=resource_state,
)
```

返回值可以是 `ContextSnapshot` dataclass，也可以是结构化 dict，但必须包含：

- `task_context: TaskContextView`
- `agent_context: AgentContextView`
- `recent_events: list[OSRuntimeEvent | OSRuntimeEventRef]`
- `constraints: list[str]`
- `diagnostics: dict`

Adapter 默认依赖可以为空；为空时从现有模块读取可用状态。测试应直接注入 fake 对象，避免真实网络或 profile 状态。

### Context Fields

`TaskContextView` 至少填充：

- `task_id`、`session_id`、`user_goal`、`active_goal`
- `recent_event_ids`
- `memory_refs`
- `tool_names`
- `constraints`
- `metadata`: authorization map version、risk config、relationship ids、resource state、context token/压缩状态、iteration budget

`AgentContextView` 至少填充：

- `agent_id` 或 profile id
- `profile_name`
- `world_identity: WorldIdentityRef`
- `capabilities` 和 `active_tools`
- `memory_summary`
- `context_summary`
- `metadata`: authorization state、allowed subjects/event types/capabilities 摘要、relationship summary、model/cost state

### SignalInterpreter Contract

建议接口：

```python
signal_set = SignalInterpreter(risk_config=...).interpret(
    task_context=snapshot.task_context,
    agent_context=snapshot.agent_context,
    events=snapshot.recent_events,
    authorization_map=auth_map,
    relationships=relationships,
)
```

解释器必须：

- 不调用 LLM、网络、工具或 state 写入。
- 输出稳定排序的 `SignalSet`。
- 将每个输入 event 转成 `event_refs`，并在信号中记录 `evidence_event_ids`。
- 不输出 `OpenIntent`、`PermissionTicket`、`ArbitrationResult` 或任何执行指令。

### Rule Families

- **needs**: 用户明确目标、未完成 TODO、standing goal、continuation。
- **world_opportunities**: `wsp.mrk.requirement.published`、公开需求广播、任务通知、world_event 中的可参与机会。
- **risks**: 文档/只读低风险，代码编辑/文件写入/终端中风险或高风险，网络发送/外部消息/审批敏感高风险。
- **world_authorization**: allowed/blocked/unknown，基于 `AuthorizationMap.allows_event()`、map state、login/identity 状态和 subject/event_type。
- **relationships**: relationship records、message source、counterparty、publisher/assignee。
- **resources**: available tools、disabled capabilities、iteration budget、model/cost state。
- **feedback**: tool_result failure、runtime_feedback、test failure、user interruption、judge continue/done、world settlement/rent/delivery status。
- **constraints**: 来自 adapter 的 fail-closed 约束、缺失 map、stale map、无 session、无可用工具等。

### Risk And Authorization

风险分类不等于许可。即使风险为低，也不能生成 intent 或 ticket。世界授权只承认结构化字段：

- identity/login/auth map state
- `AuthorizationMap.allowed_publish_subjects`
- `AuthorizationMap.allowed_publish_event_types`
- event metadata 中的 `subject` / `event_type`

自由文本只可用于任务/风险提示，不可用于身份、授权主体或权限来源。

### Determinism

- 输入事件排序以调用者顺序为主；输出时使用 `(timestamp, event_id, event_type)` 或输入 index 稳定排序。
- tools、capabilities、subjects、relationships 输出前排序。
- 不使用 `datetime.now()`、随机 id 或 dict 原始遍历顺序生成 signal 内容。
- metadata 中如需运行诊断，必须使用输入可复现字段。

## 风险与取舍

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 规则解释不够智能 | 部分复杂任务风险或机会识别不完整 | 首版以 issue 验收场景为准，保留 evidence 和 rule code，后续可扩展 |
| 多依赖读取导致测试脆弱 | ContextAdapter 可能难以隔离 | 构造函数注入，fake repository/state/memory/context/tool registry |
| 授权 map 缺失被误放行 | world side effect 可能越权 | fail-closed，缺失/failed/stale 一律 blocked/unknown |
| MemoryManager prefetch 有副作用或成本 | context build 可能触发 provider 工作 | 优先接受已产出 summary/refs；若 Builder 读取 prefetch，需测试 no external provider |
| 信号 schema 后续不够用 | LifeState/Tension 需要字段扩展 | 固定顶层键，条目使用 code/reason/evidence/metadata 扩展 |

## 验收标准

- `pytest tests/os_runtime/test_context_adapter.py tests/os_runtime/test_signals.py` 通过。
- 相同输入重复调用 `SignalInterpreter.interpret()` 得到完全相同的 `SignalSet.to_dict()`。
- `ContextAdapter` 输出覆盖 identity/map、relationship summary、session、recent event ids、available tools、risk config、memory refs、context summary 和 constraints。
- 风险规则区分低风险文档任务、代码编辑/文件写入/终端命令、网络发送/外部平台消息。
- world event 不绕过 authorization map；无登录、无 map、stale/failed map 或不允许 subject/event_type 时仅输出风险/约束信号。
- 本模块不触发 LLM、工具、网络、NATS、Linz World 发布、memory 写入或 prompt 注入。

## 测试计划

1. 写 `tests/os_runtime/test_context_adapter.py`，覆盖完整上下文、缺失 identity/map、relationship summary、recent events、tool names、memory refs、resource metadata。
2. 写 `tests/os_runtime/test_signals.py`，覆盖 deterministic 输出、七类信号、风险分类、authorization allowed/blocked/unknown、反馈信号。
3. 运行聚焦测试：`pytest tests/os_runtime/test_context_adapter.py tests/os_runtime/test_signals.py`。
4. 建议回归：`pytest tests/os_runtime`，确认模块 0/1 未回归。

## 后续交接说明

- Builder Agent 应先实现可测试的数据投影和规则输出，再考虑是否需要把 adapter 暴露给后续模块。
- 不要在本模块接入主循环自动调用、prompt 编译、OpenIntent、裁判或外部 side effect。
- Reviewer Agent 应重点审查 deterministic 行为、fail-closed 授权、只读边界和测试是否足以阻止权限/身份从文本误抽取。
