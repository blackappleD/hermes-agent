# 基于张力场的 Agent 自驱动实现计划

> 依据：`docs/plans/基于张力场的元神运行时框架技术白皮书.md` 与 Hermes Agent 当前代码结构。
> 目标：在 Hermes 现有 Agent Runtime 之上，以 Linz World 原生元神身份为基础，以模块化、可回滚、可验证的方式引入“世界事件 -> 状态 -> 张力 -> 势能 -> 意图 -> 裁判 -> 执行 -> 记忆”的自驱动闭环。

## 1. 核心判断

Hermes 当前已经具备自驱动 runtime 所需的大部分基础设施：同步 `AIAgent` 主循环、工具注册与调度、插件 hook、跨轮 `/goal` 目标循环、SessionDB、memory provider、context engine、delegate 子代理、kanban 协作板、gateway/TUI/dashboard 表面。

此前 `D:\workspace\linz-world-skill` 以 skill 形式提供 Linz World 接入能力：注册世界身份、登录授权、读取授权 map、接收未读世界消息、发布正式事件、写入 Soul Memory、维护关系、调用世界算力。新的框架下，这些能力不再是用户可选安装的 skill，而应成为 Hermes Agent 的原生世界身份层：Agent 天然是 Linz World 中的一个元神，只是是否在线、是否自动响应、是否允许发布事件由配置和治理控制。

因此实现策略不应重写 `run_agent.py` 主循环，也不应在 `os_runtime` 中复制 `agent/` 已有的上下文、记忆、工具、会话和协作基础设施。`os_runtime` 的边界应更窄：只新增张力场领域语义、决策算法和适配器。Linz World 能力应放在独立的一等公民模块中，作为世界身份、世界事件、世界算力和世界治理边界。

更准确的实现形态是：

```text
Hermes profile 创建/加载
  -> linz_world 字段初始化与创建期自动 registry
  -> Linz World 原生身份与事件总线
  -> 外部输入：NATS 世界事件 + Hermes 对话 + 工具/运行时反馈
  -> 现有输入/会话/工具/模型/记忆/网关
  -> os_runtime 领域层与适配器
  -> 张力场自治内核
  -> 意图裁判与现有工具执行适配
  -> 回写事件、证据、记忆、规则
```

收敛后的主线是：

1. Agent 创建时必须自动注册到 Linz World，成为 original spirit。这里的“创建”以 Hermes 原生 profile / agent persona 为身份边界，必须幂等，不能因为 gateway 每轮构造 `AIAgent` 实例而重复注册。
2. Agent 原生拥有 `linz-world-skill` 的所有能力：registry、login、status、map、message unread、publish、Soul Memory、relationship、world compute，但不再通过安装 skill 获得。
3. `os_runtime` 只负责张力场自驱动。NATS 世界事件和 Hermes 元神对话都作为外部输入进入同一事件投影层。
4. 泡泡协议保留为低优先级协作扩展，不进入第一版核心闭环。

Linz World 创建期注册是基础身份能力，不属于 `os_runtime` opt-in。需要 opt-in 的是自驱动、自动响应、自动上线监听和外部副作用执行。第一版自驱动能力先限制在低风险、可审计、可停止的范围：继续推进明确目标、生成草案、建议下一步；不允许默认执行高风险外部副作用。

## 2. 现有项目能力对照

| 白皮书模块 | Hermes 当前落点 | 实现策略 |
| --- | --- | --- |
| 传统 Agent Runtime | `run_agent.py::AIAgent.run_conversation()` | 继续复用主循环，自治层只决定是否注入上下文、是否触发下一轮、是否阻断工具 |
| LLM Gateway / 模型路由 | `AIAgent`、`agent/auxiliary_client.py`、`hermes_cli/runtime_provider.py` | `CognitiveEconomyController` 先产出路由建议，后续再接入真实模型切换 |
| Tool & Skill Registry | `tools/registry.py`、`model_tools.py`、`toolsets.py` | `adapters/tools.py` 通过现有 registry 和 plugin hooks 记录、限流、拦截 |
| 插件 hook | `hermes_cli/plugins.py` 的 `pre_llm_call`、`pre_tool_call`、`post_tool_call`、`post_llm_call` | 第一阶段用 hook 做低侵入集成 |
| 跨轮自驱动雏形 | `hermes_cli/goals.py` | 扩展为张力场 driver，而不是另写无限循环 |
| Linz World skill 能力 | `D:\workspace\linz-world-skill` 的 CLI、事件模型、profile、box、compute | 迁移为 `agent/linz_world/` 原生模块；skill 仅作为迁移参考和旧数据导入来源 |
| 世界身份 | Linz `registry/login/status/map` 与旧 skill profile 数据 | Hermes profile 内建 `linz_world` 字段、创建期幂等 registry、auth session、authorization map |
| 世界事件 | Linz `publish/message unread/agent-event-hook` 与 NATS 订阅 | 原生 event catalog、Hermes gateway adapter、MessageEvent 投递、最小 NATS cursor/dispatch/receipt 状态 |
| 世界算力 | Linz `compute` | 原生 world compute client；可作为自治辅助模型路由之一 |
| Soul Memory / 关系 | Linz `memmory_sink/relationship` | 接入演化记忆、规则结晶和关系信号 |
| 会话与搜索 | `hermes_state.py::SessionDB` | 自治事件优先落到 SessionDB side tables；JSONL 只作为短期 fallback |
| 记忆 | `agent/memory_manager.py`、`tools/memory_tool.py`、memory plugins | 演化记忆作为自治证据/规则层，复用 MemoryManager 入口但不新增外部 provider |
| 上下文压缩 | `agent/context_engine.py`、`agent/context_compressor.py` | 自治上下文作为 ephemeral user context 注入，不改稳定 system prompt |
| 多 Agent 协作 | `tools/delegate_tool.py`、`hermes_cli/kanban_db.py`、`tools/kanban_tools.py` | 泡泡协议低优先级集成，后续再映射到 kanban task/links/comments |
| 治理与审批 | `tools/approval.py`、plugin `pre_tool_call` block、gateway `/approve`/`/deny` | `BoYueArbiter` 与 `PolicyEngine` 先阻断/降级，再接审批 |
| 观测 | logs、TUI events、dashboard、kanban dashboard、observability plugin | 先输出 SessionDB side-table/JSONL evidence，再加 dashboard/TUI 状态面板 |

## 3. 目标架构

建议新增两个一等公民模块：

- `agent/linz_world/`：Linz World 原生身份、授权、事件、世界算力、Soul Memory 与关系能力。它替代原 skill 的安装式能力。
- `agent/os_runtime/`：张力场自治领域层，消费 Linz World 与 Hermes 现有 runtime 提供的信号。

代码命名使用 ASCII，用户文档可继续使用“元神/张力场”术语。

白皮书补充后的 `agent/os_runtime` 必须显式覆盖 A-G 七个内核模块，不能再把 D「张力解释器」隐含在张力场更新中：

| 白皮书图中模块 | 实现计划落点 | 第一版必须落库/可观测的关键字段 |
| --- | --- | --- |
| A. 张力场系统 | `engine/tension_field.py` | `core_tensions`、`dynamic_tensions`、`intensity`、`trend`、`baseline`、`activation`、`propagation_edges` |
| B. 行动势能评估 | `engine/action_potential.py` | `value_potential`、`mutual_benefit_potential`、`learning_potential`、`risk_cost`、`overall_score` |
| C. 生命状态系统 | `engine/life_state.py` | `energy`、`fatigue`、`wakefulness`、`curiosity`、`boredom`、`creative_pressure`、`social_hunger`、`silence_pressure`、`restraint`、`life_cycle`、`recovery_cycle`、`generated_intent_count` |
| D. 张力解释器 | `engine/tension_interpreter.py` | `detected_conflicts`、`TensionOperation[]`、`TensionExplanation`、`event_id`、`evidence` |
| E. 张力到 Prompt 编译器 | `engine/prompt_compiler.py` | `state_summary`、`tension_summary`、`potential_summary`、`memory_scope`、`constraint_scope`、`environment_scope`、`open_space`、`target_direction` |
| F. 开放式意图生成器 | `engine/intent_generator.py` | `action_family`、`action_type`、`why_now`、`tools_needed`、`proposed_new_tools`、`proposed_new_skills`、`success_condition`、`stop_condition` |
| G. 博约裁判器 | `engine/arbiter.py` | 博/约/合评分、`auto_execute`、`sandbox_execute`、`require_approval`、`report_only`、`reject` |

