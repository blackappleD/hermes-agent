# Linz World 泡泡协议接入实施报告

日期：2026-05-19  
状态：已完成第一阶段接入与受控写操作工具骨架  
关联方案：`docs/linz-world-bubble-protocol-integration-plan.md`

## 1. 实施范围

本次实施完成了 Hermes 侧对 linz-world BPS 泡泡协议的客户端、模型、工具和审计接入，保持 linz-world 服务端作为泡泡状态权威源。

已完成：

- 新增 Bubble Protocol HTTP 客户端，封装 `/api/v1/bubbles`
- 新增 BPS DTO，兼容 linz-world Go 服务返回的导出字段名
- 新增 Bubble 操作收据
- 新增默认只读的 `linz_world.bubble` 配置
- 新增 10 个语义化泡泡工具
- 将泡泡工具接入 `linz_world` 和独立 `linz_bubble` 工具集
- 将 Bubble 操作收据投影到 `os_runtime` 的执行收据体系
- 在 `linz_status` 中暴露 Bubble Protocol 配置状态
- 增加针对客户端、配置、工具和运行时收据投影的测试

未在本次实施中做：

- 未修改 linz-world 后端代码
- 未新增 linz-world `bubble.*` NATS 事件
- 未把 Bubble 动作直接并入 `os_runtime` 的 intent/arbiter/action_executor 主链路
- 未执行真实远端 Bubble API 写入
- 未改变 `run_agent.py` 主循环

## 2. 主要代码变更

### 2.1 Linz World Bubble 客户端和模型

新增文件：

- `agent/linz_world/bubble_client.py`
- `agent/linz_world/bubble_models.py`
- `agent/linz_world/bubble_receipts.py`

能力：

- `get_snapshot`
- `create_demand`
- `accept_demand`
- `create_task`
- `request_mount`
- `review_mount`
- `submit_task_artifact`
- `review_task_acceptance`
- `submit_demand_delivery`
- `review_demand_acceptance`

客户端统一使用现有 Linz World service URL 和 HTTP envelope 处理方式。响应模型会把 `BubbleID`、`LifecycleState`、`MountID` 等 Go 导出字段归一化为 Python 侧的 `bubble_id`、`lifecycle_state`、`mount_id`。

### 2.2 配置

修改文件：

- `agent/linz_world/config.py`
- `hermes_cli/config.py`

新增配置块：

```yaml
linz_world:
  bubble:
    enabled: true
    read_only: true
    allow_mutations: false
    require_approval_for_mutations: true
    allow_autonomous_create_demand: false
    allow_autonomous_accept_demand: false
    allow_autonomous_create_task: false
    allow_autonomous_mount: false
    allow_autonomous_submit_artifact: false
    allow_autonomous_review: false
    default_task_slot_id: slot.task.coder
    artifact_ref_scheme: hermes-session
    snapshot_context_max_events: 20
    snapshot_context_max_residues: 20
```

默认行为：

- 快照读取能力默认开启
- 写操作默认关闭
- 即使开启写操作，也默认要求显式确认
- 自主写入相关开关默认全部关闭

### 2.3 工具接入

新增文件：

- `tools/linz_world_bubble_tools.py`

新增工具：

- `linz_bubble_snapshot`
- `linz_bubble_create_demand`
- `linz_bubble_accept_demand`
- `linz_bubble_create_task`
- `linz_bubble_request_mount`
- `linz_bubble_review_mount`
- `linz_bubble_submit_artifact`
- `linz_bubble_review_task_acceptance`
- `linz_bubble_submit_demand_delivery`
- `linz_bubble_review_demand_acceptance`

工具集变更：

- `toolsets.py` 的 `linz_world` 工具集加入泡泡工具
- 新增独立 `linz_bubble` 工具集，便于单独启停泡泡能力
- `_HERMES_CORE_TOOLS` 同步加入泡泡工具，保持默认工具链可发现

写操作保护：

- `linz_world.bubble.read_only=true` 时拒绝所有写操作
- `linz_world.bubble.allow_mutations=false` 时拒绝所有写操作
- `require_approval_for_mutations=true` 时，工具必须收到 `confirm_mutation=true`
- 拒绝和失败都会生成 `BubbleReceipt`

### 2.4 元神运行时审计投影

新增文件：

- `agent/os_runtime/adapters/bubble.py`

修改文件：

- `agent/os_runtime/adapters/__init__.py`

能力：

- `build_bubble_receipt`
- `record_bubble_receipt`
- `project_bubble_receipt`

泡泡工具生成的 `BubbleReceipt` 会尝试投影成 `ExecutionReceipt`，receipt type 为 `linz_bubble`。如果当前运行时适配器不可用，投影会跳过，不影响工具调用结果。

