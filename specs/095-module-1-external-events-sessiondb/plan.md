# 实施计划: 模块 1：外部事件接入与 SessionDB 适配

**分支**: `feat/95-module-1-external-events-sessiondb`
**日期**: 2026-05-13
**规范**: `specs/095-module-1-external-events-sessiondb/spec.md`
**输入**: Issue OPE-95；`docs/基于张力场的Agent自驱动实现计划.md`

## 摘要

实现 passive `os_runtime` 事件投影和可靠外部事件接入：在 SessionDB/profile 状态边界内提供 `OSRuntimeEventRepository` 查询 API；把 Linz World/NATS、Hermes 对话、工具、assistant response、continuation、publish receipt 和 runtime error 投影为统一自治事件；确保 raw world event 先持久化再进入 gateway，NATS ack 不等待 LLM 完整处理，禁用 `os_runtime` 时保持现有行为不变。

## 技术背景

**语言/版本**: Python，沿用仓库当前支持范围。
**主要依赖**: 标准库、现有 `hermes_state.py::SessionDB`、`agent.os_runtime.domain/config`、`agent.linz_world`、gateway `MessageEvent`、plugin hooks；不新增必需依赖。
**存储**: 首选 `SessionDB` 所在 SQLite state.db side tables；允许同 profile JSONL/state fallback 作为短期过渡，但必须封装在 repository API 后。
**测试**: pytest，使用 fake SessionDB/profile 临时目录，不依赖网络、真实 NATS、真实 Linz World 服务或真实模型。
**目标平台**: Hermes CLI/gateway/TUI 当前运行环境。
**项目类型**: Python CLI/agent runtime 仓库。
**性能目标**: 单次事件 append/list 查询为轻量本地 I/O；超长工具结果不得整体写入自治事件。
**约束条件**: `os_runtime.enabled=false` 时不写事件、不注册额外工具、不注入 prompt；world raw payload 不进入普通 prompt/输出。
**规模/范围**: 模块 1，仅涉及事件仓库、投影适配器、Linz event reliability 和聚焦测试。

## 章程检查

- **Profile-Scoped State**: 通过。事件仓库必须绑定当前 Hermes profile，优先复用 `SessionDB`/`get_hermes_home()`。
- **Native Surfaces Before Optional Skills**: 通过。实现落在 `agent/linz_world`、`agent/os_runtime` 和现有 gateway/hooks，不依赖外部 skill。
- **Fail-Closed External Side Effects**: 通过。本模块不新增外部副作用；world publish receipt 只记录结果，发布治理仍由模块 -1 负责。
- **Privacy and Audit Separation**: 通过。raw payload/超长工具结果只保存摘要与引用，受限审计 payload 不进入 prompt/普通输出。
- **Testable Incremental Delivery**: 通过。任务按 repository、world event reliability、runtime projection、禁用/摘要测试拆分。

## 项目结构

### 文档(此功能)

```text
specs/095-module-1-external-events-sessiondb/
├── spec.md
├── plan.md
└── tasks.md
```

### 源代码(仓库根目录)

```text
agent/
├── linz_world/
│   ├── event_state.py
│   ├── event_bus.py
│   └── gateway_adapter.py
└── os_runtime/
    └── adapters/
        ├── __init__.py
        ├── events.py
        └── session_store.py

tests/
├── linz_world/
│   ├── test_event_state.py
│   └── test_gateway_adapter.py
└── os_runtime/
    ├── test_events_adapter.py
    └── test_session_store_adapter.py
```

**结构决策**: 不新增 runtime driver 或 engine 子模块；模块 1 只建立事件输入和查询基座，供后续模块消费。

## 修改范围

- 新增 `agent/os_runtime/adapters/__init__.py`，导出 adapters 稳定入口。
- 新增 `agent/os_runtime/adapters/session_store.py`，实现 `OSRuntimeEventRepository` 和事件记录 schema。
- 新增 `agent/os_runtime/adapters/events.py`，实现配置感知的事件投影适配器与 summary/ref 逻辑。
- 完善 `agent/linz_world/event_state.py`，确保 raw event、sequence dedupe、dispatch failure/retry/manual handling 的 contract 清晰且可测。
- 完善 `agent/linz_world/event_bus.py`，确保 `MessageEvent` 带必要关联字段和脱敏摘要。
- 完善 `agent/linz_world/gateway_adapter.py`，确保 receive-only 平台注册与 persist-before-dispatch 边界可测试。
- 新增或扩展聚焦测试文件。

## 关键设计

### Repository Contract

`OSRuntimeEventRepository` 是唯一对外事件仓库入口，提供：

- `append(event)`：写入并返回规范化事件；重复 event id 应幂等或返回既有记录。
- `get(event_id)`：按 id 获取。
- `list_recent(limit=...)`：按 timestamp/insert order 倒序。
- `list_by_session(session_id, limit=...)`。
- `list_by_trace(trace_id, limit=...)`。

