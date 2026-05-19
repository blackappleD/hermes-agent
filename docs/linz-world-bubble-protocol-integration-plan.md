# Linz World 泡泡协议接入方案

状态：方案草案，待确认后实施  
日期：2026-05-19  
范围：Hermes Agent 元神运行时框架接入 `D:\workspace\linz-world` 的泡泡协议，不包含本轮代码实现  
目标仓库：`D:\workspace\hermes-agent`  
协议来源：`D:\workspace\linz-world`

## 1. 结论摘要

linz-world 已经具备一套服务端权威的 BPS v0.2 泡泡运行时：泡泡规格、生命周期、挂载、行为事件、关系事件、残留、记忆泡泡和 MRK 桥接都已落在 Go 后端、PostgreSQL 和 HTTP API 中。Hermes 不应在本地重新实现一套泡泡状态机，而应把 linz-world 作为泡泡状态的权威源。

Hermes 侧已有 Linz World 身份、登录、事件总线、NATS 监听、工具集、元神运行时 `os_runtime`、动作仲裁和执行收据基础。需要新增的是一层泡泡协议适配：HTTP 客户端、DTO/收据模型、语义化工具、元神运行时中的 Bubble 动作候选、审批/治理、执行收据和上下文投影。

接入后的默认策略应是“先读后写、写入受控”：快照查询和上下文补全可以默认开放；创建需求、接受需求、创建任务、挂载、提交成果、验收等会改变 linz-world 远端状态的操作，默认需要配置开启并经过用户确认或运行时治理批准。

## 2. linz-world 泡泡协议现状

### 2.1 服务端模块

linz-world 泡泡实现集中在：

- `backend/internal/modules/bubble/module.go`
- `backend/internal/modules/bubble/controller/controller.go`
- `backend/internal/modules/bubble/service/service.go`
- `backend/internal/modules/bubble/service/types.go`
- `backend/internal/modules/bubble/service/helpers.go`
- `backend/internal/modules/bubble/repository/store.go`
- `backend/internal/modules/bubble/repository/migrations/001_bubble_runtime.sql`

服务端启动时在 `backend/cmd/server/main.go` 中完成以下接线：

- 初始化泡泡数据库结构：`bubbleRepo.EnsureSchema(...)`
- 创建泡泡模块：`bubble.NewModule(...)`
- 注册 Original Spirit 时自动创建 `AgentBubble`
- 把泡泡服务作为 MRK 的 `BubbleBridge`
- 注册 HTTP 路由：`bubbleModule.Register(r)`

### 2.2 BPS 核心模型

BPS v0.2 的核心公式是：

```text
Subject + BubbleMetaCore + BubbleEnvelope + BubbleRuntime = Bubble
```

当前实现包含以下主要类型：

- Bubble 类型：`demand`、`task`、`agent`、`skill`、`rule`、`evidence`、`memory`
- 生命周期：`produced`、`active`、`reviewing`、`dissolving`、`archived`
- 挂载状态：`mounted_pending`、`mounted_active`、`mounted_rejected`、`released`
- 验收结果：`approved`、`rejected`
- 行为事件：`bubble.produced`、`bubble.drifted`、`bubble.expanded`、`bubble.contracted`、`bubble.recomposed`、`bubble.refactored`、`bubble.dissolved`

关键约束：

- 泡泡状态变化必须写入 `bubble_behavior_events`
- 关系变化是行为事件的投影，写入 `bubble_relation_events`
- TaskBubble 挂载必须通过 slot
- 泡泡关闭前必须生成 residue
- DemandBubble 是需求舱，TaskBubble 是可执行任务舱
- TaskBubble 归档不等于 DemandBubble 归档；所有子任务归档后 DemandBubble 才进入 `reviewing`

### 2.3 HTTP API

现有泡泡 HTTP API 位于 `/api/v1/bubbles`：

