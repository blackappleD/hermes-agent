# 功能规范: 模块 7：工具执行适配与证据包

**功能分支**: `101-module-7-tools-evidence`  
**Issue 分支**: `feat/101-module-7-tools-evidence`  
**创建时间**: 2026-05-17  
**状态**: 草稿  
**输入**: Issue OPE-101「[Feature]模块 7：工具执行适配与证据包」、`docs/基于张力场的Agent自驱动实现计划.md`、现有 `model_tools.py` / `run_agent.py` hook 与前序 os_runtime specs

## 背景

Hermes 已有 `model_tools.py::handle_function_call()` 的 `post_tool_call` hook、`run_agent.py` 的 `post_llm_call` hook、`agent/os_runtime/adapters/events.py` 的事件投影、`agent/os_runtime/domain.py` 中的 `PermissionTicket` / `ExecutionReceipt` / `EvidencePackage` 初版对象，以及 Linz World `publisher.py` 的 `PublishReceipt`。模块 7 的目标是把模块 5 arbitration / permission 结果和模块 6 runtime continuation 串到现有工具、LLM、Linz World 发布记录上，让被允许的自治行动都有可审计 receipt 和 evidence package。

当前问题不是缺少工具执行能力，而是缺少把“为什么允许执行、执行了什么、结果如何、失败如何、可追溯到哪个 event/intent”的证据链记录下来。实现必须复用现有执行通道和 hook，不新增第二套 execution gateway。

## 目标

- 新增 `agent/os_runtime/adapters/tools.py`，把 `post_tool_call` hook payload 转成 redacted `ExecutionReceipt`，并关联 event id、intent id、arbitration id、permission ticket id。
- 完善 `agent/os_runtime/domain.py` 中 `PermissionTicket` 与 `ExecutionReceipt` 的字段或 metadata 约定，保持 JSON round-trip 兼容。
- 新增 `agent/os_runtime/adapters/linz_world.py`，把 Linz World publish receipt 转成 world receipt / os_runtime evidence 输入。
- 新增 `agent/os_runtime/evidence.py`，聚合 intent、arbitration、tool receipts、world receipts、final response、tests/commands evidence 和 known risks。
- 通过 `post_llm_call` 或薄适配入口记录 final response receipt，包含可用的 model/provider/token/cost/turn_exit_reason 摘要。
- 首版只记录 evidence，不改变现有工具返回、LLM 返回或 Linz World publisher 的执行语义。

## 非目标

- 不实现新的工具执行网关、工具路由器、sandbox 或权限审批 UI。
- 不绕过或替代 `model_tools.py`、plugin hook、tool registry、`run_agent.py` 主循环或 Linz World `publisher.py`。
- 不在本模块放开高风险自治工具执行或 world publish；执行许可仍来自模块 5 arbitration / permission 和现有 policy。
- 不把敏感参数、API key、token、private key、authorization header 或 restricted payload 明文写入 evidence。
- 不重写 os_runtime event repository 存储后端；首版优先复用现有 repository / profile-scoped 状态。

## 需求理解

模块 7 是自治行动的证据层。工具或世界发布已经由现有通道执行后，本模块在 hook 边界记录“允许执行的依据”和“执行结果摘要”。`PermissionTicket` 表示某个 intent 在裁判和 policy 后获得的受限许可；`ExecutionReceipt` 表示实际工具、LLM final response、命令或 world publish 的执行记录；`EvidencePackage` 按 trace/session/event/intent 聚合这些记录，供后续状态面板、审计、规则结晶和复盘使用。

实现时应保持可观测但低侵入：hook 记录失败不能影响工具原返回；工具失败、命令失败、publish rejected/failed 也必须有 receipt；缺少 runtime context 时记录可诊断的 orphan receipt 或 skipped reason，而不是发明权限事实。

## 用户场景与测试

### 用户故事 1 - 工具调用 receipt 记录 (优先级: P1)

作为 Builder Agent，我需要在现有工具执行完成后记录 redacted receipt，使自治 continuation 中的每次工具调用都能回溯到 event、intent、arbitration 和 permission ticket。

**优先级原因**: 工具调用是最直接的副作用入口；没有 receipt 就无法审计自治行动是否遵守裁判和权限边界。  
**独立测试**: 仅实现 `agent/os_runtime/adapters/tools.py` 和 `tests/os_runtime/test_tools_adapter.py`，用 fake post_tool_call payload 覆盖成功、失败、敏感参数和缺少 ticket 的场景。

**验收场景**:

