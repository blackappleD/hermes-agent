# 功能规范: 模块 1：外部事件接入与 SessionDB 适配

**功能分支**: `feat/95-module-1-external-events-sessiondb`
**Spec-Kit 特性目录**: `specs/095-module-1-external-events-sessiondb`
**创建时间**: 2026-05-13
**状态**: 草稿，待 Reviewer Agent 审查
**输入**: Issue OPE-95；`docs/基于张力场的Agent自驱动实现计划.md` 中“模块 1：外部事件接入与 SessionDB 适配”

## 背景

Hermes 已有 `SessionDB`、gateway `MessageEvent`、plugin hooks、goal continuation 和 Linz World 原生模块雏形。模块 1 的目标不是重写会话、消息、工具或 agent 主循环，而是把 NATS 世界事件、Hermes 对话、工具调用/结果、模型回复、continuation 和 runtime error 投影为统一的 `os_runtime` 自治事件，作为后续生命状态、张力解释、行动势能和裁判模块的输入。

当前 `agent/linz_world/event_state.py` 已有 JSON 状态仓库和 dedupe 基础，`agent/linz_world/event_bus.py` 已能把世界事件记录投影为 `MessageEvent`，`agent/linz_world/gateway_adapter.py` 已注册 receive-only 平台。模块 1 需要在这些基础上收敛到 SessionDB-first 的可靠存储边界，并提供 `os_runtime` 事件仓库与投影适配器。

## 目标

- 在 `agent/os_runtime/adapters/session_store.py` 提供 profile-aware 的 `OSRuntimeEventRepository`，优先复用 `hermes_state.py::SessionDB` 所在 SQLite/WAL 策略和同一 profile 状态路径。
- 在 `agent/os_runtime/adapters/events.py` 提供事件投影适配器，将 Linz World `MessageEvent`、Hermes 用户消息、assistant response、tool call、tool result、goal continuation、world publish receipt 和 runtime error 转成 `OSRuntimeEventRef` 兼容事件。
- 完善 `agent/linz_world/event_state.py`、`event_bus.py` 和 `gateway_adapter.py` 的可靠接入契约：raw world event 先持久化和去重，再进入 Hermes gateway `MessageEvent` 流。
- 保证 agent/LLM 处理失败不会阻塞 NATS ack；失败转化为 Hermes 内部 dispatch status、attempt_count、last_error 和 manual handling 标记。
- 增加 `tests/linz_world/` 与 `tests/os_runtime/` 覆盖，验证去重、关联字段、查询 API、禁用行为和超长工具结果摘要。

## 非目标

- 不实现生命状态计算、张力解释、张力网络、行动势能、Prompt 编译、意图生成、裁判、evidence 聚合或泡泡协议。
- 不新增独立会话数据库，不替换 `SessionDB`、MemoryManager、ContextEngine、tool registry、gateway busy queue 或 `/goal` 主流程。
- 不默认启用自驱动、自动响应、自动监听、自动 continuation 或自动外部发布。
- 不在 prompt、普通工具结果或默认日志中暴露 Linz World raw payload、token、私钥或完整未筛选工具结果。
- 不实现 Linz World 身份注册、登录、授权 map 刷新、发布治理或世界算力；这些属于模块 -1 范围。

## 需求理解

### 用户故事 1 - 普通对话产生可查询自治事件 (优先级: P1)

作为后续 `os_runtime` 引擎，我需要在 `os_runtime.enabled=true` 且 `mode=passive` 时观察 Hermes 普通对话中的用户消息、assistant response、工具调用和工具结果，并能按 session、trace 或最近事件查询。

**优先级原因**: 这是后续张力场模块的最小输入闭环；没有统一事件仓库，后续模块会重复从不同 runtime 表面解析事件。

**独立测试**: 使用 fake `SessionDB` 或临时 profile 状态目录调用 repository 与 projection adapter，append 多类事件后验证 `get()`、`list_recent()`、`list_by_session()`、`list_by_trace()`。

**验收场景**:

