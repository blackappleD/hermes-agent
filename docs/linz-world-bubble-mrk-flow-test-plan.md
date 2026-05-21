# Linz World 泡泡协议 MRK 全流程测试计划

日期：2026-05-19  
状态：草案  
目标脚本：`scripts/linz-world/linz_bubble_mrk_flow_test.py`

## 1. 目标

实现一个可重复运行的集成测试脚本，验证 Hermes 基于 linz-world 泡泡协议的 MRK 完整使用流程，并导出包含每一步运行结果的测试报告。

MRK 流程必须使用两个不同的元神：

- 需求发布方：发布需求、审核交付、确认需求验收。
- 需求接收方：接收需求、挂载自身 AgentBubble、提交成果、发起交付。

测试脚本的第一步必须检查 Hermes profiles。若只有一个可用 profile，脚本必须创建并注册第二个 Linz World 元神；创建时必须复制默认配置，等价于 Dashboard `/profiles` 页面点击“创建元神”并勾选“Clone config from default profile”。若已有多个 profiles，脚本选择一个作为发布方、一个作为接收方，并在报告中记录选择结果。

本计划区分两类测试，二者都保留：

- **Smoke 测试**：脚本直接编排 Linz publish / `linz_bubble_*` 工具，验证 Bubble 协议和 MRK 后端状态机可用。该模式用于快速发现后端、配置、权限和工具适配问题，但不能证明元神真实自主协作。
- **真实流程测试**：脚本只提供外部输入需求，并启动/检查必要 gateway；需求发布、接单、任务处理、交付和验收必须由 Hermes 元神通过真实 LLM turn、gateway 消费和工具调用完成。脚本只能读取 gateway ledger、session JSONL 和 Bubble snapshot 做观察，不能直接调用 mutating Bubble 工具推进业务状态。

测试需求内容必须是具体可交付任务，例如“开发 JSONL 事件统计脚本”，并包含交付物、输入输出、验收字段和运行方式要求；不得把“请接收方完成 MRK/Bubble 协作流程”这类测试说明当作业务需求发布给接收方。

Smoke 测试把 MRK 作为主路径，把直接 Bubble API 作为观测和辅助校验路径：

- MRK 主路径：需求发布、接单、交付、验收、结算通知。
- 泡泡辅助校验：读取 DemandBubble / TaskBubble snapshot，验证生命周期、挂载、行为事件、残留摘要。
- Hermes 侧校验：验证双 profile 工具返回、receipt、event_state、os_runtime 审计投影和敏感信息脱敏。

## 2. 范围

覆盖：

- Linz World 身份、登录、授权、配置预检。
- 双 profile / 双元神发现、选择和必要时补齐。
- 发布方发出原始 `mrk.requirement.published`；Linz World MRK 模块落库后派生 `mrk.requirement.published.broadcast` 或 `wsp.mrk.requirement.published` 通知。
- 接收方发出 `mrk.order.accepted` 到 DemandBubble 激活和默认 TaskBubble 创建。
- TaskBubble 挂载接收方 Hermes AgentBubble。
- 接收方通过 `linz_bubble_submit_artifact` 提交代码或文档成果。
- 接收方触发 `mrk.order.handover.delivered`，发布方完成 TaskBubble 验收。
- 接收方提交 DemandBubble 交付总结，发布方完成需求验收。
- `mrk.settlement.completed` / `mrk.settlement.failed` 通知观测。
- 每一步生成结构化结果并汇总为测试报告。

不覆盖：

- linz-world 后端状态机单元测试。
- 未进入正式事件目录的 `bubble.*` NATS 事件。
- 真实 EC 转账发起；结算只观测 MRK/settlement 事件和泡泡残留引用。
- Smoke 模式不覆盖 LLM 自主决策正确性评测；脚本调用确定性工具和事件发布接口。
- 真实模式覆盖“是否发生真实 LLM/tool/gateway 行为”，但不保证模型每次都做出正确商业决策；失败时必须保留完整证据。

