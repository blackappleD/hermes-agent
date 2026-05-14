# Research: Linz World 原生身份与世界接入

**Feature**: `001-native-linz-identity`
**Created**: 2026-05-12
**Spec**: `D:\workspace\hermes-agent\specs\001-native-linz-identity\spec.md`

## Decision: Linz World 能力作为内建 `agent/linz_world` 模块交付

**Rationale**: 规范要求未安装 linz-world-skill 时仍拥有原生命令和工具，并且 agent persona 创建/加载必须先满足 original spirit 身份。该能力属于 Hermes profile/persona 的身份边界，不适合放在可选 skill 或 opt-in plugin 中。

**Alternatives considered**:

- 继续通过 linz-world-skill 暴露能力: 不满足“未安装 skill 仍可用”和 persona fail-closed。
- 使用 user plugin: plugin 加载顺序和启用状态不适合作为 core persona 身份前置条件。
- 直接把逻辑分散到 `run_agent.py`、`cli.py`、`gateway/run.py`: 会扩大核心文件改动面，违背复用和小 diff 原则。

## Decision: Hermes profile 是唯一身份边界，旧 linz-world-skill 身份导入和同步范围外

**Rationale**: 澄清结果要求按全新原生开发处理，不考虑旧身份导入。2026-05-12 的 issue 人类评论 `e7605d41-d0ee-42d8-9a5c-3c46a2ececbb` 进一步确认旧身份导入和同步不属于本 issue 范围。每个当前 Hermes profile 拥有一个 Linz World original spirit，身份摘要保存在 profile-aware 配置/状态中。

**Alternatives considered**:

- 一次性导入或同步旧身份: 用户明确排除。
- 自动读取旧 `~/.linz-world` 身份: 会产生隐式迁移和覆盖风险。
- 多身份绑定同一 profile: 增加授权、事件归属和审计复杂度，不属于 MVP。

## Decision: 注册失败 fail-closed，阻止 agent persona 加载

**Rationale**: 用户澄清要求注册失败时阻止 persona 加载直到注册成功。这保证后续事件、记忆、关系和审计都绑定到稳定 world identity。

**Alternatives considered**:

- 注册失败但普通 agent 继续可用: 用户拒绝，且会产生“无世界身份 agent”。
- 隐藏 Linz 工具但继续对话: 仍会破坏“Agent 天然是 Linz World original spirit”的身份模型。

## Decision: 远端接口以 Linz World 后端/skill 实际契约为准

**Rationale**: OPE-108 明确要求 Hermes 本次身份接入接口和 `linz-world-skill` 调用的后端接口保持一致。核对 `OPEWorld-Tech/linz-world` 当前源码后，真实注册契约是统一 response envelope 下的 `POST /api/v1/auth/register`，字段为 `publicKey`、`publicKeyType`、`fingerprint`、`metadata`，返回 `agentId`、`soulId`、`soulHash`、`accessToken`、`expiresIn`、`registeredAt`。真实登录契约是 `POST /api/v1/event/agents/login`，字段为 `agentId`、`signedNonce`，返回 `token`、`expiresAt`、`subjectClaims`、`credentialId`。Hermes 原先 contract 中的 `/identity/original-spirit` 属于占位设计，不能用于真实服务接入。

**Alternatives considered**:

- 继续维护 Hermes 抽象占位接口: 会让实现通过本地 fake 测试但无法接入真实 Linz World 服务。
- 让用户手工配置任意 endpoint mapping: 增加配置复杂度，也无法保证和 skill 一致。
- 等 Linz World 后端补齐所有 publish/map 接口后再推进: 会阻塞已明确的注册、登录、compute、memory、relationship 一致性修复；缺失能力应 fail-closed 或标记 unsupported。

## Decision: publish 沿用 linz-world-skill 的 NATS 事件发布逻辑，不使用 HTTP publish

**Rationale**: 2026-05-13 的 issue 人类评论 `c5f73a92-7f17-465a-b77a-05c104b7317c` 明确 `publish` 在 `linz-world-skill` 中是用于世界交互的通用 NATS 事件发布指令，不是 HTTP 接口。Hermes 原生 publish 因此必须按原逻辑向授权 NATS subject 发布结构化事件，保留 event id、ack/sequence 或 diagnostic receipt，并在 NATS transport、credential、subject catalog 或实时授权不可用时 fail-closed。当前后端 HTTP `POST /api/v1/event/publish` 不作为成功发布路径或 fallback。

**Alternatives considered**:

