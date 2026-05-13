# 功能规范: Linz World 原生身份与世界接入

**功能分支**: `feat/88-linz-world-native-identity`
**创建时间**: 2026-05-12
**状态**: 草稿
**输入**: 用户描述: "根据 docs/基于张力场的Agent自驱动实现计划.md 中的模块 -1：Linz World 原生身份与世界接入，开发 spec。将 linz-world-skill 暴露的能力迁移为 Hermes Agent 原生能力；Hermes Agent 创建或加载时基于当前 Hermes profile 幂等注册为 Linz World original spirit；登录、上线监听、自动响应和事件发布继续受配置与治理约束。"

## Clarifications

### Session 2026-05-12

- Q: Linz World 注册失败时，agent persona 加载应如何处理？ → A: 注册失败时阻止 agent persona 加载，直到注册成功。
- Q: 旧 linz-world-skill 身份导入遇到当前 Hermes profile 已有 Linz World 身份时，应该怎么处理？ → A: 不考虑旧身份导入，按全新原生开发处理。
- Q: 旧身份导入或同步是否属于本 issue 范围？ → A: 不属于，不需要考虑旧身份导入和同步的问题。依据: issue 评论 `e7605d41-d0ee-42d8-9a5c-3c46a2ececbb`。
- Q: 世界事件已经可靠保存，但 Hermes 内部处理持续失败时，最多应该重试几次后停止自动重试？ → A: 最多 3 次，仍失败则标记为 failed 并等待人工处理。
- Q: 授权 map 已存在但刷新失败或过期时，外部副作用应该怎么处理？ → A: 每次外部副作用都必须实时刷新授权 map，刷新失败则阻断。
- Q: Linz World 原始事件 payload 应该如何保留？ → A: 保存受限审计用原始 payload；prompt 和普通输出只使用脱敏摘要。
- Q: Hermes 原生身份接入应以哪个后端接口契约为准？ → A: 必须以 `OPEWorld-Tech/linz-world` 中 `linz-world-skill`/后端实际使用的接口为准，不得继续使用 Hermes 侧占位接口。已核对当前 `linz-world` 主分支：统一响应 envelope 为 `{"code":0,"message":"success","data":...}`；注册接口是 `POST /api/v1/auth/register`，请求字段为 `publicKey`、`publicKeyType`、`fingerprint`、`metadata`，成功数据字段为 `agentId`、`soulId`、`soulHash`、`accessToken`、`expiresIn`、`registeredAt`；事件登录接口是 `POST /api/v1/event/agents/login`，请求字段为 `agentId`、`signedNonce`，成功数据字段为 `token`、`expiresAt`、`subjectClaims`、`credentialId`。依据: OPE-108 issue 描述和 OPE-88 评论 `f9f266fc-2cd3-4360-ae16-0ebc677891c7`、`e835f8ea-1408-4d55-8072-257f7c23e202`。
- Q: 用户提供的 Linz World 服务地址如何落地？ → A: 当前配置应支持 `http://8.156.84.202:17878` 和 `http://8.156.84.202:17878/api/v1` 两种输入并归一化，避免重复拼接 `/api/v1` 或遗漏版本前缀；用户可见配置只使用 `service_url`。
- Q: `publish` 应该走 HTTP `/api/v1/event/publish` 还是沿用 `linz-world-skill` 的 NATS 发布逻辑？ → A: `publish` 是 `linz-world-skill` 中用于世界交互的通用 NATS 事件发布指令，不是 HTTP 接口；Hermes 原生实现必须按原逻辑向授权 NATS subject 发布事件，并保留 receipt/ack 诊断。依据: OPE-108 人类评论 `c5f73a92-7f17-465a-b77a-05c104b7317c`。
- Q: Linz World HTTP envelope 的 `data` 是否总是 object？ → A: 否。统一 envelope 仍是 `{code,message,data}`，但 `data` 形状以 endpoint 为准；当前 `GET /api/v1/event/subjects` 成功 `data` 是 `PredefinedSubject[]` 数组，必须作为成功授权目录处理。依据: OPE-108 Spec Reviewer 评论 `163234b0-3d57-4508-81fd-1bc7222aa054` 与 `linz-world` contract test。
- Q: Relationship read 应如何消费 `/memory/projections/{agentId}/relationships`？ → A: 真实响应是 `MemoryProjection` 对象，必须保留 `projection_id`、`agent_id`、`projection_type`、`source_version`、`content`、`generated_at`、`generated_by`；只有当 `content` 可解析出结构化 `relationships/items` 时才派生关系列表，否则保留 projection content，不得静默退化为空关系列表。依据: OPE-108 Spec Reviewer 评论 `163234b0-3d57-4508-81fd-1bc7222aa054` 与 `linz-world` memory projection handler。