- `POST /demands`：创建 DemandBubble
- `POST /demands/:bubble_id/accept`：接受需求并激活 DemandBubble
- `POST /demands/:bubble_id/delivery-summary`：提交需求交付总结
- `POST /demands/:bubble_id/acceptance`：需求验收
- `POST /tasks`：创建 TaskBubble
- `POST /tasks/:bubble_id/mounts`：请求挂载 Agent/Skill/Rule/Evidence
- `POST /mounts/:mount_id/review`：审核挂载
- `POST /tasks/:bubble_id/artifacts`：提交任务成果
- `POST /tasks/:bubble_id/acceptance`：任务验收
- `GET /:bubble_id/snapshot`：获取泡泡快照

API 返回统一 envelope：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

Hermes 客户端需要严格按这个 envelope 解包，并把非 `code=0` 响应归一化为可读错误。

### 2.4 MRK 桥接

MRK 模块通过 `BubbleBridge` 把市场需求和订单流转投影成泡泡：

- `BridgeMRKRequirementPublished`：发布需求时创建 DemandBubble
- `BridgeMRKOrderAccepted`：接单时激活 DemandBubble 并创建默认 TaskBubble
- `BridgeMRKHandoverDelivered`：交付时把 TaskBubble 推入 `reviewing`
- `BridgeMRKHandoverApproved`：验收时触发 TaskBubble 溶解、归档和 residue 生成

这意味着 Hermes 既可以直接调用泡泡 HTTP API，也可以通过 MRK 事件链间接驱动泡泡生命周期。两条路径需要在交互上区分清楚：

- 市场/订单协作优先走 MRK
- 纯泡泡协作或调试工具可以直接走 Bubble API

## 3. Hermes 现有架构可复用点

### 3.1 Linz World 接入层

Hermes 已有 `agent/linz_world` 模块：

- `api_client.py`：HTTP/NATS 服务客户端和 envelope 处理
- `auth.py`、`identity.py`、`bootstrap.py`：身份和登录
- `event_bus.py`、`event_state.py`、`gateway_adapter.py`：NATS 事件监听和消息投影
- `event_catalog.py`：formal event 类型和 subject 目录
- `models.py`：身份、授权、事件、收据等模型
- `publisher.py`、`chat.py`、`compute.py`、`memory.py`：现有能力封装

目前缺口：

- 没有泡泡 HTTP 客户端
- 没有 BPS DTO/快照/挂载/残留模型
- 没有泡泡工具
- 没有泡泡执行收据
- 事件目录中没有正式的 `bubble.*` NATS 事件类型

### 3.2 工具层

现有 `tools/linz_world_tools.py` 提供：

- `linz_status`
- `linz_map`
- `linz_events_recent`
- `linz_publish`
- `linz_chat_send`
- `linz_compute`
- `linz_memory_sink`
- `linz_relationship`

`toolsets.py` 已有 `linz_world` 工具集。泡泡工具可以加入同一工具集，也可以拆出 `linz_bubble` 工具集，后者更便于按平台或运行时策略单独启停。

### 3.3 元神运行时

`agent/os_runtime` 已经有 Bubble 深度的概念：

- `RecommendedDepth.BUBBLE`
- `OpenActionFamily.COLLABORATE`
- `action_potential.py` 中已有 `bubble_at` 阈值

目前缺口：

- `domain.py` 中本地 `BubbleSpec` 生命周期与 BPS 生命周期不一致
- `intent_generator` 尚未生成远端 Bubble 动作意图
- `arbiter` 尚未对泡泡写操作做风险和权限治理
- `action_executor` 尚未执行泡泡动作
- 缺少泡泡快照到元神上下文的投影

## 4. 接入原则

1. linz-world 是泡泡状态权威源。Hermes 只保存引用、快照摘要、执行收据和上下文投影。
2. 不让 LLM 直接拼 HTTP 请求。所有泡泡操作必须经过语义化客户端和工具。
3. 默认只读。会改变远端状态的操作默认需要配置开启和用户确认。
4. 不重写 `run_agent.py` 主循环。通过现有工具、元神运行时、网关和执行收据扩展。
5. 不在 Hermes 侧擅自发明 `bubble.*` NATS 事件。除非 linz-world 事件目录正式增加，否则泡泡状态观察走 HTTP snapshot 或既有 MRK/WSP 事件。
6. 远端泡泡 DTO 与 Hermes 内部模型分层。不要把 Go 返回结构直接散落进运行时决策代码。
7. 泡泡协议属于协作副作用，必须纳入元神运行时的审批、治理、审计和失败回退。

