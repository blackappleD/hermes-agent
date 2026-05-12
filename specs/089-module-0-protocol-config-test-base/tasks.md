# Implementation Tasks: 模块 0：协议、配置与测试基座

## Phase 1: 协议对象

- [ ] 1.1 新增 `agent/os_runtime/__init__.py`
  - 导出模块 0 的稳定协议入口。
  - 不导入会产生运行时副作用的模块。
  - **Requirement**: FR-001

- [ ] 1.2 新增 `agent/os_runtime/domain.py`
  - 定义 spec 中列出的核心 dataclass。
  - 定义事件来源、张力操作、裁判结果、风险等级、泡泡生命周期、规则成熟度等枚举。
  - **Requirement**: FR-001, FR-002, FR-003

- [ ] 1.3 实现 JSON round-trip 辅助
  - 枚举序列化为稳定字符串。
  - 保留中文内容、trace id、时间戳和 metadata。
  - **Requirement**: FR-004

## Phase 2: 配置

- [ ] 2.1 新增 `agent/os_runtime/config.py`
  - 定义默认关闭的 `os_runtime` 配置。
  - 提供从 dict 加载或归一化配置的轻量入口。
  - **Requirement**: FR-007

- [ ] 2.2 更新 `hermes_cli/config.py::DEFAULT_CONFIG`
  - 追加 `os_runtime` 配置段。
  - 不 bump config version。
  - **Requirement**: FR-008

## Phase 3: 测试

- [ ] 3.1 新增 `tests/os_runtime/test_domain.py`
  - 覆盖枚举值、对象构造、JSON round-trip、metadata 保留、中文内容保留。
  - **Requirement**: FR-004, FR-009

- [ ] 3.2 新增 `tests/os_runtime/test_config.py`
  - 覆盖默认配置、`DEFAULT_CONFIG` 集成、自动能力默认关闭。
  - **Requirement**: FR-007, FR-008, FR-009, FR-010

- [ ] 3.3 运行聚焦测试
  - `pytest tests/os_runtime/test_domain.py tests/os_runtime/test_config.py`
  - 如配置加载有现有测试，追加对应现有测试。
  - **Requirement**: SC-001, SC-006

## Phase 4: 交付检查

- [ ] 4.1 检查 diff 范围
  - 只包含模块 0 协议、配置和测试相关文件。
  - 不包含 Linz World 网络、runtime driver、事件投影或工具执行实现。

- [ ] 4.2 更新交接说明
  - 确认 Builder Agent 可按 `spec.md`、`plan.md` 和本任务清单实现。