## 非目标

- 不实现旧 `linz-world-skill` 身份导入、同步或迁移。
- 不新增 `hermes linz import-skill-profile`、`agent/linz_world/migration.py` 或等价的 legacy identity 入口。
- 不读取、写入、覆盖或同步旧 `~/.linz-world` 身份目录或旧 skill profile。
- 不在本模块实现张力场自驱动算法、泡泡协议协作运行时或完整经济结算能力。

## 用户场景与测试 *(必填)*

### 用户故事 1 - Agent 自动获得原生世界身份 (优先级: P1)

Hermes 用户创建或加载一个 agent persona 时，该 agent 自动拥有 Linz World original spirit 身份。用户不需要安装额外 skill，也不会因为 CLI、TUI、gateway 或临时会话重复构造 agent 而产生多个世界身份。

**优先级原因**: 原生世界身份是后续世界事件、授权、记忆、关系和张力场自驱动的基础；如果身份边界不稳定，后续自治和审计都会失真。

**独立测试**: 可以在未安装 linz-world-skill 的环境中创建或加载同一个 Hermes profile 多次，并验证用户始终看到同一个 Linz World 身份状态。

**验收场景**:

1. **给定** 一个没有 Linz World 身份记录的 Hermes profile，**当** 用户创建或加载 agent persona，**那么** 系统会尝试为该 profile 注册 original spirit，并在成功后显示可识别的世界身份。
2. **给定** 一个已经注册成功的 Hermes profile，**当** CLI、TUI、gateway 或对话运行时再次加载该 profile，**那么** 系统复用既有身份，不重复注册。
3. **给定** Linz World 注册暂时不可用，**当** agent persona 被加载，**那么** 加载会被阻止，用户能看到明确的 pending 或 failed 状态和诊断信息，直到注册成功后才能继续使用该 agent persona。

---

### 用户故事 2 - 用户管理原生 Linz World 能力 (优先级: P2)

Hermes 用户可以在不安装 linz-world-skill 的情况下，通过 Hermes 原生命令和工具查看身份、登录状态、授权 map、未读世界事件、关系和 Soul Memory 能力。

**优先级原因**: 原生命令和工具是验证“不再依赖 skill”的可见证据，也是用户理解和控制世界身份状态的主要入口。

**独立测试**: 可以在不安装 linz-world-skill 的情况下完成状态、登录、授权 map、近期事件和关系查询。

**验收场景**:

1. **给定** 当前 profile 已有 Linz World 身份，**当** 用户查看状态、登录、退出、刷新授权 map 或查看未读世界事件，**那么** Hermes 提供原生结果和可诊断错误。
2. **给定** 用户未安装 linz-world-skill，**当** 用户列出 Hermes 的 Linz World 命令或 agent 工具，**那么** 身份、状态、授权、事件、发布、世界算力、Soul Memory 和关系能力仍然可见。
---

### 用户故事 3 - 世界事件可靠进入 Hermes 事件流 (优先级: P2)

Linz World 事件可以作为 Hermes 原生外部输入进入 agent 会话和运行时事件流。系统会持久化事件投递状态、去重重复事件，并只把适合 agent 处理的摘要暴露给对话上下文。

**优先级原因**: 世界事件是后续张力场自治的主要外部信号；可靠性和最小暴露边界必须先建立。

**独立测试**: 可以向 Hermes 投递同一个世界事件多次，并验证事件只被记录和处理一次，同时保留可追踪的投递状态。

**验收场景**:

1. **给定** 一个合法 Linz World 消息事件，**当** 事件到达 Hermes，**那么** 系统记录事件身份、投递状态和原始引用，并生成 Hermes 可处理的会话事件。
2. **给定** 同一个世界事件被重复投递，**当** Hermes 接收这些投递，**那么** 用户只看到一条有效事件记录，不会重复触发 agent turn。
3. **给定** Hermes 已经持久化世界事件但 agent 处理失败，**当** 用户查看事件状态，**那么** 状态显示为 failed 并包含诊断信息，外部事件通道不等待 LLM 完整处理。

---

### 用户故事 4 - 外部发布、算力、记忆和关系受治理保护 (优先级: P3)

用户或 agent 可以使用 Linz World 的发布、世界算力、Soul Memory 和关系能力，但任何外部副作用都必须经过身份、登录、授权、事件目录和治理检查。默认情况下，这一模块不会开启自驱动、自动上线监听、自动响应或自动外部发布。

**优先级原因**: 原生能力一旦具备外部副作用，必须先保证安全边界和审计证据，否则会扩大越权、泄密和误发布风险。

**独立测试**: 可以尝试未登录发布、未授权事件发布、禁止类型事件发布、世界算力调用和 Soul Memory 写入，并验证每个动作都有明确的允许、阻断或失败结果。

**验收场景**:

1. **给定** agent 未注册、未登录或缺少授权 map，**当** 用户尝试发布世界事件，**那么** 系统拒绝发布并说明缺失前置条件。
2. **给定** 用户尝试发布未授权 subject/event_type 或禁止 agent 直发的结算转账事件，**当** 发布被请求，**那么** 系统在外部投递前阻断并记录治理结果。
3. **给定** 用户调用世界算力，**当** 请求完成或失败，**那么** 用户看到结果或可诊断错误，且凭据不会出现在用户可见输出、prompt 或普通工具结果中。
4. **给定** agent 需要写入 Soul Memory 或更新 ACTIVE 关系，**当** 写入被允许，**那么** 系统保留交付物引用、原因和审计记录，而不是只写入无法追踪的自由文本。

### 边界情况

- 当前 Hermes profile 已有部分 Linz World 字段但缺少关键身份时，系统必须进入可诊断的 pending 或 failed 状态，并阻止 agent persona 加载，不能假定注册成功。
- 同一个 Hermes profile 被多个入口同时加载时，系统必须避免重复注册。
- 旧 linz-world-skill 本地身份导入、同步和迁移不属于当前版本范围；系统不得提供 legacy identity 入口，也不得尝试读取、覆盖、迁移或同步旧身份。
- 未安装 linz-world-skill 时，所有原生命令和工具仍必须可发现；缺少 Linz World 服务配置时返回可操作的配置错误。
- 世界事件 payload 不是对象、subject/event_type 不在正式目录或使用旧协议名称时，系统必须拒绝处理或降级为不可执行记录。
- HTTP 服务返回不符合 Linz World 统一 envelope、`code` 非 0、`data` 缺失或使用 Hermes 占位字段名时，系统必须按可诊断服务错误处理，不能把响应误判为成功。
- `service_url` 被配置为 origin 根地址或 `/api/v1` 根地址时，HTTP client 必须只拼接一次 API 版本前缀。
- 重复世界事件、乱序事件或处理失败事件必须保留可追踪状态；处理失败事件最多自动重试 3 次，仍失败后标记为 failed 并等待人工处理。
- 发布成功但 receipt 回写失败时，系统必须暴露“投递结果不确定”的状态，避免宣称已完整完成。
- 用户关闭上线监听、自动响应或外部发布时，该模块不得通过默认值绕过用户选择。
- 授权 map 刷新失败或不可达时，系统必须阻断发布、世界算力、Soul Memory 写入和关系变更等外部副作用。
- 原始世界事件 payload 只能作为受限审计记录保留；prompt、普通工具结果和用户默认视图只能使用脱敏摘要。

## 需求 *(必填)*

### 功能需求

