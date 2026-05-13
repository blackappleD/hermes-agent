# Tasks: Linz World 原生身份与世界接入

**Input**: 来自 `specs/001-native-linz-identity/` 的 spec-kit 设计文档
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `quickstart.md`, `contracts/`
**Feature**: `001-native-linz-identity`

## Format: `[ID] [P?] [Story] Description with file path`

- **[P]**: 可并行执行, 前提是任务写入不同文件且不依赖未完成任务
- **[Story]**: 用户故事标签, 对应 `spec.md` 的 US1-US4
- 所有实现任务都必须先读对应 contract, 并保持 raw token、私密字段、restricted payload 不进入 prompt、普通工具结果或用户默认视图

## Phase 1: Setup

**Purpose**: 创建 Linz World 原生模块、测试目录和测试桩的最小结构。

- [ ] T001 Create `agent/linz_world/__init__.py` and module package skeleton listed in `specs/001-native-linz-identity/plan.md`
- [ ] T002 [P] Create `tests/linz_world/` with shared pytest fixtures in `tests/linz_world/conftest.py`
- [ ] T003 [P] Create fake Linz World service and fake transport helpers in `tests/linz_world/fakes.py`
- [ ] T004 [P] Add empty CLI test module `tests/linz_world/test_cli.py` and tool test module `tests/linz_world/test_tools.py`

---

## Phase 2: Foundation

**Purpose**: Build shared data, config, redaction, service, storage, and governance primitives that block every user story.

**Critical**: No user story implementation should proceed before these tasks are complete.

- [ ] T005 Define Linz World config defaults and validation in `agent/linz_world/config.py`
- [ ] T006 [P] Define data types for identity, registration state, auth map, event dispatch, receipts, compute, memory, relationship, and governance in `agent/linz_world/models.py`
- [ ] T007 [P] Implement redaction and restricted audit reference helpers in `agent/linz_world/redaction.py`
- [ ] T008 [P] Implement formal subject/event_type catalog and forbidden settlement-transfer checks in `agent/linz_world/event_catalog.py`
- [ ] T009 Implement profile-aware runtime state repository in `agent/linz_world/event_state.py`
- [ ] T010 Implement Linz World service client boundary with fake-friendly interfaces in `agent/linz_world/api_client.py`
- [ ] T011 Implement governance result helpers and real-time authorization preflight in `agent/linz_world/governance.py`
- [ ] T012 [P] Add foundation tests for config validation and profile scoping in `tests/linz_world/test_config.py`
- [ ] T013 [P] Add foundation tests for event catalog and redaction behavior in `tests/linz_world/test_event_catalog.py`
- [ ] T014 [P] Add foundation tests for event state idempotency and receipt state transitions in `tests/linz_world/test_event_state.py`
- [ ] T014A [P] Add Linz World HTTP envelope, service_url normalization, registration, login, credential, subjects array, compute, and memory contract fixture tests in `tests/linz_world/test_api_contract.py`
- [ ] T014B [P] Add contract fixtures proving `GET /api/v1/event/subjects` accepts `{code:0,data:[...]}` and `{code:0,data:[]}` as successful `PredefinedSubject[]` envelopes for authorization map generation in `tests/linz_world/test_api_contract.py`

**Checkpoint**: Shared foundation is ready; user stories can be implemented incrementally.

---

## Phase 3: User Story 1 - Agent 自动获得原生世界身份 (P1)

**Goal**: A Hermes profile receives one stable Linz World original spirit identity before agent persona load; registration failure blocks persona load.

**Independent Test**: Load the same Hermes profile repeatedly without `linz-world-skill`; verify exactly one original spirit identity is reused and failed registration prevents persona startup with diagnostics.

### Tests for US1

- [ ] T015 [P] [US1] Add identity registration idempotency tests in `tests/linz_world/test_identity_bootstrap.py`
- [ ] T016 [P] [US1] Add fail-closed persona bootstrap tests in `tests/linz_world/test_identity_bootstrap.py`
- [ ] T017 [P] [US1] Add partial identity field fail-closed tests in `tests/linz_world/test_identity_bootstrap.py`

