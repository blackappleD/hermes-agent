# 任务: OS_RUNTIME 日志监控视图

**输入**: 来自 `specs/515-os-runtime-monitor/` 的设计文档
**前置条件**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**测试**: 本功能包含明确测试要求。后端 parser/API 使用 pytest；前端以 TypeScript build 和 quickstart 手动验证覆盖。

**组织结构**: 任务按用户故事分组，确保每个故事可以独立实现、独立测试和增量交付。

## 格式: `[ID] [P?] [Story] 描述`

- **[P]**: 可以并行运行(不同文件, 无依赖关系)
- **[Story]**: 此任务属于哪个用户故事(US1, US2, US3, US4)
- 每个任务描述都包含确切文件路径

## 路径约定

- 后端 dashboard API: `hermes_cli/web_server.py`
- OS_RUNTIME 日志聚合服务: `hermes_cli/os_runtime_logs.py`
- 后端测试: `tests/hermes_cli/test_os_runtime_logs.py`, `tests/hermes_cli/test_web_server.py`
- 前端 dashboard: `web/src/pages/LogsPage.tsx`, `web/src/lib/api.ts`, `web/src/i18n/*.ts`

---

## 阶段 1: 设置(共享基础设施)

**目的**: 建立后端 parser/API 与前端 API 类型的最小骨架，供所有故事复用。

- [X] T001 创建 `hermes_cli/os_runtime_logs.py`，定义 OS_RUNTIME 日志聚合服务入口 `get_os_runtime_logs(lines: int = 100, include_raw: bool = True) -> dict`
- [X] T002 [P] 在 `tests/hermes_cli/test_os_runtime_logs.py` 创建 OS_RUNTIME JSONL 样例写入 helper，覆盖临时 `HERMES_HOME/logs/os_runtime_YYYYMMDD.log`
- [X] T003 [P] 在 `web/src/lib/api.ts` 添加 `OSRuntimeLogsResponse`, `RuntimeModuleSnapshot`, `RuntimeParameterReading` TypeScript 接口
- [X] T004 [P] 在 `web/src/i18n/types.ts` 扩展 `logs` 文案类型，加入 OS_RUNTIME 开关、模块标题、raw line、空状态和变化提示字段

---

## 阶段 2: 基础(阻塞前置条件)

**目的**: 完成所有用户故事共享的日志读取、安全边界、API 连接和 i18n 文案。

**关键**: 此阶段完成前，不应开始用户故事 UI 集成。

- [X] T005 在 `hermes_cli/os_runtime_logs.py` 实现 profile-aware 日志文件发现，仅读取 `get_hermes_home()/logs/os_runtime_*.log`
- [X] T006 在 `hermes_cli/os_runtime_logs.py` 实现 `lines` clamp 规则，确保 raw line 请求最小 1、最大 500
- [X] T007 在 `hermes_cli/os_runtime_logs.py` 实现空响应构造，固定返回 `life_state`, `tension_field`, `action_potential` 三个 empty 模块
- [X] T008 在 `hermes_cli/web_server.py` 添加受现有 session token middleware 保护的 `GET /api/logs/os-runtime` endpoint，调用 `hermes_cli/os_runtime_logs.py`
- [X] T009 [P] 在 `web/src/lib/api.ts` 添加 `api.getOsRuntimeLogs({ lines, includeRaw })`，请求 `/api/logs/os-runtime`
- [X] T010 [P] 在 `web/src/i18n/en.ts` 添加 OS_RUNTIME 日志监控英文文案
- [X] T011 [P] 在 `web/src/i18n/zh.ts` 添加 OS_RUNTIME 日志监控中文文案
- [X] T012 在 `tests/hermes_cli/test_web_server.py` 添加 `/api/logs/os-runtime` 空状态 API 测试，断言不影响现有 `/api/logs`

**检查点**: 后端 endpoint 可返回稳定空响应，前端 API 类型和文案可编译。

---

## 阶段 3: 用户故事 1 - 从日志页切换到 OS_RUNTIME 观察 (优先级: P1) MVP

**目标**: 用户可以在日志页右上角自动刷新开关左侧打开/关闭 `OS_RUNTIME`，并在普通日志和专属观察视图之间切换。