## 3. 前置条件

运行前必须满足：

- 至少存在一个可用 Hermes profile。
- 发布方和接收方最终必须是两个不同 profile，且两个 profile 都有不同的 Linz World `os_id` / `soul_id`。
- 两个 profile 都已完成 Linz World 注册、登录和授权图刷新。
- 两个 profile 的 `hermes linz map` 都能拿到各自所需权限：
  - 发布方：发布需求、审核交付、需求验收、结算通知观测。
  - 接收方：接单、挂载、提交成果、提交交付总结。
- `linz_world.bubble.enabled=true`。
- 写操作测试必须显式开启：

```yaml
linz_world:
  bubble:
    read_only: false
    allow_mutations: true
    require_approval_for_mutations: true
```

脚本默认 fail-closed：

- 任一参与 profile 未登录、未授权、远端不可达、配置仍为只读时，脚本只执行可完成的 preflight，并输出 `BLOCKED` 报告。
- 默认不静默修改已有 profile 配置。
- 只有一个 profile 时，脚本必须创建接收方 profile；创建必须 `clone_from_default=true`，并注册为新的 Linz World 元神。
- 所有写操作都传入 `confirm_mutation=true`，并在报告里记录该确认来自脚本参数。

推荐的补齐策略：

- 优先复用已有两个已注册、已登录、授权可用的 profiles。
- 如果只有 `default`，自动创建 `bubble-mrk-receiver-<run_id>`，`clone_from_default=true`，并使用与默认 profile 不同的 `persona_seed` 注册新元神。
- 如果 Dashboard 正在运行，可调用 `POST /api/profiles/linz-world-spirit`；否则脚本应复用同等后端逻辑，等价于 `hermes_cli.profiles.create_profile(..., clone_from="default", clone_config=True)` 加 Linz World 注册/登录。

## 4. 脚本接口

建议命令：

```bash
python scripts/linz-world/linz_bubble_mrk_flow_test.py run \
  --publisher-profile default \
  --receiver-profile bubble-mrk-worker \
  --run-id bubble-mrk-001 \
  --output-root experiment/results \
  --confirm-mutations \
  --auto-create-receiver
```

真实流程命令：

```bash
python scripts/linz-world/linz_bubble_mrk_flow_test.py real \
  --publisher-profile default \
  --receiver-profile bubble-mrk-worker \
  --run-id real-bubble-mrk-001 \
  --output-root experiment/results \
  --confirm-mutations \
  --start-missing-gateways
```

建议参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `run` | 必填子命令 | 执行完整流程 |
| `--publisher-profile` | `default` | 需求发布方 profile |
| `--receiver-profile` | 自动选择或创建 | 需求接收方 profile，必须不同于发布方；未指定时选择第一个可用非发布方 profile |
| `--auto-create-receiver` | true | profiles 不足两个时自动创建并注册接收方元神 |
| `--receiver-agent-name` | `bubble-mrk-worker-<run_id>` | 自动创建接收方元神时使用的 Linz World agent name |
| `--receiver-persona-seed` | 自动生成 | 自动创建接收方元神时使用，必须不同于发布方 persona seed |
| `--clone-config-from-default` | true | 自动创建接收方时复制 default 配置；必须保持 true |
| `--hermes-home` | 空 | 仅用于解析发布方 profile 根目录；双 profile 场景优先使用 profile 解析 |
| `--run-id` | 自动生成 | 本次测试唯一 ID，写入 payload 和报告路径 |
| `--output-root` | `experiment/results` | 报告输出根目录 |
| `--confirm-mutations` | false | 允许脚本执行远端泡泡写操作 |
| `--dry-run` | false | 只生成步骤和 payload，不发布、不写远端 |
| `--skip-settlement` | false | 跳过结算通知观测 |
| `--timeout-seconds` | 120 | 每个远端状态等待上限 |
| `--poll-interval` | 3 | snapshot / event 轮询间隔 |

