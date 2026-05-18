# Implementation Plan: 正式框架实验脚本

**Branch**: `feat/118-formal-experiment-scripts` | **Date**: 2026-05-18 | **Spec**: `specs/118-formal-experiment-scripts/spec.md`

## Summary

新增一组正式实验脚本，帮助实验人员在 Hermes/Linz/gateway/os_runtime 已运行的前提下执行 P0-P5 实验阶段，并从真实本地产物导出数据。实现重点是保守接入：prepare 先 fail-closed 检查环境，run 只通过正式 Linz World catalog/governance/publisher 发送事件，export 只读取 gateway projection ledger、os_runtime state/log、Linz state 和 evidence。

## Technical Context

**Language/Version**: Python 3.11+ and POSIX shell wrappers  
**Primary Dependencies**: Existing Hermes modules only: `agent.linz_world.*`, `gateway.event_projection_store`, `gateway.status`, `agent.os_runtime.adapters.session_store`, `agent.os_runtime.debug_log` redaction helpers where useful  
**Storage**: Existing profile-scoped `$HERMES_HOME/gateway/message_events.db`, `$HERMES_HOME/state.db`, `$HERMES_HOME/logs/os_runtime_YYYYMMDD.log`, `$HERMES_HOME/linz_world/state.json`, output under `experiment/results/<run_id>/`  
**Testing**: pytest fixtures for scripts and local DB/log files  
**Target Platform**: WSL/native Linux shell used by `scripts/install-wsl-test.sh`; Python script remains portable where possible  
**Project Type**: CLI/script feature  
**Performance Goals**: Export recent single-run data in seconds for normal local ledgers; bounded JSONL/CSV output, no full unbounded scans without time/run filters  
**Constraints**: No mock data in formal outputs; no new external service dependency; no plain-text secrets in ordinary result files; fail-closed before external side effects  
**Scale/Scope**: P0-P5 scripted experiment runs for local Hermes profiles, not a batch experiment platform

## Constitution Check

- **Profile-Scoped State**: Pass. Scripts must resolve `--profile` / `--hermes-home` and record actual paths in `manifest.json`.
- **Native Surfaces Before Optional Skills**: Pass. Feature uses core scripts and existing Hermes native Linz/gateway/os_runtime modules, not optional skills.
- **Fail-Closed External Side Effects**: Pass. `prepare` and `run` gate on login, authorization, catalog, governance and gateway state before publish.
- **Privacy and Audit Separation**: Pass. Export uses redacted summaries and refs; raw restricted values do not enter ordinary result files.
- **Testable Incremental Delivery**: Pass. Tasks split prepare, P1 formal run, export, then P0-P5/all expansion and docs.

## Project Structure

### Documentation (this feature)

```text
specs/118-formal-experiment-scripts/
├── spec.md
├── plan.md
├── data-model.md
├── quickstart.md
└── tasks.md
```

### Source Code

```text
scripts/
├── formal_experiment_prepare.sh
├── formal_experiment_run.sh
├── formal_experiment_export.py
└── formal_experiment_lib.py        # optional shared implementation

docs/
└── formal-experiment-scripts.md

tests/scripts/
├── test_formal_experiment_prepare.py
├── test_formal_experiment_run.py
└── test_formal_experiment_export.py
```

**Structure Decision**: Keep shell wrappers at the requested paths for user ergonomics. Put non-trivial parsing, status checks, scenario catalog, redaction and export logic in Python so tests can call pure functions without spawning shell.

## Phase 0: Research Notes

### Formal event source of truth

Decision: Use `agent/linz_world/event_catalog.py` as the final subject/event_type validator.  
Rationale: The issue explicitly forbids mock/legacy events, and the repository has a formal catalog with direct inbox handling and forbidden settlement transfer guards.  
Rejected: Copying event names from `docs/共博自制框架实验准备.md` verbatim, because several examples use old `mrk.*` shapes that are not formal catalog entries.

### Publication route

Decision: Reuse `agent.linz_world.publisher.publish_event()` or the existing CLI-equivalent path.  
Rationale: It already performs governance preflight, auth map lookup, receipt persistence and os_runtime world receipt projection.  
Rejected: Writing directly to NATS, gateway queues or local state files, because that would bypass formal authorization and receipts.

### Export route

Decision: Prefer existing repository/store APIs, falling back to read-only SQLite/JSONL parsing only where APIs do not expose enough fields.  
Rationale: `EventProjectionStore` and `OSRuntimeEventRepository` already encode profile-scoped paths and schemas. Logs are JSONL by design.  
Rejected: Building export from in-memory script state, because formal output must be traceable to runtime artifacts.

## Data Flow

1. `prepare` resolves Hermes home and checks Linz identity/login/auth map, gateway runtime status, Linz platform status, formal catalog availability, DB/log paths and os_runtime state availability.
2. `run` loads scenario definitions for selected phase, expands repeat/persona/target context, validates catalog and authorization, then publishes events through `publish_event()`.
3. gateway consumes/project events into `gateway/message_events.db`; os_runtime writes state side-table rows and daily JSONL logs; Linz state stores receipts.
4. `export` reads the persisted artifacts by `run_id` and/or time window, joins best-effort by event ids/trace ids/session ids, redacts summaries, and writes output files plus anomalies.

## Error Handling

- Missing login, stale auth map, gateway offline, Linz platform disabled, missing target OS id for direct inbox, non-formal event, publish rejected/failed and missing runtime transition all produce structured diagnostics.
- `prepare` and `run` return non-zero for blockers before or during publication.
- `export` writes anomalies by default and returns non-zero only with `--fail-on-anomaly`.
- Script exceptions should include the phase, run_id, checked path and next action where possible.

## Security and Redaction

- Reuse existing redaction helpers where available (`agent.linz_world.redaction`, `agent.os_runtime.adapters.events.redact_for_summary`, `agent.redact.redact_sensitive_text`).
- Treat keys matching token, api_key, password, private_key, secret, authorization, credential and bearer as sensitive in nested dicts, JSON strings and plain text.
- `manifest.json` may include filesystem paths and script versions, but not tokens or raw auth map secrets.
- CSV must only contain summaries/refs, never full payload bodies.

## Testing Strategy

- Build tests around Python functions, not only subprocess calls.
- Use temporary Hermes homes with minimal `state.db`, `gateway/message_events.db`, `linz_world/state.json` and `logs/os_runtime_*.log` fixtures.
- Verify formal catalog validation with current `agent.linz_world.event_catalog.is_formal_event()`.
- Include a secret-scanning assertion across generated output files.
- Keep at least one dry-run path documented and tested so CI does not require a live Linz World service.

## Acceptance Mapping

- AC-001 and AC-002 are covered by prepare/run tests plus dry-run and fake publisher integration.
- AC-003 and AC-004 are covered by export fixture tests.
- AC-005 is covered by fail-closed prepare/run tests.
- AC-006 is covered by docs quickstart validation and parameter parity tests.

## Open Questions

No blocking product questions. Builder may need to choose exact helper module boundaries after reading current script test conventions.

## Handoff Notes

Start with a minimal P1 path that can be tested without live services via dry-run/fake publisher. Then add real publisher invocation, export, and finally full P0-P5 scenario coverage. Do not implement business code changes unrelated to script access unless a missing read-only API blocks export.