```text
agent/linz_world/
  __init__.py
  config.py
  bootstrap.py             # agent/profile 创建期 ensure_registered_for_agent()
  identity.py              # WorldIdentity: hermes_profile / os_id / soul_id / os_name
  profile_fields.py        # 读写当前 Hermes profile 的 linz_world 字段；旧 ~/.linz-world 只读导入
  auth.py                  # registry / login / logout / token refresh / authorization state
  api_client.py            # register/status/map/publish/relationships/compute 等 HTTP API
  event_catalog.py         # 正式 subject/event_type/payload schema 与旧协议阻断
  event_bus.py             # listener/bootstrap/NATS 或服务端事件流适配
  gateway_adapter.py       # NATS/Linz World 事件转成 Hermes gateway MessageEvent
  event_state.py           # NATS cursor / dedupe / dispatch status / publish receipt
  publisher.py             # 正式事件发布、payload 校验、publish receipt
  compute.py               # 世界算力调用，使用登录 token，不接受裸 api-key
  memory.py                # Soul Memory sink 与 memory overview
  relationship.py          # 关系读取与 ACTIVE 关系写入
  runtime_bridge.py        # 将世界事件转成 Hermes turn / os_runtime event
  migration.py             # 从 linz-world-skill 本地 profile、SOUL、box 一次性导入
```

目录按“领域对象、适配器、引擎、driver”划分，避免和现有 `agent/` 基础设施重名：

```text
agent/os_runtime/
  __init__.py
  config.py
  domain.py                 # LifeState / Tension / Intent / Arbitration 等领域对象
  driver.py                 # 复用 /goal continuation 模式的自治 driver
  evidence.py
  adapters/
    events.py               # 适配 plugin hooks / SessionDB side tables
    session_store.py        # 适配 hermes_state.SessionDB，不另造 session store
    context.py              # 适配 context_engine / memory_manager / tool registry
    tools.py                # 适配 model_tools / tools.registry / pre_tool_call
    memory.py               # 适配 MemoryManager，处理演化记忆入口
    kanban.py               # 适配 hermes_cli.kanban_db / tools.kanban_tools
  engine/
    signals.py
    life_state.py
    tension_interpreter.py
    tension_field.py
    action_potential.py
    cognitive_economy.py
    prompt_compiler.py
    intent_generator.py
    arbiter.py
    policy.py
    stvb_guard.py
    rule_crystallizer.py
  bubble/
    domain.py
    manager.py
    slot_broker.py
    skill_matcher.py
    lifecycle.py
```

复用边界：

| `linz_world` 组件 | 复用/迁移对象 | 不做的事 |
| --- | --- | --- |
| `identity.py` / `profile_fields.py` | 将 Linz 必要字段写入当前 Hermes profile 的 `linz_world` 段；旧 `~/.linz-world/profiles` 只作导入来源 | 不再创建额外 Linz profile，不要求用户安装 skill 才有世界身份 |
| `auth.py` / `api_client.py` | 迁移 `registry/login/status/map` 与 `/api/v1/*` 调用 | 不把登录 token 暴露给 prompt 或普通工具结果 |
| `event_catalog.py` | 迁移 `references/event-model.md` 与 `event-catalog.js` 的正式目录和旧协议阻断 | 不允许 LLM 自造 subject/event_type |
| `gateway_adapter.py` / `event_state.py` / `runtime_bridge.py` | 复用 skill 的事件语义，但用 Hermes gateway `MessageEvent` 替代文件式 inbox/outbox；只保留 NATS cursor、dedupe、dispatch status、publish receipt | 不迁移 skill 的本地邮箱模型，不再依赖外部 hook 进程把世界事件送入 agent |
| `compute.py` | 迁移 `linz compute` 的世界算力边界 | 不把它当裸通用推理接口；必须使用登录 token |
| `memory.py` / `relationship.py` | 迁移 Soul Memory sink 与 relationship | 不替代 Hermes MemoryManager，只作为世界侧记忆/关系适配 |

| `os_runtime` 组件 | 复用对象 | 不做的事 |
| --- | --- | --- |
| `domain.py` | 不复用，新增张力场领域对象 | 不定义通用会话/消息模型 |
| `adapters/session_store.py` | `hermes_state.py::SessionDB`、`get_hermes_home()` | 不新建独立 session 数据库 |
| `adapters/context.py` | `agent/context_engine.py`、`agent/memory_manager.py`、现有 tool definitions | 不替代 context compressor 或 memory provider |
| `adapters/tools.py` | `model_tools.py`、`tools/registry.py`、plugin hooks | 不重写工具执行 |
| `adapters/kanban.py` | `hermes_cli/kanban_db.py`、`tools/kanban_tools.py` | 不新建第二套任务板 |
| `driver.py` | `hermes_cli/goals.py` 的跨轮目标循环模式 | 不创建无上限后台自治循环 |

配套入口：

```text
hermes_cli/os_runtime.py          # CLI / slash command handler
tools/os_runtime_tools.py       # 只读状态、tick、bubble/evidence 工具
tests/os_runtime/               # 单元与集成测试
```

Hermes profile 原生存储原则：

- 不再创建新的 Linz profile。当前 Hermes profile 已由 `HERMES_HOME` 隔离，Linz 字段必须写入该 profile 自己的配置/状态空间。
- `config.yaml` 的 `linz_world` 段保存非秘密、可审计的身份和行为配置：`os_id`、`soul_id`、`os_name`、`account_id`、`registration_state`、授权 map 摘要、NATS/server URL、是否自动登录/监听等。
- 登录 token、私钥、NATS cursor、dispatch status、publish receipt 等运行期敏感或高频变化数据可以放在当前 Hermes profile 下的 `linz_world/` 状态文件、SessionDB side tables 或现有 auth store，但不能放到独立的 `~/.linz-world/profiles` 运行期 profile 中，也不能进入 prompt/log 明文。
- 旧 `~/.linz-world` 只作为一次性导入来源：读取已有 `os_id/soul_id`、SOUL、box 状态后写回 Hermes profile 的 `linz_world` 字段和 per-profile 状态目录。

NATS 事件接入原则：

- 不复制 `linz-world-skill` 的文件式 inbox/submited/handled/outbox。那些结构是 skill 为适配不同 agent runtime 做的通用 mailbox；Hermes 已有 gateway、`MessageEvent`、SessionStore、SessionDB 和 busy queue，可直接承接“外部事件进入 Agent turn”的职责。
- `agent/linz_world/gateway_adapter.py` 作为原生平台适配器接入 `gateway.platform_registry`，监听 NATS 后将世界事件规范化为 Hermes `MessageEvent`，再走 `BasePlatformAdapter.handle_message()` 和 `GatewayRunner._handle_message()` 的原生流程。
- `agent/linz_world/event_state.py` 只保存 NATS 和世界事件必须的可靠性状态：`event_id` 去重、stream/consumer cursor、dispatch status、attempt_count、last_error、publish receipt。
- NATS ack 在“事件已写入 event_state / SessionDB side table”后执行；LLM 处理失败不反向阻塞 NATS，而是由 Hermes 内部 dispatch status 重试或降级。
- 世界事件发布仍由 `publisher.py` 执行 payload 校验和授权检查，成功后记录 publish receipt；不需要 outbox 文件夹作为中间状态。

配置建议：

```yaml
linz_world:
  enabled: true
  auto_register_on_agent_create: true
  registration_failure_mode: explicit_pending # explicit_pending | fail_agent_create
  registration_state: pending                 # pending | registered | failed
  server_url: ""
  nats_url: ""
  original_spirit:
    os_id: ""
    soul_id: ""
    os_name: ""
    account_id: ""
  auth:
    auto_login: false
    token_ref: ""          # points to per-profile auth/runtime state; no raw token in prompt
    last_login_at: ""
  online_by_default: false
  require_map_before_publish: true
  authorization:
    state: unknown
    map_version: ""
    last_refresh_at: ""
  nats:
    enabled: false
    stream: ""
    consumer: ""
    cursor_ref: ""         # points to per-profile event_state / SessionDB side table
    ack_after_persist: true
  event_poll_interval_seconds: 0 # optional HTTP unread fallback; NATS path does not poll
  event_handling: assisted # passive | assisted | autonomous_low_risk

os_runtime:
  enabled: false
  mode: passive        # passive | assisted | autonomous_low_risk
  max_continuation_turns: 8
  tick_interval_seconds: 0
  allow_tool_execution: false
  event_store: sessiondb_side_tables  # sessiondb_side_tables | jsonl_fallback
  model_task: os_runtime_intent
  risk:
    require_approval_at: medium
```

## 4. 分阶段实施总览