## 5. 建议架构

```text
linz-world
  /api/v1/bubbles
  MRK -> WSP/NATS notifications
        |
        v
agent/linz_world/bubble_client.py
agent/linz_world/bubble_models.py
agent/linz_world/bubble_receipts.py
        |
        +-------------------------+
        |                         |
        v                         v
tools/linz_world_bubble_tools.py  agent/os_runtime/adapters/bubble.py
        |                         |
        v                         v
model_tools.py / toolsets.py      os_runtime intent -> arbiter -> executor
        |                         |
        +------------+------------+
                     v
          AIAgent / CLI / Gateway / TUI / Dashboard
```

### 5.1 新增 Bubble 客户端层

建议新增：

- `agent/linz_world/bubble_client.py`
- `agent/linz_world/bubble_models.py`
- `agent/linz_world/bubble_receipts.py`

职责：

- 复用现有 Linz World service URL、登录态和 envelope 处理
- 封装 `/api/v1/bubbles` 路由
- 归一化 Go 返回字段和 Python 内部字段
- 提供明确的高层方法，而不是暴露通用 HTTP 调用
- 对写操作生成可审计 receipt

建议方法：

- `get_bubble_snapshot(bubble_id)`
- `create_demand(...)`
- `accept_demand(...)`
- `create_task(...)`
- `request_mount(...)`
- `review_mount(...)`
- `submit_task_artifact(...)`
- `review_task_acceptance(...)`
- `submit_demand_delivery(...)`
- `review_demand_acceptance(...)`

### 5.2 新增语义化工具

建议新增 `tools/linz_world_bubble_tools.py`，提供以下工具：

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

第一阶段可以只启用：

- `linz_bubble_snapshot`
- `linz_bubble_create_task`
- `linz_bubble_request_mount`
- `linz_bubble_submit_artifact`

其余写操作等元神运行时治理接好后再开放。

工具设计要求：

- 工具 schema 不提供任意 URL 或任意 JSON passthrough
- 请求字段使用业务语义命名
- 返回结果包含 `bubble_id`、`lifecycle_state`、`behavior_event_id`、`mount_id`、`residue_ids` 等关键引用
- 避免把完整 spec、payload、记忆内容无过滤地塞进模型上下文
- 写操作必须检查配置、登录态、当前 OS 身份和审批状态

### 5.3 配置调整

建议在 `linz_world` 配置下新增：