- 继续调用 HTTP `/api/v1/event/publish`: 与人类确认的 skill 契约冲突，且当前后端该路由不是权威 publish 行为。
- 将 publish 完全标记为 unsupported: 过度收窄范围；用户已确认需要按原有 NATS 逻辑实现。
- 直接绕过授权向 NATS subject 发布: 会破坏 subject/credential 治理和外部副作用 fail-closed 边界。

## Decision: HTTP envelope 成功条件按 endpoint-specific data shape 校验

**Rationale**: `linz-world` 当前 `backend/tests/contract/event_subjects_contract_test.go` 明确 `GET /api/v1/event/subjects` 返回统一 `{code,message,data}` envelope，但成功 `data` 是 `PredefinedSubject[]` 数组。授权 map 依赖该接口，因此 Hermes 不能把“data 必须是 object”当作全局成功规则；必须按 endpoint-specific schema 校验。

**Alternatives considered**:

- 继续要求所有成功 `data` 都是 object: 会把真实 subjects 目录数组误判为 `invalid_response`，阻断授权刷新。
- 把 `data` 完全视为 untyped: 会削弱字段缺失、错误 envelope 和 contract fixture 的早期发现能力。
- 为 subjects 单独绕过 envelope 校验: 会产生特殊路径并降低统一错误处理一致性。

## Decision: relationship read 以 MemoryProjection 为权威响应，不以直接 relationships array 为准

**Rationale**: `linz-world` 当前 `GET /api/v1/memory/projections/{agentId}/relationships` handler 返回 `MemoryProjection`，字段为 `projection_id`、`agent_id`、`projection_type`、`source_version`、`content`、`generated_at`、`generated_by`。`content` 当前可能是 markdown/text 投影正文。Hermes 必须保留 projection 元数据和正文，并仅在 `content` 可结构化解析时派生 `relationships` 列表。

**Alternatives considered**:

- 继续期望顶层 `relationships` array: 会在真实后端下丢弃 projection 内容并错误显示空关系。
- 强制要求 `content` 必须 JSON: 与当前后端 markdown/text projection 不兼容。
- 只显示 projection content 不尝试解析 relationships: 可行但降低工具结果的结构化价值；当前决策允许可解析时派生，解析失败仍保留 projection。

## Decision: relationship add 使用 Linz World skill 已确认的 memory relationships mutation

**Rationale**: 旧 `linz-world-skill` 的 relationship 命令通过 `POST /api/v1/memory/relationships/{osId}` 添加 ACTIVE 关系，payload 包含 `target_os_id`、`relation_type`、`status=ACTIVE`、`summary` 和 `operator_id`。当前 event model 没有关系添加事件定义，因此 Hermes 不应通过 raw publish 自造关系事件。

**Alternatives considered**:

- 通过 `linz_publish` 发布自定义 relationship event: event catalog 中没有该事件定义，会绕开后端已确认关系写入接口。
- 继续返回 unsupported: 与已确认 skill mutation route 冲突，会让可用能力被错误屏蔽。

## Decision: compute 使用登录 JWT 契约接入，缺少 login token reference 时 fail-closed

**Rationale**: 当前 Linz World compute 契约要求 `POST /api/v1/compute/chat` 使用登录成功后返回的 JWT token 作为 `Authorization: Bearer <jwt_token>`，成功响应包含 `request_id`、`os_id`、`provider`、`model`、`choices`、`reservation`、`usage` 等字段。因此 Hermes compute 必须从当前 profile-local login token reference 解析 bearer；若缺少该 reference，返回 blocked/unsupported。

**Alternatives considered**:

- 维护单独 compute credential reference: 与当前登录后 JWT 约定重复，增加配置和轮换负担。
- 要求用户在工具参数中输入 token: 会把裸凭据暴露给 prompt、工具调用记录或日志，不符合隐私边界。
- 暂时完全移除 compute 能力: 过度收窄范围；当前后端已有可验证 compute 契约，可以在 login token reference 存在时安全接入。

## Decision: 授权 map 对所有外部副作用实时刷新

**Rationale**: 用户选择每次外部副作用前实时刷新授权 map，刷新失败即阻断。该策略最保守，覆盖 publish、compute、Soul Memory 写入和 relationship 变更。

**Alternatives considered**:

- 使用最近缓存授权 map: 性能更好，但授权撤销后存在越权窗口。
- 只对 publish 实时刷新: 不能覆盖 compute/memory/relationship 的外部副作用。
- 在服务不可达时允许低风险副作用: 与 fail-closed 安全边界冲突。

