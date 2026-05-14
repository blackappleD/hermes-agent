# 研究: OS_RUNTIME 日志监控视图

## Decision: 复用现有 dashboard `/logs` 页面作为入口

**Rationale**: 用户明确要求在日志页面右上角、自动刷新左侧增加 `OS_RUNTIME` 开关。现有 `LogsPage.tsx` 已经有 page header end controls、自动刷新 state、刷新按钮、日志筛选 toolbar 和日志 viewer，适合作为视图切换入口。

**Alternatives considered**:

- 新增侧边栏主导航页面: 与用户要求不符，也会割裂普通日志与 OS_RUNTIME raw line 核对流程。
- 只做 dashboard plugin slot: 入口可发现性弱，且用户要求 core 日志页开关。

## Decision: 新增只读 OS_RUNTIME 聚合 endpoint，而不是复用 `/api/logs` 的 raw lines 响应

**Rationale**: 普通 `/api/logs` 当前返回 `{file, lines}`，适合 raw 日志查看。OS_RUNTIME 模块视图需要模块快照、参数变化、空状态、解析错误、raw line 证据和来源文件；这些是新的响应形状。独立 endpoint 可以避免破坏普通日志契约，并让后端解析逻辑可单元测试。

**Alternatives considered**:

- 扩展 `/api/logs` 返回可选 `modules`: 会让普通日志 endpoint 语义变宽，增加现有前端和测试回归风险。
- 前端直接调用 `/api/logs?search=os_runtime` 后解析: React 组件会承担日志格式知识，难以测试，也无法读取 `os_runtime_YYYYMMDD.log` 这种动态文件。

## Decision: 优先解析 `os_runtime_YYYYMMDD.log` JSONL

**Rationale**: `agent.os_runtime.debug_log.log_pipeline_step()` 已经写入 profile-aware daily JSONL，字段包含 `timestamp`、`surface`、`session_id`、`phase`、`step`、`trace_id` 和 redacted `data`。这些字段正好能映射到生命状态、张力场、行动势能等模块，并且比普通 `agent.log` 文本更稳定。

**Alternatives considered**:

- 从 `agent.log` 文本中用正则抽取 OS_RUNTIME 参数: 普通日志格式不保证结构稳定，字段命名和上下文容易漂移。
- 新增数据库读模型: 超出用户的日志监控诉求，也会引入状态迁移和 schema 风险。

## Decision: 用宽松映射处理模块字段

**Rationale**: OS_RUNTIME 各模块已存在 dataclass `to_dict()` 输出，但实际 JSONL `data` 可能在不同阶段以 `life_state`、`tension_set`、`action_potential`、`state` 或摘要字段出现。聚合层应展示已知字段并标记缺失，而不是要求所有日志都完全一致。

**Alternatives considered**:

- 强校验固定 schema: 会让部分模块日志无法显示，和“raw line 保底”目标冲突。
- 完全不解析未知字段: 用户无法看到具体参数变化，只得到普通 raw log。

## Decision: 变化提示由相邻可比较快照计算

**Rationale**: 用户需要看到实时变化。后端在读取尾部日志时可以为同一模块保留最近两个可比较快照，对数值字段生成 up/down/unchanged，非数值字段显示 changed/unchanged。这样前端不需要保留跨刷新历史，也避免引入新持久化状态。

**Alternatives considered**:

- 前端保存上一轮响应进行 diff: 刷新、切换和页面重载后历史丢失，测试也更分散。
- 将 diff 状态持久化到服务端: 对只读日志观察过重，且违反“不新增持久化状态”的轻量目标。

## Decision: raw line 区域显示 OS_RUNTIME 相关原始行并独立滚动

**Rationale**: raw line 是模块化视图的证据来源，也覆盖无法解析的新字段。独立滚动能避免底部展开后破坏模块视图阅读。行数上限沿用日志页习惯，最大 500。

**Alternatives considered**:

- 始终展示全部 raw line: 会挤占模块信息，特别是在自动刷新时阅读体验差。
- 完全隐藏 raw line: 无法核对解析来源，也不满足用户明确要求。

## Decision: 不新增必需依赖

**Rationale**: 现有 Python 标准库足以完成 JSONL 解析和 tail；现有 dashboard 组件足以完成模块展示、开关、折叠和滚动。新增依赖不符合仓库“no new dependencies without explicit request”的工作协议。

**Alternatives considered**:

- 引入图表/时间序列库: 首版只需要最新值和变化提示，不需要持久趋势图。
- 引入日志解析库: JSONL 格式简单，标准库更可控。