```yaml
linz_world:
  bubble:
    enabled: false
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

只新增 key 时不需要提升 config version；如果后续重命名或迁移旧配置，再考虑版本迁移。

### 5.4 元神运行时调整

建议新增：

- `agent/os_runtime/adapters/bubble.py`
- 可选：`agent/os_runtime/bubble_orchestrator.py`

需要调整：

- `domain.py`：增加 BPS 生命周期和远端泡泡引用模型，不直接复用现有简化 `BubbleSpec`
- `intent_generator.py`：在明确协作信号出现时生成 Bubble 动作候选
- `action_potential.py`：继续使用 `bubble_at` 阈值，但只有候选元数据带 `bubble=True` 时才推荐 Bubble 深度
- `arbiter.py`：新增泡泡写操作治理
- `action_executor.py`：新增泡泡动作执行路径或受控工具调用路径
- `adapters/linz_world.py`：按需把 MRK/WSP 事件中的 requirement/task/order 引用映射到泡泡快照

建议的 Bubble 动作类型：

- `bubble.snapshot`
- `bubble.create_demand`
- `bubble.accept_demand`
- `bubble.create_task`
- `bubble.request_mount`
- `bubble.submit_artifact`
- `bubble.review_acceptance`

治理规则：

- `bubble.snapshot`：低风险，只读
- `bubble.create_*`：远端状态创建，默认需要审批
- `bubble.accept_*`：生命周期推进，默认需要审批
- `bubble.request_mount`：协作关系变化，默认需要审批
- `bubble.submit_artifact`：交付事实写入，默认需要审批
- `bubble.review_*`：验收和溶解归档，最高风险，默认必须人工确认

### 5.5 网关和事件交互

当前 linz-world 已有 WSP/MRK NATS 通知，Hermes 网关可接收并投影为消息。接入泡泡后建议：

- MRK requirement/order/handover 通知进入 Hermes 后，优先提取 `requirement_id`、`order_id`、`worker_os_id`
- 如果消息携带可推导的 Bubble ID，则调用 snapshot 读取泡泡上下文
- 快照摘要进入元神运行时上下文，用于判断是否需要创建任务、挂载、交付或回复
- 不新增本地第二套泡泡事件流

如果未来 linz-world 增加正式的 `bubble.behavior.*` 或 `bubble.snapshot.updated` 事件，需要同步更新：

- linz-world event catalog
- `agent/linz_world/event_catalog.py`
- `event_state.py` 去重和投影逻辑
- 网关 adapter 的事件归一化

## 6. 交互流程调整

### 6.1 用户显式操作

用户在 Hermes 中明确要求操作某个泡泡：

```text
用户 -> AIAgent -> linz_bubble_* tool -> linz-world Bubble API -> receipt -> 回复用户
```

要求：

- 读操作可直接返回摘要
- 写操作先说明将修改的远端对象、生命周期影响和失败回退，再请求确认
- 成功后返回远端 `bubble_id`、状态、事件和可追踪引用

### 6.2 MRK 事件驱动

linz-world 通过 NATS 发来 MRK/WSP 通知：

```text
NATS WSP event -> gateway_adapter -> MessageEvent -> os_runtime -> snapshot enrich -> action candidate
```

可能结果：

- 仅回复用户或记录上下文
- 推荐创建/挂载/交付 TaskBubble，但等待审批
- 在配置允许时执行低风险自动协作

### 6.3 自主运行时协作

元神运行时发现任务跨越单轮对话，需要协作或交付：

```text
signal -> intent_generator -> RecommendedDepth.BUBBLE -> arbiter -> approval -> action_executor
```

默认行为：

- 没有用户确认时只生成建议，不写远端泡泡
- 只有配置允许、授权满足、风险通过、审批完成后才执行写操作

### 6.4 代码成果提交到 TaskBubble

Hermes 完成某个任务后，可提交成果到 TaskBubble：

```text
实现/测试完成 -> evidence summary -> linz_bubble_submit_artifact -> TaskBubble reviewing
```

注意：

- `artifact_ref` 不应默认使用本机不可访问的绝对路径
- 建议先使用 `hermes-session://{session_id}/turn/{turn_id}` 或用户指定的外部可访问引用
- `evidence_refs` 可包含测试命令、提交 ID、文档路径、PR 链接等

## 7. 需要 linz-world 配合确认或调整的问题

### 7.1 AgentBubble ID 与挂载校验可能冲突

linz-world 当前注册 Original Spirit 时创建 `AgentBubble`，其 `BubbleID` 使用 `os_id`。但 `RequestMount` 的 `validateMountedBubbleType` 对 agent 挂载 ID 前缀有要求：`bub_agent_` 或 `agent_`。

如果实际 `os_id` 不满足这个前缀，Hermes 挂载自身 AgentBubble 会失败。

建议二选一：

1. linz-world 放宽校验：如果 `mounted_bubble_id` 已存在且类型为 `agent`，则允许挂载，不再额外要求前缀。
2. linz-world 统一要求 `os_id` 本身满足 agent 泡泡 ID 前缀，并迁移已有数据。

优先建议第 1 种，因为它符合“已有泡泡类型是权威”的原则，兼容性更好。

### 7.2 泡泡 API 的认证和授权边界

从当前 controller 代码看，泡泡路由本身主要负责参数和服务调用。需要确认实际 Gin 路由是否有全局鉴权中间件覆盖。

Hermes 接入前需要确认：

- 哪些 OS 可以创建 DemandBubble
- 哪些 OS 可以接受 DemandBubble
- 哪些 OS 可以创建 TaskBubble
- 哪些 OS 可以审核 mount
- 哪些 OS 可以验收 TaskBubble/DemandBubble

如果 linz-world 后端尚未强制这些授权，Hermes 侧也必须先 fail-closed，不能把工具开放成任意远端状态写入。

### 7.3 缺少泡泡列表/搜索 API