真实流程额外参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `real` | 必填子命令 | 执行真实 agent/gateway 流程测试 |
| `--start-missing-gateways` | true | profile gateway 未在线时由脚本启动前台 gateway 子进程 |
| `--keep-started-gateways` | false | 保留脚本启动的 gateway；默认测试结束后只停止脚本自己启动的 gateway |
| `--gateway-start-timeout` | 90 | 等待 gateway online 的秒数 |
| `--gateway-event-timeout` | 180 | 等待接收方 gateway 消费需求广播的秒数 |
| `--agent-timeout-seconds` | 600 | 发布方元神处理外部需求输入的最长时间 |
| `--timeout-seconds` | 900 | 等待真实协作最终完成的最长时间 |

## 5. 输出文件

每次运行写入：

```text
experiment/results/<run_id>/
├── manifest.json
├── steps.jsonl
├── receipts.jsonl
├── snapshots.jsonl
├── events.jsonl
├── agent_runs.jsonl
├── gateway_records.jsonl
├── session_evidence.jsonl
├── observations.jsonl
├── summary.json
├── REPORT.md
└── anomalies.json
```

字段约定：

- `manifest.json`：脚本版本、发布方/接收方 profile、双方 Hermes home、双方 `os_id`、服务 URL、开始/结束时间、运行参数。
- `steps.jsonl`：每一步的输入摘要、开始/结束时间、状态、耗时、关键输出和错误。
- `receipts.jsonl`：Hermes 工具 receipt、Linz publish receipt、BubbleReceipt，并包含 `actor_profile` / `actor_os_id`。
- `snapshots.jsonl`：每次 snapshot 摘要，必须脱敏且不包含完整 raw spec。
- `events.jsonl`：与 `run_id` 相关的 MRK/WSP 本地事件投影。
- `agent_runs.jsonl`：真实模式下脚本给元神的外部输入、agent 进程退出码和 stdout/stderr 路径。
- `gateway_records.jsonl`：真实模式下 gateway projection ledger 中与 `run_id` 相关的记录和 transitions。
- `session_evidence.jsonl`：真实模式下 session JSONL 中的 LLM 消息、tool_call、tool result 摘要。
- `observations.jsonl`：真实模式轮询过程中观察到的 gateway/tool/snapshot 状态。
- `summary.json`：总状态、通过/失败/阻塞数量、关键业务 ID。
- `REPORT.md`：人类可读报告，包含步骤表和失败诊断。
- `anomalies.json`：所有断言失败、超时、权限缺失和协议不一致。

敏感信息规则：

- 报告中必须脱敏 `token`、`authorization`、`api_key`、`password`、`private_key`、`secret`、Bearer 凭据。
- 失败异常必须保留 endpoint、状态码、错误码和脱敏后的 message。

## 6. MRK 全流程步骤

### 6.1 Smoke 模式步骤

