# Implementation Tasks: 模块 1：外部事件接入与 SessionDB 适配

## Phase 1: 基础仓库契约

- [ ] 1.1 新增 `agent/os_runtime/adapters/__init__.py`
  - 导出 `session_store` 与 `events` 适配器入口。
  - 不导入会产生 runtime 副作用的模块。
  - **Requirement**: FR-001, FR-009

- [ ] 1.2 新增 `agent/os_runtime/adapters/session_store.py`
  - 实现 `OSRuntimeEventRepository.append()`、`get()`、`list_recent()`、`list_by_session()`、`list_by_trace()`。
  - 事件记录兼容 `OSRuntimeEventRef`，补充 `event_type`、`content_ref`、`payload_hash`、`status` 和 metadata。
  - **Requirement**: FR-001, FR-002, FR-003

- [ ] 1.3 新增 `tests/os_runtime/test_session_store_adapter.py`
  - 覆盖 append/get/list 查询、profile isolation、重复 event id 幂等行为。
  - 覆盖 SessionDB side table 或同 profile fallback 的可观测行为。
  - **Requirement**: FR-001, FR-003, SC-007

## Phase 2: Linz World 可靠接入

- [ ] 2.1 完善 `agent/linz_world/event_state.py`
  - 保存 raw event ref、`os_id/soul_id` 可用引用、`event_id`、subject、event_type、sequence、summary、audit ref。
  - 按 `event_id` 与 `stream:consumer:nats_sequence` 去重。
  - **Requirement**: FR-004, FR-005

- [ ] 2.2 完善 dispatch status 更新
  - 确保 processing failure 更新 `attempt_count`、`last_error`、`failed/manual handling`。
  - 保持 raw event 已持久化后外部接收确认不等待 LLM 完整处理。
  - **Requirement**: FR-006, FR-007

- [ ] 2.3 完善 `agent/linz_world/event_bus.py` 与 `gateway_adapter.py`
  - `MessageEvent` 只暴露脱敏摘要和 audit ref。
  - 保持 receive-only adapter 行为。
  - 提供可测试的 persist-before-dispatch 边界。
  - **Requirement**: FR-004, FR-006, FR-010

- [ ] 2.4 扩展 `tests/linz_world/test_event_state.py`
  - 覆盖 raw persist、event id dedupe、sequence dedupe、retry limit/manual handling。
  - **Requirement**: FR-004, FR-005, FR-007

- [ ] 2.5 扩展 `tests/linz_world/test_gateway_adapter.py`
  - 覆盖平台注册、receive-only、world event 到 `MessageEvent` 的关联字段和脱敏摘要。
  - **Requirement**: FR-004, FR-006, FR-010

## Phase 3: 事件投影适配器

- [ ] 3.1 新增 `agent/os_runtime/adapters/events.py`
  - 实现 `EventProjectionAdapter`。
  - 覆盖 `world_event`、`human_request`、`conversation_turn`、`assistant_response`、`tool_called`、`tool_result`、`os_runtime_continuation`、`world_event_published`、`runtime_feedback`。
  - **Requirement**: FR-008

- [ ] 3.2 接入配置 no-op
  - `os_runtime.enabled=false` 时所有投影返回 skipped/noop，不写事件。
  - 不注册额外工具、不注入 prompt。
  - **Requirement**: FR-009

- [ ] 3.3 实现 summary/ref 策略
  - 超长工具结果只写 bounded summary、payload hash 和 content ref。
  - world raw payload 只写 summary/audit ref，不进入普通自治事件。
  - **Requirement**: FR-010

- [ ] 3.4 隔离投影失败
  - projection/repository 异常不得中断普通对话、工具执行或 gateway 处理。
  - 能记录诊断时写 `runtime_feedback` 或受限日志。
  - **Requirement**: FR-011

- [ ] 3.5 新增 `tests/os_runtime/test_events_adapter.py`
  - 覆盖每类 event_type 投影、trace/session 关联、disabled no-op、超长工具结果摘要、runtime error。
  - **Requirement**: FR-008, FR-009, FR-010, FR-011

## Phase 4: 集成检查

- [ ] 4.1 运行聚焦测试
  - `pytest tests/linz_world/test_event_state.py tests/linz_world/test_gateway_adapter.py tests/os_runtime/test_events_adapter.py tests/os_runtime/test_session_store_adapter.py`
  - **Requirement**: SC-008

- [ ] 4.2 检查 diff 范围
  - 只包含模块 1 事件接入、SessionDB 适配和聚焦测试。
  - 不包含 engine/driver/arbiter、自动自驱动或外部发布治理实现。

- [ ] 4.3 交接说明
  - 在实现结果中说明是否使用 SessionDB side tables 或临时 fallback。
  - 若使用 fallback，标明后续迁移到 SessionDB side tables 的剩余工作。

## 依赖关系与执行顺序

- Phase 1 是所有投影和可靠接入的前置。
- Phase 2 可在 Phase 1 repository contract 稳定后开始，优先保证 world event 不重复触发 agent turn。
- Phase 3 依赖 Phase 1；其中 3.2/3.3/3.4 可在 3.1 基础上并行测试。
- Phase 4 必须在所有故事完成后执行。

## 后续交接说明

- Builder Agent 应按 Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 实现，保持每个阶段独立可测。
- Reviewer Agent 应在实现前确认本任务清单未越界到后续张力场 engine 或自动执行模块。
