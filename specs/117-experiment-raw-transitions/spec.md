# 功能规范: 实验脚本：共博自制框架阶段验证与 raw transitions 采集

**功能分支**: `117-experiment-raw-transitions`  
**Issue 分支**: `feat/117-experiment-raw-transitions`  
**创建时间**: 2026-05-18  
**状态**: 草稿  
**输入**: Issue OPE-117「[Feature]实验脚本：共博自制框架阶段验证与 raw transitions 采集」与 `docs/共博自制框架实验准备.md`

## 背景

Hermes 已有 Linz World 身份、正式事件投影、OS Runtime 的生命状态、张力场、行动势能、SelfPrompt、OpenIntent、BoYueArbiter、Runtime Driver 以及 evidence/receipt 机制。`docs/共博自制框架实验准备.md` 定义了第 5-11 节实验目标、人格种子、事件脚本库、P0-P5 阶段和观测口径。当前缺口是缺少可重复执行的实验套件，把这些事件按阶段注入 mock 或真实 runtime，并把每个事件经过的 raw transitions 与模块状态 delta 归档为后续前端或 notebook 可分析的数据。

## 目标

- 在 `experiment/` 下新增实验脚本、人格种子配置、事件脚本库、运行器和结果 schema。
- 覆盖文档第 5-11 节：人格种子、P0 身份冒烟、P1 单次扰动、P2 组合意图、P3 生命状态反馈、P4 持续事件流自我演化、P5 多元神交互。
- 支持 `--phase P0|P1|P2|P3|P4|P5|all` 和 mock/runtime 两种模式。
- 每个事件保留正式事件包络和原始输入，并输出 `before_state`、`after_state`、tick/衰减后状态、raw transitions、actual action、stop reason、judgement、evidence refs。
- 输出 `experiment/results/<run_id>/`，至少包含 JSONL 原始记录、CSV/JSON 汇总、异常判定和 evidence refs。

## 非目标

- 不修改 `docs/共博自制框架实验准备.md`。
- 不重写 OS Runtime、Linz World 事件总线、裁判、evidence 或 dashboard 实现。
- 不默认连接真实 Linz World 服务；真实模式必须显式配置。
- 不在实验脚本中保存 token、私钥、restricted raw payload 或完整敏感上下文。
- 不实现前端图表或 notebook，本 issue 只准备可分析输出。

## 需求理解

实验脚本应作为 `experiment/` 下的独立工具层：读取 seed 与事件库，按阶段生成稳定事件序列，将事件注入 mock runtime 或真实 runtime 查询/执行边界，采集每个模块的快照与 delta，并把 `event -> context/signals -> life_state -> tension_field -> action_potential -> self_prompt -> open_intent -> arbitration -> action/evidence` 链路写为逐事件 transition record。mock 模式用于 CI 和本地无 Linz World 连接的结构验证；runtime 模式复用正式事件包络、os_runtime 查询能力和 evidence/receipt 归档。

## 用户场景与测试

### 用户故事 1 - 阶段化运行 P0-P3 机制验证 (优先级: P1)

作为实验执行者，我需要用一个命令按阶段运行 P0-P3，以确认事件包络、单次扰动、行动势能/意图和生命状态反馈均能产生可解释 delta。

**优先级原因**: P0-P3 是所有后续持续流和多元神实验的机制基础。  
**独立测试**: 使用 mock runtime 运行 `P0`、`P1`、`P2`、`P3` fixture，断言每个事件都有 raw transition、状态快照、delta、judgement 和汇总输出。

**验收场景**:

1. **给定** `--phase P1 --repeat 3 --mode mock`，**当** 运行单事件实验，**那么** 每个事件重复 3 次，并记录每次衰减间隔与方向/幅度/边界判断。
2. **给定** P2 组合实验，**当** 注入机会-风险冲突或压力-规则冲突，**那么** 输出能显示 action potential 排序、OpenIntent 来源和 BoYueArbiter 决策。
3. **给定** P3 生命状态实验，**当** 运行自然时间流、连续工作、连续拒绝、资源压力和恢复事件，**那么** summary 包含生命状态字段的前后值和 delta。

### 用户故事 2 - 运行 P4 持续流并观察轻量演化 (优先级: P1)

作为框架验证者，我需要运行正反馈、负反馈、规则约束、生存压力和关系记忆流，以观察阈值、偏好、记忆权重是否出现小幅、可解释变化。

**优先级原因**: 文档核心目标之一是观察持续事件流中的自我调节和自我演化。  
**独立测试**: mock runtime 对每个 P4 流生成多轮 transition，并在 summary 中输出 threshold/preference/memory delta 与异常判定。

