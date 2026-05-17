# 实施计划: 模块 7：工具执行适配与证据包

**分支**: `feat/101-module-7-tools-evidence` | **日期**: 2026-05-17 | **规范**: `specs/101-module-7-tools-evidence/spec.md`  
**输入**: 来自 `specs/101-module-7-tools-evidence/spec.md` 的功能规范

## 摘要

模块 7 在现有 Hermes 工具、LLM 和 Linz World publish 通道之后追加可审计 receipt 与 evidence package。实现重点是薄 adapter、redacted bounded summary、trace/id 绑定和失败路径记录；不新增 execution gateway，也不改变现有工具返回、final response 或 publisher return contract。

## 技术背景

**语言/版本**: Python 3.x，沿用仓库当前运行环境  
**主要依赖**: 标准库、现有 `agent/os_runtime`、`agent/linz_world`、`model_tools.py`、`run_agent.py`；不新增必需依赖  
**存储**: profile-scoped os_runtime repository / existing event side table；必要时使用现有 append-only fallback，不能写全局隐式状态  
**测试**: pytest  
**目标平台**: Hermes CLI、gateway、TUI、Linz World publisher  
**项目类型**: Python CLI/runtime/gateway  
**性能目标**: receipt 记录为短路径同步操作；大 payload 只做 bounded summary/hash，不复制完整内容  
**约束条件**: 记录失败不能改变原工具/LLM/publisher结果；敏感数据必须 redaction；缺权限上下文不得伪造授权  
**规模/范围**: 单 repo，新增 3 个 os_runtime 模块，薄扩展 2-3 个 hook 调用点，2-4 组测试

## 章程检查

- **Profile-Scoped State**: PASS。receipt/evidence 存储必须复用 profile-scoped os_runtime repository 或同 profile fallback。
- **Native Surfaces Before Optional Skills**: PASS。证据层是 Hermes 原生 runtime 能力，不依赖 optional skill。
- **Fail-Closed External Side Effects**: PASS。本模块不放开外部副作用；缺 ticket/arbitration 只记录 diagnostic，不视为授权。
- **Privacy and Audit Separation**: PASS。普通 evidence 只保存 redacted summary/hash/ref，不保存 secret 或 unrestricted payload。
- **Testable Incremental Delivery**: PASS。任务按 domain、tool receipt、final/world receipt、evidence 聚合和回归分阶段。

## 项目结构

### 文档(此功能)

```text
specs/101-module-7-tools-evidence/
├── spec.md
├── plan.md
├── data-model.md
├── quickstart.md
└── tasks.md
```

### 源代码(仓库根目录)

```text
agent/os_runtime/
├── domain.py
├── evidence.py
└── adapters/
    ├── events.py
    ├── tools.py
    └── linz_world.py

agent/linz_world/
└── publisher.py

model_tools.py
run_agent.py

tests/
└── os_runtime/
    ├── test_domain.py
    ├── test_tools_adapter.py
    └── test_evidence.py
```

**结构决策**: 采用单一 Python 项目布局。核心转换逻辑在 `agent/os_runtime` 可单测模块中，hook 文件只调用 adapter，不承载证据业务逻辑。

## 阶段 0 研究结论

- `model_tools.py::handle_function_call()` 已在工具执行后触发 `post_tool_call`，并提供 tool name、args、result、session/task/tool_call id、duration_ms；模块 7 应复用该边界。
- `run_agent.py` 已在每轮结束后触发 `post_llm_call`，并在 result dict 中计算 turn_exit_reason、model/provider、token/cost；Builder 需要以兼容方式把 final response receipt 需要的摘要传入 os_runtime adapter。
- `agent/os_runtime/adapters/events.py` 已有 `bounded_summary`、`redact_for_summary` 和 `stable_hash`，模块 7 应复用这些 helper 或抽出共享 helper，避免两套 redaction。
- `agent/linz_world/publisher.py` 已生成 `PublishReceipt` 并持久化 Linz receipt；模块 7 的 world adapter 应把它投影为 os_runtime receipt/evidence，而不是替代 publisher。
- `domain.py` 已有 `PermissionTicket` / `ExecutionReceipt` / `EvidencePackage` 初版对象。优先兼容扩展字段或明确 metadata schema，避免破坏旧 round-trip。

## 阶段 1 设计

