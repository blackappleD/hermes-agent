# 功能规范: 正式框架实验脚本

**功能分支**: `feat/118-formal-experiment-scripts`  
**Spec-Kit feature key**: `118-formal-experiment-scripts`  
**创建时间**: 2026-05-18  
**状态**: 草稿  
**输入**: Issue OPE-118、`docs/共博自制框架实验准备.md`、现有 Linz World / gateway / os_runtime / evidence 代码

## 背景

`docs/共博自制框架实验准备.md` 已定义 P0-P5 实验目标、人格种子、事件脚本库、观察变量和判定口径。当前缺口是：实验人员无法用一套正式脚本在 Hermes 已安装、Linz World 已登录、gateway/os_runtime 已运行的环境中复现这些阶段，并把真实运行产物导出为可分析数据。

本需求不是 mock backend 验证，也不是离线伪造 transition。脚本必须走 Linz World governance/authorization/catalog/publisher、gateway 投影账本、os_runtime 事件仓库/日志和 evidence 链路；当正式 runtime 没有产生数据时，必须输出 anomaly，而不是补假值。

## 目标

- 新增正式实验脚本，支持 `prepare`、`run`、`export` 三个阶段，覆盖 P0-P5 或单阶段执行。
- `prepare` 在发布任何事件前 fail-closed 检查 Hermes profile、Linz 登录/授权、gateway/Linz 平台状态、os_runtime 配置、数据库和日志路径。
- `run` 使用正式 Linz World event catalog 允许的 `subject` / `event_type` 发布或接收事件，支持 P1 单事件重复和阶段间延迟。
- `export` 只从真实运行产物导出数据：`gateway/message_events.db`、`logs/os_runtime_YYYYMMDD.log`、`linz_world/state.json`、`state.db` 中 os_runtime/evidence side table。
- 输出 `experiment/results/<run_id>/` 数据集，包含 manifest、events、transitions、raw runtime、summary、CSV 和 anomalies。
- 新增文档说明脚本顺序、参数含义、最小可运行示例和 fail-closed 诊断。

## 非目标

- 不实现 mock backend、离线 transition 生成器或用于演示的假数据导出。
- 不新增第二套 Linz World 发布/订阅通道；正式事件必须复用现有 `agent.linz_world.publisher.publish_event()` 或 Hermes CLI 等价路径。
- 不绕过 `agent.linz_world.event_catalog`、authorization map、governance preflight、gateway projection ledger、os_runtime adapter 或 evidence redaction。
- 不实现前端监控页面、图表设计或 dashboard 可视化。
- 不迁移现有 `state.db` / `message_events.db` schema，除非 Builder 发现必要且能保持兼容。

## 需求理解

实验人员的主要流程是：安装 Hermes WSL 原生环境，完成 `hermes setup linz`、`hermes linz login`、`hermes linz map`，启动 `hermes gateway`，再在另一个 shell 运行实验脚本。脚本应能证明正式链路可用，并把 P0-P5 的事件、投影、runtime transition、生命状态、张力场、行动势能、SelfPrompt、OpenIntent、裁判、行动/evidence 结果串成一份可追溯数据集。

仓库中的正式 catalog 当前以 `agent/linz_world/event_catalog.py` 为准，例如市场需求事件应映射为 `subject=wsp.mrk.requirement.published`、`event_type=requirement.published`，直接 inbox 聊天使用 `subject=wsp.<target_os_id>`、`event_type=wsp.chat.message.sent`。文档中的旧式 `mrk.*` 或 `linz.*` 示例只能作为实验语义来源，不能原样绕过 catalog。

## 用户场景与测试

### 用户故事 1 - 运行前正式环境检查 (优先级: P1)

作为实验人员，我希望在执行事件前确认 profile、Linz 登录、授权 map、gateway、Linz 平台、os_runtime、数据库和日志路径都可用，以免把环境问题误判为框架行为。

**独立测试**: 用临时 Hermes home 和 fake status/DB/log fixture 调用 prepare 逻辑，分别覆盖登录缺失、授权 map 缺失、gateway 离线、os_runtime 产物缺失和通过场景。

**验收场景**:

1. **给定** Linz 未登录或 `authorization_state` 不是 current，**当** 运行 prepare，**那么** 退出码非零并输出具体缺失项。
2. **给定** gateway 未运行或 Linz World 平台未 enabled/online，**当** 运行 prepare，**那么** 脚本不发布事件并提示先启动 `hermes gateway`。
3. **给定** `gateway/message_events.db`、`state.db` 或 `logs/` 路径不可访问，**当** 运行 prepare，**那么** 输出路径诊断和修复建议。

### 用户故事 2 - 执行正式实验阶段 (优先级: P1)

作为实验人员，我希望按 P0-P5 或 `all` 执行事件流程，并能通过 `--repeat`、`--run-id`、`--target-os-id`、`--seed-id` 控制阶段上下文。

**独立测试**: 用 fake publisher 和 catalog 验证每个阶段生成的事件均通过 `is_formal_event()`，dry-run 不发布，非法 subject/event_type fail-closed，P1 repeat 生成 3 次可区分事件。

**验收场景**:

1. **给定** `--phase P1 --repeat 3`，**当** 运行脚本，**那么** 发布三次单事件扰动，每次带同一 `run_id` 和不同 `scenario_id` / sequence。
2. **给定** `--phase all`，**当** 执行环境权限不足以覆盖某阶段，**那么** 脚本标记该阶段 blocked/anomaly，而不是改用 mock 事件。
3. **给定** 事件不在正式 catalog 或 governance preflight 拒绝，**当** run 尝试发布，**那么** 退出非零并保留诊断 receipt。

### 用户故事 3 - 导出真实运行数据 (优先级: P1)

作为实验分析者，我希望按 `run_id` 和时间窗口导出 events、transitions、os_runtime raw、summary、CSV 和 anomalies，用于复盘 P0-P5 的机制表现。

**独立测试**: 构造真实格式的 `EventProjectionStore`、`OSRuntimeEventRepository`、os_runtime JSONL log 和 Linz state fixture，验证导出字段、脱敏、缺失 transition anomaly 和 CSV summary。

**验收场景**:

1. **给定** run 已产生 gateway projection 和 os_runtime events，**当** export 执行，**那么** 输出目录包含 `manifest.json`、`events.jsonl`、`transitions.jsonl`、`os_runtime_raw.jsonl`、`summary.json`、`summary.csv`、`anomalies.json`。
2. **给定** gateway 有事件但 os_runtime 没有对应 transition，**当** export 执行，**那么** `anomalies.json` 标记 `missing_transition`，不在 `transitions.jsonl` 伪造字段。
3. **给定** 原始 payload 或日志包含 token/api_key/password/private_key/authorization，**当** export 写普通结果文件，**那么** 明文秘密不会出现。

### 用户故事 4 - 使用文档与交接 (优先级: P2)

作为后续实验人员或 Builder，我需要文档明确脚本顺序、参数、示例、输出字段和常见失败诊断，便于复现实验。

**独立测试**: 按文档命令执行 `--dry-run` 和 prepare fixture，确认参数名、默认值和顺序与脚本实现一致。

## 需求

### 功能需求