**验收场景**:

1. **给定** S1 正反馈流，**当** 连续 5 轮低风险任务成功，**那么** 输出记录 accept_task 阈值、confidence/credit 和相关记忆权重的变化。
2. **给定** S2/S3 负反馈或规则约束流，**当** 事件重复触发，**那么** 输出记录 ask_clarify、risk/governance 权重或 submit 前 self_check 的变化。
3. **给定** 任一 P4 流，**当** 出现非预期漂移、变量爆表或长期卡死，**那么** 异常判定写入 summary。

### 用户故事 3 - 运行 P5 多元神交互实验 (优先级: P1)

作为多元神交互观察者，我需要并行或准并行注入多个 seed 的事件，比较不同元神的张力、行动势能、意图、裁判结果和关系变化。

**优先级原因**: P5 是验证不同人格种子在真实灵治文明事件系统内产生差异化行为的关键阶段。  
**独立测试**: mock runtime 使用至少 6 个 seed 运行 M1-M6，断言每个 seed 有独立状态轨迹，summary 能比较竞争、协作、求助、拒绝、评价和关系变化。

**验收场景**:

1. **给定** M1 同一清晰高价值需求广播，**当** 拓野、竞锋、衡元同时接收事件，**那么** 输出展示三者不同的 AP 排序、OpenIntent 和裁判结果。
2. **给定** M3 协作求助或 M4 拒绝后修复，**当** 多 seed 交互运行，**那么** 输出记录关系变化、协作/求助/拒绝/评价行为和 evidence refs。
3. **给定** `--mode runtime`，**当** runtime 连接不可用或授权不足，**那么** 脚本 fail closed，报告缺失能力，不伪造真实结果。

### 用户故事 4 - 产出可分析、安全的实验结果 (优先级: P2)

作为后续前端或 notebook 使用者，我需要稳定 JSONL/CSV/JSON 输出，并确认敏感信息不会进入 SelfPrompt、OpenIntent、Arbitration 或 raw transition 的普通结果文件。

**优先级原因**: 实验输出必须可复用、可审计、可安全分享。  
**独立测试**: 用包含 token、private_key、restricted payload 的事件 fixture 运行 mock 模式，断言结果文件只保存 redacted summary、hash 或 content_ref。

**验收场景**:

1. **给定** 一次完整 `--phase all` 运行，**当** 完成后，**那么** `experiment/results/<run_id>/` 至少包含 `events.jsonl`、`transitions.jsonl`、`summary.json`、`summary.csv`、`anomalies.json`。
2. **给定** 任一事件，**当** 查看 transition record，**那么** 可追溯每个模块的 before/after/delta、排序/评分、stop reason、judgement 和 evidence refs。
3. **给定** 敏感字段存在于输入或模块输出，**当** 写结果，**那么** 普通输出不包含明文秘密。

### 边界情况

- mock 模式必须在无 Linz World、无模型、无网络时可运行，并验证脚本结构和数据格式。
- runtime 模式缺少登录、权限、os_runtime 查询能力或 evidence repository 时必须停止并报告 blocked reason。
- 事件包络缺少 `subject`、`event_type`、`event_id` 或 `payload` 时必须记录 invalid event，不进入业务解释。
- P1 重复事件必须保留 repeat index、衰减/tick 间隔和每次状态边界判断。
- P5 多 seed 运行必须隔离每个 seed 的状态，不允许串写状态或混淆 evidence refs。
- 输出路径已存在时必须按 run_id 新建目录，避免覆盖旧实验结果。
- 大 payload、二进制或 restricted raw payload 只保存摘要、hash、content_ref 或 audit_ref。

## 需求

### 功能需求

