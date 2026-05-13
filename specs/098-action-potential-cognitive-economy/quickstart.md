# Quickstart: 模块 4 行动势能与认知经济

## 实现顺序

1. 在 `agent/os_runtime/domain.py` 做最小协议扩展，优先复用现有 `ActionPotential.metadata`；只有测试需要类型化建议时再新增 dataclass。
2. 新增 `agent/os_runtime/engine/action_potential.py`，实现纯内存、无 I/O 的 `ActionPotentialEvaluator`。
3. 新增 `tests/os_runtime/test_action_potential.py`，先覆盖闲聊、未完成目标、高风险工具、recommended depth 限定值和 evidence。
4. 新增 `agent/os_runtime/engine/cognitive_economy.py`，实现 `CognitiveEconomyController` 和 world compute eligibility。
5. 新增 `tests/os_runtime/test_cognitive_economy.py`，使用 stub repository/service 或 injectable compute function，禁止真实网络。

## 建议验证命令

```bash
pytest tests/os_runtime/test_action_potential.py tests/os_runtime/test_cognitive_economy.py
pytest tests/os_runtime/test_domain.py tests/os_runtime/test_signals.py tests/os_runtime/test_life_state.py tests/os_runtime/test_tension_interpreter.py tests/os_runtime/test_tension_field.py
```

## 实现边界

- 不修改 `run_agent.py`。
- 不自动 continuation。
- 不执行工具。
- 不切换主模型。
- 不直接发布 Linz World 事件。
- world compute 必须通过 `agent/linz_world/compute.py`，测试必须 stub。