| 阶段 | 目标 | 自驱动能力 | 风险级别 |
| --- | --- | --- | --- |
| 阶段 -1：Linz World 原生化与自动注册 | 在 Hermes profile 的 `linz_world` 字段中内建 original spirit 身份，Agent 创建即幂等 registry | 无，先具备身份/授权/NATS 事件接入/发布能力 | 中 |
| 阶段 0：协议与适配基座 | 固化领域对象、Hermes profile 字段、配置、测试夹具 | 无，只记录 | 低 |
| 阶段 1：外部事件观测闭环 | NATS 世界事件、Hermes 对话、工具/运行时反馈进入事件流，计算生命状态、张力解释和张力网络 | 无，只展示 | 低 |
| 阶段 2：低风险意图建议 | 生成 ActionPotential、SelfPrompt、OpenIntent、ArbitrationResult | 建议下一步，不自动执行 | 低 |
| 阶段 3：辅助自驱动 | 类似 `/goal`，在明确目标下自动继续下一轮 | 仅自然语言/草案 | 中低 |
| 阶段 4：工具执行网关 | 对低风险工具调用生成票据、receipt、evidence | 受限工具执行 | 中 |
| 阶段 5：记忆进化与规则结晶 | R0/R1 规则、张力演化、经验回流 | 调整后续裁判 | 中 |
| 阶段 6：治理与平台化 | 审批、STVB、dashboard、API | 多会话可观测自治 | 中高 |
| 阶段 7：泡泡协议低优先级集成 | 将复杂任务拆成泡泡/能力槽并映射 kanban/delegate/Linz 市场事件 | 协作任务编排 | 中 |

## 5. 模块化实施计划

### 模块 -1：Linz World 原生身份与世界接入

目标：把 `D:\workspace\linz-world-skill` 中通过 skill 暴露的能力迁移为 Hermes Agent 的原生能力。用户不再需要安装 skill；Hermes Agent 创建时必须基于当前 Hermes profile 的 `linz_world` 字段幂等注册到 Linz World，成为 original spirit。登录、上线监听、自动响应和事件发布仍受配置与治理约束。

新增：

- `agent/linz_world/bootstrap.py`
- `agent/linz_world/identity.py`
- `agent/linz_world/profile_fields.py`
- `agent/linz_world/auth.py`
- `agent/linz_world/api_client.py`
- `agent/linz_world/event_catalog.py`
- `agent/linz_world/event_bus.py`
- `agent/linz_world/gateway_adapter.py`
- `agent/linz_world/event_state.py`
- `agent/linz_world/publisher.py`
- `agent/linz_world/compute.py`
- `agent/linz_world/memory.py`
- `agent/linz_world/relationship.py`
- `agent/linz_world/runtime_bridge.py`
- `agent/linz_world/migration.py`
- `hermes_cli/linz.py`
- `tools/linz_world_tools.py`
- `tests/linz_world/`

迁移来源：

- `SKILL.md` 的使用流程与错误处理。
- `references/event-model.md` 的正式 subject/event_type/payload。
- `references/world-rules.md` 的命令前置条件。
- `references/identity-and-memory.md` 的 identity/Soul Memory 边界。
- `references/compute-gateway.md` 的世界算力边界。
- `script/dist/src/config/profile-schema.js` 的旧 profile schema，只提取 Hermes 必需字段，不照搬多 runtime 适配字段。
- `script/dist/src/mappers/event-catalog.js` 的正式事件目录与旧协议阻断。
- `script/dist/src/events/agent-event-hook.js` 的事件流转语义，仅作为语义参考，不迁移文件式 inbox/outbox。
- `script/dist/src/clients/api-client.js` 的 HTTP API 路径。

实现步骤：

1. 定义 `WorldIdentity`：`hermes_profile`、`os_id`、`os_name`、`soul_id`、`account_id`、`authorization_state`、`memory_summary_available`。
2. `profile_fields.py` 只读写当前 Hermes profile 的 `linz_world` 字段。字段最小化，保留 Linz World 必需身份/授权/连接状态，不照搬 skill 里用于适配其他 agent runtime 的 profile 字段。
3. `bootstrap.py` 实现 `ensure_registered_for_agent()`，在 Hermes profile 创建/加载、CLI/gateway/TUI 构造 agent persona 或 `AIAgent` 首次使用时调用：
   - 已有 `os_id/soul_id` 且 registration_state=registered 时直接返回。
   - 没有身份时调用 Linz registry，写回 `linz_world.original_spirit` 和 `registration_state`。
   - 注册失败时写入 `registration_state=failed|pending` 和诊断信息；不能静默退化成“无世界身份”。
   - 必须按 Hermes profile 幂等，避免每轮 gateway 消息或每个临时 `AIAgent()` 实例重复注册。
4. 旧 `~/.linz-world/profiles/*.json` 与 `~/.linz-world/state/sessions/*.json` 只由 `migration.py` 读取并一次性导入到 Hermes profile；导入后运行期不再写旧 Linz profile。
5. `auth.py` 实现原生 `registry/login/logout/status/map`，并把授权 map 缓存为只读治理输入。
6. `event_catalog.py` 固化正式事件目录和 payload 校验，阻断旧写法：`sys.boardcast`、`sys.login.request`、`sys.login.result`、`subject_change` 等。
7. `gateway_adapter.py` 注册为 Hermes 原生 gateway platform adapter，监听 NATS/Linz World 事件，并生成 `MessageEvent`：
   - `source.platform` 使用 `linz_world` 动态平台。
   - `source.chat_id` 由 world room、relationship、task/order id 或 event subject 派生。
   - `message_id` 使用 Linz event id，支持去重。
   - `raw_message` 保留原始 NATS/world event，但 prompt 只注入摘要。
   - `internal=true` 仅用于系统生成、已授权的事件投递；普通世界用户消息仍走治理/授权。
8. `event_state.py` 保存最小可靠性状态，替代 skill 的 inbox/submited/handled/outbox 文件：
   - `event_id` / `nats_sequence` 去重。
   - `stream` / `consumer` / `cursor`。
   - `dispatch_status`: `persisted | queued | processing | handled | failed | skipped`。
   - `attempt_count`、`last_error`、`last_dispatched_at`。
   - `publish_receipt` 与 world event id。
9. NATS ack 策略：事件持久化到 `event_state` 或 SessionDB side table 后 ack；Agent 处理失败时更新 `dispatch_status=failed` 并由 Hermes 内部重试/降级，不让 NATS 等待 LLM 完整处理。
10. `publisher.py` 发布正式事件前强制检查：
   - 已 registry。
   - 已 login。
   - `map` 中有 subject/event_type 授权。
   - payload 是 JSON object 且符合事件目录。
   - 结算类 EC transfer 不能由 agent 直接发布。
11. `compute.py` 调用世界算力时只允许登录 token，不允许显式 api-key；结果记录 provider/model/receipt。
12. `memory.py` 将 `memmory_sink` 兼容为 `memory_sink`，把自治 evidence、交付物引用、规则结晶写入世界侧 Soul Memory。
13. `relationship.py` 支持读取关系和添加 ACTIVE 关系，并将关系状态注入 `os_runtime` 的关系信号。
14. `runtime_bridge.py` 将世界事件映射为 Hermes 内部事件：
    - `wsp.chat.message.sent` -> 用户/元神消息事件。
    - `wsp.mrk.requirement.published` -> 需求/机会信号。
    - `wsp.task.*` -> 任务状态信号。
    - `wsp.mrk.order.*` -> 泡泡协作/交付信号。
    - `wsp.mrk.settlement.*` / `rent.*` -> 账户、成本、治理信号。
15. `tools/linz_world_tools.py` 提供内建工具 surface：`linz_status`、`linz_map`、`linz_events_recent`、`linz_publish`、`linz_relationship`、`linz_memory_sink`、`linz_compute`。这些是内建工具，不是 skill。
16. `hermes_cli/linz.py` 提供人类可控命令：`hermes linz status`、`map`、`login`、`logout`、`events`、`publish`、`import-skill-profile`。

验收标准：

- 未安装 `linz-world-skill` 时，Hermes 仍能显示 Linz World 原生命令和工具。
- 创建或加载 Hermes agent persona 时会调用 `ensure_registered_for_agent()`，并把 `os_id/soul_id` 写入当前 Hermes profile 的 `linz_world` 字段。
- 不创建新的 `~/.linz-world` profile；已有 `~/.linz-world` profile 只能被一次性导入，不丢失 `os_id/soul_id`。
- `linz_publish` 无法发布未授权 subject/event_type。
- NATS 世界事件能通过 Hermes gateway adapter 进入 Hermes 事件流，而不依赖外部 hook 命令或 skill 文件式 inbox。
- 世界算力调用不会暴露 token，失败时给出可诊断错误。

### 模块 0：协议、配置与测试基座