1. **给定** 一个带 session/task/tool_call id、event id、intent id、arbitration id、permission ticket id 的 `post_tool_call` payload，**当** 工具 adapter 记录 receipt，**那么** receipt 包含 tool name、args 摘要、result 摘要、duration 和所有 trace id。
2. **给定** args/result 中包含 token、api_key、password、authorization 或 restricted payload，**当** 生成摘要，**那么** receipt 中只保留 redacted summary 和 hash/ref，不出现明文秘密。
3. **给定** 工具返回错误 JSON 或异常摘要，**当** 记录 receipt，**那么** receipt status 是 failed/error，仍进入 evidence，而不是只记录成功路径。
4. **给定** runtime context 缺少 permission ticket，**当** 记录 receipt，**那么** receipt 明确标记 missing_ticket/diagnostic，不伪造授权。

### 用户故事 2 - final response 与世界发布 receipt 记录 (优先级: P1)

作为 Builder Agent，我需要 final assistant response 和 Linz World publish 也进入 receipt/evidence，使自治 continuation 的输出和正式世界事件都有同一条审计链。

**优先级原因**: 模块 6 continuation 的结果不一定调用工具，但 final response 仍是自治行动输出；world publish 则必须能回溯到 Linz World event id。  
**独立测试**: 用 fake `post_llm_call` payload 和 fake `PublishReceipt` 验证 final response receipt、published/rejected/failed world receipt、authorization map version 和 arbitration id。

**验收场景**:

1. **给定** `run_agent.py` 可提供 final response、model/provider、token/cost 和 turn_exit_reason 摘要，**当** post LLM adapter 记录 receipt，**那么** evidence package 包含 final_response receipt 且不保存完整敏感上下文。
2. **给定** Linz World publisher 返回 `published` receipt，**当** world adapter 记录 receipt，**那么** receipt 包含 subject、event_type、world_event_id、payload 摘要、authorization map version 和 arbitration id。
3. **给定** publisher 返回 rejected/failed/uncertain，**当** world adapter 记录 receipt，**那么**失败状态也会进入 evidence，并保留 governance code 或错误摘要。

### 用户故事 3 - EvidencePackage 聚合与复盘 (优先级: P1)

作为 Reviewer 或后续状态面板，我需要按一次自治 continuation 聚合 intent、arbitration、tool/world/final receipts、测试命令证据和 known risks，以便复盘为什么继续、做了什么、哪些风险仍存在。

**优先级原因**: 单个 receipt 只能说明一次动作，EvidencePackage 才能表达完整自治回合。  
**独立测试**: 仅实现 `agent/os_runtime/evidence.py` 和 `tests/os_runtime/test_evidence.py`，用 fake intent/arbitration/receipts/commands 聚合并验证 redaction、缺失项诊断和 JSON round-trip。

**验收场景**:

1. **给定** 一个自治 continuation 的 event id、intent、arbitration、tool receipts、world receipts 和 final response，**当** 构建 evidence package，**那么** package 可回溯到 trace id、event id、intent id 和 receipt ids。
2. **给定** 测试/命令执行失败证据，**当** 聚合 evidence，**那么** package 包含 command、exit status、redacted output summary 和 known risk。
3. **给定** 缺少 arbitration 或 permission ticket，**当** 聚合 evidence，**那么** package 标记 known risk，不把证据链标为 complete。

### 边界情况

- `os_runtime.enabled=false` 时不写 receipt/evidence，现有工具/LLM/publisher 行为不变。
- hook 记录失败必须 fail-open 到原工具/LLM返回，但记录错误应可通过 debug log 或 runtime feedback 诊断。
- 大结果、二进制结果、多模态结果和长 payload 只存 bounded summary、hash、content_ref，不内嵌完整内容。
- 敏感字段出现在嵌套 dict、JSON 字符串、普通文本或 authorization header 中时都必须 redaction。
- 缺少 event id/intent id 时可生成 receipt，但必须标记 orphan/missing_context，不满足 autonomous evidence complete。
- 同一个 tool_call_id 重试或重复 hook 时应避免把同一次调用误聚合为多个成功事实；首版至少应通过 deterministic receipt id 或 duplicate metadata 支持去重。

## 需求

### 功能需求