- **FR-001**: 系统必须在未安装 linz-world-skill 的情况下提供 Linz World 原生身份、状态、授权、事件、发布、世界算力、Soul Memory 和关系能力。
- **FR-002**: 系统必须为每个 Hermes profile 维护一个稳定的 Linz World original spirit 身份记录，至少包含 profile 标识、agent_id/agentId、兼容别名 os_id、os_name、soul_id、soul_hash、account_id、授权状态和记忆摘要可用性。
- **FR-003**: 系统必须在 agent persona 创建或加载时检查 Linz World 身份状态；已注册身份必须被复用，缺失身份必须触发注册尝试。
- **FR-004**: 系统必须保证身份注册按 Hermes profile 幂等执行，重复加载同一 profile 不得产生多个 Linz World 身份。
- **FR-005**: 注册成功后，系统必须把 Linz World 返回的 agentId、soulId、soulHash、accessToken 引用、expiresIn/过期时间和注册状态保存到当前 Hermes profile 的 Linz World 身份记录或 secret/runtime store 中；内部 os_id 只能作为 agentId 的兼容别名。
- **FR-006**: 注册失败或服务不可用时，系统必须保存 pending 或 failed 状态、最后错误和下一步诊断，并阻止该 agent persona 加载，直到注册成功。
- **FR-007**: 系统不得在当前版本中实现旧 linz-world-skill 本地身份导入、同步或迁移入口，也不得读取、导入、覆盖、迁移或同步旧身份来源。
- **FR-008**: 用户必须能够通过 Hermes 原生命令查看 Linz World 状态、登录、退出、授权 map、近期事件和发布入口。
- **FR-009**: Agent 可用工具必须包含 Linz World 状态、授权 map、近期事件、发布、关系、Soul Memory 和世界算力能力，并且这些工具必须受到相同治理规则约束。
- **FR-010**: 系统必须把授权 map 作为只读治理输入；每次外部副作用执行前都必须实时刷新授权 map，刷新失败或授权未知时必须阻断该副作用。
- **FR-011**: 系统必须只接受正式目录中的世界事件 subject/event_type，并拒绝旧协议名称或 agent 自造的事件类型。
- **FR-012**: 系统必须校验待发布世界事件的 payload 是结构化对象，并在外部投递前验证身份、登录状态、实时授权 map 和事件目录。
- **FR-013**: 系统必须禁止 agent 直接发布结算转账类事件；这类请求必须被拒绝或要求人类治理流程处理。
- **FR-014**: 世界事件进入 Hermes 时，系统必须记录事件 id、来源、投递状态、尝试次数、最后错误、最后投递时间和必要原始引用；原始 payload 仅允许作为受限审计记录保存。
- **FR-015**: 系统必须根据世界事件 id 和投递序列去重，重复事件不得重复创建用户可见会话事件或重复触发 agent turn。
- **FR-016**: 系统必须在世界事件已被可靠保存后确认接收；agent 处理失败必须转化为 Hermes 内部失败状态，最多自动重试 3 次，仍失败后等待人工处理。
- **FR-017**: 系统必须把可处理的世界消息、需求、任务、订单、交付、结算和治理事件映射为 Hermes 内部事件类别，供后续张力场和用户界面消费。
- **FR-018**: 系统必须在对话上下文、普通工具结果和用户默认视图中只暴露脱敏摘要和必要引用，不得暴露原始凭据、私密字段或完整未筛选 payload。
- **FR-019**: 世界事件发布必须沿用 `linz-world-skill` 的 NATS 事件发布逻辑：通过当前 NATS transport/credential 向授权 subject 发布结构化事件，而不是调用 HTTP `/api/v1/event/publish`；发布成功后必须记录 publish receipt，发布失败时必须记录失败原因、被拒绝的 subject/event_type 摘要和治理结果。
- **FR-020**: 世界算力调用必须使用当前 Hermes profile 的 Linz World 登录 token reference 调用当前后端，不得通过工具参数、prompt、普通 CLI 输出或日志接受/回显裸凭据；缺少有效登录 token reference 时必须返回 blocked/unsupported 诊断。
- **FR-021**: Soul Memory 写入必须包含 artifact_ref 或等价交付物引用、sink_reason 和证据摘要；系统不得只写入无来源的自由文本。
- **FR-022**: 系统必须兼容旧 Soul Memory sink 命名输入并归一为新的记忆写入语义，确保旧命名调用不会因名称差异失败。
- **FR-023**: 系统必须支持读取 Linz World 关系状态和添加 ACTIVE 关系；关系读取必须按 Linz World `MemoryProjection` 响应建模，保留 projection 元数据和 `content`，并在可解析时从 `content.relationships`、`content.items` 或等价结构派生关系列表，作为后续自治层可消费的关系信号。
- **FR-024**: 系统必须默认不启用自驱动、自动上线监听、自动响应或自动外部发布；这些行为只能由用户配置或显式命令开启。
- **FR-025**: 所有注册、登录、事件接收、发布、算力、记忆和关系操作必须产生用户可追踪的状态或审计结果。
- **FR-026**: Linz World HTTP client 必须解析 Linz World 统一响应 envelope `{code,message,data}`：只有 `code == 0` 且 `data` 符合 endpoint-specific 形状时才视为成功；`data` 可以按 endpoint 契约为对象或数组，当前 `GET /api/v1/event/subjects` 成功 `data` 必须支持 `PredefinedSubject[]` 数组；非 0 code、HTTP 错误、缺失 data 或字段不匹配必须转为用户可诊断错误。
- **FR-027**: 身份注册必须调用 Linz World 当前后端/skill 契约 `POST /api/v1/auth/register`，请求字段为 `publicKey`、`publicKeyType`、`fingerprint`、`metadata`；不得调用 Hermes 占位路径 `/identity/original-spirit`。成功后必须从 `data.agentId`、`data.soulId`、`data.soulHash`、`data.accessToken`、`data.expiresIn`、`data.registeredAt` 建立当前 profile 身份和登录状态；内部可保留 `os_id` 别名，但对外接口不得发送 `os_id` 替代 `agentId`。
- **FR-028**: 登录与刷新必须匹配 Linz World 事件模块接口：登录调用 `POST /api/v1/event/agents/login`，请求字段为 `agentId`、`signedNonce`；刷新调用 `POST /api/v1/event/agents/refresh`，请求字段为 `token`；成功结果必须读取 `data.token`、`data.expiresAt`、`data.subjectClaims`、`data.credentialId`，并禁止在用户可见输出中泄露 token。
- **FR-029**: 授权 map 不得调用未在 `linz-world` 后端或 skill 中存在的占位接口；当前版本必须从登录/凭证响应的 `subjectClaims`、`publishScopeSnapshot`、`subscribeScopeSnapshot` 以及 `GET /api/v1/event/subjects` 的 `PredefinedSubject[]` 主题定义组合授权摘要，若后端缺少必要数据则返回可诊断的 unsupported/unknown 状态并阻断外部副作用。
- **FR-030**: 世界算力调用必须匹配当前 Linz World Compute Gateway 契约 `POST /api/v1/compute/chat`，使用 `Authorization: Bearer <compute_api_key>`，请求至少包含 `model`、`messages`、`stream`、`temperature`、`metadata`；成功响应必须从统一 envelope 的 `data.request_id`、`data.os_id`、`data.provider`、`data.model`、`data.choices`、`data.reservation`、`data.usage` 建模，并把 `request_id` 作为主要 receipt。缺失 Authorization、无效或吊销 compute key 的 401 响应必须保留为用户可诊断失败。
- **FR-031**: Soul Memory 相关能力必须匹配 Linz World Memory 模块路由：人格种子使用 `/api/v1/memory/seeds`，Soul Memory 使用 `/api/v1/memory/soul`，记忆事件归档使用 `/api/v1/memory/events`，投影/快照/lineage 使用对应 `/api/v1/memory/...` 路由；不得调用未确认的 Hermes 占位 memory sink 路径。
- **FR-032**: 发布与事件接收必须匹配 Linz World 事件系统实际契约：NATS subject 使用 `sys.*`、`mrk.*`、`wsp.{agentId}.*`、`apl.*`、`rent.*`、`poca.*` 等正式主题族；`publish` 必须走 NATS publish transport，并使用 event id 去重、subject 授权和 receipt 记录。HTTP `POST /api/v1/event/publish` 不是本功能的 publish 实现路径，不得作为成功发布依据或 fallback。
- **FR-033**: 配置必须使用 `linz_world.service_url` 作为唯一用户可见服务地址键，并支持将 origin 根地址和 `/api/v1` 根地址归一化为同一 HTTP 调用行为。