- **FR-001**: 系统必须在 `experiment/` 下新增可执行实验入口，支持按 `P0`、`P1`、`P2`、`P3`、`P4`、`P5` 或 `all` 运行。
- **FR-002**: 系统必须提供 dry-run/mock runtime 模式和真实 runtime 模式，mock 模式不得依赖真实 Linz World、真实模型或网络。
- **FR-003**: 事件脚本库必须使用正式事件包络：`subject`、`event_type`、`event_id`、`payload`，并保留原始事件输入的 redacted/hash 形式。
- **FR-004**: 人格种子配置必须至少包含 `seed_neutral_001`、`seed_bold_001`、`seed_prudent_001`、`seed_social_001`、`seed_competitive_001`、`seed_fragile_001`。
- **FR-005**: P0 必须覆盖登录、心跳或系统通知等身份/环境冒烟事件，并验证初始生命状态。
- **FR-006**: P1 必须支持每个单事件重复 3 次，并记录衰减间隔、方向、幅度和边界。
- **FR-007**: P2 必须覆盖机会-清晰、机会-风险冲突、压力-规则冲突、失败-修复、生存-机会、奖励-探索。
- **FR-008**: P3 必须覆盖自然时间流、连续工作、连续拒绝、资源压力和恢复事件。
- **FR-009**: P4 必须覆盖正反馈流、负反馈流、规则约束学习流、生存压力适应流和关系记忆流。
- **FR-010**: P5 必须支持多 seed 并行或准并行事件注入，并记录差异化响应、关系变化、协作/竞争/求助/拒绝/评价行为。
- **FR-011**: 每个事件必须记录 `before_state`、`after_state`、tick/衰减后状态、actual action、stop reason 和 judgement。
- **FR-012**: 每个事件必须收集 raw transitions，至少覆盖 `event -> context/signals -> life_state -> tension_field -> action_potential -> self_prompt -> open_intent -> arbitration -> action/evidence`。
- **FR-013**: 张力场输出必须记录 `T_value`、`T_risk`、`T_consensus`、`T_creation`、`T_survival`、`T_reputation`、`T_resource`、`T_governance` 的当前值和 delta；实现字段不同可通过 mapping 输出。
- **FR-014**: 行动势能输出必须记录 `AP_accept_task`、`AP_ask_clarify`、`AP_submit`、`AP_refuse`、`AP_seek_help`、`AP_review`、`AP_negotiate`、`AP_learn` 的当前值、排序和 delta；实现字段不同可通过 mapping 输出。
- **FR-015**: 生命状态输出必须记录 `energy`、`stability`、`confidence`、`credit`、`trust`、`curiosity`、`stress`、`fatigue` 等字段的前后值和 delta；实现字段不同可通过 mapping 输出。
- **FR-016**: SelfPrompt 输出必须记录结构化字段、摘要、生成原因和 evidence refs，不得写入 token、私钥、restricted raw payload 或完整敏感上下文。
- **FR-017**: OpenIntent 输出必须记录 action family、action type、why_now、open_space、target_direction、tools_needed、success_condition、stop_condition、排序/评分和来源 tension/action potential。
- **FR-018**: BoYueArbiter 输出必须区分 `auto_execute`、`sandbox_execute`、`require_approval`、`report_only`、`reject`，并记录博/约倾向、风险等级、主裁判结果、约束原因、审批需求和 permission/evidence refs。
- **FR-019**: 输出目录必须保存 JSONL 原始记录和 CSV/JSON 汇总，文件名稳定，便于前端或 notebook 分析。
- **FR-020**: 结果写入必须复用现有 redaction 规则或同等规则，禁止明文保存 token、API key、password、private key、authorization header 或 restricted raw payload。

### 关键实体

- **ExperimentSeed**: 人格种子，包含 identity、博/约倾向、初始生命状态、张力权重、行动阈值和适用阶段。
- **ExperimentEvent**: 正式事件包络与 redacted 原始输入。
- **ExperimentScenario**: P0-P5 的阶段、事件序列、repeat/tick 策略、期望观测点和判定口径。
- **RuntimeBackend**: mock 或真实 runtime 适配边界，负责注入事件并返回模块快照。
- **TransitionRecord**: 单事件 raw transition，包含状态快照、delta、排序/评分、judgement 和 evidence refs。
- **ExperimentRunResult**: 一次 run 的文件目录、汇总、异常、统计和 capability diagnostics。

## 建议方案

在 `experiment/` 下新增独立 Python package/脚本，分成 `seeds`、`events`、`scenarios`、`runtime`、`collectors`、`reporting` 六层。mock backend 用确定性规则生成结构完整的状态/delta，保证 CI 可验证输出 schema；runtime backend 复用现有 `agent.os_runtime` domain 对象、driver/query 能力、`agent.os_runtime.evidence` 与 Linz World 事件/receipt 边界读取真实状态。所有输出先归一化到实验 schema，再写 JSONL/CSV/JSON。Builder 不应修改核心 runtime 计算逻辑，除非发现缺少只读查询 adapter；若需要，只能增加薄 adapter 和测试，不改变决策语义。

## 修改范围

- 新增：`experiment/` 实验 package、CLI 入口、seed/event/scenario 数据文件、runtime backend、结果 writer。
- 新增测试：`tests/experiment/` 下的单元和集成式 mock 测试。
- 可能只读复用：`agent/os_runtime/domain.py`、`agent/os_runtime/driver.py`、`agent/os_runtime/evidence.py`、`agent/linz_world/event_bus.py`、`agent/linz_world/publisher.py`。
- 仅在必要时新增薄查询适配器：`agent/os_runtime/adapters/experiment.py` 或同等路径；不得改变核心 runtime 决策。