- **FR-001**: 系统必须新增正式脚本入口，建议为 `scripts/linz-world/formal_experiment_prepare.sh`、`scripts/linz-world/formal_experiment_run.sh`、`scripts/linz-world/formal_experiment_export.py`；如 Builder 合并入口，也必须保留同等子命令能力。
- **FR-002**: 所有脚本必须支持 `--profile` 和 `--hermes-home`，默认解析当前 profile 的 `get_hermes_home()`，不得隐式读取错误 profile。
- **FR-003**: prepare 必须检查 Linz identity/login/auth map、gateway runtime state、Linz World gateway platform state、`gateway/message_events.db`、`state.db`、`logs/os_runtime_*.log` 路径和 os_runtime 配置。
- **FR-004**: run 必须支持 `--phase P0|P1|P2|P3|P4|P5|all`、`--run-id`、`--repeat`、`--dry-run`、`--target-os-id`、`--seed-id`、`--persona`。
- **FR-005**: run 必须在发布前使用 `agent.linz_world.event_catalog.is_formal_event()` 校验 catalog，并拒绝 `linz.*`、`skill.*`、`legacy.*` 或未授权事件。
- **FR-006**: run 必须通过正式 Linz World publish/governance/authorization 路径发布事件；直接 inbox 事件必须使用 `wsp.<target_os_id>` subject 和允许的 chat event type。
- **FR-007**: P1 必须支持单事件重复和间隔，以观察扰动方向、幅度和衰减。
- **FR-008**: P4/P5 必须记录多轮演化和多元神交互上下文；权限不足时标记 blocked/anomaly。
- **FR-009**: export 必须从真实产物读取 gateway projection、os_runtime state/log、Linz state/receipts 和 evidence，不得从脚本内存或 mock 结果生成正式数据。
- **FR-010**: export 必须支持 `--since`、`--until`、`--output-root`、`--fail-on-anomaly`，并按 `run_id` 过滤或关联事件。
- **FR-011**: 输出字段至少覆盖 issue 要求的 run、phase、scenario、seed/persona、event、subject/event_type、payload summary、audit refs、MessageEvent projection、runtime transition、life/tension/action/self_prompt/open_intent/arbitration/action/evidence、stop reason 和 anomaly。
- **FR-012**: 普通结果文件必须脱敏 token、api_key、password、private_key、authorization 和 restricted raw payload；完整原始引用只能以 hash/ref/audit_ref 表达。
- **FR-013**: 当正式 runtime 没有对应模块数据，export 必须写 anomaly 并在 `summary.json` 中计数；不得填默认假值。
- **FR-014**: 文档必须包含安装后使用顺序、参数说明、示例命令、输出目录说明和常见失败诊断。

### 关键实体

- **FormalExperimentRun**: 一次正式实验运行，包含 `run_id`、profile、hermes_home、phase set、seed/persona、时间窗口、脚本版本和环境检查结果。
- **FormalScenario**: P0-P5 中可执行的一个事件或事件序列，包含 `phase`、`scenario_id`、formal subject/event_type、payload template、expected observation 和 required capability。
- **PublishedFormalEvent**: 通过 Linz publisher/governance 产生的 receipt 或 blocked result，带 `world_event_id`、request id、audit ref、payload summary 和 run metadata。
- **RuntimeTransitionExport**: 从 os_runtime event/log/evidence 聚合出的正式 transition，不存在时只能生成 anomaly。
- **ExperimentAnomaly**: 环境、权限、catalog、publish、projection、runtime 或 export 缺失的结构化异常记录。

## 建议方案

- 建议新增共享 Python 模块 `scripts/linz-world/formal_experiment_lib.py` 承载参数解析、Hermes home 解析、scenario catalog、redaction、DB/log 读取和 summary 聚合；shell 脚本只做环境激活友好的薄入口。
- prepare 直接复用 `agent.linz_world.status.status_summary()`、`gateway.status.read_runtime_status()`、`gateway.event_projection_store.EventProjectionStore` 和 `agent.os_runtime.adapters.session_store.OSRuntimeEventRepository` 做只读检查。
- run 将 `docs/共博自制框架实验准备.md` 的语义事件映射到正式 catalog；每个 payload 写入 `run_id`、`phase`、`scenario_id`、`seed_id/persona`、`sequence` 和 `published_at`，便于 export 关联。
- export 优先通过 repository/store API 读取；缺 API 的部分可只读 SQLite/JSONL，但必须保持 profile-scoped 路径和脱敏。
- summary 聚合以 “真实字段优先、缺失即 anomaly” 为原则；`transitions.jsonl` 不应包含脚本计算出的假 life_state/tension/action 值。

## 修改范围

- 新增 `scripts/linz-world/formal_experiment_prepare.sh`
- 新增 `scripts/linz-world/formal_experiment_run.sh`
- 新增 `scripts/linz-world/formal_experiment_export.py`
- 可新增 `scripts/linz-world/formal_experiment_lib.py` 或等价共享模块
- 新增文档，建议 `docs/formal-experiment-scripts.md`
- 新增测试，建议 `tests/scripts/test_formal_experiment_prepare.py`、`tests/scripts/test_formal_experiment_run.py`、`tests/scripts/test_formal_experiment_export.py`
- 不修改核心业务链路，除非 Builder 发现脚本无法通过现有只读 API 访问必要数据；如需补薄 API，必须保持兼容并补测试。

