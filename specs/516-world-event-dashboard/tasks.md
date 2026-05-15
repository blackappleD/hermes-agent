# 任务: World Event Dashboard

**输入**: 来自 `D:\workspace\hermes-agent\specs\516-world-event-dashboard\` 的设计文档  
**前置条件**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts\world-event-dashboard.openapi.yaml`, `quickstart.md`

**测试策略**: 本功能涉及持久化、gateway 投影链路、Linz World/NATS 关联和 dashboard API, 属于项目章程中要求显式测试的高风险路径; 因此各用户故事包含先写测试任务。

**组织结构**: 任务按用户故事分组, 确保每个故事可以独立实施、独立验证并作为增量交付。

## 格式: `[ID] [P?] [Story] 描述`

- **[P]**: 可以并行运行(不同文件, 无依赖关系)
- **[Story]**: 用户故事标签, 仅用于用户故事阶段
- 每个任务描述包含确切文件路径

## 阶段 1: 设置(共享基础设施)

**目的**: 建立新功能的文件落点和测试落点, 不改变运行时行为。

- [X] T001 创建 gateway 投影账本模块骨架 `gateway\event_projection_store.py`, 定义公开类/函数占位符和模块级文档说明。
- [X] T002 [P] 创建 projection store 测试文件骨架 `tests\gateway\test_event_projection_store.py`, 包含隔离 Hermes home/profile 的测试辅助函数占位。
- [X] T003 [P] 创建 dashboard API 测试文件骨架 `tests\hermes_cli\test_web_server_world_events.py`, 复用现有 `hermes_cli\web_server.py` TestClient 测试模式。
- [X] T004 [P] 创建 dashboard 页面骨架 `web\src\pages\WorldEventsPage.tsx`, 导出空状态页面组件但不接入路由。

---

## 阶段 2: 基础(阻塞前置条件)

**目的**: 完成所有用户故事依赖的本地持久化账本基础能力。

**关键**: 在此阶段完成之前, 不开始用户故事实现。

- [X] T005 [P] 在 `tests\gateway\test_event_projection_store.py` 编写失败测试: store 使用 profile-scoped 路径初始化 SQLite schema, 空库查询返回 `records=[]` 和 `next_cursor=None`。
- [X] T006 [P] 在 `tests\gateway\test_event_projection_store.py` 编写失败测试: store 可关闭后重新打开并读取重启前记录, 验证跨 gateway/dashboard 重启持久化。
- [X] T007 在 `gateway\event_projection_store.py` 实现 profile-scoped SQLite 连接生命周期、schema 初始化、索引和关闭逻辑。
- [X] T008 在 `gateway\event_projection_store.py` 实现 `GatewayInboundEventRecord`, `HermesMessageEventProjection`, `EventProcessingTransition` 数据结构与 JSON 序列化/反序列化辅助函数。
- [X] T009 在 `gateway\event_projection_store.py` 实现基础 `list_records(limit=100)`, `get_record(record_id)`, `record_transition(record_id, ...)` 读写方法, 通过 T005-T006。

**检查点**: 本地账本可创建、可关闭重开、可保存基础记录, 现在可以开始用户故事任务。

---

## 阶段 3: 用户故事 1 - 排查世界事件投影链路 (优先级: P1) MVP

**目标**: 用户能在 dashboard 中查看 gateway 入站事件和 Hermes `MessageEvent` 的关联详情, 包括 Linz World/NATS 分类、重启后历史记录、失败/待处理/重复状态。

**独立测试**: 准备一条普通 gateway `MessageEvent` 和一条 Linz World/NATS 事件, 验证 dashboard API 列表可见、详情可见、Linz 分类可筛选、重启后仍可查询。

### 用户故事 1 的测试