**独立测试**: 打开 dashboard `/logs`，确认 `OS_RUNTIME` 开关位于自动刷新左侧；打开后页面主体切换为 OS_RUNTIME 视图，关闭后恢复普通日志列表和原筛选行为。

### 用户故事 1 的测试

- [X] T013 [US1] 在 `web/src/pages/LogsPage.tsx` 手动验证前写出切换验收清单注释或测试计划块，覆盖开关位置、普通模式回归、自动刷新状态保持
- [X] T014 [US1] 在 `tests/hermes_cli/test_web_server.py` 添加 endpoint 回归测试，确认 `GET /api/logs` 仍只返回 `{file, lines}` 形状

### 用户故事 1 的实施

- [X] T015 [US1] 在 `web/src/pages/LogsPage.tsx` 增加 `osRuntimeMode` state，并把 `OS_RUNTIME` Switch 渲染到 page header 自动刷新开关左侧
- [X] T016 [US1] 在 `web/src/pages/LogsPage.tsx` 调整 `fetchLogs` 流程，`osRuntimeMode=false` 时保持现有 `api.getLogs` 行为不变
- [X] T017 [US1] 在 `web/src/pages/LogsPage.tsx` 新增 OS_RUNTIME 模式 fetch 分支，`osRuntimeMode=true` 时调用 `api.getOsRuntimeLogs`
- [X] T018 [US1] 在 `web/src/pages/LogsPage.tsx` 新增 OS_RUNTIME 模式基础容器，显示模块视图占位、加载状态和错误状态
- [X] T019 [US1] 在 `web/src/pages/LogsPage.tsx` 确保切换 `osRuntimeMode` 不重置 `autoRefresh`, `file`, `level`, `component`, `lineCount`
- [X] T020 [US1] 运行 `cd web && npm run build`，修复 `web/src/pages/LogsPage.tsx` 和 `web/src/lib/api.ts` 中的类型或构建错误

**检查点**: 用户故事 1 完成后，OS_RUNTIME 开关和视图切换可独立演示，普通日志页核心流程不回归。

---

## 阶段 4: 用户故事 2 - 按模块查看 OS_RUNTIME 参数变化 (优先级: P1)

**目标**: OS_RUNTIME 模式按生命状态、张力场、行动势能以及可选附加模块展示最新参数、更新时间和变化提示。

**独立测试**: 使用包含生命状态、张力场和行动势能 JSONL 的样例，打开 OS_RUNTIME 模式后能看到每个模块的标题、更新时间、参数名、当前值和变化提示。

### 用户故事 2 的测试

- [X] T021 [US2] 在 `tests/hermes_cli/test_os_runtime_logs.py` 添加 life_state JSONL 解析测试，断言 energy、fatigue、wakefulness、curiosity、restraint 参数进入 `life_state` 模块
- [X] T022 [US2] 在 `tests/hermes_cli/test_os_runtime_logs.py` 添加 tension_set JSONL 解析测试，断言 active tension count、intensity、activation、trend、confidence 进入 `tension_field` 模块
- [X] T023 [US2] 在 `tests/hermes_cli/test_os_runtime_logs.py` 添加 action_potential JSONL 解析测试，断言 value_potential、learning_potential、risk_cost、overall_score、recommended_depth 进入 `action_potential` 模块
- [X] T024 [US2] 在 `tests/hermes_cli/test_os_runtime_logs.py` 添加同模块连续快照变化测试，断言数值字段生成 `up`、`down` 或 `unchanged`

### 用户故事 2 的实施