1. **给定** `os_runtime.enabled=true` 且 `mode=passive`，**当** 一次普通对话包含用户消息和 assistant 回复，**那么** 系统写入可查询的 `human_request` 与 `assistant_response` 事件。
2. **给定** 一个工具调用产生结果，**当** post-tool 投影执行，**那么** 系统写入 `tool_called` 和 `tool_result` 事件，并保留 tool name、trace id、session id 和摘要。
3. **给定** `os_runtime.enabled=false`，**当** 相同对话、工具和 continuation 流程发生，**那么** 系统不写自治事件、不注册额外工具、不注入 prompt。

---

### 用户故事 2 - NATS 世界事件可靠进入 Hermes (优先级: P1)

作为 Linz World 事件接入层，我需要先保存 raw event ref、subject、event_type、event_id、nats_sequence 和 dispatch state，再把脱敏摘要投递为 Hermes `MessageEvent`，避免重复事件触发重复 agent turn。

**优先级原因**: 世界事件是最重要的外部信号；可靠保存、dedupe 和 ack 边界直接影响外部事件通道稳定性。

**独立测试**: 通过 fake world event 调用 `LinzStateRepository`/gateway adapter/projector，重复投递同一 `event_id` 或同一 sequence，验证只生成一次 dispatch 和一次 `MessageEvent`。

**验收场景**:

1. **给定** 合法 NATS/Linz World raw event，**当** gateway adapter 接收事件，**那么** raw ref 与 dispatch record 在进入 `handle_message()` 前已持久化。
2. **给定** 同一 `event_id` 或 `stream:consumer:nats_sequence` 重复投递，**当** adapter 处理，**那么** 不重复触发 agent turn，dispatch 状态保留为同一记录。
3. **给定** raw event 已持久化但 Hermes agent 处理失败，**当** adapter 结束该次投递，**那么** NATS 不等待完整 LLM 处理，失败仅更新内部 dispatch status。

---

### 用户故事 3 - Runtime 反馈和 continuation 统一投影 (优先级: P2)

作为后续自治 driver，我需要把 goal continuation、world publish receipt、runtime error 和模型/工具反馈统一落为 `os_runtime` event，以便后续模块按 trace 聚合上下文。

**优先级原因**: 自治闭环不仅消费用户/世界输入，也必须消费自身执行反馈和失败状态。

**独立测试**: 构造 continuation、publish receipt 和 runtime error 输入，验证事件 source/type、trace、session、summary 和 metadata 保持稳定。

**验收场景**:

1. **给定** `/goal` 或等价 continuation 产生下一轮 prompt，**当** projection adapter 被调用，**那么** 写入 `os_runtime_continuation` 事件。
2. **给定** Linz World publish receipt，**当** receipt 被记录，**那么** 写入 `world_event_published` 事件并关联 subject、event_type、event_id 和 payload hash 摘要。
3. **给定** runtime 或投影阶段异常，**当** 错误被捕获，**那么** 写入 `runtime_feedback` 事件，且不包含敏感 raw payload。

---

### 用户故事 4 - 超长结果和敏感内容被摘要化 (优先级: P3)

作为 Hermes 用户和审计者，我需要工具结果、world raw payload 和错误详情在自治事件中只保存摘要和引用，避免 SessionDB/JSONL 膨胀或 prompt 泄密。

**独立测试**: 构造超过阈值的工具结果和含敏感字段的 world payload，验证普通事件只含 bounded summary、content_ref/audit_ref 和 redaction metadata。

## 修改范围

- `agent/os_runtime/adapters/__init__.py`
- `agent/os_runtime/adapters/events.py`
- `agent/os_runtime/adapters/session_store.py`
- `agent/linz_world/event_state.py`
- `agent/linz_world/event_bus.py`
- `agent/linz_world/gateway_adapter.py`
- `tests/os_runtime/test_events_adapter.py`
- `tests/os_runtime/test_session_store_adapter.py`
- `tests/linz_world/test_event_state.py`
- `tests/linz_world/test_gateway_adapter.py`

## 建议方案

以 `SessionDB` 为主存储边界新增自治 side tables 或 wrapper：`os_runtime_events` 用于统一事件，`linz_world_events`/`linz_world_dispatch` 用于外部事件可靠性，`linz_world_publish_receipts` 用于发布回执。若 Builder 判断直接修改 `hermes_state.py` schema 风险过高，可保留当前 per-profile JSON state 作为短期 append-only fallback，但必须通过统一 repository API 暴露，并在 plan 中标记为过渡实现。