### 关键实体 *(如果功能涉及数据则包含)*

- **Hermes Profile**: 用户当前使用的 Hermes 身份和配置边界；每个 profile 拥有自己的 Linz World 身份记录、授权状态和运行期状态。
- **World Identity**: Hermes profile 在 Linz World 中的 original spirit 身份，包含 agent_id/agentId、兼容别名 os_id、os_name、soul_id、soul_hash、account_id、注册状态和授权摘要。
- **Registration State**: 身份注册生命周期状态，表示 pending、registered 或 failed，并包含最近诊断信息。
- **Authorization Map**: Linz World 授权摘要，说明当前身份可以读取、发布或调用哪些世界能力；它是治理输入，不是 prompt 中的自由文本。
- **World Event**: 来自 Linz World 的外部事件，具有事件 id、subject/event_type、来源、脱敏 payload 摘要、受限审计 payload 和原始引用。
- **Event Dispatch Record**: Hermes 对世界事件接收、去重、排队、处理、失败或跳过的可靠性状态，包含自动重试次数和是否需要人工处理。
- **Publish Request**: 用户或 agent 试图发布到 Linz World 的结构化事件请求，必须通过身份、登录、授权、目录和治理检查。
- **Publish Receipt**: 世界事件发布后的可追踪结果，记录成功的 world event id 或失败原因。
- **World Compute Request**: 使用 profile secret store 中的 Linz World 登录 token reference 发起的世界算力调用，带有 request_id、provider、model、usage、reservation、choices 摘要、结果或诊断错误。
- **Soul Memory Entry**: 写入 Linz World 记忆侧的证据、交付物引用、规则或摘要，必须说明写入原因。
- **Relationship Record**: Linz World 关系状态或 ACTIVE 关系变更，用于后续关系信号和治理判断。
- **Governance Result**: 对发布、算力、记忆和关系动作的允许、拒绝、降级或需审批结论及其理由。

