# 任务: 模块 7：工具执行适配与证据包

**输入**: 来自 `specs/101-module-7-tools-evidence/` 的设计文档  
**前置条件**: `spec.md`, `plan.md`, `data-model.md`, `quickstart.md`

## 阶段 1: Domain contract 与 redaction 基础

**目的**: 明确 receipt/ticket/evidence 字段并保持兼容 round-trip。

- [ ] T001 [P] 在 `tests/os_runtime/test_domain.py` 添加 `PermissionTicket` 扩展字段或 metadata schema 的 JSON round-trip 测试
- [ ] T002 [P] 在 `tests/os_runtime/test_domain.py` 添加 `ExecutionReceipt` tool/final_response/world_publish/command 四类 receipt round-trip 测试
- [ ] T003 [P] 在 `tests/os_runtime/test_tools_adapter.py` 添加 dict、JSON string、普通文本、Authorization header 的 redaction 测试
- [ ] T004 在 `agent/os_runtime/domain.py` 兼容扩展 `PermissionTicket`、`ExecutionReceipt`、`EvidencePackage`
- [ ] T005 复用或抽出 `bounded_summary`、`redact_for_summary`、`stable_hash`，避免重复 redaction 逻辑

**检查点**: domain 和 redaction 基础可独立测试，不接触 hook。

## 阶段 2: 工具 receipt adapter

**目的**: 复用 `post_tool_call` payload 生成可追溯工具 receipt。

- [ ] T006 [P] 在 `tests/os_runtime/test_tools_adapter.py` 覆盖成功工具调用记录 tool name、args/result summary、duration、session/task/tool_call id
- [ ] T007 [P] 在 `tests/os_runtime/test_tools_adapter.py` 覆盖 event id、intent id、arbitration id、permission ticket id 绑定
- [ ] T008 [P] 在 `tests/os_runtime/test_tools_adapter.py` 覆盖工具错误 JSON、命令失败和异常结果仍生成 failed/error receipt
- [ ] T009 [P] 在 `tests/os_runtime/test_tools_adapter.py` 覆盖缺少 permission ticket 时标记 missing_ticket diagnostic，不伪造授权
- [ ] T010 在 `agent/os_runtime/adapters/tools.py` 实现 receipt recorder 纯逻辑和 repository/sink 注入
- [ ] T011 在 `model_tools.py` 现有 `post_tool_call` / os_runtime projection 附近薄接入 tools adapter，保持原工具 result 不变

**检查点**: 工具 receipt 可单测，hook 接入不改变工具返回。

## 阶段 3: final response 与 Linz World receipt

**目的**: final assistant response 和 world publish 进入同一 evidence 链。

- [ ] T012 [P] 在 `tests/os_runtime/test_evidence.py` 或 dedicated fixture 中覆盖 final response receipt 的 model/provider/token/cost/turn_exit_reason 摘要
- [ ] T013 [P] 在 `tests/os_runtime/test_evidence.py` 覆盖 Linz World published receipt 映射 subject、event_type、world_event_id、payload summary、authorization map version、arbitration id
- [ ] T014 [P] 在 `tests/os_runtime/test_evidence.py` 覆盖 Linz World rejected/failed/uncertain 也生成 receipt
- [ ] T015 在 `run_agent.py` 或 os_runtime adapter 中以兼容方式记录 final response receipt，不破坏 `post_llm_call` plugin hook
- [ ] T016 在 `agent/os_runtime/adapters/linz_world.py` 实现 `PublishReceipt` -> `ExecutionReceipt` 映射
- [ ] T017 如需接入 `agent/linz_world/publisher.py`，只追加 adapter 调用，不改变 `publish_event()` 返回对象

**检查点**: final response/world receipt 可被 evidence 聚合，publisher 语义不变。

## 阶段 4: EvidencePackage 聚合

**目的**: 聚合一次自治 continuation 的 intent、arbitration、receipts、commands 和风险。

- [ ] T018 [P] 在 `tests/os_runtime/test_evidence.py` 覆盖完整 evidence package 聚合 intent/arbitration/tool/world/final receipts
- [ ] T019 [P] 在 `tests/os_runtime/test_evidence.py` 覆盖 command/test evidence 的 command、exit status、redacted output summary
- [ ] T020 [P] 在 `tests/os_runtime/test_evidence.py` 覆盖缺 arbitration、缺 ticket、orphan receipt 时 package `complete=false` 并记录 known risks
- [ ] T021 在 `agent/os_runtime/evidence.py` 实现 `build_evidence_package(...)` 和 completeness diagnostics
- [ ] T022 确保 EvidencePackage JSON round-trip 保留中文、trace id、receipt ids 和 unknown metadata

**检查点**: evidence package 可作为后续状态面板/规则结晶输入。

## 阶段 5: 回归与收口

**目的**: 验证低侵入、隐私和前序模块兼容。

- [ ] T023 运行 `pytest tests/os_runtime/test_tools_adapter.py tests/os_runtime/test_evidence.py`
- [ ] T024 运行 `pytest tests/os_runtime/test_domain.py tests/os_runtime/test_events_adapter.py`
- [ ] T025 运行 `pytest tests/os_runtime/test_driver.py tests/run_agent/test_os_runtime_turn_hooks.py`
- [ ] T026 如接入 publisher，运行 `pytest tests/linz_world/test_publisher.py`
- [ ] T027 检查实现没有新增 execution gateway，没有改变工具/LLM/publisher 返回，没有明文 secret 输出

## 依赖关系与执行顺序

- 阶段 1 阻塞后续所有阶段。
- 阶段 2 依赖阶段 1。
- 阶段 3 依赖阶段 1，可与阶段 2 部分并行。
- 阶段 4 依赖阶段 2 和阶段 3 的 receipt contract。
- 阶段 5 依赖所有实现阶段。

## 并行机会

- 标记 `[P]` 的测试任务可并行。
- Tool adapter 与 Linz World adapter 可由不同 Builder 并行实现，但必须共享 `ExecutionReceipt` contract。

## 实施策略

先以测试固定 redaction 和 receipt contract，再接工具 hook；final response/world receipt 只做薄接入；最后实现 EvidencePackage 聚合。实现过程中不要新增执行网关，不要放开新的外部副作用，不要把缺失权限上下文当成已授权。
