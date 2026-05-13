# Quickstart: 模块 3 生命状态、张力解释器与张力场内核

## Validate Existing Context

```bash
pytest tests/os_runtime/test_domain.py tests/os_runtime/test_signals.py
```

## Implement Module 3

1. Extend protocol objects in `agent/os_runtime/domain.py` only where required by the spec.
2. Add `agent/os_runtime/engine/life_state.py`.
3. Add `agent/os_runtime/engine/tension_interpreter.py`.
4. Add `agent/os_runtime/engine/tension_field.py`.
5. Add focused tests under `tests/os_runtime/`.

## Validate Module 3

```bash
pytest tests/os_runtime/test_life_state.py tests/os_runtime/test_tension_interpreter.py tests/os_runtime/test_tension_field.py
pytest tests/os_runtime/test_domain.py tests/os_runtime/test_signals.py
```

## Boundary Checks

- Do not import Hermes main loop, gateway, tool execution, or Linz World clients from new engine modules.
- Do not perform network, filesystem persistence, or external side effects.
- Keep interpreter output as explanation and operations only; let field engine mutate a copied tension set.
