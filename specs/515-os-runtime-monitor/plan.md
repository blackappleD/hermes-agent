# 实施计划: OS_RUNTIME 日志监控视图

**分支**: `515-os-runtime-monitor` | **日期**: 2026-05-14 | **规范**: [spec.md](./spec.md)
**输入**: `specs/515-os-runtime-monitor/spec.md`

## 摘要

在现有 dashboard 日志页内增加 `OS_RUNTIME` 观察模式。页面右上角在自动刷新左侧新增开关；关闭时保持普通日志页不变，打开时调用只读 OS_RUNTIME 日志聚合接口，按生命状态、张力场、行动势能和相关附加模块展示最新参数、变化提示和更新时间，并在底部提供可展开 raw line 滚动区。实现复用现有 React/Vite dashboard、FastAPI backend、profile-aware Hermes log path 和已存在的 `os_runtime_YYYYMMDD.log` JSONL debug log，不新增必需依赖。

## 技术背景

**语言/版本**: Python 3.x；TypeScript；React 19；Vite
**主要依赖**: FastAPI、Pydantic、React、lucide-react、`@nous-research/ui` dashboard components；不新增必需第三方依赖
**存储**: `$HERMES_HOME/logs/` 下 profile-aware log files；OS_RUNTIME 专属来源优先为 `os_runtime_YYYYMMDD.log` JSONL，并保留 agent/gateway/errors 普通日志读取
**测试**: pytest；TypeScript build/lint via existing `web` scripts
**目标平台**: Hermes local dashboard `/logs`
**项目类型**: Python FastAPI backend + React dashboard frontend
**性能目标**: 单次刷新读取最多 500 条 raw OS_RUNTIME 行用于展示；常规自动刷新间隔沿用日志页 5 秒；解析失败不阻断页面展示
**约束条件**: 只读观察能力；不改变 OS_RUNTIME 决策链；不暴露未脱敏 secrets；不破坏普通日志页筛选/刷新行为；所有 log path 使用 profile-aware helpers
**规模/范围**: 单 dashboard 日志页内的视图切换；首版聚合当前 profile 最近 OS_RUNTIME 日志，不做跨 profile 或长期统计

**Language/Version**: Python 3.x; TypeScript; React 19; Vite
**Primary Dependencies**: FastAPI, Pydantic, React, lucide-react, `@nous-research/ui`; no new required dependencies

## 章程检查

- **Profile-Scoped State**: 本功能不新增持久化状态；所有日志读取必须通过 `get_hermes_home()` 读取当前 profile 的 `logs/`。
- **Native Surfaces Before Optional Skills**: 作为 dashboard 原生日志页能力实现，不依赖 plugin 或 optional skill。
- **Fail-Closed External Side Effects**: 本功能只读日志，不执行外部副作用；任何解析异常都返回空/局部数据而不是触发 runtime 操作。
- **Privacy and Audit Separation**: OS_RUNTIME JSONL 已由 `agent.os_runtime.debug_log` 做 redaction；新增聚合层不得绕过 redaction，不得从受限原始 payload 重构敏感内容。raw line 展示仅使用已写入日志的文本，并受 dashboard session token 保护。
- **Testable Incremental Delivery**: 后端解析与 API 可独立测试；前端切换和空状态可独立验证；普通日志页回归必须覆盖。

## 项目结构

### 文档(此功能)

```text
specs/515-os-runtime-monitor/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── os-runtime-logs-api.md
│   └── os-runtime-logs-ui.md
└── checklists/
    └── requirements.md
```

### 源代码(仓库根目录)

```text
hermes_cli/
├── web_server.py
└── os_runtime_logs.py

web/src/
├── lib/
│   └── api.ts
├── pages/
│   └── LogsPage.tsx
└── i18n/
    ├── en.ts
    ├── zh.ts
    └── types.ts

tests/hermes_cli/
├── test_os_runtime_logs.py
└── test_web_server.py
```