### Implementation for US1

- [ ] T018 [US1] Implement profile identity field load/save helpers in `agent/linz_world/profile_fields.py`
- [ ] T019 [US1] Implement idempotent original spirit registration and verification in `agent/linz_world/identity.py`
- [ ] T020 [US1] Implement persona load bootstrap and fail-closed diagnostics in `agent/linz_world/bootstrap.py`
- [ ] T021 [US1] Integrate bootstrap with agent/persona load path in `run_agent.py`
- [ ] T022 [US1] Add Linz status data provider for registered, pending, and failed states in `agent/linz_world/status.py`
- [ ] T023 [US1] Wire `hermes linz status` registration diagnostics in `hermes_cli/linz.py`
- [ ] T024 [US1] Register the `linz` CLI command group in `hermes_cli/commands.py`
- [ ] T024A [US1] Replace any Hermes placeholder registration route such as `/identity/original-spirit` with `POST /api/v1/auth/register`, using `publicKey`, `publicKeyType`, `fingerprint`, `metadata`, and parsing `data.agentId`, `data.soulId`, `data.soulHash`, `data.accessToken`, `data.expiresIn`, `data.registeredAt`

**Checkpoint**: US1 is independently usable and satisfies MVP identity behavior.

---

## Phase 4: User Story 2 - 用户管理原生 Linz World 能力 (P2)

**Goal**: Users and agents can inspect and operate Linz World status, login, auth map, events, publish entrypoint, compute, Soul Memory, and relationship capabilities without installing `linz-world-skill`.

**Independent Test**: In an environment without `linz-world-skill`, execute native CLI commands and agent tools for status, login, map, recent events, publish entrypoint, compute, Soul Memory, and relationship discovery.

### Tests for US2

- [ ] T025 [P] [US2] Add native CLI command tests in `tests/linz_world/test_cli.py`
- [ ] T026 [P] [US2] Add native agent tool schema and redaction tests in `tests/linz_world/test_tools.py`
- [ ] T027 [P] [US2] Add native CLI discoverability tests in `tests/linz_world/test_cli.py`

### Implementation for US2

- [ ] T028 [US2] Implement login, logout, map, events, and publish CLI handlers in `hermes_cli/linz.py`
- [ ] T029 [US2] Implement Linz login/session operations in `agent/linz_world/auth.py`
- [ ] T030 [US2] Implement native Linz agent tools in `tools/linz_world_tools.py`
- [ ] T031 [US2] Register Linz tools with the existing tool registry in `tools/registry.py`
- [ ] T032 [US2] Expose Linz toolset entries in `toolsets.py`
- [ ] T033 [US2] Ensure command and tool outputs use redacted summaries in `agent/linz_world/status.py`
- [ ] T033A [US2] Align login, refresh, credential issue/revoke, and authorization summary with `POST /api/v1/event/agents/login`, `POST /api/v1/event/agents/refresh`, `POST /api/v1/event/agents/credentials`, `POST /api/v1/event/agents/credentials/revoke`, and `GET /api/v1/event/subjects`; do not call unconfirmed authorization-map endpoints

**Checkpoint**: US2 is independently visible through CLI and tools, with no skill dependency.

---

## Phase 5: User Story 3 - 世界事件可靠进入 Hermes 事件流 (P2)

**Goal**: Linz World events are persisted, deduplicated, projected into Hermes gateway/session events, and retried at most three times for internal processing failures.

**Independent Test**: Inject the same valid world event five times; verify one user-visible event, one agent turn trigger at most, persisted dispatch state, and failed state after three internal processing failures.

### Tests for US3

- [ ] T034 [P] [US3] Add gateway adapter projection tests in `tests/linz_world/test_gateway_adapter.py`
- [ ] T035 [P] [US3] Add duplicate event and duplicate stream sequence tests in `tests/linz_world/test_event_state.py`
- [ ] T036 [P] [US3] Add retry limit and manual handling tests in `tests/linz_world/test_event_state.py`