- [X] T010 [P] [US1] 在 `tests\gateway\test_message_event_projection_ledger.py` 编写失败测试: 普通 `MessageEvent` 记录为 `source_category`, `message_event_id`, `payload_summary`, `projection_status=projected`, 并保存 session 引用。
- [X] T011 [P] [US1] 在 `tests\linz_world\test_gateway_adapter.py` 增加失败测试: Linz World/NATS 原始事件写入投影账本后保留 `source_category=linz_world_nats`, `subject`, `event_id`, `nats_sequence`, 完整 raw payload 和投影后的 `MessageEvent` 摘要。
- [X] T012 [P] [US1] 在 `tests\hermes_cli\test_web_server_world_events.py` 编写失败测试: `GET /api/gateway/message-events` 返回最新记录摘要且默认 limit 为 100。
- [X] T013 [P] [US1] 在 `tests\hermes_cli\test_web_server_world_events.py` 编写失败测试: `GET /api/gateway/message-events/{record_id}` 返回原始入站事件、投影 `MessageEvent`、状态转换和完整 raw payload; 缺失记录返回 404。

### 用户故事 1 的实施

- [X] T014 [US1] 在 `gateway\event_projection_store.py` 实现从 `gateway.platforms.base.MessageEvent` 和 `gateway.session.SessionSource` 提取 source snapshot、message summary、raw payload、media count、source category 的转换函数。
- [X] T015 [US1] 在 `gateway\event_projection_store.py` 实现 `record_message_event_received()`, `record_message_event_projected()`, `mark_handled()`, `mark_failed()`, `mark_duplicate()`, `mark_ignored()` 等生命周期写入方法。
- [X] T016 [US1] 在 `gateway\run.py` 的 `GatewayRunner._handle_message()` 和 `_handle_message_with_agent()` 路径中接入投影账本, 记录 received/projected/processing/handled/failed/unauthorized/ignored 状态且不改变现有消息处理行为。
- [X] T017 [US1] 在 `agent\linz_world\gateway_adapter.py` 接入投影账本写入, 在 `persist_world_event_for_gateway()` 或 `dispatch_world_event()` 中把 Linz raw event 与生成的 `MessageEvent` 关联到同一个 record。
- [X] T018 [US1] 在 `agent\linz_world\event_bus.py` 调整 Linz World 投影元数据, 确保 `raw_message` 含有 dashboard 需要的 `event_id`, `audit_ref`, `subject`, `event_type`, `sequence_key`, `nats_sequence`, `os_id`, `soul_id`。
- [X] T019 [US1] 在 `hermes_cli\web_server.py` 添加只读 API `GET /api/gateway/message-events` 和 `GET /api/gateway/message-events/{record_id}`, 响应字段匹配 `specs\516-world-event-dashboard\contracts\world-event-dashboard.openapi.yaml`。
- [X] T020 [US1] 在 `web\src\lib\api.ts` 添加 `GatewayMessageEvent` 列表/详情 TypeScript 类型和 `api.getGatewayMessageEvents()`, `api.getGatewayMessageEventDetail()` 方法。
- [X] T021 [US1] 在 `web\src\App.tsx` 注册 `/events` 内置路由和侧边栏导航入口, 使用不会卸载 `/chat` 持久 PTY host 的现有路由模式。
- [X] T022 [US1] 在 `web\src\pages\WorldEventsPage.tsx` 实现 MVP 列表和详情视图: 展示消费时间、事件标识、subject、event type、来源摘要、消费状态、投影状态、关联 `MessageEvent` 标识和详情 payload 展开区。
- [X] T023 [US1] 运行并修复 `tests\gateway\test_message_event_projection_ledger.py`, `tests\linz_world\test_gateway_adapter.py`, `tests\hermes_cli\test_web_server_world_events.py` 中 US1 相关失败。

**检查点**: 用户故事 1 可独立演示: dashboard 能看到入站事件到 `MessageEvent` 的关联详情, Linz World/NATS 可被识别, 重启后记录仍存在。

---

## 阶段 4: 用户故事 2 - 筛选和定位问题事件 (优先级: P2)