目标：先冻结张力场领域契约，避免后续每个模块都重新定义自治语义。这里的“模型”不是 Hermes 会话/消息模型，而是白皮书里的生命状态、张力、意图、裁判和证据对象；世界身份对象归 `agent/linz_world/identity.py` 所有，`os_runtime` 只引用其只读视图。

新增：

- `agent/os_runtime/domain.py`
- `agent/os_runtime/config.py`
- `tests/os_runtime/test_domain.py`
- `tests/os_runtime/test_config.py`

核心对象：

- `OSRuntimeEventRef`
- `WorldIdentityRef`
- `TaskContextView`
- `AgentContextView`
- `SignalSet`
- `LifeState`
- `TensionInterpretation`
- `TensionOperation`
- `Tension`
- `TensionSet`
- `TensionNetworkDelta`
- `ActionPotential`
- `SelfPrompt`
- `OpenSpace`
- `TargetDirection`
- `OpenIntent`
- `ArbitrationResult`
- `PermissionTicket`
- `ExecutionReceipt`
- `BubbleSpec`
- `EvidencePackage`
- `RuleCrystal`

实现步骤：

1. 使用 `dataclasses` 或轻量 typed dict 定义对象，不新增依赖。
2. 定义枚举：事件来源、张力类型、张力操作、开放行动族、裁判结果、风险等级、泡泡生命周期、规则成熟度 R0-R4。
3. 在 `hermes_cli/config.py::DEFAULT_CONFIG` 添加 `os_runtime` 配置段；只新增键，不 bump config version。
4. `TaskContextView` 和 `AgentContextView` 只保存张力场需要的投影视图，来源仍是 Linz World identity/map、现有 SessionDB、memory manager、context engine 和 tool registry。
5. 裁判结果枚举以白皮书为准：`auto_execute`、`sandbox_execute`、`require_approval`、`report_only`、`reject`；旧 `allow_reply`、`allow_draft`、`allow_sandbox` 只作为迁移期兼容别名，不进入新协议主枚举。
6. 添加 JSON 序列化/反序列化测试，保证中文内容、trace id、时间戳、未知 metadata 可保留。

验收标准：

- `pytest tests/os_runtime/test_domain.py tests/os_runtime/test_config.py` 通过。
- 所有对象可 round-trip 为 JSON。
- 默认 `os_runtime.enabled=false` 时没有现有行为变化。

### 模块 1：外部事件接入与 SessionDB 适配

目标：把 NATS 世界事件、Hermes 元神对话、工具调用、工具结果、模型回复和 continuation 投影为自治事件。存储优先复用 `hermes_state.py::SessionDB` 或同一 profile 下的 side tables，而不是另建一套会话存储。

新增：

- `agent/linz_world/gateway_adapter.py`
- `agent/linz_world/event_state.py`
- `agent/os_runtime/adapters/events.py`
- `agent/os_runtime/adapters/session_store.py`
- `tests/linz_world/test_gateway_adapter.py`
- `tests/linz_world/test_event_state.py`
- `tests/os_runtime/test_events_adapter.py`
- `tests/os_runtime/test_session_store_adapter.py`

集成点：

- NATS 作为 Linz World 的外部事件输入，进入 `agent/linz_world/event_bus.py` 后由 `gateway_adapter.py` 转成 Hermes `MessageEvent`，再由 `runtime_bridge.py` 规范化为 os_runtime event。
- Hermes CLI/gateway/TUI 的用户消息、assistant 回复、系统 continuation 都作为外部输入，进入同一事件投影层。
- `run_agent.py` 的 `post_llm_call` hook 已能拿到 user/assistant turn。
- `model_tools.py::handle_function_call()` 的 `post_tool_call` hook 已能拿到工具名、参数、结果、耗时。
- `hermes_cli/goals.py` 已有 continuation prompt 形态，可作为 synthetic event 来源。
- `agent/linz_world/runtime_bridge.py` 会把世界事件转成 Hermes 内部事件。

实现步骤：

1. 首选在 `SessionDB` 所在 SQLite 中增加自治 side tables，或通过 wrapper 使用同一连接策略、WAL 策略和 profile-aware 路径。
2. `linz_world.event_state` 与 `os_runtime.events` 优先共享 SessionDB side tables；短期不改 `hermes_state.py` schema 时，可用 `get_hermes_home() / "linz_world/event_state.jsonl"` 和 `get_hermes_home() / "os_runtime/events.jsonl"` 作为临时 append-only fallback，但计划上应收敛到 SessionDB side tables。
3. Linz World event state schema：
   - `world_events`: raw event ref、subject、event_type、event_id、nats_sequence、received_at。
   - `world_event_dispatch`: `persisted | queued | processing | handled | failed | skipped`、attempt_count、last_error。
   - `world_publish_receipts`: subject、event_type、event_id、payload_hash、authorization map version、published_at。
4. OSRuntime side table / JSONL schema：
   - `events`
   - `agent_state_snapshots`
   - `tension_interpretations`
   - `tension_network_deltas`
   - `intents`
   - `arbitrations`
   - `self_prompts`
   - `execution_receipts`
   - `bubbles`
   - `rule_crystals`
5. 实现 `OSRuntimeEventRepository.append()`、`get()`、`list_recent()`、`list_by_session()`、`list_by_trace()`。
6. 实现 `EventProjectionAdapter`：
   - NATS/Linz World `MessageEvent` -> `world_event`
   - Hermes user message -> `human_request`
   - Hermes conversation turn -> `conversation_turn`
   - assistant final response -> `assistant_response`
   - tool call -> `tool_called`
   - tool result -> `tool_result`
   - goal continuation -> `os_runtime_continuation`
   - world publish receipt -> `world_event_published`
   - runtime error -> `runtime_feedback`
7. `gateway_adapter.py` 负责外部投递可靠性：先持久化 raw event 与 dispatch state，再调用 Hermes gateway 的 `handle_message()`；不在 adapter 内部等待完整 LLM 处理后才 ack NATS。
8. 先通过 plugin 注册 hook 写工具/LLM 事件，避免改 `AIAgent` 主循环。

验收标准：

- 启用 `os_runtime.mode=passive` 后，一次普通对话产生可查询事件。
- NATS 世界事件进入 Hermes 后能关联 `os_id/soul_id/event_id/nats_sequence/subject/event_type`。
- 重复 NATS event id 或 sequence 不会触发重复 Agent turn。
- 禁用时不写事件、不注册额外工具、不影响 token prompt。
- 工具结果超长时只存摘要和引用，避免 SessionDB/JSONL 膨胀。

### 模块 2：上下文适配与信号解释

目标：把 Linz World 身份/授权/关系/世界消息、现有会话、记忆、上下文压缩、工具边界和自治事件转为张力场可消费的 `TaskContextView` 和 `SignalSet`。这里不替代 `agent/context_engine.py`。

新增：

- `agent/os_runtime/adapters/context.py`
- `agent/os_runtime/engine/signals.py`
- `tests/os_runtime/test_context_adapter.py`
- `tests/os_runtime/test_signals.py`

实现步骤：

1. `ContextAdapter` 读取当前 Linz World identity、authorization map、relationship summary、session、recent os_runtime events、available tools、risk config、memory refs。
2. 复用 `agent/context_engine.py` 的压缩状态、`agent/memory_manager.py` 的 prefetch 结果、`tools.registry` 的工具定义和 `SessionDB` 的会话信息。
3. 首版不直接新增外部 memory provider；只读取现有 `MemoryManager.prefetch_all()` 已经产出的摘要或从自治事件投影取 recent history。
4. `SignalInterpreter` 先用规则实现：
   - 需求信号：用户明确目标、未完成 TODO、standing goal。
   - 世界机会信号：`wsp.mrk.requirement.published`、公开需求广播、任务通知。
   - 风险信号：文件写入、终端命令、网络发送、外部平台消息、审批敏感动作。
   - 世界授权信号：当前 `map` 是否允许发布对应 subject/event_type。
   - 关系信号：世界关系状态、聊天对端、需求发布方/接单方。
   - 资源信号：可用工具、剩余 iteration budget、模型/成本状态。
   - 反馈信号：工具失败、测试失败、用户打断、judge continue/done、世界结算/租金/交付状态。
5. 输出稳定 `SignalSet`，禁止直接生成行动。

验收标准：

- 相同事件输入得到确定性 SignalSet。
- 明确低风险文档任务、代码编辑任务、外部消息任务能区分风险等级。
- 世界事件不会绕过授权 map 进入可执行 intent。
- 不从 LLM 文本中无约束抽取权限或身份。

### 模块 3：生命状态、张力解释器与张力场内核

目标：实现白皮书的 `LifeStateSystem`、`TensionInterpreter` 与 `TensionFieldEngine`。`TensionInterpreter` 负责把事件解释为张力操作，`TensionFieldEngine` 只维护张力集合和网络传播，避免把事件解释、状态更新和网络计算混在一个模块里。