### Domain Contract

`PermissionTicket` 保持 JSON-friendly dataclass，补齐或通过 metadata 约定：

- `ticket_id`, `intent_id`, `arbitration_id`, `decision`
- `issued_at`, `expires_at`
- `allowed_tools`, `constraints`
- `issuer`, `approval_ref`, `policy_version`, `metadata`

`ExecutionReceipt` 补齐或通过 metadata 约定：

- `receipt_id`, `receipt_type` (`tool`, `final_response`, `world_publish`, `command`)
- `status` (`succeeded`, `failed`, `error`, `rejected`, `uncertain`, `skipped`)
- `event_id`, `intent_id`, `arbitration_id`, `ticket_id`
- `session_id`, `task_id`, `tool_call_id`
- `started_at`, `completed_at`, `duration_ms`
- `input_summary`, `output_summary`, `error`, `payload_hash`, `content_ref`, `metadata`

### Tool Adapter

`agent/os_runtime/adapters/tools.py` 提供纯函数/轻量 service：

- 接收 `post_tool_call` 参数和可选 runtime context。
- 使用 redaction helper 生成 bounded args/result summary 和 stable hash。
- 根据 result/error 形态判断 status。
- 生成 deterministic 或 trace-friendly receipt id。
- 写入 repository/evidence sink 时 fail-open，返回 recorder status 供测试断言。

### Final Response Adapter

final response receipt 可由 `run_agent.py` 的 os_runtime adapter 记录：

- response summary 使用 bounded redaction。
- metadata 保存 model、provider/platform、turn_exit_reason、token/cost摘要。
- 不保存完整 conversation history。
- 兼容既有 plugin hook；新增字段必须可选或仅传给 os_runtime 专用函数。

### Linz World Adapter

`agent/os_runtime/adapters/linz_world.py` 映射 `PublishReceipt`：

- `published` status 记录 `world_event_id`、subject、event_type、payload_summary、authorization map version、arbitration id。
- `rejected/failed/uncertain` status 也记录 governance code/message。
- 不改变 `publish_event()` 的返回对象和异常处理语义。

### Evidence Aggregator

`agent/os_runtime/evidence.py` 提供 `build_evidence_package(...)`：

- 输入 event refs、intent、arbitration、receipts、commands、known risks。
- 输出 `EvidencePackage`，包含 completeness diagnostics。
- 对 commands/tests 记录 command、exit status、redacted output summary。
- 缺少 arbitration/ticket/intent 时标记 incomplete，不阻塞 package 生成。

## 复杂度跟踪

| 违规 | 为什么需要 | 拒绝更简单替代方案的原因 |
| --- | --- | --- |
| 无 | 无 | 无 |

## 风险

- hook 参数兼容：`post_llm_call` 已有第三方 plugin 使用，新增 metadata 只能兼容扩展。
- 证据重复：events adapter 已记录 tool_called/tool_result，receipt 应作为审计层对象并包含 receipt_type，避免与 event projection 混淆。
- 缺失 runtime context：Builder 需要从模块 6 state/metadata 查找 event/intent/arbitration/ticket，找不到时必须标记 diagnostic。
- redaction 漏洞：工具 args/result 可能是 dict、JSON string、普通文本、多模态 envelope 或异常字符串，测试必须覆盖多形态。

## 验收标准

- 每个自治 continuation 能生成 `EvidencePackage`；缺少 receipt/context 时标记 incomplete。
- 工具 receipt 可回溯 event id、intent id、arbitration id、permission ticket id 或明确 missing_context。
- world publish receipt 可回溯 Linz World `world_event_id`。
- 工具失败、命令失败、publish rejected/failed 和 final response 都进入 evidence。
- 敏感参数不以明文出现在 receipt/evidence。
- 现有工具、LLM、publisher 返回行为不变。

## 测试计划

- Unit: `pytest tests/os_runtime/test_tools_adapter.py`
- Unit: `pytest tests/os_runtime/test_evidence.py`
- Domain regression: `pytest tests/os_runtime/test_domain.py`
- Publisher regression if touched: `pytest tests/linz_world/test_publisher.py`
- Runtime regression: `pytest tests/os_runtime/test_events_adapter.py tests/os_runtime/test_driver.py tests/run_agent/test_os_runtime_turn_hooks.py`