**目标**: 用户能按状态、时间、来源分类、来源、subject、event type 和关键字定位问题事件, 默认最近 100 条并支持分页/加载更多。

**独立测试**: 准备不同状态、来源分类、时间范围和 subject/event type 的记录, 调整筛选条件后验证列表只显示匹配记录; 清除筛选恢复默认最近 100 条; 加载更多保持筛选条件。

### 用户故事 2 的测试

- [X] T024 [P] [US2] 在 `tests\gateway\test_event_projection_store.py` 编写失败测试: `list_records()` 支持 `source_category`, `consume_status`, `projection_status`, `subject`, `event_type`, `q`, `from`, `to` 过滤。
- [X] T025 [P] [US2] 在 `tests\gateway\test_event_projection_store.py` 编写失败测试: cursor/load-more 基于 `(consumed_at, record_id)` 稳定分页, 新记录插入后不会重复返回已加载记录。
- [X] T026 [P] [US2] 在 `tests\hermes_cli\test_web_server_world_events.py` 编写失败测试: API 查询参数校验 limit 上限、非法状态返回 400、合法筛选返回匹配记录和 `next_cursor`。

### 用户故事 2 的实施

- [X] T027 [US2] 在 `gateway\event_projection_store.py` 实现筛选查询、全文-like 搜索、时间范围查询、cursor 编解码和 `next_cursor` 生成。
- [X] T028 [US2] 在 `hermes_cli\web_server.py` 实现 `/api/gateway/message-events` 查询参数解析、状态枚举校验、limit 边界处理和错误响应。
- [X] T029 [US2] 在 `web\src\lib\api.ts` 扩展 `api.getGatewayMessageEvents()` 参数类型, 支持 source category、状态、subject、event type、关键字、时间范围和 cursor。
- [X] T030 [US2] 在 `web\src\pages\WorldEventsPage.tsx` 实现筛选 toolbar: 来源分类、消费状态、投影状态、subject、event type、关键字搜索和清除筛选操作。
- [X] T031 [US2] 在 `web\src\pages\WorldEventsPage.tsx` 实现默认最近 100 条、加载更多、保留筛选条件的分页行为以及无匹配空状态。
- [X] T032 [US2] 运行并修复 `tests\gateway\test_event_projection_store.py` 和 `tests\hermes_cli\test_web_server_world_events.py` 中 US2 相关失败。

**检查点**: 用户故事 1 和 2 均可独立验证: 页面可以查看事件详情, 也可以快速筛选定位异常事件。

---

## 阶段 5: 用户故事 3 - 保持 dashboard 视觉与操作一致 (优先级: P3)

**目标**: 新页面与现有 Logs/OS_RUNTIME dashboard 视觉和操作一致, 包括高密度暗色布局、状态标签、刷新入口、自动刷新开关、响应式布局和长 payload 展开体验。

**独立测试**: 在同一浏览器中切换 Logs/OS_RUNTIME 与事件投影视图, 验证导航、控件密度、刷新行为和响应式布局一致; 桌面宽屏与较窄视口无文本重叠。

### 用户故事 3 的测试

- [X] T033 [P] [US3] 在 `web\src\pages\WorldEventsPage.tsx` 添加本地可视状态数据分支或 mockable render helpers, 支持手动检查 loading/error/empty/records/detail/payload-expanded 状态。
- [X] T034 [P] [US3] 在 `specs\516-world-event-dashboard\quickstart.md` 扩展视觉验证清单, 明确桌面宽屏、窄视口、自动刷新、payload 展开和 `/chat` 切换检查项。

### 用户故事 3 的实施