- **FR-001**: 系统必须新增 `agent/os_runtime/adapters/tools.py`，提供从 `post_tool_call` payload 生成 `ExecutionReceipt` 的入口。
- **FR-002**: 工具 receipt 必须记录 tool name、redacted args summary、redacted result summary、duration_ms、session_id、task_id、tool_call_id、event_id、intent_id、arbitration_id、permission_ticket_id。
- **FR-003**: 工具执行成功、工具返回错误、命令失败或 adapter 看到错误结果时都必须生成 receipt，status 不得只覆盖成功路径。
- **FR-004**: 系统必须完善或约定 `PermissionTicket` 字段，至少能表达 ticket id、intent id、arbitration id/decision、allowed tools、constraints、issued/expires、metadata。
- **FR-005**: 系统必须完善或约定 `ExecutionReceipt` 字段，至少能表达 receipt id、receipt type、status、event id、intent id、arbitration id、permission ticket id、started/completed/duration、input/output summary、error、metadata。
- **FR-006**: 系统必须通过 `post_llm_call` 或等价薄适配入口记录 final response receipt，包含 final response 摘要、model/provider、token/cost/turn_exit_reason 可用摘要。
- **FR-007**: 系统必须新增 `agent/os_runtime/adapters/linz_world.py`，把 Linz World `PublishReceipt` 映射为 world receipt，并保留 subject、event_type、world_event_id、payload summary、authorization map version、arbitration id 和 status。
- **FR-008**: `EvidencePackage` 必须聚合 intent、arbitration、tool receipts、world receipts、final response receipt、tests/commands evidence、known risks 和 completeness/diagnostics。
- **FR-009**: 所有 receipt/evidence summary 必须使用现有 redaction 或同等规则，禁止明文写入 API key、token、password、private key、authorization header 或 restricted payload。
- **FR-010**: 首版实现不得改变现有工具返回、LLM final response、plugin hook 返回或 Linz World publish 返回。
- **FR-011**: 新增测试必须覆盖 `tests/os_runtime/test_tools_adapter.py` 和 `tests/os_runtime/test_evidence.py`；如 domain 字段变化，必须补充 `tests/os_runtime/test_domain.py` round-trip。

### 关键实体

- **PermissionTicket**: 模块 5/Policy 输出的受限执行许可，约束某个 intent 可使用哪些工具、有效期、审批和裁判来源。
- **ExecutionReceipt**: 单次工具、LLM final response、命令或 world publish 的执行结果摘要，必须可追溯到 event/intent/arbitration/ticket。
- **ToolReceiptAdapter**: `post_tool_call` 的薄适配器，负责 redaction、摘要、状态判断和 receipt 写入。
- **WorldReceiptAdapter**: Linz World `PublishReceipt` 的薄适配器，负责 world_event_id、authorization map version 和 arbitration id 绑定。
- **EvidencePackage**: 一次自治 continuation 或 trace 的聚合证据包，包含 receipts、intent/arbitration、测试命令证据和 known risks。

## 建议方案

沿用现有 hook 与事件投影：`model_tools.py` 继续负责执行工具并触发 `post_tool_call`；模块 7 在 `agent/os_runtime/adapters/tools.py` 中提供可被 hook 调用的 receipt recorder。`run_agent.py` 的 `post_llm_call` 继续作为 final response 边界，必要时以兼容方式增加 result metadata。Linz World publisher 继续返回 `PublishReceipt`，模块 7 只在 publisher 成功/失败后追加 world receipt/evidence 投影。

Evidence 聚合放在 `agent/os_runtime/evidence.py`，作为纯函数/轻量服务：输入 intent/arbitration/receipts/command evidence，输出 JSON-friendly `EvidencePackage`。存储优先复用已有 profile-scoped `OSRuntimeEventRepository` 或现有 event side table；如果 Builder 选择 append-only fallback，必须仍使用 profile-scoped 路径并保留迁移边界。

## 修改范围

- 新增：`agent/os_runtime/adapters/tools.py`
- 新增：`agent/os_runtime/adapters/linz_world.py`
- 新增：`agent/os_runtime/evidence.py`
- 扩展：`agent/os_runtime/domain.py` 中 `PermissionTicket` / `ExecutionReceipt` / `EvidencePackage` 的字段或 metadata 约定
- 可能扩展：`agent/os_runtime/adapters/events.py`，复用 redaction/hash/summary helpers 或追加 receipt projection
- 可能扩展：`model_tools.py` hook 调用点，仅用于调用 tools adapter，不改变工具返回
- 可能扩展：`run_agent.py` `post_llm_call` metadata，仅用于 final response receipt，不破坏现有 plugin hook 参数
- 可能扩展：`agent/linz_world/publisher.py`，发布后调用 world adapter，不改变 publisher 返回类型
- 新增测试：`tests/os_runtime/test_tools_adapter.py`
- 新增测试：`tests/os_runtime/test_evidence.py`
- 可能更新测试：`tests/os_runtime/test_domain.py`、`tests/linz_world/test_publisher.py`

## 关键设计

