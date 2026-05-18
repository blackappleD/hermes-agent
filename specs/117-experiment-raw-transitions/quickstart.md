# Quickstart: 实验脚本

## Mock 模式

```bash
python -m experiment.run --phase P1 --mode mock --repeat 3
python -m experiment.run --phase all --mode mock
```

预期输出：

```text
experiment/results/<run_id>/
├── manifest.json
├── events.jsonl
├── transitions.jsonl
├── summary.json
├── summary.csv
└── anomalies.json
```

## Runtime 模式

```bash
python -m experiment.run --phase P0 --mode runtime --profile <profile-name>
```

runtime 模式必须先完成 capability check。若缺少 Linz World 登录、权限、os_runtime 查询能力或 evidence repository，命令应退出为 blocked/diagnostic 状态，不生成伪造 transition。

## 聚焦测试

```bash
pytest tests/experiment/test_event_library.py
pytest tests/experiment/test_seed_library.py
pytest tests/experiment/test_scenario_registry.py
pytest tests/experiment/test_mock_runtime_transitions.py
pytest tests/experiment/test_result_writer.py
pytest tests/experiment/test_redaction.py
pytest tests/os_runtime/test_domain.py tests/os_runtime/test_evidence.py tests/os_runtime/test_driver.py
```

## 验收检查

- P0-P5 场景均可通过 registry 枚举。
- P1 每个单事件至少 3 次 repeat，并保留 tick/decay 记录。
- 每条 transition 都有 event 包络、before/after/tick state、raw transition chain、delta、judgement 和 evidence refs。
- 普通结果文件不包含 token、api_key、password、private_key、authorization 原值。