事件投影采用低侵入 hook/adapter 模式：gateway adapter 在 world event 持久化和 dedupe 后投递 `MessageEvent`；plugin hooks 或显式 adapter 调用观察 `post_llm_call`、`post_tool_call` 和 continuation；所有写入先检查 `os_runtime.enabled`，禁用时直接 no-op。

## 功能需求

- **FR-001**: 系统必须提供 `OSRuntimeEventRepository.append()`、`get()`、`list_recent()`、`list_by_session()`、`list_by_trace()`。
- **FR-002**: 自治事件必须至少包含 `event_id`、`event_type`、`source`、`trace_id`、`session_id`、`timestamp`、`summary`、`metadata`，并兼容 `OSRuntimeEventRef`。
- **FR-003**: repository 必须 profile-aware，优先使用 `SessionDB` 所在 SQLite 和 WAL/fallback 策略；若使用 JSONL fallback，必须保持同一 profile 下路径且不另建会话存储。
- **FR-004**: Linz World raw event 必须在进入 Hermes `handle_message()` 前可靠保存，保存字段至少包含 `os_id/soul_id` 或其可用引用、`event_id`、`nats_sequence`、`subject`、`event_type`、received timestamp、payload summary 和 audit ref。
- **FR-005**: 系统必须根据 `event_id` 与 NATS sequence 去重，重复事件不得重复触发 agent turn。
- **FR-006**: NATS ack 或等价接收确认边界必须在 raw event/dispatch state 已持久化后，不得等待 LLM 完整处理。
- **FR-007**: Agent 处理失败必须更新内部 dispatch status、attempt_count、last_error；达到 retry limit 后标记 failed/manual handling。
- **FR-008**: EventProjectionAdapter 必须覆盖 `world_event`、`human_request`、`conversation_turn`、`assistant_response`、`tool_called`、`tool_result`、`os_runtime_continuation`、`world_event_published`、`runtime_feedback`。
- **FR-009**: `os_runtime.enabled=false` 时不得写自治事件、不得注册额外工具、不得注入 prompt 或改变现有 token prompt。
- **FR-010**: 工具结果和 world raw payload 超长或敏感时，普通自治事件只能保存 bounded summary 与 content/audit reference。
- **FR-011**: 所有投影失败不得中断正常对话或工具执行；失败应写入诊断事件或受限日志，并保持用户原流程可继续。
- **FR-012**: 测试不得依赖真实 NATS、真实 Linz World 服务、真实模型或网络。

## 关键实体

- **OSRuntimeEvent**: 统一自治事件记录，兼容 `OSRuntimeEventRef`，补充 event_type、content_ref、payload_hash、status 和 metadata。
- **OSRuntimeEventRepository**: profile-aware 事件仓库，提供 append/get/list 查询 API，隐藏 SessionDB side table 或 JSONL fallback 细节。
- **EventProjectionAdapter**: 把 gateway、LLM、tool、goal 和 runtime 输入转成 `OSRuntimeEvent` 的适配层。
- **World Event Record**: Linz World/NATS raw event 的可靠保存记录，包含 raw ref、subject、event_type、event_id、sequence、source identity 和摘要。
- **Dispatch Record**: 世界事件从 persisted、queued、processing 到 handled/failed/skipped 的内部状态。
- **Publish Receipt Event**: 世界发布结果的自治投影，关联 subject、event_type、event_id、payload hash、authorization map version 和诊断。

## 关键设计

- 存储 API 先行：Builder 应先实现 repository contract 和测试，再把 gateway/hook 投影接入该 contract。
- SessionDB-first：优先在 `state.db` 使用 side tables，并复用 `apply_wal_with_fallback()`、写锁/重试策略和 profile-aware `get_hermes_home()`；fallback 不得形成第二套会话语义。
- 投影 no-op 可控：所有 `os_runtime` 写入都通过配置检查；禁用时返回明确 skipped/noop 结果，便于测试。
- 去重双键：world event 同时按 `event_id` 和 `stream:consumer:nats_sequence` 去重；缺失 sequence 时仍按 event id 去重。
- 摘要与引用分离：普通事件保存 summary、payload_hash、content_ref/audit_ref；raw payload 仅进入受限审计路径或现有 Linz state。
- 失败隔离：projection、repository 或 dispatch status 更新失败不得让工具调用、普通对话或 NATS 外部通道等待 LLM 完成。