- **不新增 execution gateway**: 所有工具执行仍走 `model_tools.py` / registry；本模块只在 hook 边界记录 receipt。
- **Fail-open 记录，fail-closed 授权事实**: 记录失败不能影响原执行返回；但缺少 ticket/arbitration 时 evidence 必须标记不完整，不能伪造授权。
- **Redaction first**: receipt 的 args/result/payload/final response 只保存 redacted bounded summary、hash 和 ref；完整 restricted payload 不进入普通 evidence。
- **可追溯 id**: tool receipt 至少绑定 session/task/tool_call；自治路径还必须绑定 event/intent/arbitration/ticket，缺失时诊断。
- **状态覆盖失败路径**: success/error/failed/rejected/uncertain 都是 receipt 状态，不因失败跳过 evidence。
- **低侵入集成**: adapters 应可单测；hook 调用只做薄包装，避免把业务逻辑塞入 `model_tools.py` 或 `run_agent.py`。

## 风险与取舍

- **上下文 id 来源不完整**: 现有 hook 已有 session/task/tool_call id，但 event/intent/arbitration/ticket 可能需要从模块 6 driver state 或 runtime metadata 读取。取舍是先显式标记 missing_context，而不是猜测。
- **domain 兼容风险**: `PermissionTicket` / `ExecutionReceipt` 已存在初版对象。Builder 应做向后兼容字段扩展或 metadata 约定，避免破坏现有 round-trip 测试。
- **hook 参数兼容风险**: `post_llm_call` 已被 plugin 使用。新增 token/cost/turn_exit_reason 信息应采用可选 keyword 或 os_runtime 专用 adapter 数据，不破坏插件。
- **重复记录风险**: 既有 `adapters/events.py` 已投影 tool_called/tool_result。模块 7 应明确 receipt 是更高层审计对象，避免把同一 event 当作多个执行事实。
- **敏感信息风险**: 工具 args/result 和 payload 形态复杂。测试必须覆盖嵌套 dict、JSON 字符串和普通文本 redaction。

## 验收标准

- **AC-001**: 每个自治触发的 continuation 至少能生成一个 `EvidencePackage`；缺少 receipt 时 package 标记 incomplete 和 known risk。
- **AC-002**: 每个自治工具 receipt 可回溯到 event id、intent id、arbitration id 和 permission ticket id；缺失时有明确 diagnostic。
- **AC-003**: 每个 successful world publish receipt 可回溯到 Linz World `world_event_id`，并记录 subject、event_type、authorization map version 和 arbitration id。
- **AC-004**: 敏感参数不会以明文出现在 receipt/evidence summary、metadata 普通字段或测试断言输出中。
- **AC-005**: 工具失败、命令失败、publisher rejected/failed 和 final response 仍进入 evidence。
- **AC-006**: 现有工具返回、LLM final response 和 publisher return contract 不因记录 evidence 发生变化。

## 测试计划

- `pytest tests/os_runtime/test_tools_adapter.py`
- `pytest tests/os_runtime/test_evidence.py`
- 如扩展 domain：`pytest tests/os_runtime/test_domain.py`
- 如接入 publisher：`pytest tests/linz_world/test_publisher.py`
- 回归：`pytest tests/os_runtime/test_events_adapter.py tests/os_runtime/test_driver.py tests/run_agent/test_os_runtime_turn_hooks.py`

## 成功标准

### 可衡量的结果

- **SC-001**: 工具 receipt 测试覆盖 success/error、redaction、duration、trace ids 和 missing ticket diagnostics。
- **SC-002**: EvidencePackage 聚合测试证明 intent/arbitration/tool/world/final/commands/risks 都可 JSON round-trip。
- **SC-003**: redaction 测试中 `api_key`、`token`、`password`、`Authorization: Bearer` 原值均不会出现在输出。
- **SC-004**: adapter 测试证明记录逻辑不修改原工具 result。

## 假设

- 模块 5 的 arbitration / permission 输出能通过 runtime state、metadata 或 adapter 参数传入模块 7；若缺失，首版记录 missing context。
- 模块 6 的 continuation 已能提供 session/trace/event/intent 关联入口。
- Builder Agent 负责业务代码实现；Planner Agent 本轮只维护 spec-kit artifacts。
- 首版 evidence 存储可复用现有 os_runtime repository；不要求本 issue 迁移到最终 side table schema。

## 后续交接说明

Builder Agent 应按 `tasks.md` 的测试优先顺序实现。先扩展/约定 domain receipt 字段并保证 round-trip，再实现 tool receipt adapter 和 redaction，随后接 final response/world publish adapter，最后实现 EvidencePackage 聚合。实现期间不要新增执行网关，不要改变工具/LLM/publisher 返回，不要把缺失权限上下文当作已授权事实。Spec Reviewer Agent 重点审查 redaction、缺失 ticket 诊断、失败路径 evidence 和 hook 兼容性。
