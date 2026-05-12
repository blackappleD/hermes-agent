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
