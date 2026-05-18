# Tasks: 正式框架实验脚本

**Input**: Design documents from `specs/118-formal-experiment-scripts/`  
**Prerequisites**: `spec.md`, `plan.md`, `data-model.md`, `quickstart.md`

## Phase 1: Foundation

**Purpose**: Shared script infrastructure and fixtures.

- [ ] T001 Create `scripts/formal_experiment_lib.py` with argument dataclasses, Hermes home/profile resolution, JSONL helpers and redaction helpers.
- [ ] T002 [P] Add test fixture builders for temporary Hermes home, `gateway/message_events.db`, `state.db`, Linz state and os_runtime JSONL logs in `tests/scripts/`.
- [ ] T003 [P] Define the formal P0-P5 scenario catalog in `scripts/formal_experiment_lib.py`, mapping doc scenarios to `agent.linz_world.event_catalog` allowed subject/event_type pairs.
- [ ] T004 Add secret-scanning test helper that asserts generated result files do not contain token/api_key/password/private_key/authorization sample values.

## Phase 2: Prepare (US1, P1)

**Goal**: Fail-closed preflight before any formal publish.

**Independent Test**: Prepare can be tested with fake status/DB/log fixtures and no live Linz service.

- [ ] T005 [P] Write prepare tests for successful environment, Linz logged out, stale/missing auth map, gateway offline, Linz platform disabled and missing DB/log paths in `tests/scripts/test_formal_experiment_prepare.py`.
- [ ] T006 Implement prepare logic using `agent.linz_world.status.status_summary()`, `gateway.status.read_runtime_status()`, `EventProjectionStore` path checks and `OSRuntimeEventRepository` read checks.
- [ ] T007 Add `scripts/formal_experiment_prepare.sh` shell wrapper that calls the Python prepare entry and preserves exit codes.
- [ ] T008 Validate prepare output includes checked profile, Hermes home, blocked reason and next action.

## Phase 3: Formal Run MVP (US2, P1)

**Goal**: Dry-run and real publish path for P1 single-event perturbation.

**Independent Test**: P1 scenario generation and publisher interaction can be tested with a fake publisher.

- [ ] T009 [P] Write run tests for formal catalog validation, `--dry-run`, illegal event rejection, P1 `--repeat 3`, missing `--target-os-id` for direct inbox and publisher rejected/failed receipts.
- [ ] T010 Implement run argument parsing for `--profile`, `--hermes-home`, `--phase`, `--run-id`, `--repeat`, `--target-os-id`, `--seed-id`, `--persona`, `--dry-run`.
- [ ] T011 Implement P1 scenario expansion with run metadata in payload and stable `scenario_id` / sequence fields.
- [ ] T012 Implement catalog/governance fail-closed checks before calling `agent.linz_world.publisher.publish_event()`.
- [ ] T013 Add `scripts/formal_experiment_run.sh` shell wrapper that calls the Python run entry and preserves exit codes.

## Phase 4: Export (US3, P1)

**Goal**: Export persisted formal artifacts and anomalies.

**Independent Test**: Export can run entirely on temporary DB/JSONL fixtures.

- [ ] T014 [P] Write export tests for required output files, run_id/time filtering, gateway projection rows, os_runtime events, os_runtime raw JSONL, Linz receipts, missing transition anomaly and `--fail-on-anomaly`.
- [ ] T015 Implement read-only gateway projection extraction from `gateway/message_events.db` via `EventProjectionStore` or compatible SQLite queries.
- [ ] T016 Implement read-only os_runtime extraction from `state.db` `os_runtime_events` and daily `logs/os_runtime_YYYYMMDD.log`.
- [ ] T017 Implement Linz state/receipt extraction from `linz_world/state.json` or current repository helper, preserving only redacted summaries and refs.
- [ ] T018 Write `manifest.json`, `events.jsonl`, `transitions.jsonl`, `os_runtime_raw.jsonl`, `summary.json`, `summary.csv`, `anomalies.json` under `experiment/results/<run_id>/`.
- [ ] T019 Apply redaction and run the secret-scanning helper across all ordinary output files.

## Phase 5: P0-P5 Coverage (US2, P1/P2)

**Goal**: Extend beyond P1 while keeping blocked stages explicit.

- [ ] T020 [P] Add scenario tests for P0 smoke, P2 event combinations, P3 life-state feedback, P4 continuous evolution and P5 multi-spirit interactions.
- [ ] T021 Implement P0, P2 and P3 scenario generation using formal catalog events and required metadata.
- [ ] T022 Implement P4 multi-round flow support with repeat/interval controls and evolution-oriented scenario ids.
- [ ] T023 Implement P5 multi-spirit flow support with `--target-os-id`, `--seed-id` and blocked/anomaly output when authorization is missing.
- [ ] T024 Ensure `--phase all` runs phases in order and records blocked stages without switching to mock data.

## Phase 6: Documentation (US4, P2)

**Goal**: Make the scripts reproducible for experiment operators.

- [ ] T025 Add `docs/formal-experiment-scripts.md` with required usage order, parameters, examples, output schema and common diagnostics.
- [ ] T026 [P] Add a docs/quickstart parity test or script-help assertion ensuring documented parameters match implemented CLI options.
- [ ] T027 Update relevant README or docs index only if the repository has an established index entry for scripts.

## Phase 7: Validation

- [ ] T028 Run `python -m pytest tests/scripts/test_formal_experiment_prepare.py`.
- [ ] T029 Run `python -m pytest tests/scripts/test_formal_experiment_run.py`.
- [ ] T030 Run `python -m pytest tests/scripts/test_formal_experiment_export.py`.
- [ ] T031 Run dry-run smoke: `bash scripts/formal_experiment_run.sh --profile default --phase P1 --repeat 3 --run-id smoke --dry-run`.
- [ ] T032 Confirm no business-code behavior changed outside script/doc/test surfaces unless a documented thin read-only API was required.

## Dependencies

- T001-T004 block all implementation phases.
- Prepare (T005-T008) should land before real publish.
- Run MVP (T009-T013) can proceed after Foundation and Prepare.
- Export (T014-T019) can proceed after Foundation; it does not require real publish when using fixtures.
- P0-P5 coverage depends on Run MVP.
- Documentation depends on final option names from Prepare/Run/Export.

## Parallel Opportunities

- Fixture builders, scenario catalog and redaction tests can be split across different files.
- Export fixture tests and run scenario tests can proceed in parallel after Foundation.
- P0/P2/P3 and P4/P5 scenario additions can be divided between Builders once catalog mapping is agreed.