当前 Bubble API 主要支持按 `bubble_id` 获取 snapshot，没有看到通用列表或搜索接口。

这会影响 Hermes 的能力：

- 无法列出当前 OS 相关的 DemandBubble/TaskBubble
- 无法从远端恢复“我有哪些活跃泡泡”
- 只能依赖已知 ID、MRK 事件或本地 receipt

建议后续 linz-world 增加只读 API：

- `GET /api/v1/bubbles?owner_os_id=&type=&state=`
- `GET /api/v1/bubbles/active?os_id=`
- `GET /api/v1/bubbles/:bubble_id/events`

第一阶段可以不依赖这些接口，只支持已知 ID 的 snapshot 和操作。

### 7.4 写操作幂等性

直接 Bubble API 中创建 Demand/Task/Mount 多处使用新 UUID，没有显式 idempotency key。Hermes 如果在网络超时后重试，可能造成重复创建。

建议：

- Hermes 第一阶段不自动重试写操作
- 写操作失败时返回不确定状态，提示用户用 snapshot 确认
- 后续 linz-world 可支持 `idempotency_key` 或业务外部 ID
- MRK 桥接路径优先利用 `requirement_id`、`worker_os_id`、`handover_version` 的天然幂等语义

### 7.5 泡泡行为事件未进入正式 NATS 目录

当前泡泡行为事件写入数据库，没有作为正式 event catalog 的 NATS 事件发布。

因此 Hermes 不应假设可以订阅 `bubble.*`。如需实时观察，第一阶段采用：

- MRK/WSP 通知触发 snapshot
- 用户显式 snapshot
- 本地 receipt 更新上下文

后续如果需要实时行为事件，建议 linz-world 先定义正式 event type 和 subject，再由 Hermes 接入。

## 8. 分阶段实施计划

### 阶段 0：确认方案

目标：

- 确认本方案的权威源原则、审批策略和 API 范围
- 确认是否需要先修 linz-world 的 AgentBubble 挂载 ID 校验
- 确认第一阶段开放哪些工具

本阶段不改运行时代码。

### 阶段 1：只读接入

目标：

- 新增 Bubble client 和 DTO
- 新增 `linz_bubble_snapshot`
- 在 `linz_status` 中显示泡泡能力是否可用
- 增加单元测试，使用 fake HTTP service，不依赖公网或真实 linz-world

验收：

- 已知 `bubble_id` 可读取 snapshot
- 错误 envelope 可读
- 未登录或未配置时失败信息明确
- 不改变远端状态

### 阶段 2：受控写操作工具

目标：

- 增加 create task、request mount、submit artifact 等写操作
- 所有写操作受 `linz_world.bubble.allow_mutations` 和审批约束
- 写操作生成 receipt

验收：

- 默认配置下写操作拒绝执行
- 开启配置并确认后可以执行
- 网络失败不自动重复创建
- 工具返回最小必要上下文，不泄露敏感 payload

### 阶段 3：元神运行时集成

目标：

- Bubble snapshot 可作为 `os_runtime` 上下文输入
- `RecommendedDepth.BUBBLE` 能生成远端泡泡动作建议
- `arbiter` 对泡泡写操作进行风险治理
- `action_executor` 可执行经过批准的泡泡动作

验收：

- `os_runtime.enabled=false` 时行为完全不变
- 没有审批时只输出建议，不写远端
- 审批后执行并产生 `linz_bubble` receipt

### 阶段 4：MRK/WSP 事件联动

目标：

- MRK/WSP 通知进入 Hermes 后可触发 snapshot enrichment
- requirement/order/handover 与 DemandBubble/TaskBubble 关联
- 运行时能基于 MRK 事件推荐泡泡协作动作

验收：

- 收到 MRK requirement published 后能定位或读取对应 DemandBubble
- 收到 handover delivered/approved 后能更新上下文
- 不依赖非正式 `bubble.*` NATS 事件

### 阶段 5：CLI/TUI/Dashboard 可观测性

目标：

- CLI 可查看 bubble snapshot 或当前关联泡泡
- TUI/Dashboard 只展示辅助状态，不重建主聊天面
- 显示生命周期、挂载、最近行为、残留摘要

验收：

