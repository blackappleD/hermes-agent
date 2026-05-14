# Quickstart: OS_RUNTIME 日志监控视图

## 前置条件

使用临时或开发 Hermes profile。为了生成 OS_RUNTIME 专属 JSONL，确保运行环境允许写入 OS_RUNTIME debug log：

```bash
HERMES_OS_RUNTIME_LOG=1
```

如果没有真实 runtime 数据，可在测试中写入样例 `os_runtime_YYYYMMDD.log` JSONL。

## 手动验证流程

1. 启动 Hermes dashboard。
2. 打开 `/logs` 页面。
3. 确认右上角自动刷新开关左侧出现 `OS_RUNTIME` 开关。
4. 保持 `OS_RUNTIME` 关闭，验证普通日志文件、级别、组件、行数、刷新和自动刷新仍按原样工作。
5. 打开 `OS_RUNTIME` 开关。
6. 验证页面主体切换为 OS_RUNTIME 模块视图，并至少包含生命状态、张力场、行动势能模块。
7. 展开底部 raw line 区域，确认 OS_RUNTIME 原始日志行可滚动查看。
8. 开启自动刷新，写入一条新的 OS_RUNTIME JSONL，确认下一轮刷新后模块值或 raw line 更新。
9. 使用空日志 profile 打开 OS_RUNTIME 模式，确认显示空状态而不是默认零值。

## 样例 JSONL

```json
{"timestamp":"2026-05-14T15:30:00.000+08:00","route":"goal_event -> signal_set -> life_state -> tension_operation -> tension_set -> action_potential -> self_prompt -> open_intent -> arbiter","surface":"cli","session_id":"session-1","profile_id":"default","phase":"after_turn","step":"life_state","step_index":3,"trace_id":"trace-1","data":{"life_state":{"energy":0.82,"fatigue":0.12,"wakefulness":0.9,"curiosity":0.45,"restraint":0.3}}}
{"timestamp":"2026-05-14T15:30:01.000+08:00","surface":"cli","session_id":"session-1","profile_id":"default","phase":"after_turn","step":"tension_set","step_index":5,"trace_id":"trace-1","data":{"tension_set":{"dynamic_tensions":[{"tension_id":"goal:unsatisfied","tension_type":"unsatisfied_goal","intensity":0.76,"activation":0.7,"trend":0.15,"confidence":0.9}]}}}
{"timestamp":"2026-05-14T15:30:02.000+08:00","surface":"cli","session_id":"session-1","profile_id":"default","phase":"after_turn","step":"action_potential","step_index":6,"trace_id":"trace-1","data":{"action_potential":{"value_potential":0.7,"learning_potential":0.5,"risk_cost":0.2,"overall_score":0.72,"recommended_depth":"continue_turn"}}}
```

## 测试命令

```bash
python -m pytest -o "addopts=" tests/hermes_cli/test_os_runtime_logs.py tests/hermes_cli/test_web_server.py -k "os_runtime or get_logs"
cd web && npm run build
```

如果本机 pytest 环境已安装 xdist，也可以省略 `-o "addopts="` 使用项目默认 pytest 配置。

## API 响应字段

`GET /api/logs/os-runtime?lines=100&include_raw=true` 返回:

- `mode`: 固定为 `os_runtime`
- `source_files`: 当前 profile 下读取到的 `os_runtime_*.log`
- `updated_at`: 最新可解析 OS_RUNTIME 记录时间
- `modules`: 固定包含 `life_state`, `tension_field`, `action_potential`，并在有数据时追加 `self_prompt`, `open_intent`, `arbitration`, `runtime_driver`
- `raw_lines` / `raw_line_count`: 原始 OS_RUNTIME 行，`include_raw=false` 时省略文本
- `parse_error_count`: JSONL 解析失败行数
- `empty_reason`: 无 OS_RUNTIME 数据时的空状态说明
- `limits`: `requested_lines`, `max_lines`, `read_lines`

## 期望结果

- 普通日志模式完全可用。
- `OS_RUNTIME` 模式显示模块化参数、更新时间和变化提示。
- raw line 区域可展开、折叠、独立滚动。
- 无 OS_RUNTIME 日志时显示明确空状态。
- 坏 JSON 或未知 step 不会破坏整个响应，仍能在 raw line 中看到。
