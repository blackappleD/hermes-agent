# 数据模型: 模块 7：工具执行适配与证据包

## PermissionTicket

执行许可票据，来源于模块 5 arbitration / policy。

- `ticket_id`: 稳定票据 id。
- `intent_id`: 被授权的 intent id。
- `arbitration_id`: 生成许可的 arbitration 记录 id，若 domain 仍无显式字段可放入 metadata。
- `decision`: 许可对应的裁判结果。
- `issued_at` / `expires_at`: 有效期。
- `allowed_tools`: 允许使用的工具列表。
- `constraints`: 执行约束摘要。
- `metadata`: `issuer`, `policy_version`, `approval_ref`, `diagnostics` 等兼容字段。

## ExecutionReceipt

单次执行结果记录。首版可通过显式字段或 metadata 保持向后兼容。

- `receipt_id`: receipt id，应支持由 trace/tool_call 生成稳定 id。
- `receipt_type`: `tool | final_response | world_publish | command`。
- `status`: `succeeded | failed | error | rejected | uncertain | skipped`。
- `event_id`: 触发执行的 os_runtime event id。
- `intent_id`: 对应 open intent id。
- `arbitration_id`: 对应 arbitration id。
- `ticket_id`: permission ticket id。
- `session_id`, `task_id`, `tool_call_id`: Hermes 执行面 id。
- `started_at`, `completed_at`, `duration_ms`: 时间与耗时。
- `input_summary`, `output_summary`: redacted bounded summary。
- `payload_hash`, `content_ref`: 大内容或 restricted 内容的引用。
- `error`: redacted 错误摘要。
- `metadata`: `tool_name`, `model`, `provider`, `turn_exit_reason`, `world_event_id`, `subject`, `event_type`, `authorization_map_version`, `diagnostics`。

## EvidencePackage

一次自治 continuation 或 trace 的聚合证据包。

- `evidence_id`: package id。
- `trace_id`: runtime trace/session 关联 id。
- `event_ids`: 相关 event ids。
- `intent`: intent 摘要或 id/ref。
- `arbitration`: arbitration 摘要或 id/ref。
- `receipt_ids`: 相关 receipt ids。
- `tool_receipts`: 工具 receipt 摘要列表。
- `world_receipts`: Linz World receipt 摘要列表。
- `final_response`: final response receipt 摘要。
- `commands`: 测试/命令执行 evidence，含 command、exit status、redacted output summary。
- `known_risks`: 缺失 context、缺少 ticket、失败命令、publish failed 等风险。
- `complete`: 布尔或 metadata 标记，表达证据链是否完整。
- `metadata`: 兼容扩展。

## Redaction Rules

- 字段名匹配 `token`, `api_key`, `password`, `secret`, `private_key`, `authorization` 时值必须替换为 `[REDACTED]`。
- 文本中的 `Authorization: Bearer <value>` 必须替换 token 值。
- 大 payload 不进入普通 evidence，只保留 bounded summary、hash 和 ref。
- restricted payload 原文不得写入 receipt metadata。
