# Formal Experiment Scripts

These scripts run formal Linz World experiments against an already installed
Hermes profile. They do not create mock transitions and they do not export
offline fake data. Published events must pass `agent.linz_world.event_catalog`,
and exported rows come from the local gateway, Linz World, os_runtime and log
artifacts under the selected Hermes profile.

## Required Order

```bash
# 1. Install and enter the native WSL checkout
bash scripts/install-wsl-test.sh -- --skip-setup
cd /src/hermes-agent
source venv/bin/activate

# 2. Configure the formal Linz World identity and authorization map
hermes setup linz
hermes linz login
hermes linz map
hermes linz status

# 3. Start the formal gateway/os_runtime path
hermes gateway

# 4. In another shell, check the formal runtime before publishing
bash scripts/formal_experiment_prepare.sh --profile default --phase all

# 5. Publish one phase or all phases
bash scripts/formal_experiment_run.sh --profile default --phase P1 --repeat 3 --run-id formal-p1-001
bash scripts/formal_experiment_run.sh --profile default --phase all --run-id formal-all-001

# 6. Export persisted formal artifacts
python scripts/formal_experiment_export.py --profile default --run-id formal-all-001 --output-root experiment/results
```

For a no-side-effect smoke check, use:

```bash
bash scripts/formal_experiment_run.sh --profile default --phase P1 --repeat 3 --run-id smoke --dry-run
```

## Scripts

- `scripts/formal_experiment_prepare.sh`: fail-closed preflight for Linz login,
  authorization, gateway state, Linz gateway platform state, `message_events.db`,
  `state.db`, `linz_world/state.json`, os_runtime logs and os_runtime config.
- `scripts/formal_experiment_run.sh`: expands P0-P5 scenarios, validates each
  `subject` / `event_type` through the formal event catalog, and publishes via
  `agent.linz_world.publisher.publish_event()`.
- `scripts/formal_experiment_export.py`: reads persisted formal artifacts and
  writes analysis files under `<output-root>/<run-id>/`.

## Parameters

- `--profile`: Hermes profile name. Defaults to `default`.
- `--hermes-home`: explicit Hermes data directory. When set, it overrides
  profile resolution and scopes every read/write to that directory.
- `--phase`: experiment phase, one of `P0|P1|P2|P3|P4|P5|all`.
- `--run-id`: experiment run identifier. It is written into published payloads
  and used to filter export artifacts.
- `--repeat`: repeat count for repeatable scenarios. P1 defaults to three
  perturbation events.
- `--interval-seconds`: pause between published repeat events.
- `--target-os-id`: target spirit/OS id for direct inbox events using
  `subject=wsp.<target_os_id>`.
- `--seed-id`: experiment seed/spirit identifier recorded in event payloads.
- `--persona`: persona label recorded in event payloads.
- `--dry-run`: validate and print planned formal events without publishing.
- `--output-root`: export root directory. Defaults to `experiment/results`.
- `--since` / `--until`: optional ISO-8601 time window for export filtering.
- `--fail-on-anomaly`: make export return non-zero when anomalies are found.

`prepare` also supports `--no-live-check` for fixture or offline diagnostics
against cached Linz status. Do not use it for a final formal run.

## Formal Event Mapping

Legacy examples in `docs/共博自制框架实验准备.md` are mapped to the current formal
catalog:

| Phase | Formal subject | Formal event type | Notes |
| --- | --- | --- | --- |
| P0 | `wsp.governance.notice` | `governance.notice` | Smoke check for governance path |
| P1 | `wsp.mrk.requirement.published` | `requirement.published` | Repeatable single perturbation |
| P2 | `wsp.task.created` | `task.created` | Task context signal |
| P2 | `wsp.mrk.order.created` | `order.created` | Collaboration signal |
| P3 | `wsp.task.updated` | `task.updated` | Life-state feedback signal |
| P3 | `wsp.mrk.delivery.submitted` | `delivery.submitted` | Delivery/evidence signal |
| P4 | `wsp.mrk.order.updated` | `order.updated` | Repeatable multi-round evolution |
| P5 | `wsp.<target_os_id>` | `wsp.chat.message.sent` | Direct inbox multi-spirit interaction |

Events using `linz.*`, `skill.*`, `legacy.*` or unmapped `mrk.*` shapes are
rejected. If `--phase all` cannot run P5 because `--target-os-id` is missing,
the script reports that phase as blocked instead of publishing a mock event.

## Export Output

Each export writes:

```text
experiment/results/<run_id>/
├── manifest.json
├── events.jsonl
├── transitions.jsonl
├── os_runtime_raw.jsonl
├── summary.json
├── summary.csv
└── anomalies.json
```

`events.jsonl` contains gateway projection rows, MessageEvent projections,
payload summaries, audit refs and Linz receipts. `transitions.jsonl` contains
only os_runtime records found in `state.db` or logs. If life state, tension
field/set, action potential, self prompt, open intent, arbitration, action or
evidence fields are missing, the exporter records an anomaly instead of filling
defaults.

Sensitive keys and text patterns such as token, api_key, password,
private_key, authorization, bearer credentials and secrets are redacted from
ordinary output files.

## Common Diagnostics

- `linz_login` failed: run `hermes linz login`, then `hermes linz status`.
- `linz_authorization` failed: run `hermes linz map` and confirm
  `authorization_state=current`.
- `gateway_runtime` failed: start `hermes gateway` in a separate shell.
- `linz_gateway_platform` failed: enable the Linz World gateway platform and
  restart the gateway.
- `gateway_message_events_db` or `state_db` missing: verify `--profile` /
  `--hermes-home` and confirm the gateway/os_runtime wrote runtime artifacts.
- `target_os_id_missing`: pass `--target-os-id` for P5 direct inbox scenarios.
- `missing_transition`: gateway saw a matching event, but os_runtime produced
  no corresponding persisted transition for the selected `run_id`/time window.