**结构决策**: 保持现有 dashboard 日志页作为唯一入口。新增 `hermes_cli/os_runtime_logs.py` 承担日志发现、JSONL 解析、模块快照聚合和 raw line 过滤，避免把解析规则堆进 FastAPI route 或 React 组件。`web_server.py` 只暴露只读 endpoint；`LogsPage.tsx` 负责开关、布局和展示。

## 技术方案

### 1. 后端日志聚合

- 新增 `hermes_cli/os_runtime_logs.py`，提供纯函数/服务函数：
  - 发现当前 profile 最近的 `os_runtime_*.log` 文件，优先读取当天文件，必要时读取最近文件。
  - 读取尾部有限行数，逐行 JSON decode；失败行保留为 raw line。
  - 将 `step`、`phase`、`data` 映射为模块快照：`life_state`、`tension_field`、`action_potential`、`self_prompt`、`open_intent`、`arbiter`、`runtime_driver`。
  - 对同一模块保留最新快照，并与前一个可比较快照生成变化提示。
  - 返回 raw OS_RUNTIME 行列表，包含可解析和不可解析行。
- 解析层接受宽松字段：例如 `life_state` 可出现在 `data.life_state`、`data.state.life_state` 或顶层相邻字段；字段缺失时只展示已知参数。
- 不从普通 `agent.log` 中做复杂启发式解析作为首选；如需要兼容非 JSONL OS_RUNTIME 行，可只把包含 `os_runtime` / `OS_RUNTIME` / 相关 step 关键词的普通行放入 raw line，模块参数仍以结构化 JSONL 为准。

### 2. FastAPI endpoint

- 在 `hermes_cli/web_server.py` 增加只读 endpoint，例如 `GET /api/logs/os-runtime`。
- 查询参数沿用日志页习惯：`lines` 最大 500；可选 `file` 默认自动；可选 `raw_only` 或 `include_raw` 由契约固定。
- 返回结构化 payload：模块快照、raw lines、来源文件、更新时间、解析错误计数、空状态原因。
- endpoint 使用 dashboard 现有 session token middleware；不加入 public API allowlist。

### 3. 前端切换与展示

- 在 `web/src/pages/LogsPage.tsx` 增加 `osRuntimeMode` state。
- Page header 右上角在自动刷新开关左侧渲染 `OS_RUNTIME` 开关。
- `osRuntimeMode=false` 时继续调用 `api.getLogs()` 并渲染现有普通日志 UI。
- `osRuntimeMode=true` 时调用 `api.getOsRuntimeLogs()`，渲染：
  - 顶部保持现有日志页控制密度和 Badge 风格。
  - 主体为模块面板/网格：生命状态、张力场、行动势能为固定 P1 模块；SelfPrompt/OpenIntent/Arbitration/Runtime Driver 有数据时显示附加模块。
  - 每个模块使用紧凑参数行，包含名称、值、变化、更新时间、证据 step。
  - 底部 raw line 区域可折叠，展开后独立滚动。
- 自动刷新复用现有 5 秒 interval；切换 OS_RUNTIME 模式不重置 `autoRefresh`。
- 普通日志筛选 toolbar 在 OS_RUNTIME 模式下不应误导用户：可隐藏普通 file/level/component/lines filter，或仅保留 line count 作为 raw line 数量控制；具体 UI 以不破坏普通日志回归为准。

### 4. 国际化与风格

- 扩展 `web/src/i18n/types.ts`、`en.ts`、`zh.ts` 的 `logs` 文案，覆盖 `OS_RUNTIME` 开关、模块标题、空状态、raw line 展开/折叠、更新时间和变化标签。
- 保持现有 dashboard 视觉语言：现有 `Badge`、`Button`、`Switch`、`Card`、`FilterGroup`、`Segmented`、`font-mono-ui` 和日志页颜色 token。
- 布局必须使用稳定高度、滚动容器和响应式网格，避免参数值变长导致控件重排或遮挡。

### 5. 测试策略