- [X] T035 [US3] 在 `web\src\pages\WorldEventsPage.tsx` 使用 `usePageHeader`, `Button`, `Switch`, `Segmented`, `Badge`, `Card` 复用 `web\src\pages\LogsPage.tsx` 的刷新/自动刷新/状态呈现模式。
- [X] T036 [US3] 在 `web\src\pages\WorldEventsPage.tsx` 实现 5 秒自动刷新开关、最近刷新时间、数据来源状态 badge 和刷新失败提示。
- [X] T037 [US3] 在 `web\src\pages\WorldEventsPage.tsx` 实现响应式列表/详情布局, 为长 subject、event type、payload、错误摘要使用 wrapping、scroll container 或 expandable section 防止重叠。
- [X] T038 [US3] 在 `web\src\i18n\types.ts`, `web\src\i18n\en.ts`, `web\src\i18n\zh.ts`, `web\src\i18n\zh-hant.ts`, `web\src\i18n\af.ts`, `web\src\i18n\de.ts`, `web\src\i18n\es.ts`, `web\src\i18n\fr.ts`, `web\src\i18n\ga.ts`, `web\src\i18n\hu.ts`, `web\src\i18n\it.ts`, `web\src\i18n\ja.ts`, `web\src\i18n\ko.ts`, `web\src\i18n\pt.ts`, `web\src\i18n\ru.ts`, `web\src\i18n\tr.ts`, `web\src\i18n\uk.ts` 添加事件投影视图导航和页面文本; 非中文 locale 可使用英文 fallback 文案保持类型完整。
- [X] T039 [US3] 在 `web\src\App.tsx` 确认 `/events` 页面切换不挂载或覆盖 `ChatPage` 持久 host, 并保持 plugin override/hidden route 逻辑不受影响。
- [X] T040 [US3] 运行并修复 `web\src\pages\WorldEventsPage.tsx`, `web\src\App.tsx`, `web\src\lib\api.ts`, `web\src\i18n\types.ts` 相关的 `cd web; npm run build; npm run lint` 失败。

**检查点**: 页面视觉与 dashboard 统一, 自动刷新和手动刷新行为一致, 响应式布局可读。

---

## 阶段 6: 完善与横切关注点

**目的**: 完成端到端验证、性能/边界检查和文档收口。

- [X] T041 [P] 在 `tests\gateway\test_event_projection_store.py` 增加大样本测试: 插入 150 条记录后默认查询只返回最近 100 条且耗时在合理本地测试范围内。
- [X] T042 [P] 在 `tests\hermes_cli\test_web_server_world_events.py` 增加边界测试: 无记录、监听状态未知、raw payload 不可序列化时 API 返回可读状态而非 500。
- [X] T043 在 `gateway\event_projection_store.py` 确认 raw payload 序列化失败时保存 `raw_payload_available=false` 和 `raw_payload_error`, 不阻断 gateway 消息处理。
- [X] T044 在 `hermes_cli\web_server.py` 确认 API 仅读取本地投影账本和 runtime status, 不新增 replay/delete/publish 等副作用端点。
- [X] T045 在 `specs\516-world-event-dashboard\quickstart.md` 记录最终验证命令和任何无法自动化的视觉检查结果。
- [X] T046 运行完整聚焦验证命令 `python -m pytest tests\gateway\test_event_projection_store.py tests\gateway\test_message_event_projection_ledger.py tests\hermes_cli\test_web_server_world_events.py tests\linz_world\test_gateway_adapter.py` 并修复相关文件失败。
- [X] T047 运行前端验证命令 `cd web; npm run build; npm run lint` 并修复 `web\src` 相关文件失败。

---

## 依赖关系与执行顺序

### 阶段依赖关系

- **阶段 1 设置**: 无依赖, 可立即开始。
- **阶段 2 基础**: 依赖阶段 1, 阻塞所有用户故事。
- **阶段 3 US1**: 依赖阶段 2, 是 MVP。
- **阶段 4 US2**: 依赖阶段 2, 可在独立分支/人员中与 US1 后半部分并行, 但最终需要 US1 的基础 API/page 接入点。
- **阶段 5 US3**: 依赖阶段 3 的页面/API 存在, 可在 US2 后或与 US2 前端收尾并行协调。
- **阶段 6 完善**: 依赖计划内目标用户故事完成。