### Implementation for US3

- [ ] T037 [US3] Implement world event validation, persistence, dedupe, and dispatch transitions in `agent/linz_world/event_state.py`
- [ ] T038 [US3] Implement world-to-Hermes event projection in `agent/linz_world/event_bus.py`
- [ ] T039 [US3] Implement `linz_world` gateway platform adapter in `agent/linz_world/gateway_adapter.py`
- [ ] T040 [US3] Register dynamic Linz World platform integration in `gateway/platform_registry.py`
- [ ] T041 [US3] Connect adapter output to existing `gateway.platforms.base.MessageEvent` flow in `gateway/platforms/base.py`
- [ ] T042 [US3] Add recent event query support for CLI/tools in `agent/linz_world/event_state.py`

**Checkpoint**: US3 events can be received reliably without blocking external ack on LLM completion.

---

## Phase 6: User Story 4 - 外部发布、算力、记忆和关系受治理保护 (P3)

**Goal**: Publish, world compute, Soul Memory, and relationship mutations are available but fail closed on missing login, unknown authorization, forbidden catalog events, or refresh failure.

**Independent Test**: Attempt unregistered, unauthenticated, unauthorized, forbidden settlement-transfer, malformed payload, compute, memory, and relationship requests; verify each returns allowed, rejected, failed, or uncertain with audit state.

### Tests for US4

- [ ] T043 [P] [US4] Add authorization and governance preflight tests in `tests/linz_world/test_auth_and_authorization.py`
- [ ] T044 [P] [US4] Add NATS publish success, reject, failure, missing transport, and uncertain receipt tests in `tests/linz_world/test_publisher.py`; verify HTTP `/api/v1/event/publish` is never called for native publish
- [ ] T045 [P] [US4] Add compute, memory, and relationship side-effect tests in `tests/linz_world/test_compute_memory_relationship.py`, including missing login token reference fail-closed behavior
- [ ] T045A [P] [US4] Add Linz World compute contract fixtures in `tests/linz_world/test_api_contract.py` covering `Authorization: Bearer <compute_api_key>`, missing/invalid/revoked key 401 envelopes, and successful `data.request_id/os_id/provider/model/choices/reservation/usage` parsing
- [ ] T045B [P] [US4] Add Linz World relationship projection contract fixtures in `tests/linz_world/test_api_contract.py` covering `GET /api/v1/memory/projections/{agentId}/relationships` MemoryProjection fields `projection_id/agent_id/projection_type/source_version/content/generated_at/generated_by` and ensuring projection content is not discarded when parsed relationships are empty
- [ ] T046 [P] [US4] Add no-credential-leak regression tests for tools and CLI in `tests/linz_world/test_tools.py`

### Implementation for US4

- [ ] T047 [US4] Implement real-time authorization refresh for all side effects in `agent/linz_world/auth.py`
- [ ] T048 [US4] Implement publish request validation, governance, NATS transport publish, ack/sequence diagnostic receipt, and receipt persistence in `agent/linz_world/publisher.py`
- [ ] T049 [US4] Implement world compute invocation in `agent/linz_world/compute.py` using the profile-local Linz World login token reference, with request_id receipt, provider/model summary, usage/reservation diagnostics, and no raw token exposure
- [ ] T050 [US4] Implement Soul Memory write validation with `artifact_ref` and `sink_reason` in `agent/linz_world/memory.py`
- [ ] T051 [US4] Implement relationship read as MemoryProjection preservation plus optional parsed relationships, and ACTIVE mutation governance in `agent/linz_world/relationship.py`
- [ ] T052 [US4] Update `tools/linz_world_tools.py` to route publish, compute, memory, and relationship calls through governance helpers
- [ ] T053 [US4] Update `hermes_cli/linz.py` publish path to surface `published`, `rejected`, `failed`, and `uncertain` outcomes
- [ ] T053A [US4] Align publish with `linz-world-skill` NATS event publishing semantics, compute with current Linz World `POST /api/v1/compute/chat` API-key contract and response fields, subjects with `GET /api/v1/event/subjects` array `data`, and memory with `/api/v1/memory/seeds`, `/api/v1/memory/soul`, `/api/v1/memory/events`, `/api/v1/memory/projections`, `/api/v1/memory/snapshots`, and `/api/v1/memory/lineage`; do not use HTTP `/api/v1/event/publish` for native publish

