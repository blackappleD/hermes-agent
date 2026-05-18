# formal-all-006-map 实验结果说明

本目录是 `formal-all-006-map` 这轮 Hermes/Linz World formal experiment 的导出结果。

## 推荐查看顺序

1. `report.html`
   - 首选入口，直接用浏览器打开。
   - 已内嵌事件列表、事件扰动、张力扰动、Runtime Pipeline、异常和源文件信息。
   - 默认页签 `Event Effects` 用来看每个事件引发的行动势能和生命状态变化。
   - `Tension Effects` 页签用来看每个事件对具体张力项的扰动数值。

2. `event_action_life_effects.csv`
   - 事件级数值表。
   - 每行对应一个 formal event。
   - 用于分析事件对行动势能和生命状态的影响。

3. `event_tension_effects.csv`
   - 张力长表。
   - 每行对应“一个事件对一个 tension 的扰动”。
   - 用于分析具体张力项的 `intensity_delta`、`activation_after`、`intensity_after` 等变化。

4. `event_effects.md`
   - 面向阅读的 Markdown 摘要。
   - 按事件列出行动势能、生命状态、张力增量和处理后张力值。

## 文件说明

### 汇总与入口

- `README.md`
  - 当前说明文档。

- `report.html`
  - 单文件静态 HTML 报告。
  - 包含：
    - `Event Effects`：事件级势能/生命状态表
    - `Tension Effects`：事件级张力扰动表
    - `Events`：gateway 投影事件
    - `Runtime Pipeline`：os_runtime 原始管线行
    - `Trace Groups`：runtime trace 分组
    - `Anomalies`：导出校验异常
    - `Sources`：导出来源路径

- `summary.json`
  - 本轮导出的机器可读摘要。
  - 当前结果：
    - `events`: 42
    - `transitions`: 64
    - `anomalies`: 0
    - `phases`: P0-P5

- `summary.csv`
  - `summary.json` 的 CSV 版本，方便表格工具打开。

- `manifest.json`
  - 导出元信息。
  - 记录 run_id、profile、导出时间、Hermes home、来源数据库和日志路径。

### 事件扰动分析文件

- `event_action_life_effects.csv`
  - 每行一个 formal event。
  - 主要字段：
    - `phase`
    - `scenario_id`
    - `event_type`
    - `overall_score`
    - `value_potential`
    - `mutual_benefit_potential`
    - `learning_potential`
    - `risk_cost`
    - `recommended_depth`
    - `cycle`
    - `recovery`
    - `energy`
    - `fatigue`
    - `wakefulness`
    - `restraint`
  - 用途：分析事件对行动势能和生命状态的影响。

- `event_tension_effects.csv`
  - 每行一个“事件 x tension”扰动。
  - 主要字段：
    - `phase`
    - `scenario_id`
    - `event_type`
    - `tension_id`
    - `tension_type`
    - `operation`
    - `intensity_delta`
    - `activation_after`
    - `baseline_after`
    - `intensity_after`
    - `trend_after`
    - `trend_slope_after`
    - `reason`
  - 用途：分析每个事件具体扰动了哪些张力项，以及扰动后的数值状态。

- `event_effects.json`
  - `event_effects` 的结构化 JSON 版本。
  - 用于程序读取或进一步加工。

- `event_effects.csv`
  - 事件级综合效果表。
  - 包含事件、张力摘要、行动势能、生命状态摘要等合并字段。

- `event_effects.md`
  - 事件扰动的 Markdown 阅读版。
  - 适合人工快速审阅，不适合做精细统计。

### Gateway 事件链路文件

- `events.jsonl`
  - Gateway MessageEvent 投影结果。
  - 每行一个 gateway event。
  - 包含：
    - formal event id
    - subject
    - event_type
    - payload summary
    - gateway transitions
    - message event projection
    - consume/projection status

- `event_transitions.md`
  - 按事件格式化后的 gateway transition 文档。
  - 模仿 dashboard Events 页 `Copy as MD` 的内容。
  - 每个事件包含：
    - raw inbound payload
    - gateway transition metadata
  - 用途：追溯某个事件如何被 gateway 接收、投影、唤醒 runtime。

### Runtime 原始与归并文件

- `transitions.jsonl`
  - 导出器归并后的 runtime pipeline transition。
  - 每行是一个 runtime pipeline 分组。
  - 包含：
    - `pipeline_scope`
    - `source_event_ids`
    - `tension_field`
    - `tension_set`
    - `action_potential`
    - `self_prompt`
    - `open_intent`
    - `raw_transitions`
  - 用途：查看 runtime 对事件的结构化处理结果。

- `os_runtime_raw.jsonl`
  - 原始 os_runtime 日志行。
  - 每行来自 `/root/.hermes/logs/os_runtime_*.log`。
  - 这是最原始、最细粒度的数据源。
  - 用途：当 `report.html` 或 CSV 中的信息不够时，用它追查具体管线步骤。

### 校验与异常

- `anomalies.json`
  - 导出校验发现的问题。
  - 当前为 `[]`，表示本轮导出没有校验异常。

## 当前数据能支持的分析

可以支持：

- 每个事件引起哪些 tension 的扰动。
- 每个 tension 的 `intensity_delta`。
- 事件处理后 tension 的 `activation_after`、`intensity_after`、`trend_after`。
- 每个事件后的行动势能：
  - `overall_score`
  - `value_potential`
  - `mutual_benefit_potential`
  - `learning_potential`
  - `risk_cost`
  - `recommended_depth`
- 每个事件后的生命状态摘要：
  - `cycle`
  - `recovery`
  - `energy`
  - `fatigue`
  - `wakefulness`
  - `restraint`

需要注意：

- 当前 `life_state` 不是独立 runtime step 的结构化对象，而是从 `self_prompt.state_summary` 中解析出来的。
- 张力和行动势能来自 runtime pipeline 的结构化输出，可信度高于自然语言摘要。
- 若要做严格时间序列曲线，建议优先使用 `event_action_life_effects.csv` 和 `event_tension_effects.csv`。
