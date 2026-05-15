# 实施计划: World Event Dashboard

**分支**: `516-world-event-dashboard` | **日期**: 2026-05-15 | **规范**: `D:\workspace\hermes-agent\specs\516-world-event-dashboard\spec.md`
**输入**: 来自 `D:\workspace\hermes-agent\specs\516-world-event-dashboard\spec.md` 的功能规范

## 摘要

在 Hermes dashboard 中新增一个事件投影视图, 用于查看所有进入 gateway 并可投影或已尝试投影成 Hermes `MessageEvent` 的入站事件。实现方向是新增一个 profile-scoped 的本地投影记录账本, 由 gateway 在 `MessageEvent` 边界记录消费、投影、处理状态, 由 dashboard 通过只读 API 查询最近 100 条、筛选、分页和详情。前端复用现有日志/OS Runtime 页面风格: 左侧导航、暗色高密度布局、手动刷新、自动刷新开关、状态标签、卡片和受控展开区域。

## 技术背景

**语言/版本**: Python 3.11+; TypeScript 5.9; React 19  
**主要依赖**: FastAPI/Pydantic style endpoint models in `hermes_cli\web_server.py`; Python stdlib `sqlite3`; React Router; `@nous-research/ui`; `lucide-react`; existing dashboard components under `web\src`  
**存储**: Profile-scoped local SQLite ledger under `get_hermes_home()` for gateway inbound event projection records; reuse existing `SessionDB` only for session/message references, not as the envelope store  
**测试**: `pytest` for gateway/store/API behavior; `npm run build` and `npm run lint` in `web`; focused visual/manual verification against dashboard logs page  
**目标平台**: Local Hermes dashboard and gateway on supported developer machines/profiles; no remote multi-user dashboard assumption  
**项目类型**: Python gateway/web service + React dashboard page in existing monorepo  
**性能目标**: Default list of latest 100 records returns within SC-003's 5 second target; filtered queries use indexed columns and cursor pagination/load-more  
**约束条件**: No new required dependency; state must be profile-scoped; raw payload is collapsed by default and only displayed after explicit expansion; new dashboard page must not interfere with embedded chat/PTY host  
**规模/范围**: One built-in dashboard page, one read-only API surface, one local projection ledger, gateway write integration for existing platform `MessageEvent` flow plus Linz World/NATS metadata preservation

**Language/Version**: Python 3.11+; TypeScript 5.9; React 19  
**Primary Dependencies**: FastAPI/Pydantic style endpoint models; Python stdlib `sqlite3`; React Router; `@nous-research/ui`; `lucide-react`  
**Storage**: Profile-scoped local SQLite ledger under `get_hermes_home()`  
**Testing**: `pytest`; `npm run build`; `npm run lint`

## 章程检查

*门控: 必须在阶段 0 研究前通过. 阶段 1 设计后重新检查.*

| 原则 | 检查结果 | 证据/约束 |
|---|---|---|
| I. Profile-Scoped State | 通过 | 投影记录账本必须使用 `get_hermes_home()` 下的当前 profile 路径, 不写全局状态。 |
| II. Native Surfaces Before Optional Skills | 通过 | 功能属于 gateway/dashboard 原生能力, 不依赖 optional skill 或 plugin。 |
| III. Fail-Closed External Side Effects | 通过 | 页面和 API 只读; 不新增重投递、删除、发布或其他外部副作用。 |
| IV. Privacy and Audit Separation | 通过, 带约束 | 默认列表和详情摘要不展示完整 payload; 完整原始 payload 仅在本地 dashboard 中由用户显式展开。 |
| V. Testable Incremental Delivery | 通过 | 按持久化账本、API、dashboard 页面、gateway/Linz 集成和视觉/构建验证拆分。 |

**阶段 1 设计后复查**: 仍通过。`research.md`, `data-model.md`, `contracts/world-event-dashboard.openapi.yaml` 和 `quickstart.md` 均保持 profile-scoped、本地只读、无新依赖、可测试的实现边界。

## 项目结构

### 文档(此功能)

```
D:\workspace\hermes-agent\specs\516-world-event-dashboard\
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts\
│   └── world-event-dashboard.openapi.yaml
└── tasks.md
```

### 源代码(仓库根目录)

```
D:\workspace\hermes-agent\
├── gateway\
│   ├── event_projection_store.py      # 新增: profile-scoped SQLite ledger
│   ├── run.py                         # 记录 MessageEvent lifecycle/status
│   └── platforms\base.py              # 读取 MessageEvent/SessionSource 字段, 尽量避免行为改动
├── agent\linz_world\
│   ├── gateway_adapter.py             # 保留 NATS raw event 与投影记录的关联
│   ├── event_bus.py                   # Linz World -> MessageEvent 元数据投影
│   └── event_state.py                 # 现有 Linz 状态继续作为 Linz-specific 状态来源
├── hermes_cli\
│   └── web_server.py                  # 新增只读 dashboard API endpoints
├── web\src\
│   ├── App.tsx                        # 新增内置导航和路由
│   ├── lib\api.ts                     # 新增 API client/types
│   └── pages\WorldEventsPage.tsx      # 新增事件投影视图页面
└── tests\
    ├── gateway\
    │   ├── test_event_projection_store.py
    │   └── test_message_event_projection_ledger.py
    ├── hermes_cli\
    │   └── test_web_server_world_events.py
    └── linz_world\
        └── test_gateway_adapter.py
```

**结构决策**: 采用现有 Python gateway + `hermes_cli\web_server.py` + React dashboard 结构。持久化账本放在 gateway 共享模块中, 由 gateway 写入、dashboard API 读取; 不改造 `SessionDB.messages` 为 envelope store, 因为它只保存 LLM 会话转录, 不保存完整 `MessageEvent.raw_message`、消费状态和投影状态。

## 复杂度跟踪

无章程违规需要豁免。
