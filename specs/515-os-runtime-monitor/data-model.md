# 数据模型: OS_RUNTIME 日志监控视图

## OSRuntimeLogRecord

从 OS_RUNTIME JSONL 或相关 raw line 中解析出的单条记录。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `timestamp` | string | 日志记录时间，优先使用 JSONL `timestamp` |
| `source_file` | string | 来源日志文件名，例如 `os_runtime_20260514.log` |
| `surface` | string | CLI/TUI/gateway/test 等来源面 |
| `session_id` | string | Hermes session id，如日志提供 |
| `profile_id` | string | profile id，如日志提供 |
| `phase` | string | runtime 阶段，例如 `before_turn`、`after_turn`、`driver` |
| `step` | string | pipeline step，例如 `life_state`、`tension_set`、`action_potential` |
| `step_index` | number | pipeline step 顺序；未知为 0 |
| `trace_id` | string | trace/evidence id，如日志提供 |
| `data` | object | redacted structured payload |
| `raw_line` | string | 原始日志行文本 |
| `parse_status` | enum | `parsed`、`partial`、`raw_only`、`invalid_json` |

### 验证规则

- `raw_line` 必须始终保留，作为 UI raw line 区域的证据。
- `data` 不得包含 parser 新增的 secrets；parser 不得尝试反脱敏。
- JSON decode 失败时，记录必须以 `invalid_json` 或 `raw_only` 进入 raw line，不进入模块参数。

## RuntimeParameterReading

单个可展示参数。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `key` | string | 稳定参数 key，例如 `energy` |
| `label` | string | 用户可读名称，例如 `Energy` / `能量` |
| `value` | string/number/boolean | 当前值 |
| `previous_value` | string/number/boolean/null | 上一个可比较值 |
| `change` | enum | `up`、`down`、`unchanged`、`changed`、`unknown` |
| `delta` | number/null | 数值变化量 |
| `unit` | string | 可选单位或值域说明 |
| `evidence_step` | string | 来源 step |
| `evidence_trace_id` | string | 来源 trace id |

### 验证规则

- 缺失参数不得伪造为 `0`；应省略该 reading 或以 `unknown` 展示。
- 数值字段可计算 `delta`；非数值字段只计算 changed/unchanged。
- 参数 label 由前端 i18n 或服务端可读 key 映射生成，必须避免裸内部枚举难以理解。

## RuntimeModuleSnapshot

某个 OS_RUNTIME 模块的最新展示快照。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `module_id` | enum | `life_state`、`tension_field`、`action_potential`、`self_prompt`、`open_intent`、`arbitration`、`runtime_driver`、`unknown` |
| `title` | string | 模块标题 |
| `summary` | string | 可读摘要 |
| `updated_at` | string | 最新记录时间 |
| `status` | enum | `ok`、`partial`、`empty`、`stale` |
| `parameters` | RuntimeParameterReading[] | 参数读数 |
| `raw_line_indexes` | number[] | 对应 raw line 在响应 raw list 中的位置 |
| `metadata` | object | 非敏感扩展摘要 |

### 模块字段优先级

#### `life_state`

优先字段：`energy`、`fatigue`、`health`、`wakefulness`、`curiosity`、`boredom`、`creative_pressure`、`social_hunger`、`silence_pressure`、`restraint`、`life_cycle`、`recovery_cycle`、`generated_intent_count`。

#### `tension_field`

优先字段：active tension count、top tension id/type、`intensity`、`activation`、`trend`、`trend_slope`、`confidence`、`baseline`、propagation edge count。

#### `action_potential`

优先字段：`value_potential`、`mutual_benefit_potential`、`learning_potential`、`risk_cost`、`overall_score`、`recommended_depth`、`rationale`。

#### 附加模块

- `self_prompt`: `prompt_id`、state/tension/potential summary、target direction、open space。
- `open_intent`: `intent_id`、intent/action family、risk、success condition。
- `arbitration`: decision/verdict、risk、rationale、approval requirement。
- `runtime_driver`: status、should_continue、reason、turns/budget、paused reason。

### 验证规则

- P1 模块没有数据时，必须返回 `status=empty` 或由前端展示缺失状态。
- 附加模块只有存在数据时展示；没有数据不应挤占页面。
- `updated_at` 必须来自最新贡献记录，不得使用当前服务器时间伪装数据新鲜度。

## OSRuntimeLogsResponse

`GET /api/logs/os-runtime` 的响应。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `mode` | string | 固定为 `os_runtime` |
| `source_files` | string[] | 本次读取的文件 |
| `updated_at` | string | 最新 OS_RUNTIME 记录时间；无记录为空字符串 |
| `modules` | RuntimeModuleSnapshot[] | 模块快照 |
| `raw_lines` | string[] | OS_RUNTIME 相关原始日志行 |
| `raw_line_count` | number | raw line 数量 |
| `parse_error_count` | number | JSON decode 或字段解析错误数 |
| `empty_reason` | string | 无数据时的用户可读/可诊断原因 |
| `limits` | object | 行数上限与实际读取说明 |

## 状态转换

页面本地状态：

```text
normal_logs -> os_runtime
os_runtime -> normal_logs
os_runtime(raw_collapsed) -> os_runtime(raw_expanded)
os_runtime(raw_expanded) -> os_runtime(raw_collapsed)
```

切换 `normal_logs` 和 `os_runtime` 不改变 `autoRefresh` 状态。普通日志筛选只影响普通模式；OS_RUNTIME 模式只使用 raw line 行数上限。