## 成功标准 *(必填)*

### 可衡量的结果

- **SC-001**: 在未安装 linz-world-skill 的全新环境中，用户可以在 2 分钟内查看 Hermes 原生 Linz World 状态；如果注册失败，100% 的 agent persona 加载尝试会被阻止并显示 pending 或 failed 诊断。
- **SC-002**: 同一 Hermes profile 连续加载 10 次后，只保留一个 Linz World original spirit 身份，且用户可见审计记录中没有重复注册成功事件。
- **SC-003**: 100% 的注册失败、登录失败和授权 map 刷新失败都会向用户显示可操作诊断，而不是静默跳过。
- **SC-004**: 100% 的实现和任务中不包含旧 linz-world-skill 身份导入、同步或迁移入口，且不会读取、写入或修改旧身份来源。
- **SC-005**: 100% 的未登录、未授权、未知 subject/event_type、缺少 NATS transport/credential 或禁止结算转账发布请求会在外部投递前被阻断，并返回用户可理解原因；有效 publish 请求必须通过 fake 或真实 NATS transport 发出，不得调用 HTTP `/api/v1/event/publish`。
- **SC-006**: 同一个世界事件重复投递 5 次时，Hermes 只生成 1 条用户可见事件记录和最多 1 次 agent turn 触发。
- **SC-007**: 在 Linz World 服务可达时，95% 的状态、授权 map 和近期事件查询会在 5 秒内向用户返回结果或明确错误。
- **SC-008**: 对登录、发布、世界算力和事件接收流程的安全检查中，用户可见输出、prompt 注入内容和普通工具结果中不出现 raw token、私钥或等价凭据。
- **SC-009**: 100% 的世界算力调用成功或失败后都有 receipt 或诊断记录，用户不会只看到“失败”而没有下一步信息。
- **SC-010**: 默认配置下，自动上线监听、自动响应、自驱动 continuation 和自动外部发布的启用率为 0%，除非用户显式开启。
- **SC-011**: 100% 的世界事件内部处理失败会在第 3 次自动重试后停止自动重试，标记为 failed，并暴露人工处理状态。
- **SC-012**: 100% 的发布、世界算力、Soul Memory 写入和关系变更请求在授权 map 实时刷新失败时会被阻断，并返回用户可理解原因。
- **SC-013**: 100% 的世界事件 prompt 注入、普通工具结果和用户默认视图只显示脱敏摘要；原始 payload 只能通过受限审计路径访问。
- **SC-014**: 使用 `service_url: "http://8.156.84.202:17878"` 或 `service_url: "http://8.156.84.202:17878/api/v1"` 时，注册请求都会落到单一规范路径 `/api/v1/auth/register`，不会出现 `/api/v1/api/v1/...` 或遗漏 `/api/v1`。
- **SC-015**: 身份注册测试中 100% 的请求 payload 使用 `publicKey`、`publicKeyType`、`fingerprint`、`metadata`，并从响应 envelope 的 `data.agentId`、`data.soulId`、`data.soulHash`、`data.accessToken` 等字段建模；不得出现 `/identity/original-spirit`、`hermes_profile`、`os_name` 作为远端注册契约字段。
- **SC-016**: 登录/授权测试中 100% 的登录请求使用 `POST /api/v1/event/agents/login` + `agentId`/`signedNonce`，并从 `subjectClaims` 或 credential scope snapshot 生成授权摘要；若授权数据缺失，发布、compute、memory、relationship 外部副作用全部阻断。
- **SC-017**: Contract fixture 或 fake service 测试必须覆盖 Linz World 统一响应 envelope 成功、非 0 code、缺失 data、字段缺失和 HTTP 错误，且所有错误都会保存 failed/pending 状态和用户可诊断 next_action。
- **SC-018**: `POST /api/v1/compute/chat` contract fixture 必须覆盖缺失 Authorization、无效或吊销登录 token 的 401 envelope，以及成功 envelope 中 `request_id`、`os_id`、`provider`、`model`、`choices`、`reservation`、`usage` 字段解析；缺少登录 token reference 时 Hermes compute 外部副作用必须 fail-closed。
- **SC-019**: publish contract fixture 必须覆盖 NATS subject/event payload、授权通过后的 publish ack/sequence 或 diagnostic receipt、NATS 不可用 fail-closed、未授权 subject 拒绝，以及确认不会调用 HTTP `/api/v1/event/publish`。
- **SC-020**: subjects contract fixture 必须覆盖 `GET /api/v1/event/subjects` 返回 `{code:0,message:"success",data:[...]}` 和 `{code:0,data:[]}`；两者都必须被视为成功 envelope，并用于授权摘要生成或空目录诊断，不得因 `data` 是数组而错误阻断授权刷新。
- **SC-021**: relationship projection contract fixture 必须覆盖 `GET /api/v1/memory/projections/{agentId}/relationships` 返回 MemoryProjection envelope，且工具/CLI 结果必须保留 `projection_id`、`agent_id`、`projection_type`、`source_version`、`content`、`generated_at`、`generated_by`；如果无法从 `content` 派生关系列表，也不得丢弃 projection 或退化为只有空 `relationships` list。