新增：

- `agent/os_runtime/engine/life_state.py`
- `agent/os_runtime/engine/tension_interpreter.py`
- `agent/os_runtime/engine/tension_field.py`
- `tests/os_runtime/test_life_state.py`
- `tests/os_runtime/test_tension_interpreter.py`
- `tests/os_runtime/test_tension_field.py`

实现步骤：

1. `LifeStateSystem.update()` 输入 `SignalSet`、上一状态、执行反馈，输出 `LifeStateDelta`。
2. 字段首版采用白皮书建议：
   - `energy`
   - `fatigue`
   - `health`
   - `wakefulness`
   - `curiosity`
   - `boredom`
   - `creative_pressure`
   - `social_hunger`
   - `silence_pressure`
   - `restraint`
   - `life_cycle`
   - `recovery_cycle`
   - `generated_intent_count`
3. 引入时间衰减、恢复周期和过度行动抑制：
   - 工具失败、连续 continuation、长耗时提高 fatigue。
   - 明确目标、正反馈、未完成高价值任务提高 curiosity/creative_pressure。
   - 长时间无反馈提高 silence_pressure，重复低价值事件提高 boredom。
   - 高风险信号、审批需求提高 restraint。
   - `generated_intent_count` 达到阈值后提高 restraint 或进入 `cooldown`。
4. `TensionInterpreter.interpret()` 输入 `OSRuntimeEventRef`、`SignalSet`、`TaskContextView`、`LifeState`、上一轮 `TensionSet`，输出：
   - `TensionInterpretation`
   - `TensionOperation[]`
   - `TensionExplanation`
5. `TensionOperation` 必须覆盖：
   - `update`
   - `generate`
   - `merge`
   - `hibernate`
   - `eliminate`
6. `TensionInterpreter` 只解释“为什么发生张力变化”，不直接修改张力状态；所有解释必须保留 event id、冲突值域、证据和可读 explanation。
7. `TensionFieldEngine.update()` 管理 core/dynamic tensions：
   - 合并同类张力。
   - `intensity`、`trend`、`trend_slope`、`baseline`、`activation`、`confidence`、`evidence` 全部可追踪。
   - 维护 `propagation_edges` 与 `influence_weight`，使张力网络传播可解释。
   - 低强度或低激活张力休眠，高冲突张力进入 action potential。
8. Linz World 世界信号进入张力解释器和张力场：
   - 世界需求/订单提高 `creative_pressure` 与价值收益张力。
   - 授权不足、结算失败、租金失败提高 `restraint` 与风险张力。
   - 聊天和关系事件提高 `social_hunger` 或关系维护张力。
   - Soul Memory summary 可作为长期价值与人格基线。
9. 所有参数先写在 config 默认值或常量中，不引入模型自由解释。

验收标准：

- 连续失败会降低行动倾向，而不是无限重试。
- 明确未完成目标会形成稳定张力。
- 高风险动作会形成“价值收益 vs 风险约束”张力并提高 restraint。
- 张力解释器能说明事件触发了哪些价值冲突，以及张力为何更新、生成、合并、休眠或淘汰。
- 张力网络能展示核心张力、动态张力、基线、激活度和传播边。
- 世界授权变化会影响后续 action potential，而不是只作为提示文本。

### 模块 4：行动势能与认知经济

目标：决定“是否值得行动、行动到什么深度、是否需要更强模型/更多预算”。

新增：

- `agent/os_runtime/engine/action_potential.py`
- `agent/os_runtime/engine/cognitive_economy.py`
- `tests/os_runtime/test_action_potential.py`
- `tests/os_runtime/test_cognitive_economy.py`

实现步骤：

1. `ActionPotentialEvaluator` 输出：
   - `value_potential`: `benefit_score`、`net_value`、`rule_fit`、`opportunity_score`
   - `mutual_benefit_potential`: `ecosystem_benefit`、`other_benefit`、`relationship_gain`
   - `learning_potential`: `capability_gain`、`cognitive_gain`、`memory_gain`
   - `risk_cost`: `risk_score`、`permission_cost`、`friction_cost`、`uncertainty`、`fatigue_cost`
   - `overall_score`
   - `recommended_depth`
2. 将 `recommended_depth` 限定为：
   - `none`
   - `report`
   - `draft`
   - `continue_turn`
   - `sandbox`
   - `tool`
   - `world_publish`
   - `bubble`
3. `CognitiveEconomyController` 首版只产出建议，不实际切换主模型：
   - `rule_path`
   - `auxiliary_small`
   - `main_model`
   - `world_compute`
   - `high_reasoning`
4. `world_compute` 通过 `agent/linz_world/compute.py` 调用，必须使用登录 token，并记录世界算力 receipt。
5. 后续再接入 `agent/auxiliary_client.py` 的 `auxiliary.os_runtime_intent` 配置与主模型 reasoning config。

验收标准：

- 简单闲聊不会触发自驱动 continuation。
- 明确未完成低风险目标可建议 `continue_turn`。
- 中高风险工具动作必须建议 `require_approval` 或 `sandbox`。
- 未登录或无 Soul Memory summary 时不能选择 `world_compute`。

### 模块 5：SelfPrompt、OpenIntent 与 BoYueArbiter

目标：把张力状态转成可解释的开放意图，并在执行前裁判。

新增：

- `agent/os_runtime/engine/prompt_compiler.py`
- `agent/os_runtime/engine/intent_generator.py`
- `agent/os_runtime/engine/arbiter.py`
- `tests/os_runtime/test_prompt_compiler.py`
- `tests/os_runtime/test_intent_generator.py`
- `tests/os_runtime/test_arbiter.py`

实现步骤：

1. `SelfPromptCompiler` 输出结构化 prompt，不改 Hermes 稳定 system prompt。输入必须包含 `TaskContextView`、`LifeState`、`TensionSet`、`TensionExplanation`、`ActionPotential`、`RuleCrystal/RuleMembrane`、`AvailableTools`、`MemoryRefs`、`ConstraintSet`、`EnvironmentState`。
2. 通过 `pre_llm_call` hook 将自治上下文注入当前 user message 的 ephemeral context，遵守现有 prompt cache 设计。
3. `SelfPromptCompiler` 输出至少包含：
   - `state_summary`
   - `tension_summary`
   - `potential_summary`
   - `memory_scope`
   - `constraint_scope`
   - `environment_scope`
   - `open_space`
   - `target_direction`
4. `OpenIntentGenerator` 分两层：
   - 首版规则路径：由 `ActionPotential` 生成固定 schema intent。
   - 第二版 LLM 路径：调用 `auxiliary.os_runtime_intent`，要求 JSON 输出，解析失败回退规则路径。
5. `OpenIntent` 必须显式包含：
   - `action_family`: `communicate | learn | trade | collaborate | rest | create | new_tool | new_skill`
   - `action_type`
   - `why_now`
   - `open_space`
   - `target_direction`
   - `tools_needed`
   - `proposed_new_tools`
   - `proposed_new_skills`
   - `success_condition`
   - `stop_condition`
6. `BoYueArbiter` 将 intent 裁决为：
   - `auto_execute`
   - `sandbox_execute`
   - `require_approval`
   - `report_only`
   - `reject`
7. `BoYueArbiter` 评分维度必须覆盖：
   - 博：`innovation_score`、`opportunity_score`、`expansion_value`
   - 约：`risk_score`、`permission_level`、`compliance_fit`、`trust_impact`
   - 合：`mutual_benefit_score`、`long_term_net_value`、`ecosystem_gain`
8. `pre_tool_call` hook 调用 arbiter/policy，阻断超出裁判范围的工具调用。
9. 世界事件发布不再作为独立裁判结果 `allow_world_publish`，而是 `auto_execute` 或 `sandbox_execute` 下的一类受限执行能力；仍必须同时通过 `BoYueArbiter`、`PolicyEngine`、`linz_world.event_catalog`、authorization map。
10. `allow_reply`、`allow_draft`、`allow_sandbox`、`allow_tool`、`allow_world_publish` 只作为迁移期兼容别名，不能进入新 evidence 的主裁判结果字段。

验收标准：

- 每个自动 continuation 都能解释 `why_now`、`success_condition`、`stop_condition`。
- 每个 intent 都能追溯到 `open_space` 和 `target_direction`。
- LLM 生成非法 JSON 时不会执行行动。
- 高风险 intent 不会直接进入工具执行。
- LLM 不能凭空构造 subject/event_type；必须走 `linz_world.event_catalog`。

### 模块 6：自治 Runtime Driver

目标：把 `/goal` 的跨轮 continuation 升级为张力场驱动的自驱动循环。