## 风险与取舍

- **SessionDB schema 风险**: 直接扩展 `hermes_state.py` 可能影响已有迁移。缓解：新增 side tables 保持独立命名，测试 schema upgrade；若采用 JSONL fallback，必须标记为过渡并保持 repository API。
- **hook 覆盖不足风险**: 所有 Hermes 表面并非都天然触发同一 hook。缓解：先覆盖 issue 明确要求的 post LLM、post tool、goal continuation 和 gateway 输入，并在测试中用 adapter 直接调用保证 contract。
- **重复触发风险**: NATS redelivery 或 gateway retry 可能重复 agent turn。缓解：raw event persist 和 dedupe 必须发生在 `handle_message()` 前。
- **泄密/膨胀风险**: raw payload 或工具大结果直接入库会污染 prompt 和增大 state。缓解：bounded summary + ref，敏感字段只进受限审计路径。
- **配置漂移风险**: enabled=false 时被 hook 误写事件。缓解：repository/projection 两层都检查配置或注入 disabled policy，新增禁用测试。

## 验收标准

- **SC-001**: 启用 `os_runtime.enabled=true`、`mode=passive` 后，一次普通对话可产生并查询 `human_request` 与 `assistant_response` 自治事件。
- **SC-002**: 工具调用和工具结果能投影为 `tool_called`、`tool_result`，超长结果只保存摘要和引用。
- **SC-003**: NATS/Linz World 事件进入 Hermes 后可关联 `os_id/soul_id/event_id/nats_sequence/subject/event_type`。
- **SC-004**: 重复 NATS `event_id` 或 sequence 不会重复触发 agent turn。
- **SC-005**: raw world event 持久化后即可确认接收；agent 处理失败只更新 dispatch status，不要求外部通道等待 LLM 完整处理。
- **SC-006**: `os_runtime.enabled=false` 时不写事件、不注册额外工具、不注入 prompt，默认 token prompt 保持不变。
- **SC-007**: `OSRuntimeEventRepository` 五个查询 API 均有单元测试覆盖。
- **SC-008**: 聚焦测试通过：`pytest tests/linz_world/test_event_state.py tests/linz_world/test_gateway_adapter.py tests/os_runtime/test_events_adapter.py tests/os_runtime/test_session_store_adapter.py`。

## 测试计划

- 新增/扩展 `tests/os_runtime/test_session_store_adapter.py`，覆盖 append/get/list_recent/list_by_session/list_by_trace、profile isolation、SessionDB side table 或 fallback 行为。
- 新增/扩展 `tests/os_runtime/test_events_adapter.py`，覆盖每类事件投影、禁用 no-op、超长工具结果摘要、runtime error 诊断。
- 扩展 `tests/linz_world/test_event_state.py`，覆盖 raw event 持久化、event id/sequence dedupe、dispatch failure retry/manual handling。
- 扩展 `tests/linz_world/test_gateway_adapter.py`，覆盖平台注册、receive-only、persist-before-message 投影、`MessageEvent` 关联字段。
- 建议回归运行：`pytest tests/os_runtime tests/linz_world/test_event_state.py tests/linz_world/test_gateway_adapter.py`。

## 假设

- 模块 -1 的 Linz World identity/event catalog/gateway 基础和模块 0 的 `OSRuntimeEventRef`、`EventSource`、配置默认值已在 Builder 开始前可用。
- Hermes 当前 `SessionDB` 是 profile 内 state 边界；新增 side tables 可以在不改变现有 sessions/messages 语义的前提下共存。
- 第一版 passive 事件投影不需要修改 `AIAgent` 主循环；若 hook 参数不足，Builder 可在最小范围内补充显式 adapter 调用。

## 后续交接说明

- Builder Agent 应在同一分支按 `tasks.md` 的故事顺序实现，先完成 repository contract，再接 Linz event reliability，最后接 runtime/continuation 投影和摘要策略。
- Reviewer Agent 应重点审查 SessionDB-first 是否可落地、禁用行为是否强约束、NATS ack 与 LLM 处理是否解耦、raw payload 是否只在受限审计路径保存。
- 本 spec 被 Reviewer Agent APPROVED 后，再交给 Builder Agent 实现；Planner Agent 不修改业务代码。