## 假设

- Hermes profile 是本功能的身份边界；同一 profile 共享一个 Linz World original spirit，不同 profile 允许拥有不同身份。
- Linz World 注册、登录、授权 map、事件、发布、世界算力、Soul Memory 和关系服务由外部 Linz World 提供，本功能负责 Hermes 原生接入和治理边界。
- Linz World 后端/skill 接口是跨仓库契约源；Hermes spec/实现必须定期对照 `OPEWorld-Tech/linz-world` 的 docs、specs 和 handler/service 测试，避免 Hermes 侧自造路径或字段名。
- 当前 `linz-world` compute gateway 使用成功登录后的 JWT token 作为 Bearer 凭证。
- Linz World original spirit 身份是 agent persona 加载的硬性前置条件；没有已注册身份时，该 persona 不进入普通对话运行状态。
- 旧 linz-world-skill 身份导入和同步不属于当前版本范围；新运行期不依赖用户继续安装或调用该 skill，也不提供 legacy identity 迁移入口。
- 默认交互模式是被动和用户可控的；自驱动、自动响应、上线监听和外部发布由后续模块或显式配置控制。
- 世界事件 payload 可能包含敏感信息，因此默认只向 agent 上下文、普通工具结果和用户默认视图暴露脱敏摘要和引用；原始 payload 仅用于受限审计。
- 授权 map 是发布和世界能力调用的主要治理输入；每次外部副作用都要求实时授权 map 校验，如果授权状态未知或刷新失败，系统默认拒绝外部副作用。
- 本规范覆盖“模块 -1”的原生身份与世界接入，不包含张力场自驱动算法、泡泡协议协作运行时或完整经济结算能力。