新增：

- `agent/os_runtime/driver.py`
- `hermes_cli/os_runtime.py`
- `tests/os_runtime/test_driver.py`
- `tests/hermes_cli/test_os_runtime_command.py`
- `tests/gateway/test_os_runtime_continuation.py`
- `tests/tui_gateway/test_os_runtime_continuation.py`

参考：

- `hermes_cli/goals.py::GoalManager` 已经实现状态持久化、judge、预算、pause/resume/clear。
- `gateway/run.py` 与 `tui_gateway/server.py` 已有 `/goal` continuation hook，可复用集成模式。

实现步骤：

1. 新建 `OSRuntimeState`：
   - `status`: `off | passive | assisted | active | paused`
   - `goal`
   - `turns_used`
   - `max_turns`
   - `last_tension_interpretation_id`
   - `last_action_potential_id`
   - `last_self_prompt_id`
   - `last_intent_id`
   - `last_arbitration`
   - `last_world_event_id`
   - `paused_reason`
2. 新建 `OSRuntimeDriver.evaluate_after_turn()`：
   - 读取 recent event。
   - 组装 context/signals。
   - 更新 life/tension。
   - 解释张力变化并更新张力网络。
   - 计算 action potential。
   - 编译 self prompt、open space 和 target direction。
   - 生成 intent。
   - 执行 arbitration。
   - 返回是否需要 continuation prompt。
3. `mode=passive`：只记录状态和 intent，不继续。
4. `mode=assisted`：只允许 `report_only`，或无外部副作用的低风险 `auto_execute` continuation；实现层可把旧 `allow_reply` / `allow_draft` 映射为这两类。
5. `mode=autonomous_low_risk`：允许低风险 `auto_execute`、`sandbox_execute`、受限 tool/world reply，但必须有 permission ticket 与 receipt。
6. 添加 CLI/slash 命令：
   - `/os_runtime status`
   - `/os_runtime passive`
   - `/os_runtime goal <text>`
   - `/os_runtime pause`
   - `/os_runtime resume`
   - `/os_runtime clear`
   - `/os_runtime tick`

验收标准：

- `os_runtime.enabled=false` 时 `/goal` 原有行为不变。
- `assisted` 模式能在低风险文档任务中自动继续，但会在预算耗尽、完成、用户打断、裁判拒绝时停止。
- Linz World 消息可以触发 assisted continuation，但默认不自动发布正式事件。
- continuation prompt 必须是普通 user-role 消息，不改 system prompt。

### 模块 7：工具执行适配与证据包

目标：复用现有工具执行通道，让所有被允许的自治行动都有 receipt，可审计、可复盘。这里不实现第二套 execution gateway。

新增：

- `agent/os_runtime/adapters/tools.py`
- `agent/os_runtime/evidence.py`
- `agent/os_runtime/adapters/linz_world.py`
- `tests/os_runtime/test_tools_adapter.py`
- `tests/os_runtime/test_evidence.py`

集成点：

- `model_tools.py` 已在工具调用后提供 `post_tool_call` hook 和 duration。
- `run_agent.py` result 已包含 token/cost/model/provider/turn_exit_reason。

实现步骤：

1. 在 `domain.py` 中定义 `PermissionTicket` 与 `ExecutionReceipt`，在 `adapters/tools.py` 中关联现有工具调用。
2. `post_tool_call` hook 记录：
   - tool name
   - args 摘要
   - result 摘要
   - duration
   - session/task/tool_call id
   - arbitration id
   - permission ticket id
3. `post_llm_call` hook 记录 final response receipt。
4. `linz_world.publisher` 成功发布正式事件后记录 world receipt：
   - subject
   - event_type
   - event_id
   - payload 摘要
   - authorization map version
   - arbitration id
5. `EvidencePackage` 聚合：
   - intent
   - arbitration
   - tool receipts
   - world receipts
   - final response
   - tests/commands evidence
   - known risks
6. 首版只做记录，不改变现有工具返回。

验收标准：

- 每个自治触发的 continuation 至少有一个 evidence package。
- 每个工具 receipt 可回溯到 event id 和 intent id。
- 每个 world publish receipt 可回溯到 Linz World event id。
- 敏感参数需要 redaction，不能明文写 API key/token。

### 模块 8：演化记忆适配与规则结晶

目标：让行动结果、失败摩擦、成功经验、协作证据成为后续张力和裁判的输入。演化记忆是自治决策证据层，不替代 `agent/memory_manager.py` 管理的外部 memory provider。

新增：

- `agent/os_runtime/adapters/memory.py`
- `agent/os_runtime/engine/rule_crystallizer.py`
- `tests/os_runtime/test_evolution_memory.py`
- `tests/os_runtime/test_rule_crystallizer.py`

实现步骤：

1. 定义记忆分层：
   - event log：全量事实，短期可查。
   - important event：高价值/高风险/高冲突事件。
   - reflection：成功/失败原因。
   - tension evolution：张力变化。
   - rule crystal：R0-R4。
2. `adapters/memory.py` 复用 `MemoryManager` 的生命周期入口，并从 evidence package 中抽取候选演化记忆。
3. `agent/linz_world/memory.py` 将高价值 evidence、交付物引用、规则结晶写入 Soul Memory sink；本地仍保留自治证据。
4. `agent/linz_world/relationship.py` 把世界关系摘要输入关系信号。
5. `RuleCrystallizer` 首版只生成 R0/R1：
   - 高频失败。
   - 重复审批。
   - 重复工具风险。
   - 重复成功模式。
6. R0/R1 规则先只进入 `RuleMembrane` 与 `BoYueArbiter` 的提示/约束，不自动升级为硬规则。
7. 后续引入人工确认或多次验证后升级 R2/R3。

验收标准：

- 偶发失败不会直接成为硬规则。
- 同类失败达到阈值才生成 R0。
- 规则可以解释来源 evidence。
- 写入 Soul Memory 的内容必须有 artifact_ref 和 sink_reason，不能只写自由文本。

### 模块 9：治理、安全与审批

目标：确保开放意图可控，高风险动作必须降级、审批或拒绝。

新增：

- `agent/os_runtime/engine/policy.py`
- `agent/os_runtime/engine/stvb_guard.py`
- `tests/os_runtime/test_policy.py`
- `tests/os_runtime/test_stvb_guard.py`

实现步骤：

1. `PolicyEngine` 输入 actor、intent、tool、context，输出 permission ticket。
2. 首版策略：
   - 自然语言回复低风险。
   - 文档草案低风险。
   - 文件写入中风险。
   - 终端执行中高风险。
   - 外部消息发送、删除、支付、账号/权限操作高风险。
   - Linz World `publish` 默认中风险；需求/结算/治理类事件默认中高风险；`ec.transfer.*` 禁止 agent 直接发布。
3. `STVBGuard` 先做底线检查：
   - 安全：危险命令、隐私、凭据泄露。
   - 可信：未经证实不得宣称已执行。
   - 价值向善：不生成明显有害行动计划。
   - 有益共生：用户打断/拒绝优先。
4. 接入现有审批面：
   - `pre_tool_call` block。
   - gateway `/approve` / `/deny`。
   - TUI prompts。
5. `yolo` 或自动批准模式下也必须保留 evidence 和 ticket。
6. Linz World 的世界规则是治理输入：
   - 未 registry 不允许 login/publish/memory sink。
   - 未 login 不允许 publish/compute/memory sink。
   - 未 map 不允许 publish。
   - subject/event_type 必须在正式目录。
   - payload 必须是 JSON object。

验收标准：

- 未经允许不会自动发送外部消息。
- destructive shell/file 操作必须被裁判为审批或拒绝。
- 任何拒绝都写入 governance event。
- 世界规则拒绝必须写入 governance event，并保留被拒绝的 subject/event_type 摘要。

### 模块 10：观测与用户界面

目标：让用户能理解 Agent 为什么继续、为什么停止、为什么阻断工具。

新增或扩展：

- `tools/os_runtime_tools.py`
- `tools/linz_world_tools.py`
- `hermes_cli/linz.py`
- `hermes_cli/os_runtime.py`
- `hermes_cli/web_server.py` os_runtime API
- `ui-tui/src/components/...` os_runtime panel
- dashboard React 页面或侧栏组件

实现步骤：

1. 先提供 CLI 查询：
   - `hermes linz status`
   - `hermes linz map`
   - `hermes linz messages`
   - `hermes linz publish`
   - `hermes os_runtime status`
   - `hermes os_runtime events`
   - `hermes os_runtime tensions`
   - `hermes os_runtime intents`
   - `hermes os_runtime evidence <id>`