## 关键设计

- **正式 catalog 边界**: 脚本内 scenario catalog 必须以 `agent.linz_world.event_catalog` 为最终校验，不以文档旧字段为准。
- **Fail-closed 边界**: 登录、授权、gateway、catalog、publisher、projection 或 runtime 数据缺失时阻断发布或标记 anomaly，不能降级 mock。
- **Profile 边界**: 所有路径通过 `--hermes-home` 或 profile-aware helper 解析；结果 manifest 必须记录实际读取路径。
- **Trace 边界**: `run_id`、`phase`、`scenario_id`、`event_id`、`world_event_id`、`message_event_id`、`trace_id`、`session_id` 必须尽量串联。
- **脱敏边界**: 普通 JSONL/CSV 只保存 bounded summary、hash、audit_ref 或 content_ref；原始密钥类字段禁止落盘。
- **可复现边界**: `--dry-run` 只打印将发布的正式事件和检查结果，不调用 publisher。

## 风险与取舍

- **文档事件名与 formal catalog 不一致**: 以代码 catalog 为准，并在脚本文档列出映射；无法映射的场景标记 blocked。
- **运行环境不可控**: prepare 拆出明确诊断，避免 run/export 把环境失败解释为框架异常。
- **权限不足导致 P4/P5 不完整**: `all` 允许阶段 blocked/anomaly，但必须报告缺失的 capability/authorization。
- **runtime 数据粒度不稳定**: export 从现有 os_runtime event/log/evidence 中提取可用字段；缺字段进入 anomaly，不制造默认值。
- **敏感数据泄露**: 复用现有 redaction helpers，并对导出文件做测试级扫描。

## 验收标准

- **AC-001**: 按文档顺序执行后，至少 P1 能基于正式 Hermes/gateway/os_runtime 运行并导出真实数据。
- **AC-002**: `--phase all` 覆盖 P0-P5 的正式事件流程，或明确列出因权限/环境缺失而 blocked 的阶段。
- **AC-003**: 输出目录包含 `manifest.json`、`events.jsonl`、`transitions.jsonl`、`os_runtime_raw.jsonl`、`summary.json`、`summary.csv`、`anomalies.json`。
- **AC-004**: `transitions.jsonl` 中真实存在的记录包含 life_state、tension_field/tension_set、action_potential、self_prompt、open_intent、arbitration 和 evidence/action 相关字段；缺失项进入 anomalies。
- **AC-005**: 关闭 gateway 或退出 Linz 登录后，prepare/run/export 失败或 anomaly 诊断明确，不发布正式事件。
- **AC-006**: 文档包含完整使用方法、参数说明和最小可运行示例。

## 测试计划

- 单元测试 prepare：fake Linz status、gateway status、profile home、DB/log 路径，覆盖通过和 fail-closed。
- 单元测试 run：P0-P5 scenario 生成、formal catalog 校验、dry-run、P1 repeat、非法事件拒绝、publisher receipt 记录。
- 单元测试 export：SQLite fixture、JSONL fixture、Linz state fixture、run_id/time 过滤、缺 transition anomaly、`--fail-on-anomaly` 非零退出。
- 安全测试：扫描导出文件，确认 token/api_key/password/private_key/authorization 原值不出现。
- 文档验证：执行文档中的 `--dry-run` 示例和 prepare fixture。
- 聚焦回归：`pytest tests/scripts/test_formal_experiment_prepare.py tests/scripts/test_formal_experiment_run.py tests/scripts/test_formal_experiment_export.py`。

## 后续交接说明

Builder Agent 应先实现共享数据模型、redaction 和 prepare 检查，再实现 dry-run + P1 run，最后扩展 P0-P5/all 与 export 聚合。实现期间不得把 mock 数据写入正式结果；如发现现有正式链路无法暴露必要字段，应在同一分支评论 BLOCKED 或请求 Planner 更新 spec。
