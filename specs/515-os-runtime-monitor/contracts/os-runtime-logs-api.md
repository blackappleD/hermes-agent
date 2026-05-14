# Contract: OS_RUNTIME Logs API

## Endpoint

`GET /api/logs/os-runtime`

只读 dashboard endpoint。必须受现有 dashboard session token middleware 保护，不加入 public API allowlist。

## Query Parameters

| 参数 | 类型 | 默认 | 规则 |
| --- | --- | --- | --- |
| `lines` | integer | `100` | 返回 raw line 数量，最小 1，最大 500 |
| `source` | string | `auto` | 首版仅要求 `auto`；未来可扩展为具体 `os_runtime_YYYYMMDD.log` |
| `include_raw` | boolean | `true` | `false` 时可省略 raw line 文本但仍返回模块快照 |

## 200 Response

```json
{
  "mode": "os_runtime",
  "source_files": ["os_runtime_20260514.log"],
  "updated_at": "2026-05-14T15:30:02.000+08:00",
  "modules": [
    {
      "module_id": "life_state",
      "title": "Life State",
      "summary": "energy 0.82, wakefulness 0.90",
      "updated_at": "2026-05-14T15:30:00.000+08:00",
      "status": "ok",
      "parameters": [
        {
          "key": "energy",
          "label": "Energy",
          "value": 0.82,
          "previous_value": 0.8,
          "change": "up",
          "delta": 0.02,
          "unit": "",
          "evidence_step": "life_state",
          "evidence_trace_id": "trace-1"
        }
      ],
      "raw_line_indexes": [0],
      "metadata": {}
    }
  ],
  "raw_lines": [
    "{\"timestamp\":\"2026-05-14T15:30:00.000+08:00\",...}"
  ],
  "raw_line_count": 1,
  "parse_error_count": 0,
  "empty_reason": "",
  "limits": {
    "requested_lines": 100,
    "max_lines": 500,
    "read_lines": 1
  }
}
```

## Empty Response

When no OS_RUNTIME log exists or no relevant lines are found:

```json
{
  "mode": "os_runtime",
  "source_files": [],
  "updated_at": "",
  "modules": [
    {"module_id": "life_state", "title": "Life State", "summary": "", "updated_at": "", "status": "empty", "parameters": [], "raw_line_indexes": [], "metadata": {}},
    {"module_id": "tension_field", "title": "Tension Field", "summary": "", "updated_at": "", "status": "empty", "parameters": [], "raw_line_indexes": [], "metadata": {}},
    {"module_id": "action_potential", "title": "Action Potential", "summary": "", "updated_at": "", "status": "empty", "parameters": [], "raw_line_indexes": [], "metadata": {}}
  ],
  "raw_lines": [],
  "raw_line_count": 0,
  "parse_error_count": 0,
  "empty_reason": "No OS_RUNTIME log lines found for the current profile.",
  "limits": {"requested_lines": 100, "max_lines": 500, "read_lines": 0}
}
```

## Error Behavior

- Invalid `lines` values are clamped into the allowed range rather than failing the request.
- Missing log files return 200 with an empty response.
- JSON decode errors increment `parse_error_count` and preserve the raw line.
- Unexpected file permission or IO errors return 500 with a concise diagnostic; the server must not expose sensitive path internals beyond current profile log filename.

## Compatibility Requirements

- Existing `GET /api/logs` behavior and response shape remain unchanged.
- This endpoint must not execute OS_RUNTIME, mutate config, start background loops, or write state.