事件结构应兼容 `OSRuntimeEventRef`，同时补充 `event_type`、`content_ref`、`payload_hash`、`status` 和 metadata。Builder 可用 dataclass 或轻量 dict normalization，但必须保持 JSON round-trip。

### SessionDB/State Strategy

首选方案是在 `state.db` 内新增独立 side tables，例如 `os_runtime_events`、`linz_world_events`、`linz_world_dispatch`、`linz_world_publish_receipts`，复用 `apply_wal_with_fallback()` 与 SessionDB 写入锁/重试策略。若为降低 schema 风险采用 JSONL fallback，fallback 必须：

- 位于当前 profile 的 `get_hermes_home()` 下。
- 只作为 repository 后端，不暴露第二套 API。
- 保持 append-only、bounded summary 和 deterministic query 行为。
- 在代码注释或 plan follow-up 中标记后续迁移到 SessionDB side tables。

### Projection Adapter

`EventProjectionAdapter` 负责把不同输入归一化：

- Linz/NATS `MessageEvent` -> `world_event`
- Hermes user message -> `human_request`
- Hermes conversation turn -> `conversation_turn`
- assistant final response -> `assistant_response`
- tool call -> `tool_called`
- tool result -> `tool_result`
- goal continuation -> `os_runtime_continuation`
- world publish receipt -> `world_event_published`
- runtime exception/status -> `runtime_feedback`

Adapter 必须在入口读取 `OSRuntimeConfig`；disabled 时 no-op。投影异常应被隔离，不破坏原始对话/工具执行。

### Linz World Reliability

世界事件处理顺序：

1. normalize raw event，生成 payload summary 和 audit ref。
2. 按 event id 与 sequence 去重。
3. 持久化 raw ref 和 dispatch record。
4. 生成 Hermes `MessageEvent`，只带脱敏 summary/raw audit ref。
5. 交给 gateway `handle_message()` 或等价 runner。
6. LLM/agent 失败时只更新 dispatch status；NATS ack 不等待完整处理。

### Privacy/Size Policy

普通自治事件中工具结果和 world payload 使用 bounded summary、payload hash、content_ref/audit_ref。默认阈值应由常量控制并在测试中覆盖；敏感字段不得出现在 prompt 注入、普通工具结果或默认日志。

## 风险与取舍

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| SessionDB schema 扩展影响旧用户 | state.db migration 可能破坏现有会话 | 使用独立 side tables、聚焦 migration 测试；必要时先以 repository 封装 JSONL fallback |
| hook 参数不足 | 无法捕获所有 runtime 细节 | 先覆盖明确 hook/post_tool/post_llm/goal/gateway 输入；缺口用显式 adapter 调用最小补齐 |
| NATS redelivery 重复触发 | agent turn 被重复执行 | persist-before-dispatch，event id 与 sequence 双键 dedupe |
| raw payload 泄漏 | prompt 或普通输出包含敏感数据 | summary/ref 分离，测试敏感/超长 payload |
| disabled 配置漏写 | 默认关闭仍产生事件或 prompt 变化 | projection 和 repository 两层 no-op/guard，新增禁用测试 |

## 验收标准

- `pytest tests/linz_world/test_event_state.py tests/linz_world/test_gateway_adapter.py tests/os_runtime/test_events_adapter.py tests/os_runtime/test_session_store_adapter.py` 通过。
- `OSRuntimeEventRepository.append()`、`get()`、`list_recent()`、`list_by_session()`、`list_by_trace()` 均可用且被测试覆盖。
- 普通对话、assistant response、tool call、tool result、goal continuation、world publish receipt、runtime error 均有投影测试。
- NATS/Linz World 事件先持久化再投递，重复 event id/sequence 不重复触发 agent turn。
- `os_runtime.enabled=false` 时不写事件、不注册额外工具、不注入 prompt。
- 超长工具结果只保存摘要和引用，raw payload 不进入普通自治事件。

## 测试计划

1. 先写 `tests/os_runtime/test_session_store_adapter.py`，验证 repository API 与 profile isolation。
2. 写 `tests/os_runtime/test_events_adapter.py`，验证投影类型、disabled no-op、summary/ref 和 runtime error。
3. 扩展 `tests/linz_world/test_event_state.py`，验证 raw persist、dedupe、dispatch retry/manual handling。
4. 扩展 `tests/linz_world/test_gateway_adapter.py`，验证平台注册、receive-only、`MessageEvent` 关联字段和 persist-before-dispatch。
5. 回归运行 `pytest tests/os_runtime tests/linz_world/test_event_state.py tests/linz_world/test_gateway_adapter.py`。

## 后续交接说明

- Builder Agent 不应实现后续 engine/driver/arbiter，也不应修改普通 prompt 注入策略，除非为 disabled no-op 或 hook 参数补齐所需的最小连接。
- Reviewer Agent 应审查：SessionDB-first 是否真实可执行；fallback 是否只是过渡；NATS ack 与 LLM 处理是否解耦；禁用行为和隐私摘要测试是否足够。
- 本计划 APPROVED 后，交给 Builder Agent 在同一分支实现。