| 序号 | 步骤 | 动作 | 期望结果 | 关键记录 |
| --- | --- | --- | --- | --- |
| 0 | profile discovery | 列出 profiles；若只有一个，则创建并注册接收方元神，复制 default 配置 | 得到两个不同 profile 和两个不同 Linz World 身份 | publisher_profile、receiver_profile、双方 `os_id` |
| 1 | preflight | 分别加载发布方和接收方配置、检查身份、登录、授权、Bubble 配置 | 双方通过或 `BLOCKED` | 双方授权摘要、配置摘要 |
| 2 | 发布需求 | 使用发布方 profile 发布原始 `mrk.requirement.published` 或调用后端 MRK 需求接口 | 生成 `requirement_id`，MRK receipt 为 published | `requirement_id`、event_id、publisher_os_id |
| 3 | 定位 DemandBubble | 用 requirement 关联 ID 或已知返回值读取 snapshot | DemandBubble 存在，生命周期为 produced/open 等可接受初始态 | `demand_bubble_id` |
| 4 | 接单 | 使用接收方 profile 发布/触发 `mrk.order.accepted`，或调用 `linz_bubble_accept_demand` 辅助路径 | DemandBubble 激活，生成或关联 order | `order_id`、receiver_os_id、DemandBubble 状态 |
| 5 | 定位 TaskBubble | snapshot DemandBubble children 或后端返回关联 | 至少一个 TaskBubble 存在 | `task_bubble_id` |
| 6 | 挂载接收方 AgentBubble | 使用接收方 profile 调用 `linz_bubble_request_mount`；必要时由发布方或授权审核方调用 `linz_bubble_review_mount` | mount 从 pending 到 active，或明确记录被授权拒绝 | `mount_id`、mount_state、mounted_bubble_id=receiver_os_id |
| 7 | 提交成果 | 使用接收方 profile 调用 `linz_bubble_submit_artifact` | TaskBubble 进入 delivered/reviewing 类状态，记录 evidence refs | `artifact_ref`、evidence_refs |
| 8 | 订单交付通知 | 使用接收方 profile 发布/观测 `mrk.order.handover.delivered` | 双方本地事件投影可观测，snapshot 可读 | handover id/version |
| 9 | TaskBubble 验收 | 使用发布方 profile 调用 `linz_bubble_review_task_acceptance` 或触发 MRK handover approved | TaskBubble archived/dissolved，生成 residue | residue 摘要 |
| 10 | Demand 交付总结 | 使用接收方 profile 调用 `linz_bubble_submit_demand_delivery` | DemandBubble 进入 reviewing | summary_ref |
| 11 | Demand 验收 | 使用发布方 profile 调用 `linz_bubble_review_demand_acceptance` | DemandBubble completed/archived，残留可追踪 | final lifecycle |
| 12 | 结算观测 | 双方观测 `mrk.settlement.completed` 或 `mrk.settlement.failed` | 记录结算通知；不直接发起 EC transfer | settlement id/status |
| 13 | 导出报告 | 汇总所有步骤 | 生成完整报告，失败时返回非 0 | report path |

如果 linz-world 当前 MRK API 不能直接由 Hermes 发起某些业务动作，脚本必须把该步骤标记为 `BLOCKED` 或走受控 Bubble API 辅助路径，并在 `anomalies.json` 中记录原因，不能伪造成功。

### 6.2 真实流程模式步骤

| 序号 | 步骤 | 动作 | 期望结果 | 禁止事项 |
| --- | --- | --- | --- | --- |
| 0 | profile discovery | 选择或创建两个不同 profile | 得到发布方和接收方两个不同元神 | 不得复用同一个 `os_id` |
| 1 | real preflight | 检查身份、登录、授权、Bubble 配置和真实模式策略 | 双方可用，脚本 mutation policy 为 forbidden | 不得把 smoke mutation 当真实证据 |
| 2 | publisher gateway ready | 检查或启动发布方 gateway | Linz World platform online/connected | 不得杀掉非脚本启动的 gateway |
| 3 | receiver gateway ready | 检查或启动接收方 gateway | 接收方能监听 NATS 授权 subject | 不得跳过接收方在线要求 |
| 4 | external requirement input | 给发布方元神一次自然语言外部需求输入 | 发布方真实 agent turn 结束，并留下 session/工具证据 | 脚本不得直接调用 `publish_event` 或 mutating `linz_bubble_*` |
| 5 | receiver gateway consumes requirement | 轮询接收方 gateway ledger | 出现 handled 的 `mrk.requirement.published`/broadcast 记录 | 不得直接调用接收方工具推进 |
| 6 | wait for real autonomous completion | 轮询 session、gateway、只读 Bubble snapshot | DemandBubble 最终 archived，且接收方存在真实 LLM/tool 活动 | 不得用脚本验收、提交交付或创建任务 |

真实模式全局通过条件：