- [X] T025 [US2] 在 `hermes_cli/os_runtime_logs.py` 实现 JSONL decode 到 `OSRuntimeLogRecord` 字典，保留 timestamp、step、trace_id、data、raw_line
- [X] T026 [US2] 在 `hermes_cli/os_runtime_logs.py` 实现 life_state 字段提取，支持 `data.life_state` 和 `data.state.life_state`
- [X] T027 [US2] 在 `hermes_cli/os_runtime_logs.py` 实现 tension_field 字段提取，支持 `data.tension_set.core_tensions` 和 `data.tension_set.dynamic_tensions`
- [X] T028 [US2] 在 `hermes_cli/os_runtime_logs.py` 实现 action_potential 字段提取，支持 `data.action_potential`
- [X] T029 [US2] 在 `hermes_cli/os_runtime_logs.py` 实现附加模块提取，覆盖 `self_prompt`, `open_intent`, `arbiter`, `runtime_driver`
- [X] T030 [US2] 在 `hermes_cli/os_runtime_logs.py` 实现相邻快照 diff，填充 `previous_value`, `change`, `delta`
- [X] T031 [US2] 在 `tests/hermes_cli/test_web_server.py` 添加 `/api/logs/os-runtime` 样例响应测试，断言返回 modules、source_files、updated_at、raw_line_count
- [X] T032 [US2] 在 `web/src/pages/LogsPage.tsx` 实现 `RuntimeModuleSnapshot` 渲染组件，展示标题、更新时间、摘要、参数行和变化提示
- [X] T033 [US2] 在 `web/src/pages/LogsPage.tsx` 将生命状态、张力场、行动势能作为固定 P1 模块排序展示
- [X] T034 [US2] 在 `web/src/pages/LogsPage.tsx` 将 SelfPrompt、OpenIntent、Arbitration、Runtime Driver 作为有数据时出现的附加模块展示
- [X] T035 [US2] 运行 `pytest tests/hermes_cli/test_os_runtime_logs.py tests/hermes_cli/test_web_server.py -k "os_runtime or logs"`，修复 `hermes_cli/os_runtime_logs.py` 和 `hermes_cli/web_server.py` 相关失败

**检查点**: 用户故事 2 完成后，模块化参数视图可用，并能显示最新值和变化提示。

---

## 阶段 5: 用户故事 3 - 展开底部 raw line 日志核对细节 (优先级: P2)

**目标**: 用户可以在 OS_RUNTIME 模块下方展开 raw line 区域，独立滚动查看 OS_RUNTIME 原始日志和无法解析的日志行。

**独立测试**: 在 OS_RUNTIME 模式底部展开 raw line 区域，确认该区域独立滚动、只显示 OS_RUNTIME 相关原始行，并可折叠回模块视图。

### 用户故事 3 的测试

- [X] T036 [US3] 在 `tests/hermes_cli/test_os_runtime_logs.py` 添加坏 JSON 行保留测试，断言 `parse_error_count` 增加且 raw line 未丢失
- [X] T037 [US3] 在 `tests/hermes_cli/test_os_runtime_logs.py` 添加 unknown step raw line 测试，断言未知 OS_RUNTIME 行进入 `raw_lines`
- [X] T038 [US3] 在 `tests/hermes_cli/test_web_server.py` 添加 `include_raw=false` 测试，断言模块仍返回且 `raw_lines` 可为空

### 用户故事 3 的实施

- [X] T039 [US3] 在 `hermes_cli/os_runtime_logs.py` 实现 invalid JSON 和 unknown step 的 raw-only 记录路径
- [X] T040 [US3] 在 `hermes_cli/os_runtime_logs.py` 实现 `include_raw` 参数处理，允许 API 省略 raw line 文本但保留模块快照
- [X] T041 [US3] 在 `web/src/pages/LogsPage.tsx` 新增 `rawExpanded` state 和底部 raw line 展开/折叠按钮
- [X] T042 [US3] 在 `web/src/pages/LogsPage.tsx` 实现 raw line 独立滚动容器，使用 `font-mono-ui` 和日志页现有颜色分类
- [X] T043 [US3] 在 `web/src/pages/LogsPage.tsx` 调整自动刷新后的 raw line 滚动行为，避免用户查看历史时强制跳到底部
- [X] T044 [US3] 运行 `cd web && npm run build`，修复 `web/src/pages/LogsPage.tsx` raw line UI 相关构建错误

**检查点**: 用户故事 3 完成后，raw line 证据区满足展开、折叠、独立滚动和未解析日志保底。

---

## 阶段 6: 用户故事 4 - 空状态与异常日志可理解 (优先级: P3)

**目标**: 没有 OS_RUNTIME 日志、只有部分模块日志或日志格式异常时，页面清晰展示空/局部状态，不误导用户。