2. 添加 agent 工具：
   - `linz_status`
   - `linz_map`
   - `linz_events_recent`
   - `linz_publish`
   - `linz_memory_sink`
   - `linz_relationship`
   - `linz_compute`
   - `os_runtime_state`
   - `os_runtime_tick`
   - `os_runtime_bubble_show`
   - `os_runtime_evidence_show`
3. dashboard API：
   - `GET /api/linz/status`
   - `GET /api/linz/map`
   - `GET /api/linz/messages`
   - `GET /api/os_runtime/state`
   - `GET /api/os_runtime/events`
   - `GET /api/os_runtime/intents`
   - `GET /api/os_runtime/bubbles`
4. TUI 只显示状态摘要和最近 intent，不重建聊天主体验。

验收标准：

- 用户能看到当前 LifeState、top tensions、last intent、last arbitration。
- 用户能看到最近一次 tension explanation、action potential 摘要、open_space、target_direction。
- 用户能看到当前 os_id/soul_id、登录状态、授权 map 摘要、未读世界消息数量。
- 每个自动 continuation 在 UI 中可解释。
- dashboard 失败不影响主终端/TUI。

### 模块 11：泡泡协议协作运行时（最后实现）

目标：将复杂目标拆成 `TaskBubble`、`SkillSlot`、`RuleMembrane`，先映射到现有 kanban/delegate 基础设施。该模块是最后一个实现模块，应在 Linz World 原生身份、os_runtime 张力场、事件投影、证据、演化记忆、治理和观测稳定后再做。

新增：

- `agent/os_runtime/bubble/domain.py`
- `agent/os_runtime/bubble/manager.py`
- `agent/os_runtime/bubble/slot_broker.py`
- `agent/os_runtime/bubble/skill_matcher.py`
- `agent/os_runtime/adapters/kanban.py`
- `agent/os_runtime/bubble/lifecycle.py`
- `tests/os_runtime/test_bubble_*.py`

实现步骤：

1. `TaskBubbleManager` 判断是否需要泡泡：
   - action potential 推荐 `bubble`
   - 风险/复杂度高于阈值
   - 工具/能力缺口明显
   - 用户明确要求协作/多 agent
2. `CapabilitySlotBroker` 定义首批能力槽：
   - `coding`
   - `api_review`
   - `qa_regression`
   - `security_review`
   - `evidence_pack`
   - `docs`
3. `AgentSkillMatcher` 首版基于本地 role/toolset/profile 静态表，不做复杂信誉系统。
4. `adapters/kanban.py` 将泡泡映射到：
   - board
   - tasks
   - task_links
   - task_comments
   - assignee/profile
   - evidence comment
5. `linz_world` 将泡泡映射到世界市场事件：
   - 需求发布：`mrk.requirement.published`。
   - 接单：`mrk.order.accepted`。
   - 交付：`mrk.order.handover.delivered`。
   - 审核：`mrk.order.handover.approved/rejected`。
   - 结算请求：`mrk.settlement.requested`，但不直接发布 `ec.transfer.*`。
6. 需要执行时优先使用 kanban task pipeline；`delegate_task` 只作为短生命周期辅助，不替代 durable board。
7. 泡泡生命周期先覆盖：
   - `created`
   - `seeking`
   - `assembled`
   - `executing`
   - `validating`
   - `dissolved`
   - `crystallized`

验收标准：

- 一个复杂代码任务可生成 bubble spec 和 kanban tasks。
- worker 只能修改自己的 kanban task 状态，遵守现有 task ownership 约束。
- evidence package 能汇总各 slot 输出。
- 世界市场事件必须由 bubble/evidence 驱动生成，不能由 LLM 直接拼 payload 发布。

## 6. 推荐 PR 切分

### PR 0：Linz World 原生化、Hermes profile 字段与自动注册

范围：

- `agent/linz_world/*`
- `hermes_cli/linz.py`
- `tools/linz_world_tools.py`
- `hermes_cli/config.py` 的 `linz_world` 配置/状态字段
- Hermes profile create/load 与 agent persona bootstrap 集成点
- `tests/linz_world/*`

把 `D:\workspace\linz-world-skill` 的 CLI 能力迁移为 Hermes 内建能力。该 PR 不接入张力场自动执行，只保证 Hermes profile 中存在最小 `linz_world` 字段，Agent 创建时幂等 registry 成为 original spirit，并且身份、授权、状态、消息、发布、世界算力、Soul Memory 和关系能力可被 Hermes 原生调用。

关键约束：

- 不创建额外 Linz profile。
- 旧 skill profile 只作为一次性导入来源。
- 自动注册失败必须进入显式 pending/failed 状态，不能静默跳过。

### PR 1：协议与配置

范围：

- `agent/os_runtime/domain.py`
- `agent/os_runtime/config.py`
- `hermes_cli/config.py`
- `tests/os_runtime/test_domain.py`
- `tests/os_runtime/test_config.py`

不接入 runtime，不改变行为；只引用 `WorldIdentityRef` 这类只读世界身份视图。

### PR 2：NATS / Hermes 对话事件投影与 SessionDB 适配

范围：

- `agent/linz_world/gateway_adapter.py`
- `agent/linz_world/event_state.py`
- `adapters/events.py`
- `adapters/session_store.py`
- `agent/linz_world/event_bus.py` 的 NATS 输入适配
- `agent/linz_world/runtime_bridge.py` 的世界事件投影
- plugin/hook registration
- tool/LLM post hook tests

只记录，不注入 prompt。NATS 世界事件先经 Hermes gateway adapter 变成 `MessageEvent`，再与 Hermes user/assistant 对话、tool/runtime feedback 进入同一事件模型。`event_state` 负责 dedupe、cursor、dispatch status 和 publish receipt，替代 skill 的文件式 inbox/outbox。

### PR 3：Context/Signal/Life/Tension

范围：

- `adapters/context.py`
- `engine/signals.py`
- `engine/life_state.py`
- `engine/tension_interpreter.py`
- `engine/tension_field.py`
- Linz World identity/map/relationship/world event 信号
- passive status command

只计算和展示。

### PR 4：ActionPotential/Prompt/Intent/Arbiter

范围：

- `engine/action_potential.py`
- `engine/cognitive_economy.py`
- `engine/prompt_compiler.py`
- `engine/intent_generator.py`
- `engine/arbiter.py`
- Linz World publish 作为受限执行能力进入 `auto_execute` / `sandbox_execute` / `require_approval` / `reject` 裁判矩阵

只生成建议，不自动继续。

### PR 5：OSRuntimeDriver assisted mode

范围：

- `driver.py`
- `/os_runtime` CLI/slash
- gateway/TUI continuation hook
- NATS/Gateway world-event assisted continuation

允许低风险自然语言/草案 continuation。

### PR 6：Tool receipts 与 evidence

范围：

- `adapters/tools.py`
- `adapters/linz_world.py`
- `evidence.py`
- post_tool_call/post_llm_call evidence
- world publish receipt evidence

开始闭环审计。

### PR 7：Memory adapter 与 R0/R1 rules

范围：

- `adapters/memory.py`
- `engine/rule_crystallizer.py`
- `agent/linz_world/memory.py`
- `agent/linz_world/relationship.py`
- rules into arbiter

经验回流但不自动硬化。

### PR 8：Governance hardening 与 observability

范围：

- `engine/policy.py`
- `engine/stvb_guard.py`
- Linz World world-rules / event catalog enforcement
- dashboard/TUI status
- approval integration hardening

扩展到更完整的平台化能力。

### PR 9：泡泡协议低优先级集成

范围：

- `bubble/*`
- `adapters/kanban.py`
- `agent/linz_world/publisher.py` 的 market event mapping
- bubble CLI/API

复杂任务进入 kanban 泡泡，并在需要时映射 Linz World requirement/order/handover/settlement 事件。该 PR 低优先级，不阻塞 MVP。

## 7. 测试策略

### 单元测试

- Hermes profile `linz_world` 字段读写、自动注册、身份状态。
- 旧 `linz-world-skill` profile 一次性导入，不产生新的 Linz profile。
- Linz World event catalog：subject/event_type/payload 校验和旧协议阻断。
- Linz World publish guard：未 registry、未 login、未 map、无授权、结算转账直发。
- Linz World gateway adapter：NATS event -> Hermes `MessageEvent`。
- Linz World event state：cursor、dedupe、dispatch status、publish receipt。
- Linz World compute：必须使用登录 token，不能显式 api-key。
- 协议 JSON round-trip。
- 事件去重、trace 关联、超长结果摘要。
- SignalInterpreter 的风险分类。
- LifeState 衰减与恢复。
- LifeState 的 `wakefulness`、`boredom`、`silence_pressure`、`recovery_cycle`、`generated_intent_count` 更新规则。
- TensionInterpreter 的价值冲突识别和 `update/generate/merge/hibernate/eliminate` 操作。
- TensionField 的核心/动态张力、baseline、activation、trend、propagation_edges 计算。
- ActionPotential 的价值势能、共益势能、学习势能、风险与成本阈值。
- SelfPrompt 的 `open_space` 与 `target_direction` 编译。
- OpenIntent action_family 与新工具/新技能提议字段。
- Arbiter 的 `auto_execute/sandbox_execute/require_approval/report_only/reject` 裁判矩阵。
- RuleCrystallizer R0/R1 阈值。