- `tests/hermes_cli/test_os_runtime_logs.py`
  - JSONL life_state/tension_set/action_potential 解析。
  - 同模块连续快照的变化计算。
  - 无日志、缺失模块、坏 JSON 行和 unknown step 的 raw line 保留。
  - secret/redacted 字符串不被解析层还原或扩大暴露。
- `tests/hermes_cli/test_web_server.py`
  - `/api/logs/os-runtime` 空状态。
  - 样例 OS_RUNTIME 日志返回 modules + raw lines。
  - `lines` 上限和 dashboard auth 行为。
  - 现有 `/api/logs` 默认/非法文件测试不回归。
- Frontend verification
  - `cd web && npm run build`
  - 手动或 browser 验证 `/logs`：普通模式、OS_RUNTIME 模式、自动刷新、raw line 展开、空状态。

## 数据与契约

- 数据模型见 [data-model.md](./data-model.md)。
- HTTP API contract 见 [contracts/os-runtime-logs-api.md](./contracts/os-runtime-logs-api.md)。
- UI contract 见 [contracts/os-runtime-logs-ui.md](./contracts/os-runtime-logs-ui.md)。

## 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| OS_RUNTIME 日志格式演进导致解析失败 | JSONL 解析宽松匹配；未知字段保留 raw line；模块缺失显示暂无数据 |
| 普通日志页回归 | `osRuntimeMode=false` 走原有 `api.getLogs` 和渲染路径；新增测试保持 `/api/logs` 行为 |
| 大日志刷新卡顿 | 后端只读取尾部有限行；前端 raw line 限制最多 500 行并独立滚动 |
| 敏感信息展示 | 仅消费已 redacted 的 OS_RUNTIME debug log；不做反脱敏；endpoint 保持受 session token 保护 |
| UI 风格漂移或拥挤 | 复用现有组件和 token；模块卡片紧凑显示；raw line 折叠到底部 |
| 用户误以为缺失参数为 0 | 缺失字段显示暂无数据/unknown，保留最近更新时间，不填默认零值 |

## 复杂度跟踪

| 违规 | 为什么需要 | 拒绝更简单替代方案的原因 |
| --- | --- | --- |
| 新增 OS_RUNTIME 日志聚合 helper | 日志模块化解析需要独立测试，且规则会随 OS_RUNTIME 字段演进 | 直接在 React 中解析 raw lines 会重复后端 tail/filter 逻辑，难以测试并可能泄露未统一处理的文本 |
| 新增专属 API endpoint | 现有 `/api/logs` 只返回 raw `lines`，无法表达模块快照、变化、空状态和解析错误 | 在现有 endpoint 上塞入兼容字段会模糊普通日志契约，增加回归风险 |

## 阶段 1 章程复查

- **Profile-Scoped State**: 通过；只读当前 profile logs，不新增状态。
- **Native Surfaces Before Optional Skills**: 通过；dashboard 原生能力。
- **Fail-Closed External Side Effects**: 通过；无外部副作用。
- **Privacy and Audit Separation**: 通过；不扩展敏感原始 payload 暴露边界，raw line 受 dashboard auth 保护。
- **Testable Incremental Delivery**: 通过；解析、API、前端切换可分层测试。

## 验收与测试映射

- SC-001/SC-006: `LogsPage.tsx` 切换路径验证；`tests/hermes_cli/test_web_server.py` 保持 `/api/logs` 回归。
- SC-002/SC-003: `tests/hermes_cli/test_os_runtime_logs.py` 样例模块解析和连续快照变化。
- SC-004: 手动/browser 验证 raw line 展开、折叠、独立滚动；前端 build 保证结构可编译。
- SC-005: 后端空状态测试 + 前端空状态手动验证。

## 后续交接

Builder Agent 应先实现后端 parser/service 与测试，再接 FastAPI endpoint，最后更新 `LogsPage.tsx` 和 i18n。实现期间不得改变 OS_RUNTIME runtime 行为，不得把 OS_RUNTIME 专属模式做成新的侧边栏页面，不得破坏普通日志页。