**独立测试**: 使用无 OS_RUNTIME 日志、只有部分模块日志、包含格式异常日志的样例，确认页面显示缺失提示、局部模块和 raw line 证据。

### 用户故事 4 的测试

- [X] T045 [US4] 在 `tests/hermes_cli/test_os_runtime_logs.py` 添加无 OS_RUNTIME 日志测试，断言返回三个 empty P1 模块和 `empty_reason`
- [X] T046 [US4] 在 `tests/hermes_cli/test_os_runtime_logs.py` 添加部分模块日志测试，断言已有模块为 `ok`，缺失 P1 模块为 `empty`
- [X] T047 [US4] 在 `tests/hermes_cli/test_os_runtime_logs.py` 添加敏感字段测试，断言 parser 不还原或扩大暴露 redacted token 字段
- [X] T048 [US4] 在 `tests/hermes_cli/test_web_server.py` 添加 `lines` clamp 测试，断言 `/api/logs/os-runtime?lines=9999` 响应 limits 最大为 500

### 用户故事 4 的实施

- [X] T049 [US4] 在 `hermes_cli/os_runtime_logs.py` 完善 empty/partial/stale 状态生成，避免缺失字段显示为默认零值
- [X] T050 [US4] 在 `hermes_cli/os_runtime_logs.py` 确保 `updated_at` 来自最新日志记录，而不是当前服务器时间
- [X] T051 [US4] 在 `web/src/pages/LogsPage.tsx` 实现 OS_RUNTIME 无数据空状态，展示 `empty_reason` 并保留刷新/返回普通日志入口
- [X] T052 [US4] 在 `web/src/pages/LogsPage.tsx` 实现模块 partial/empty 状态样式，明确标记“暂无数据”或等价状态
- [X] T053 [US4] 在 `web/src/pages/LogsPage.tsx` 确保长参数值、徽标和 raw line 区域在常见桌面宽度下不互相遮挡
- [X] T054 [US4] 运行 `pytest tests/hermes_cli/test_os_runtime_logs.py tests/hermes_cli/test_web_server.py -k "os_runtime or logs"`，修复空状态、异常日志和 clamp 相关失败

**检查点**: 用户故事 4 完成后，无日志、部分日志和异常日志都能清晰呈现。

---

## 阶段 7: 完善与横切关注点

**目的**: 完成全量验证、视觉检查、文档对齐和回归确认。

- [X] T055 [P] 在 `web/src/i18n/en.ts` 和 `web/src/i18n/zh.ts` 校对 OS_RUNTIME 文案，确保模块标题、变化提示和空状态自然准确
- [X] T056 [P] 在 `specs/515-os-runtime-monitor/quickstart.md` 按最终实现更新手动验证命令和样例响应字段
- [X] T057 在 `web/src/pages/LogsPage.tsx` 做 UI 清理，确保没有卡片嵌套卡片、文字遮挡或一键切换造成布局跳动
- [X] T058 运行 `pytest tests/hermes_cli/test_os_runtime_logs.py tests/hermes_cli/test_web_server.py -k "os_runtime or logs"` 完整后端验证
- [X] T059 运行 `cd web && npm run build` 完整前端构建验证
- [X] T060 按 `specs/515-os-runtime-monitor/quickstart.md` 手动验证 `/logs` 普通模式、OS_RUNTIME 模式、自动刷新、raw line 展开和空状态

---

## 依赖关系与执行顺序

### 阶段依赖关系

- **阶段 1 设置**: 无依赖，可立即开始。
- **阶段 2 基础**: 依赖阶段 1，阻塞所有用户故事。
- **阶段 3 US1**: 依赖阶段 2；MVP 范围。
- **阶段 4 US2**: 依赖阶段 2；建议在 US1 后接入 UI，但后端 parser 测试可与 US1 前端工作并行。
- **阶段 5 US3**: 依赖 US2 的 raw line 响应和模块 UI。
- **阶段 6 US4**: 依赖阶段 2；可与 US3 并行处理后端异常路径，但最终 UI 状态依赖 US1/US2。
- **阶段 7 完善**: 依赖目标故事完成。

### 用户故事依赖关系