### 2.5 状态摘要

修改文件：

- `agent/linz_world/status.py`

`linz_status` 现在会返回：

- `bubble_protocol.enabled`
- `bubble_protocol.read_only`
- `bubble_protocol.allow_mutations`
- `bubble_protocol.require_approval_for_mutations`
- `bubble_protocol.default_task_slot_id`

## 3. 测试结果

新增或修改测试：

- `tests/linz_world/test_bubble_client.py`
- `tests/linz_world/test_config.py`
- `tests/linz_world/test_tools.py`
- `tests/os_runtime/test_bubble_adapter.py`

已运行：

```bash
pytest tests/linz_world/test_bubble_client.py tests/linz_world/test_config.py tests/linz_world/test_tools.py tests/os_runtime/test_bubble_adapter.py
```

结果：

```text
14 passed
```

已运行：

```bash
pytest tests/linz_world tests/os_runtime/test_bubble_adapter.py
```

结果：

```text
82 passed
```

已运行：

```bash
pytest tests/tools/test_registry.py
```

结果：

```text
31 passed
```

已运行：

```bash
python -m compileall agent\linz_world\bubble_client.py agent\linz_world\bubble_models.py agent\linz_world\bubble_receipts.py agent\os_runtime\adapters\bubble.py tools\linz_world_bubble_tools.py
```

结果：通过，无编译错误。

说明：测试输出中存在 Python 3.14 下 `pytest_asyncio` 的弃用警告，属于现有依赖警告，本次改动未引入失败。

## 4. 当前行为说明

### 4.1 读取快照

`linz_bubble_snapshot` 会：

1. 检查 Linz World 和 Bubble Protocol 配置是否启用
2. 确保当前 profile 有 Linz World identity
3. 确保有登录 session
4. 调用 `/api/v1/bubbles/:bubble_id/snapshot`
5. 返回摘要化 snapshot

快照摘要不会返回完整 raw spec/payload，避免把过大的远端结构或敏感 payload 直接塞进模型上下文。

### 4.2 写操作

所有写操作当前默认拒绝。要调用写操作，配置至少需要：

```yaml
linz_world:
  bubble:
    read_only: false
    allow_mutations: true
```

如果保持：

```yaml
require_approval_for_mutations: true
```

则工具参数还必须包含：

```json
{"confirm_mutation": true}
```

该确认字段只表示当前对话中用户已经明确批准该次远端泡泡状态变更；它不是全局免审开关。

## 5. 风险和后续事项

### 5.1 linz-world AgentBubble 挂载校验仍需确认

方案中提到的风险仍存在：linz-world 注册 Original Spirit 时创建的 `AgentBubble` 使用 `os_id` 作为 `BubbleID`，但当前挂载校验可能要求 agent 类型 ID 以 `agent_` 或 `bub_agent_` 开头。

如果实际 `os_id` 不符合前缀，Hermes 调用 `linz_bubble_request_mount` 挂载自身 AgentBubble 时会被后端拒绝。

建议优先在 linz-world 后端放宽校验：如果 mounted bubble 已存在且类型匹配，则允许挂载。

### 5.2 写操作幂等性仍由后续协议增强解决

直接 Bubble API 的创建类操作目前没有显式 idempotency key。本次工具层不会自动重试写操作，避免网络不确定状态下重复创建。

后续建议 linz-world 增加：

- `idempotency_key`
- 或业务外部 ID
- 或按 actor/action/request_ref 去重

### 5.3 os_runtime 主链路尚未自动生成 Bubble 动作

本次只完成 Bubble receipt 到 `os_runtime` 的审计投影，没有把 Bubble 动作自动接入：

- `intent_generator`
- `action_potential`
- `arbiter`
- `action_executor`

这样做是为了先让语义化工具和受控写入边界稳定。下一阶段再让元神运行时在明确协作信号或 MRK 上下文下生成 Bubble 动作候选。

### 5.4 缺少远端列表 API

当前 Hermes 仍只能按已知 `bubble_id` 读取 snapshot。要实现“列出我相关的活跃泡泡”，仍需要 linz-world 提供只读列表/搜索 API，或由 MRK/WSP 事件和本地 receipt 累积引用。

## 6. 建议下一步

建议下一阶段按以下顺序推进：

1. 与 linz-world 确认 AgentBubble ID 挂载校验策略
2. 在真实 linz-world 环境手动验证 `linz_bubble_snapshot`
3. 开启临时测试配置验证 `create_task`、`request_mount`、`submit_artifact`
4. 为 `os_runtime` 增加 Bubble action candidate 和 arbiter gating
5. 设计 MRK/WSP 事件进入 Hermes 后的 snapshot enrichment