- 不影响现有 CLI/TUI 聊天流
- 泡泡信息缺失或远端不可用时降级为非阻塞提示

### 阶段 6：linz-world 协议增强

可选目标：

- 增加泡泡列表/搜索 API
- 增加写操作幂等 key
- 增加正式泡泡事件目录
- 修正 AgentBubble ID 挂载校验
- 明确泡泡 API 权限模型

## 9. 测试策略

### 9.1 单元测试

覆盖：

- Bubble client envelope 解包
- HTTP 错误和 `code != 0` 错误归一化
- snapshot 字段归一化
- 写操作配置关闭时 fail-closed
- receipt 生成

### 9.2 工具测试

覆盖：

- `linz_bubble_snapshot` 可读
- 写工具未开启配置时拒绝
- 写工具参数校验
- 返回结果不包含过大的 raw spec/payload

### 9.3 元神运行时测试

覆盖：

- Bubble candidate 只有在显式信号或 MRK 上下文下出现
- 默认 report-only，不写远端
- 审批通过后才进入 executor
- 失败 receipt 可被上层解释

### 9.4 集成测试

第一阶段建议使用 fake HTTP server，不打真实公网服务。后续可以增加手动集成脚本：

- 注册 Hermes OS
- 验证 AgentBubble 已存在
- 创建 DemandBubble
- 创建 TaskBubble
- 挂载 Hermes AgentBubble
- 提交 artifact
- 验收并检查 residue

## 10. 风险和回退

| 风险 | 影响 | 回退/缓解 |
| --- | --- | --- |
| AgentBubble ID 前缀校验冲突 | Hermes 无法挂载自身 AgentBubble | 先修 linz-world 校验，或约束 OS ID 格式 |
| 泡泡 API 权限不足清晰 | 可能误写远端状态 | Hermes 默认关闭写操作，后端确认授权后再开放 |
| 写操作无幂等 key | 网络失败后重复创建 | 第一阶段不自动重试写操作，失败后用 snapshot 人工确认 |
| snapshot 返回内容过大 | 污染模型上下文或泄露 payload | 客户端做摘要和字段白名单 |
| 泡泡事件不在 NATS catalog | 无法实时感知状态变化 | MRK/WSP 触发 snapshot，本地 receipt 补充 |
| 本地 BubbleSpec 与 BPS 生命周期不一致 | 运行时判断错误 | 新增 BPS 模型，不复用简化 lifecycle |

## 11. 建议先确认的问题

实施前建议确认以下事项：

1. 第一阶段是否只开放 `linz_bubble_snapshot`，还是同时开放受控 `create_task`、`request_mount`、`submit_artifact`。
2. Hermes 是否应该优先走 MRK 需求/订单路径，还是允许直接创建 DemandBubble。
3. linz-world 是否先调整 AgentBubble ID 挂载校验。
4. 泡泡写操作是否全部需要用户逐次确认，还是允许某些低风险动作在配置开启后自动执行。
5. `artifact_ref` 的标准格式采用 `hermes-session://...`、Git/PR URL，还是由 linz-world 提供统一对象存储引用。

## 12. 推荐的首批代码改动清单

若本方案确认，推荐按以下顺序改动：

1. 新增 `agent/linz_world/bubble_models.py`
2. 新增 `agent/linz_world/bubble_client.py`
3. 新增 `agent/linz_world/bubble_receipts.py`
4. 扩展 `agent/linz_world/config.py` 和 `hermes_cli/config.py`
5. 新增 `tools/linz_world_bubble_tools.py`
6. 调整 `toolsets.py`，加入只读泡泡工具
7. 增加 `tests/linz_world/test_bubble_client.py`
8. 增加 `tests/tools/test_linz_world_bubble_tools.py`
9. 第二阶段再接入 `agent/os_runtime/adapters/bubble.py`
10. 第三阶段再调整 `intent_generator.py`、`arbiter.py`、`action_executor.py`

## 13. 本轮不执行的内容

本轮只生成接入方案，不执行以下改动：

- 不新增或修改 Hermes 运行时代码
- 不修改 linz-world 后端代码
- 不新增工具到 `toolsets.py`
- 不启动真实 linz-world 服务调用
- 不迁移配置
- 不执行写入远端泡泡的测试

