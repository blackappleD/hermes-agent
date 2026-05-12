# 实施计划: Linz World 原生身份与世界接入

**分支**: `001-native-linz-identity` | **日期**: 2026-05-12 | **规范**: [D:\workspace\hermes-agent\specs\001-native-linz-identity\spec.md](D:\workspace\hermes-agent\specs\001-native-linz-identity\spec.md)
**输入**: 来自 `D:\workspace\hermes-agent\specs\001-native-linz-identity\spec.md` 的功能规范

**注意**: 此计划由 `$speckit-plan` 生成，覆盖阶段 0 研究与阶段 1 设计制品；阶段 2 任务拆分由 `$speckit-tasks` 生成。

## 摘要

将 Linz World 从可选 skill 能力提升为 Hermes 原生世界身份层：每个 Hermes profile 拥有一个 original spirit 身份，agent persona 创建/加载时必须成功注册或复用身份，注册失败时 fail-closed 并阻止 persona 进入普通对话状态。本功能提供原生命令、agent 工具、事件接入、授权治理、发布 receipt、世界算力、Soul Memory 和关系能力；不做旧 linz-world-skill 身份导入。外部副作用每次执行前实时刷新授权 map，刷新失败即阻断。世界事件可靠保存后确认接收，Hermes 内部处理最多自动重试 3 次；原始 payload 仅限受限审计路径，prompt 和普通输出只使用脱敏摘要。

技术方法采用 `agent/linz_world/` 作为内建领域模块，复用现有 `get_hermes_home()` profile-aware 路径、`hermes_cli/config.py` 配置体系、`gateway.platform_registry` 动态平台、`gateway.platforms.base.MessageEvent`、`tools.registry` 自注册工具、`toolsets.py` 工具暴露和 `hermes_state.SessionDB` 持久化能力。NATS 监听作为可选传输适配，不在本计划中引入新的必需依赖。

## 技术背景

**语言/版本**: Python >=3.11 (`D:\workspace\hermes-agent\pyproject.toml`)
**主要依赖**: 复用现有 `httpx`、`rich`、`prompt_toolkit`、gateway platform registry、plugin hooks、tool registry、SessionDB；NATS 传输使用可选适配层，不新增必需依赖
**存储**: `config.yaml` 的 `linz_world` 非秘密配置和身份摘要；`get_hermes_home()/linz_world/` 或 SessionDB side tables 保存运行期状态、event dispatch、publish receipt、受限审计 payload；token 不进入 prompt 或普通工具结果
**测试**: pytest、pytest-asyncio；目标测试目录 `D:\workspace\hermes-agent\tests\linz_world\`
**目标平台**: Hermes CLI、TUI、gateway、agent runtime；Windows/Linux/macOS Python 环境
**项目类型**: Python CLI + agent runtime + messaging gateway
**性能目标**: 服务可达时 95% 的 status/map/events 查询在 5 秒内返回；重复 5 次同一世界事件只产生 1 条用户可见事件和最多 1 次 agent turn；处理失败第 3 次重试后停止自动重试
**约束条件**: 注册失败 fail-closed；不读取/导入/迁移旧 linz-world-skill 身份；外部副作用必须实时授权 map 校验；默认不启用自驱动、自动监听、自动响应、自动外部发布；原始 payload 仅限受限审计；无新必需依赖
**规模/范围**: 每个 Hermes profile 一个 original spirit；MVP 覆盖身份、授权、事件、发布、compute、Soul Memory、relationship，不覆盖张力场自驱动、泡泡协议或经济结算

**Language/Version**: Python >=3.11
**Primary Dependencies**: existing httpx, rich, prompt_toolkit, gateway platform registry, plugin hooks, tool registry, SessionDB; optional NATS transport adapter only
**Storage**: config.yaml profile fields, get_hermes_home profile runtime state, SessionDB side tables for dispatch/receipts/audit refs
**Project Type**: Python CLI + agent runtime + messaging gateway

## 章程检查

*门控: 必须在阶段 0 研究前通过. 阶段 1 设计后重新检查.*

`.specify/memory/constitution.md` 仍是未填充模板，没有可执行的项目章程条款。实际门控采用仓库 AGENTS.md 工作协议：

- **行为保护**: 默认不启用自驱动、自动监听、自动响应、自动外部发布；外部副作用 fail-closed。通过。
- **依赖控制**: 不新增必需依赖；NATS 监听设计为可选适配，若后续实现需要新增包，必须在任务阶段显式记录并获得用户授权。通过。
- **Profile-aware 路径**: 所有运行期状态使用当前 Hermes profile 和 `get_hermes_home()`，不得写入旧 `~/.linz-world` 身份。通过。
- **测试先行**: 后续任务必须先覆盖身份幂等、注册失败阻断、授权阻断、事件去重/重试、payload 脱敏等高风险行为。通过。
- **复用现有基础设施**: 复用 config、gateway、tool registry、SessionDB、memory/tool hooks，不复制 agent runtime 主循环。通过。
- **可观测性**: 注册、登录、事件、发布、compute、memory、relationship 均需要状态或审计结果。通过。

阶段 0 前门控结果: **PASS**。

## 项目结构

### 文档(此功能)

```
D:\workspace\hermes-agent\specs\001-native-linz-identity\
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts\
│   ├── cli.md
│   ├── config.md
│   ├── gateway-events.md
│   ├── tools.md
│   └── world-service.md
└── tasks.md              # 由后续 /speckit.tasks 创建
```

### 源代码(仓库根目录)

```
D:\workspace\hermes-agent\
├── agent\
│   └── linz_world\
│       ├── __init__.py
│       ├── config.py
│       ├── identity.py
│       ├── profile_fields.py
│       ├── bootstrap.py
│       ├── auth.py
│       ├── api_client.py
│       ├── event_catalog.py
│       ├── event_bus.py
│       ├── gateway_adapter.py
│       ├── event_state.py
│       ├── publisher.py
│       ├── compute.py
│       ├── memory.py
│       ├── relationship.py
│       └── runtime_bridge.py
├── hermes_cli\
│   ├── config.py
│   ├── commands.py
│   └── linz.py
├── gateway\
│   ├── config.py
│   └── platform_registry.py
├── tools\
│   └── linz_world_tools.py
├── toolsets.py
├── run_agent.py
├── cli.py
└── tests\
    └── linz_world\
        ├── test_identity_bootstrap.py
        ├── test_auth_and_authorization.py
        ├── test_event_catalog.py
        ├── test_event_state.py
        ├── test_gateway_adapter.py
        ├── test_publisher.py
        ├── test_compute_memory_relationship.py
        ├── test_tools.py
        └── test_cli.py
