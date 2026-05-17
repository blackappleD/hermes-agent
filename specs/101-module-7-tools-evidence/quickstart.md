# Quickstart: 模块 7：工具执行适配与证据包

## 预期实现顺序

1. 扩展或约定 `agent/os_runtime/domain.py` 的 receipt/ticket/evidence 字段，保持 JSON round-trip。
2. 实现 `agent/os_runtime/adapters/tools.py` 的 post-tool receipt recorder。
3. 实现 final response receipt 和 `agent/os_runtime/adapters/linz_world.py` world receipt adapter。
4. 实现 `agent/os_runtime/evidence.py` 聚合逻辑。
5. 只在现有 hook 边界做薄接入，不改变原返回。

## 验证命令

```bash
pytest tests/os_runtime/test_tools_adapter.py
pytest tests/os_runtime/test_evidence.py
pytest tests/os_runtime/test_domain.py
pytest tests/os_runtime/test_events_adapter.py tests/os_runtime/test_driver.py tests/run_agent/test_os_runtime_turn_hooks.py
```

如果接入 `agent/linz_world/publisher.py`，同时运行：

```bash
pytest tests/linz_world/test_publisher.py
```