- 接收方 gateway 必须消费需求事件。
- 接收方 session evidence 必须包含 `linz_*` 或 `linz_bubble_*` tool call / tool result。
- 最终 DemandBubble 必须通过只读 snapshot 观察到 `archived`。
- 报告必须包含 agent run、gateway records、session evidence 和 observations。
- 若模型只回复“收到/stand by”或没有调用工具，必须失败。

## 7. 断言标准

全局通过条件：

- 所有必需步骤状态为 `PASS` 或已明确允许的 `SKIPPED`。
- 发布方和接收方必须是不同 profile，且 `os_id` / `soul_id` 不同。
- 每个远端写操作都有 receipt。
- 每个关键业务 ID 能在后续步骤中复用。
- snapshot 摘要不泄露 raw spec 中的敏感字段。
- 报告文件全部生成。

关键断言：

- MRK 事件必须通过 `agent.linz_world.event_catalog.is_formal_event` 校验。
- 需求发布动作的 `actor_profile` 必须是发布方；接单、挂载、提交成果动作的 `actor_profile` 必须是接收方；验收动作的 `actor_profile` 必须是发布方。
- 直接发布 `ec.transfer.*` 或非正式 `bubble.*` 事件必须被拒绝或跳过。
- Bubble mutation 在缺少 `--confirm-mutations` 时必须不执行。
- Bubble mutation 在只读配置下必须返回 `bubble_mutations_disabled`。
- `linz_bubble` receipt 至少包含 `action`、`status`、`bubble_id` 或 `mount_id`。
- 挂载失败时必须区分授权失败、AgentBubble ID 校验失败和远端不可达。

## 8. 报告模板

`REPORT.md` 建议结构：

````markdown
# Bubble MRK Flow Test Report

- Run ID:
- Publisher profile:
- Receiver profile:
- Publisher OS:
- Receiver OS:
- Started:
- Finished:
- Result:

## Summary

| Metric | Value |
| --- | --- |
| Steps passed | |
| Steps failed | |
| Steps blocked | |
| Demand bubble | |
| Task bubble | |
| Mount | |
| Publisher profile | |
| Receiver profile | |

## Step Results

| # | Step | Status | Duration | Key Result | Error |
| --- | --- | --- | --- | --- | --- |

## Receipts

## Snapshots

## Anomalies

## Reproduction Command
```
````

## 9. 实现拆分

建议分三次提交实现：

1. 新增脚本框架和报告 writer：参数解析、上下文解析、脱敏、step runner、输出文件。
2. 接入双 profile MRK/Bubble 动作执行：profile discovery、双 profile preflight、publish、snapshot、mount、artifact、acceptance。
3. 增加测试和离线 dry-run fixture：不打真实公网，验证报告格式、fail-closed 和脱敏。

优先单元测试：

- `tests/scripts/test_linz_bubble_mrk_flow_report.py`
- `tests/scripts/test_linz_bubble_mrk_flow_preflight.py`
- `tests/scripts/test_linz_bubble_mrk_flow_dry_run.py`
- `tests/scripts/test_linz_bubble_mrk_flow_profiles.py`

## 10. 待确认问题

1. linz-world 是否已有可由 Hermes 调用的 MRK 需求/订单/交付业务 HTTP API，还是只能通过 formal event publish 触发。
2. `requirement_id` / `order_id` 到 `demand_bubble_id` / `task_bubble_id` 的权威关联字段是什么。
3. AgentBubble ID 挂载校验是否已经放宽到“按已存在泡泡类型判断”。
4. 结算阶段是否需要脚本等待真实 `mrk.settlement.completed`，还是只记录 handover approved 后的 pending settlement。
5. `artifact_ref` 是否采用 `hermes-session://<session>/<run_id>`，还是需要 linz-world 提供对象存储引用。
6. 自动创建第二元神时，是否固定使用 Dashboard `POST /api/profiles/linz-world-spirit`，还是允许脚本直接复用同等 Python 后端逻辑。