```

**结构决策**: 使用内建 `agent/linz_world/` 模块，而不是 plugin 或 skill。原因是规范要求未安装 linz-world-skill 时仍内建可用，并且 agent persona 加载需要身份 bootstrap；该行为属于 core runtime 身份边界。Gateway 输入仍通过现有 `gateway.platform_registry` 暴露为动态平台，工具通过 `tools.registry` 和 `toolsets.py` 暴露给 agent。

## 阶段 0: 研究输出

研究结果写入 [D:\workspace\hermes-agent\specs\001-native-linz-identity\research.md](D:\workspace\hermes-agent\specs\001-native-linz-identity\research.md)。所有技术未知项已收敛为可执行决策，没有剩余未解决澄清项。

## 阶段 1: 设计输出

设计制品:

- [D:\workspace\hermes-agent\specs\001-native-linz-identity\data-model.md](D:\workspace\hermes-agent\specs\001-native-linz-identity\data-model.md)
- [D:\workspace\hermes-agent\specs\001-native-linz-identity\contracts\config.md](D:\workspace\hermes-agent\specs\001-native-linz-identity\contracts\config.md)
- [D:\workspace\hermes-agent\specs\001-native-linz-identity\contracts\cli.md](D:\workspace\hermes-agent\specs\001-native-linz-identity\contracts\cli.md)
- [D:\workspace\hermes-agent\specs\001-native-linz-identity\contracts\tools.md](D:\workspace\hermes-agent\specs\001-native-linz-identity\contracts\tools.md)
- [D:\workspace\hermes-agent\specs\001-native-linz-identity\contracts\gateway-events.md](D:\workspace\hermes-agent\specs\001-native-linz-identity\contracts\gateway-events.md)
- [D:\workspace\hermes-agent\specs\001-native-linz-identity\contracts\world-service.md](D:\workspace\hermes-agent\specs\001-native-linz-identity\contracts\world-service.md)
- [D:\workspace\hermes-agent\specs\001-native-linz-identity\quickstart.md](D:\workspace\hermes-agent\specs\001-native-linz-identity\quickstart.md)

## 设计后章程检查

- **行为保护**: Contracts 明确注册 fail-closed、授权实时刷新、默认无自动外部副作用。PASS。
- **依赖控制**: Research 明确 NATS 为可选适配，不新增必需依赖。PASS。
- **Profile-aware 路径**: Data model 和 config contract 绑定当前 Hermes profile，不使用旧身份目录。PASS。
- **测试先行**: Quickstart 和计划结构列出 pytest 覆盖面。PASS。
- **复用现有基础设施**: Contracts 使用 CommandDef、tool registry、dynamic gateway Platform、SessionDB/event_state。PASS。
- **可观测性**: Data model 包含 Registration State、Event Dispatch Record、Publish Receipt、Governance Result。PASS。

阶段 1 后门控结果: **PASS**。

## 复杂度跟踪

无章程违规。当前复杂度来自功能自身的安全边界，而非额外架构层：

| 决策 | 为什么需要 | 拒绝更简单替代方案的原因 |
|-----------|------------|-------------------------------------|
| 内建 `agent/linz_world/` 而非 skill/plugin | 身份注册是 agent persona 加载前置条件，未安装 skill 时也必须可用 | plugin/skill 无法可靠承载 core persona fail-closed 行为 |
| 实时授权 map 校验 | 用户要求每次外部副作用前刷新授权，刷新失败阻断 | 使用缓存授权会降低网络成本，但会扩大越权窗口 |
| 受限审计 payload + 脱敏摘要双轨 | 需要诊断和证据，同时防止 prompt/普通输出泄露 | 只保存摘要会削弱排错；默认暴露原文违反安全边界 |