### 用户故事依赖关系

- **US1(P1)**: 无其他故事依赖; 交付 MVP。
- **US2(P2)**: 依赖投影账本和列表 API, 但筛选/分页可独立测试。
- **US3(P3)**: 依赖页面存在; 不改变后端数据语义。

### 每个用户故事内部

- 测试任务先于实现任务。
- Store 数据结构先于 gateway/API/page 集成。
- API client 类型先于页面数据加载。
- 页面功能先于视觉/响应式收口。
- 每个检查点后都可以独立验证该故事。

### 并行机会

- T002-T004 可并行创建测试/page 骨架。
- T005-T006 可并行写 store 基础失败测试。
- T010-T013 可并行写 US1 的 gateway/Linz/API 失败测试。
- T024-T026 可并行写 US2 的 store/API 筛选失败测试。
- T033-T034 可并行准备 US3 的可视状态与 quickstart 检查清单。
- T041-T042 可并行补充边界/性能测试。

---

## 并行示例: 用户故事 1

```text
任务: "在 tests\gateway\test_message_event_projection_ledger.py 编写普通 MessageEvent 投影账本失败测试"
任务: "在 tests\linz_world\test_gateway_adapter.py 编写 Linz World/NATS 投影账本失败测试"
任务: "在 tests\hermes_cli\test_web_server_world_events.py 编写列表 API 失败测试"
任务: "在 tests\hermes_cli\test_web_server_world_events.py 编写详情 API 失败测试"
```

## 并行示例: 用户故事 2

```text
任务: "在 tests\gateway\test_event_projection_store.py 编写筛选查询失败测试"
任务: "在 tests\gateway\test_event_projection_store.py 编写 cursor/load-more 分页失败测试"
任务: "在 tests\hermes_cli\test_web_server_world_events.py 编写 API 查询参数失败测试"
```

## 并行示例: 用户故事 3

```text
任务: "在 web\src\pages\WorldEventsPage.tsx 添加可视状态分支或 mockable render helpers"
任务: "在 specs\516-world-event-dashboard\quickstart.md 扩展视觉验证清单"
```

---

## 实施策略

### 仅 MVP(用户故事 1)

1. 完成阶段 1 设置。
2. 完成阶段 2 基础账本。
3. 完成阶段 3 US1。
4. 运行 US1 聚焦测试并手动确认 dashboard 可以查看事件详情。
5. 暂停并演示: 已能回答“是否收到、是否投影、是否失败、对应 MessageEvent 是什么”。

### 增量交付

1. 设置 + 基础账本。
2. US1: 事件投影链路可见。
3. US2: 筛选、搜索、分页和加载更多。
4. US3: 视觉一致性、自动刷新和响应式细节。
5. 阶段 6: 边界、性能、quickstart 验证。

### 并行团队策略

1. 共同完成阶段 1-2。
2. 后端人员处理 US1/US2 的 `gateway\event_projection_store.py`, `gateway\run.py`, `hermes_cli\web_server.py`。
3. Linz 集成人员处理 `agent\linz_world\gateway_adapter.py`, `agent\linz_world\event_bus.py`, `tests\linz_world\test_gateway_adapter.py`。
4. 前端人员处理 `web\src\pages\WorldEventsPage.tsx`, `web\src\App.tsx`, `web\src\lib\api.ts`, `web\src\i18n\*`。
5. 每个故事检查点独立验证后再合并。

---

## 注意事项

- 不新增必需依赖; 使用 stdlib `sqlite3` 和现有 dashboard 组件。
- 投影账本必须使用 `get_hermes_home()` 做 profile-scoped 状态。
- 完整 raw payload 只在详情中显式展开显示; 列表只显示摘要。
- API 保持只读, 不实现重投递、删除、修改或外部发布。
- 不重写 dashboard `/chat` 或嵌入式 TUI; 新页面只作为旁路排查视图。
