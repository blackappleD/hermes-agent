# Quickstart: 正式框架实验脚本

## Expected User Flow

```bash
# 1. Install and enter WSL native checkout
bash scripts/install-wsl-test.sh -- --skip-setup
cd /src/hermes-agent
source venv/bin/activate

# 2. Configure and verify formal Linz state
hermes setup linz
hermes linz login
hermes linz map
hermes linz status

# 3. Start formal gateway/os_runtime
hermes gateway

# 4. In another shell, run preflight
bash scripts/linz-world/formal_experiment_prepare.sh --profile default --phase all

# 5. Run one phase or all phases
bash scripts/linz-world/formal_experiment_run.sh --profile default --phase P1 --repeat 3 --run-id formal-p1-001
bash scripts/linz-world/formal_experiment_run.sh --profile default --phase all --run-id formal-all-001

# 6. Export persisted formal data
python scripts/linz-world/formal_experiment_export.py --profile default --run-id formal-all-001 --output-root experiment/results
```

## Required Parameters

- `--profile`: Hermes profile name; default `default`.
- `--phase`: `P0|P1|P2|P3|P4|P5|all`.
- `--run-id`: experiment run id used for payload metadata and export directory.
- `--repeat`: repeated events within a phase; P1 must support default 3 for single-event perturbation.
- `--output-root`: export directory root.
- `--hermes-home`: explicit Hermes data directory override.
- `--target-os-id`: direct inbox target for `wsp.<os_id>` events.
- `--seed-id` / `--persona`: experiment identity labels.
- `--since` / `--until`: export time window.
- `--dry-run`: validate and print formal events without publishing.
- `--fail-on-anomaly`: make export return non-zero when anomalies are present.

## Validation Commands

```bash
python -m pytest tests/scripts/test_formal_experiment_prepare.py
python -m pytest tests/scripts/test_formal_experiment_run.py
python -m pytest tests/scripts/test_formal_experiment_export.py
```

## Manual Smoke Checks

1. Run prepare with gateway stopped; it must fail with a gateway diagnostic.
2. Run prepare after `hermes linz logout`; it must fail with a login diagnostic.
3. Run `scripts/linz-world/formal_experiment_run.sh --dry-run --phase P1`; output events must all pass the formal catalog.
4. Export a run with no os_runtime transitions; `anomalies.json` must include `missing_transition`.