- **US1 (P1)**: 可在基础完成后独立实现，是 MVP。
- **US2 (P1)**: 后端 parser 可在基础完成后独立实现；最终 UI 展示依赖 US1 的 OS_RUNTIME 模式容器。
- **US3 (P2)**: 依赖 OS_RUNTIME 响应包含 raw_lines，建议在 US2 后实现。
- **US4 (P3)**: 后端空/异常状态可独立实现；最终视觉状态依赖 US1/US2 UI。

### 每个用户故事内部

- 测试任务必须先于对应实现任务完成并失败。
- 后端 parser/service 先于 FastAPI endpoint。
- API types 先于前端 fetch 分支。
- 前端数据 fetch 先于模块渲染。
- 故事完成后运行对应 checkpoint 验证。

### 并行机会

- T002、T003、T004 可并行。
- T009、T010、T011 可并行。
- US2 的 T021、T022、T023 都落在同一文件，应按顺序写入，避免补丁冲突。
- US3 的 T036、T037 都落在同一文件，应按顺序写入，避免补丁冲突。
- US4 的 T045、T046、T047 都落在同一文件，应按顺序写入，避免补丁冲突。
- 后端 parser 任务 T025-T030 与 US1 前端开关任务 T015-T019 在不同文件中可由不同执行者并行推进，但集成前需协调 API shape。

---

## 并行示例: 用户故事 2

```bash
任务: "在 hermes_cli/os_runtime_logs.py 实现 life_state 字段提取"
任务: "在 web/src/pages/LogsPage.tsx 实现 RuntimeModuleSnapshot 渲染组件"
任务: "在 tests/hermes_cli/test_web_server.py 添加 /api/logs/os-runtime 样例响应测试"
```

> 注意: 三个任务分别落在 service、frontend 和 API 测试文件，可在 API shape 已对齐后并行推进。

## 并行示例: 用户故事 4

```bash
任务: "在 hermes_cli/os_runtime_logs.py 完善 empty/partial/stale 状态生成"
任务: "在 web/src/pages/LogsPage.tsx 实现 OS_RUNTIME 无数据空状态"
任务: "在 tests/hermes_cli/test_web_server.py 添加 lines clamp 测试"
```

> 注意: 后端状态生成、前端空状态和 API clamp 测试在不同文件，可并行推进后再集成验证。

---

## 实施策略

### 仅 MVP(US1)

1. 完成阶段 1: 设置。
2. 完成阶段 2: 基础 endpoint、API 类型和 i18n。
3. 完成阶段 3: `OS_RUNTIME` 开关和视图切换。
4. 验证普通日志模式和 OS_RUNTIME 空视图可切换。

### 增量交付

1. 设置 + 基础: 后端 endpoint 返回稳定空响应，前端可调用。
2. US1: 日志页可切换 OS_RUNTIME 模式。
3. US2: 模块参数可展示生命状态、张力场、行动势能。
4. US3: raw line 证据区可展开和滚动。
5. US4: 空/异常/部分数据状态完善。
6. 完善: 全量 pytest、前端 build、quickstart 手动验证。

### 并行团队策略

1. 一名执行者完成 `hermes_cli/os_runtime_logs.py` parser 与 `tests/hermes_cli/test_os_runtime_logs.py`。
2. 一名执行者完成 `hermes_cli/web_server.py` endpoint 与 `tests/hermes_cli/test_web_server.py`。
3. 一名执行者完成 `web/src/lib/api.ts`, `web/src/i18n/*.ts`, `web/src/pages/LogsPage.tsx`。
4. 集成时以 `contracts/os-runtime-logs-api.md` 为 API shape 的单一来源。

---

## 注意事项

- `[P]` 仅表示文件不同或逻辑上可并行；同一文件任务并行时需要人工协调补丁边界。
- 不得新增必需第三方依赖。
- 不得改变 OS_RUNTIME runtime 决策链、配置、后台循环或日志写入语义。
- 不得把 OS_RUNTIME 专属观察做成新的侧边栏主页面；入口必须在 `/logs` 页面。
- 缺失参数必须显示 unknown/暂无数据，不能用默认零值误导用户。
- raw line 展示只能使用当前 profile 日志中已有的 redacted 文本，不得重构或暴露 secrets。