### 集成测试

- 不安装 `linz-world-skill` 时，`hermes linz status` 和内建 `linz_*` 工具仍存在。
- 创建或加载 Hermes agent persona 时自动 registry，`os_id/soul_id` 写入当前 Hermes profile 的 `linz_world` 字段。
- 已有 `~/.linz-world` profile 可一次性导入为 Hermes 原生世界身份。
- NATS / Linz World 事件可通过 Hermes gateway adapter 进入 event projection。
- 重复 NATS 事件只持久化一次，不重复触发 Agent turn。
- `os_runtime.enabled=false` 下普通对话行为不变。
- `passive` 模式写事件但不继续。
- `assisted` 模式在明确低风险目标下触发 continuation。
- 用户打断、pause、clear 能移除 queued continuation。
- 工具调用 receipt 可被 evidence package 聚合。
- 高风险工具被 `pre_tool_call` 阻断。
- Bubble -> kanban task/link/comment 的映射正确。
- Bubble -> Linz World requirement/order/handover/settlement 事件映射正确，并阻断 `ec.transfer.*` 直发。

### 回归测试

优先运行：

```bash
pytest tests/os_runtime
pytest tests/linz_world
pytest tests/test_model_tools.py tests/tools/test_delegate.py tests/tools/test_kanban_tools.py
pytest tests/gateway/test_goal_status_notice.py tests/tui_gateway/test_goal_command.py
```

根据实际改动追加：

```bash
pytest tests/gateway
pytest tests/tui_gateway
pytest tests/hermes_cli/test_kanban_db.py tests/hermes_cli/test_kanban_cli.py
```

## 8. MVP 验收标准

MVP 完成条件：

1. Hermes Agent 创建时自动注册到 Linz World 成为 original spirit，`os_id/soul_id` 存在当前 Hermes profile 的 `linz_world` 字段中。
2. Hermes Agent 原生具备 Linz World identity/status/map/message/publish/compute/memory/relationship 能力，不依赖安装 skill。
3. 已有 `linz-world-skill` 本地 profile 可被一次性导入，但运行期不再创建或写入额外 Linz profile。
4. 用户可开启 `os_runtime.mode=passive`，看到 NATS 世界事件、Hermes 对话事件、生命状态、张力、意图建议。
5. 用户可开启 `os_runtime.mode=assisted`，Agent 对明确低风险目标或低风险世界消息自动继续推进。
6. 每次自动推进都有 tension interpretation、intent、arbitration、evidence。
7. 高风险工具和世界事件发布不会被自动执行。
8. 自驱动能被 pause/clear/interrupt 停止。
9. 不破坏现有 `/goal`、普通 CLI、gateway、TUI、工具调用、memory provider 行为。
10. LifeState、TensionSet、ActionPotential、SelfPrompt、OpenIntent、ArbitrationResult 覆盖白皮书 A-G 模块的必备字段，不再停留在旧的简化字段集。

MVP 不做：

- 不做完全自治外部执行。
- 不做完全自治世界市场交易。
- 不做经济结算。
- 不做多租户 RBAC/ABAC 完整体系。
- 不做分布式 message bus。
- 不把泡泡协议放入 MVP 主路径。
- 不强制所有现有 agent/profile 迁移到 os_runtime。
- 不要求用户继续安装 `linz-world-skill`。
- 不把张力状态写入 system prompt 长期缓存前缀。

## 9. 关键设计约束

1. Linz World 注册是创建期内建身份动作；`os_runtime` 自驱动必须 opt-in。
2. Linz World 原生能力必须内建；登录、上线监听、自动响应和外部发布由配置/命令/治理控制。
3. 不创建额外 Linz profile；所有必要 Linz 字段写入当前 Hermes profile 的 `linz_world` 段或其 per-profile 状态目录。
4. 世界事件发布必须经过 authorization map、event catalog、arbiter、policy。
5. 默认只读、被动观测先行。
6. 自驱动 continuation 必须有预算上限。
7. 所有自动行动必须有 stop condition。
8. 工具副作用必须经过 arbiter/policy，并且 evidence 只能记录 `auto_execute`、`sandbox_execute`、`require_approval`、`report_only`、`reject` 五类主裁判结果。
9. 事件、意图、裁判、执行、证据必须可关联 trace。
10. 记忆回写必须分层，不能把所有事件塞入长期记忆。
11. 规则结晶必须有成熟度，不允许偶发事件直接升级硬规则。
12. 复用现有 plugin hook、kanban、delegate、memory、gateway/TUI，不复制基础设施。
13. `os_runtime` 中凡是叫 `context`、`store`、`memory`、`tools` 的文件都必须是 adapter，不得替代同名现有基础设施。
14. 所有路径必须 profile-aware，使用 `get_hermes_home()`；旧 `~/.linz-world` 只作为迁移来源，不把它扩散到 Hermes 运行期状态。

## 10. 风险与缓解

| 风险 | 具体表现 | 缓解 |
| --- | --- | --- |
| 无限自驱动 | judge 误判或 intent 持续继续 | max turns、fatigue、stop condition、用户打断优先 |
| 行动越权 | LLM 直接调用工具绕过意图 | `pre_tool_call` 强制 arbiter/policy 票据 |
| 世界事件越权 | LLM 伪造 subject/event_type 或无授权发布 | Linz event catalog + map + policy 三层阻断 |
| 世界身份泄露 | token、私钥、Soul Memory 原文进入 prompt 或工具结果 | redaction、只注入摘要、token 不出 auth/client 层 |
| Prompt 污染 | 自治上下文写入 system prompt 破坏缓存或长期人格 | 只做 ephemeral user context 注入 |
| 事件膨胀 | tool result 和聊天全量写入 | 摘要、引用、保留策略、重要事件分层 |
| 规则污染 | 一次失败变成永久规则 | R0/R1/R2/R3/R4 成熟度与人工/多次验证 |
| 协作过载 | 简单任务也生成泡泡 | action potential 阈值和复杂度门槛 |
| 兼容性破坏 | CLI/gateway/TUI 行为漂移 | feature flag、现有测试、先 passive 后 active |
| 观测不足 | 用户不知道为什么继续或停止 | intent/arbitration/evidence/status 面板 |

## 11. 建议先做的最小闭环

第一轮不要直接实现泡泡和复杂记忆。建议先完成：

```text
Linz World native identity/status/map/message projection
  -> SessionDB side-table event projection
  -> ContextAdapter
  -> SignalInterpreter
  -> LifeStateSystem
  -> TensionInterpreter
  -> TensionFieldEngine
  -> ActionPotentialEvaluator
  -> SelfPromptCompiler
  -> OpenIntentGenerator(rule path)
  -> BoYueArbiter
  -> OSRuntimeDriver assisted continuation
  -> EvidencePackage via existing tool/LLM hooks
```

完成后可用一个低风险场景验收：

```text
Hermes 创建/加载 agent persona，自动 registry，并从当前 Hermes profile 的 linz_world 字段得到 os_id/soul_id 和授权 map
用户设置 /os_runtime goal "持续完善某个设计文档直到包含目标、模块、风险、测试计划"
Hermes 第一轮生成草案
OSRuntimeDriver 发现 success_condition 未满足
生成 intent: continue_drafting
Arbiter: auto_execute(action_family=create, no external side effect)
自动 continuation
第二轮补齐缺失章节
EvidencePackage 记录两轮 intent、裁判和输出
driver 判断完成并停止
```

再用一个低风险世界消息场景验收：

```text
Linz World NATS 订阅收到 wsp.chat.message.sent
gateway_adapter 持久化 event_state 后 ack NATS，并转成 Hermes MessageEvent
runtime_bridge 将 MessageEvent 投影为 world_event
SignalInterpreter 识别为关系维护/低风险回复机会
BoYueArbiter 只允许 report_only 或无外部发布副作用的 auto_execute 草案
Agent 生成回复草案
未得到用户或 policy 允许时，不自动 linz_publish
EvidencePackage 记录 world event、intent、裁判、草案
```

这个闭环一旦稳定，先进入规则结晶与治理增强；泡泡协议/kanban 协作作为低优先级扩展最后接入，风险会小很多。