## Decision: 原始 world event payload 仅作为受限审计记录保存

**Rationale**: 用户选择保存受限审计用原始 payload，但 prompt、普通工具结果和用户默认视图只显示脱敏摘要。这样同时支持诊断/证据和隐私保护。

**Alternatives considered**:

- 只保存摘要: 减少敏感数据风险，但事件映射和故障诊断证据不足。
- 默认保存并直接展示完整 payload: 不符合凭据和敏感数据最小暴露原则。
- 仅调试模式保存原文: 操作模式切换会让审计覆盖不稳定。

## Decision: 世界事件可靠保存后确认接收，内部处理最多自动重试 3 次

**Rationale**: 事件外部接收与 LLM/agent 处理解耦。事件持久化后即可确认接收；内部处理失败最多重试 3 次，仍失败则 `failed` 并等待人工处理，避免无限重试。

**Alternatives considered**:

- 等 agent 完整处理后再确认接收: 会让外部事件通道受 LLM 时延和失败影响。
- 不自动重试: 对临时错误过于脆弱。
- 重试 5 次或无限重试: 增加重复处理和资源消耗风险。

## Decision: 事件状态和 receipt 使用 SessionDB side tables 或 profile-aware 运行期状态，不使用文件式 inbox/outbox

**Rationale**: Hermes 已有 SessionDB、gateway session store 和 busy queue，不需要复制 linz-world-skill 的通用 mailbox。事件可靠性只需要 event id 去重、dispatch status、attempt count、last error、cursor 和 publish receipt。

**Alternatives considered**:

- 复制 skill 的 inbox/submited/handled/outbox 文件夹: 与 Hermes 原生 gateway/session 流程重复，并增加状态同步风险。
- 只写 JSONL: 简单但难以高效去重、查询和关联 session/evidence。
- 完全内存态: 无法满足重启后去重和审计。

## Decision: Gateway 接入使用动态 platform registry + `MessageEvent`

**Rationale**: `gateway.config.Platform` 支持动态 plugin/platform 名称，`gateway.platform_registry` 可注册 adapter，`MessageEvent` 是所有平台的规范输入。Linz World 事件应映射为 `platform=linz_world` 的 source，并走现有 gateway processing path。

**Alternatives considered**:

- 直接调用 `AIAgent.run_conversation()`: 绕过 gateway 授权、session、busy queue 和平台一致性。
- 新建世界事件处理主循环: 复制 gateway 能力，并更难与 TUI/dashboard/session 协同。
- 使用外部 hook 命令投递事件: 不满足原生化和可靠状态要求。

## Decision: CLI 使用 CommandDef 注册，agent 工具使用 `tools.registry`

**Rationale**: Hermes slash/CLI/gateway help 由 `hermes_cli/commands.py::COMMAND_REGISTRY` 派生，工具由 `tools.registry` 自发现并通过 `toolsets.py` 暴露。该路径符合仓库现有扩展约定。

**Alternatives considered**:

- 只实现 Python API: 用户无法用原生命令管理状态和授权。
- 直接在 model_tools 里硬编码 schema: 违反工具注册架构。
- 只做 CLI 不做 agent tools: 不满足规范要求 agent 原生具备 Linz World 能力。

## Decision: NATS 监听作为可选 transport adapter，不作为必需依赖引入

**Rationale**: 当前 `pyproject.toml` 未包含 NATS 客户端，仓库约束要求无明确请求不得新增依赖。计划将 NATS 实现为可选适配；没有依赖或配置时，平台状态返回可诊断错误，测试使用 in-memory fake transport 覆盖事件可靠性。

**Alternatives considered**:

- 立即添加 `nats-py`: 违反“无新依赖无显式请求”的工作协议。
- 放弃 NATS，仅轮询 HTTP unread: 不满足世界事件接入方向。
- 在核心代码中硬依赖某个 NATS SDK: 增加安装和平台风险。

## Decision: 配置新增不需要 config version bump，除非后续任务迁移旧结构

**Rationale**: AGENTS.md 指出新增配置键由 deep-merge 自动处理，不需要 bump `_config_version`；本功能不迁移旧 linz-world-skill 身份，也不重命名已有 Hermes config 键。

**Alternatives considered**:

- bump `_config_version`: 没有迁移动作，增加不必要配置版本 churn。
- 只使用 env vars: 非秘密设置应放在 config.yaml；env 仅用于密钥/令牌。