## 关键设计

- **实验层隔离**: 主要代码和数据都放在 `experiment/`，避免把实验 fixture 混入 `docs/` 或核心 runtime。
- **后端可替换**: mock backend 保证结构测试；runtime backend 只做显式能力检查后运行。
- **统一 transition schema**: 不直接暴露内部对象形状，先映射到 T/AP/Life/SelfPrompt/OpenIntent/Arbitration 的分析字段。
- **证据优先但隐私隔离**: evidence refs、receipt ids、audit refs 可进入输出；完整 restricted payload 和秘密只保存 hash/ref。
- **fail closed runtime**: 真实模式缺少登录、权限、查询能力或 evidence repository 时报告 blocked，不回退为 mock 并假装真实。

## 风险与取舍

- **前序模块接口可能不稳定**: 取舍是将实验输出 schema 与 runtime 对象解耦，通过 mapping 兼容字段差异。
- **真实 runtime 查询能力可能不足**: 首版允许 Builder 增加只读 adapter，但不允许改核心行为来适配实验。
- **P5 并行真实性有限**: mock 模式可准并行模拟；真实并行需要 runtime 能隔离多 seed 状态，若能力不足必须报告 blocked。
- **事件库字段与正式 event-model 可能有差异**: 事件必须保留包络和 payload mapping；不明确字段用 metadata/diagnostics 标注，不猜测业务语义。

## 验收标准

- **AC-001**: `python -m experiment.run --phase P1 --mode mock --repeat 3` 能产生包含重复与衰减记录的结果目录。
- **AC-002**: `python -m experiment.run --phase all --mode mock` 覆盖 P0-P5 全部场景并生成 JSONL/CSV/JSON 汇总。
- **AC-003**: 每条 transition record 都包含事件包络、before/after/tick 状态、T/AP/Life delta、SelfPrompt、OpenIntent、Arbitration、action/evidence 和 judgement。
- **AC-004**: P2-P5 的必需组合流、持续流和多元神场景全部在 scenario registry 中可枚举。
- **AC-005**: runtime 模式在能力不足时 fail closed，并在 summary 中写明缺少登录、权限、查询或 evidence 能力。
- **AC-006**: 敏感字段不会明文出现在普通结果文件。

## 测试计划

- `pytest tests/experiment/test_event_library.py`
- `pytest tests/experiment/test_seed_library.py`
- `pytest tests/experiment/test_scenario_registry.py`
- `pytest tests/experiment/test_mock_runtime_transitions.py`
- `pytest tests/experiment/test_result_writer.py`
- `pytest tests/experiment/test_redaction.py`
- 聚焦回归：`pytest tests/os_runtime/test_domain.py tests/os_runtime/test_evidence.py tests/os_runtime/test_driver.py`

## 成功标准

### 可衡量的结果

- **SC-001**: mock `--phase all` 运行后至少写出 `events.jsonl`、`transitions.jsonl`、`summary.json`、`summary.csv`、`anomalies.json` 五类文件。
- **SC-002**: scenario registry 枚举 P0-P5 时，P2 至少 6 个组合、P3 至少 5 个生命状态实验、P4 至少 5 个持续流、P5 至少 6 个多元神实验。
- **SC-003**: P1 单事件 fixture 的每个事件至少有 3 条 repeat transition 和对应 tick/decay 记录。
- **SC-004**: redaction 测试证明 token、api_key、password、private_key、authorization 原值不会出现在结果文件。

## 假设

- 前序模块 1-6.5、7、10 的核心能力已经在对应分支或 main 中可被导入、调用或通过只读 adapter 观测。
- 文档第 12 节事件可作为首批事件库基础；第 6-11 节组合/持续/多元神流可由这些事件和少量衍生事件组成。
- 实验结果目录可以进入 gitignore 或通过测试临时目录生成；本 issue 的实现代码应提交，实际运行结果不应默认提交。
- Builder Agent 负责业务实现；Planner Agent 本轮只维护 spec-kit artifacts。

## 后续交接说明

Builder Agent 应按 `tasks.md` 的故事顺序实现：先完成 seed/event/scenario registry 和 mock backend，再完成 transition schema 与结果写入，随后实现 P4/P5 聚合，最后接 runtime backend。实现过程中不要修改 `docs/`，不要把实验数据放入核心 runtime 目录，不要默认连接真实 Linz World，不要把敏感 payload 写入结果。