**Checkpoint**: US4 external side effects are governed and auditable.

---

## Phase 7: Polish and Cross-Cutting Validation

**Purpose**: Finish documentation, privacy review, and regression coverage after all user stories.

- [ ] T054 [P] Update `specs/001-native-linz-identity/quickstart.md` if implementation command names or test paths changed
- [ ] T055 [P] Add developer notes for Linz World native module boundaries in `docs/plans/基于张力场的元神运行时框架技术白皮书.md`
- [ ] T056 Run `python -m pytest tests/linz_world` and record any failures in the implementation handoff
- [ ] T057 Run targeted regressions from `specs/001-native-linz-identity/quickstart.md`
- [ ] T058 Audit CLI, tool, gateway, and logs for raw token/private field/restricted payload exposure in `agent/linz_world/`, `hermes_cli/linz.py`, and `tools/linz_world_tools.py`
- [ ] T059 Audit `agent/linz_world/api_client.py`, `auth.py`, `identity.py`, `compute.py`, `memory.py`, `publisher.py`, tests, and docs for placeholder paths or field names (`/identity/original-spirit`, remote `os_id`, `hermes_profile` as top-level register field, extra legacy service URL config key)

---

## Dependencies and Execution Order

- **Phase 1 Setup**: no dependencies.
- **Phase 2 Foundation**: depends on Phase 1 and blocks all user stories.
- **US1 (P1)**: depends on Phase 2; recommended MVP.
- **US2 (P2)**: depends on Phase 2 and uses US1 status/identity behavior for full value.
- **US3 (P2)**: depends on Phase 2 and can proceed in parallel with US2 after identity/status interfaces settle.
- **US4 (P3)**: depends on Phase 2 and should reuse US2 command/tool surfaces plus US3 event state for receipts/audit.
- **Polish**: depends on all selected user stories.

## Parallel Opportunities

- T002-T004 can run in parallel after T001.
- T006-T008 and T012-T014 can run in parallel once T005 establishes config shape.
- T014A/T014B can run in parallel with other foundation tests after T010 defines the HTTP client boundary.
- US2 CLI tests (T025, T027) and tool tests (T026) can run in parallel.
- US3 adapter, duplicate, and retry tests (T034-T036) can run in parallel.
- US4 governance, publish, compute/memory/relationship, and privacy tests (T043-T046) can run in parallel.
- Implementation tasks in US4 can split by file after T047 establishes shared authorization behavior.

## Implementation Strategy

### MVP First

1. Complete Phase 1 and Phase 2.
2. Complete US1 only.
3. Verify identity bootstrap, idempotency, and fail-closed registration.
4. Hand back for review before enabling external side effects.

### Incremental Delivery

1. US1: stable native original spirit identity and fail-closed persona load.
2. US2: native CLI/tool visibility without `linz-world-skill`.
3. US3: reliable event ingest, dedupe, retry, and redacted projection.
4. US4: governed publish, compute, Soul Memory, and relationship side effects.

### Builder Handoff Notes

- Keep implementation commits on the same branch after Reviewer approval.
- This issue explicitly revises publish to use NATS. Prefer the existing optional transport adapter pattern; if Builder needs a concrete NATS client dependency, it must be scoped to Linz World publish/listen, documented, and covered by fake transport tests.
- Treat authorization refresh failure as a blocker for every external side effect.
- Do not implement legacy identity import, sync, or migration paths, and never read, import, sync, or migrate old `linz-world-skill` identity state in this feature.
- Treat `OPEWorld-Tech/linz-world` backend/skill contracts as authoritative. Do not keep Hermes-only placeholder service paths; if a Linz World capability is not backed by a confirmed route or NATS contract, surface `unsupported` or `unknown` and fail closed.
