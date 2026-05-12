# 实施计划: 模块 0：协议、配置与测试基座

**分支**: `feat/89-module-0-protocol-config-test-base`
**日期**: 2026-05-12
**规范**: `specs/089-module-0-protocol-config-test-base/spec.md`
**输入**: Issue OPE-89；`docs/基于张力场的Agent自驱动实现计划.md`

## 摘要

实现 `os_runtime` 的协议、配置和测试基座。新增轻量领域对象与枚举，保证 JSON round-trip；新增默认关闭的 `os_runtime` 配置段；新增聚焦测试。该计划不接入运行时、不改变现有行为、不实现 Linz World 网络能力或自治闭环。

## 技术背景

**语言/版本**: Python，沿用仓库当前支持范围；实现使用标准库。
**主要依赖**: `dataclasses`、`enum`、`typing`、标准库 JSON 友好结构；不新增依赖。
**存储**: N/A，本模块只定义协议对象和配置默认值。
**测试**: pytest。
**目标平台**: Hermes Agent 当前支持的 CLI/gateway/TUI 运行环境。
**项目类型**: Python CLI/agent runtime 仓库。
**性能目标**: 协议对象构造和序列化为轻量内存操作，不引入 I/O。
**约束条件**: 默认 `os_runtime.enabled=false`；不改变现有对话、工具、gateway、TUI、memory provider 或 `/goal` 行为。
**规模/范围**: 模块 0，仅涉及 `agent/os_runtime` 协议、`hermes_cli/config.py` 默认配置和 `tests/os_runtime`。

## 章程检查

当前 `.specify/memory/constitution.md` 仍为占位模板，没有可执行的项目特定门控。以 issue 和实现计划中的约束作为本轮门控：

- 默认只读、被动观测先行：通过，模块 0 默认关闭且不接 runtime。
- 复用现有基础设施：通过，本模块只定义投影视图，不替代 SessionDB、MemoryManager、ContextEngine 或 tool registry。
- 不新增外部依赖：通过，使用标准库。
- 可测试：通过，新增 `tests/os_runtime/test_domain.py` 与 `tests/os_runtime/test_config.py`。

## 项目结构

### 文档(此功能)

```text
specs/089-module-0-protocol-config-test-base/
├── spec.md
├── plan.md
└── tasks.md
```

### 源代码(仓库根目录)

```text
agent/
└── os_runtime/
    ├── __init__.py
    ├── domain.py
    └── config.py

hermes_cli/
└── config.py

tests/
└── os_runtime/
    ├── test_domain.py
    └── test_config.py
```

**结构决策**: `agent/os_runtime` 只承载自治领域协议和配置，不创建 adapters、engine、driver 或 bubble 子模块；这些属于后续模块。

## 修改范围

- 新增 `agent/os_runtime/__init__.py`，导出稳定协议入口。
- 新增 `agent/os_runtime/domain.py`，定义领域对象、枚举和序列化辅助。
- 新增 `agent/os_runtime/config.py`，定义默认配置和加载/归一化逻辑。
- 更新 `hermes_cli/config.py::DEFAULT_CONFIG`，追加 `os_runtime` 段。
- 新增 `tests/os_runtime/test_domain.py` 和 `tests/os_runtime/test_config.py`。

## 关键设计

### 领域对象

建议以 dataclass 为主，字段使用 JSON 友好类型：id/ref 字段使用 `str`；时间字段使用 ISO 字符串；metadata 使用 `dict[str, Any]`；数值评分使用 `float`，计数使用 `int`；关系和边使用列表或字典表示，避免后续模块被具体图结构绑定。

### 枚举

主枚举必须包含 event source、tension operation、arbitration decision、risk level、bubble lifecycle、rule maturity。裁判结果必须以 `auto_execute`、`sandbox_execute`、`require_approval`、`report_only`、`reject` 为主集合。

### 序列化策略

提供统一 `to_dict()` / `from_dict()` 或等效函数；枚举序列化为稳定字符串值；未知 metadata 保留；必填字段由 dataclass 默认值或构造测试覆盖。

### 配置策略

`os_runtime` 默认配置建议包含 `enabled=false`、`mode=passive`、`max_continuation_turns=8`、`tick_interval_seconds=0`、`allow_tool_execution=false`、`event_store=sessiondb_side_tables`、`model_task=os_runtime_intent`、`risk.require_approval_at=medium`。模块 0 只新增配置键，不实现后台 tick、event store 或 risk policy。

## 风险与取舍

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 协议对象过宽 | Builder 可能实现大量暂时无用字段 | 只做轻量字段容器，不接行为 |
| 默认配置影响现有加载 | 可能破坏配置兼容 | 默认关闭、不 bump config version、测试 DEFAULT_CONFIG |
| 序列化未来不兼容 | 后续模块无法读取旧 evidence | 枚举用稳定字符串，metadata 保留 |
| WorldIdentityRef 边界混淆 | 误把 auth/token 放入 prompt | spec 明确只读视图，不含 token |

## 验收标准

- `pytest tests/os_runtime/test_domain.py tests/os_runtime/test_config.py` 通过。
- 所有核心协议对象可 JSON round-trip。
- 中文文本、trace id、时间戳和 metadata round-trip 后不丢失。
- 默认配置中 `enabled=false`、`allow_tool_execution=false`、`tick_interval_seconds=0`。
- `hermes_cli/config.py` 未 bump config version。
- Diff 不包含业务实现以外的模块 0 协议、配置与测试基座改动。

## 测试计划

1. 运行 `pytest tests/os_runtime/test_domain.py tests/os_runtime/test_config.py`。
2. 如果 `hermes_cli/config.py` 的默认配置加载有现有测试，追加运行相关配置测试。
3. 执行 import smoke：导入 `agent.os_runtime.domain`、`agent.os_runtime.config` 和 `hermes_cli.config`，确认无副作用。

## 后续交接说明

- Builder Agent 应在同一分支实现模块 0，并保持默认无行为变化。
- Reviewer Agent 应先审查本 spec；若 APPROVED，再交给 Builder Agent。
- 后续模块 1 需要事件投影和 SessionDB 适配时，应复用本模块对象，不能重新定义平行协议。
