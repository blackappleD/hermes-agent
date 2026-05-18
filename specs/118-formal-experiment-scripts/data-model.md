# Data Model: 正式框架实验脚本

## FormalExperimentRun

- `run_id`: user-supplied stable id, output directory key.
- `profile`: Hermes profile name.
- `hermes_home`: resolved profile-scoped data root.
- `phases`: selected phases, one or more of P0-P5.
- `seed_id` / `persona`: experiment identity labels.
- `target_os_id`: direct inbox target, required for `wsp.<os_id>` scenarios.
- `started_at` / `completed_at`: ISO timestamps.
- `script_version`: git commit or local version marker if available.
- `checks`: prepare result summary.

## FormalScenario

- `phase`: P0-P5.
- `scenario_id`: stable id such as `P1-E2-001`.
- `description`: short human-readable purpose.
- `subject`: formal Linz World subject.
- `event_type`: formal Linz World event type.
- `payload_template`: bounded payload without secrets.
- `required_capability`: publish or direct inbox capability.
- `expected_observation`: life/tension/action fields the experiment expects to inspect.
- `repeat_index`: integer for repeated scenarios.

## PublishedFormalEvent

- `run_id`, `phase`, `scenario_id`, `seed_id`, `persona`.
- `request_id`: publisher request id.
- `event_id`: local scenario event id if present.
- `world_event_id`: Linz World receipt event id when published.
- `subject`, `event_type`.
- `payload_summary`: redacted bounded summary.
- `audit_ref`: formal state or receipt reference if available.
- `status`: published, rejected, failed, uncertain, dry_run, blocked.
- `diagnostic`: structured reason for non-published state.

## RuntimeTransitionExport

- `run_id`, `phase`, `scenario_id`.
- `event_id`, `world_event_id`, `message_event_id`, `trace_id`, `session_id`.
- `message_event_projection`: gateway projection summary.
- `raw_transitions`: references or redacted raw runtime records.
- `life_state`, `tension_field` / `tension_set`, `action_potential`.
- `self_prompt`, `open_intent`, `arbitration`, `actual_action`.
- `evidence_refs`, `stop_reason`, `judgement`.
- `anomaly`: null when transition is complete, otherwise structured code.

## ExperimentAnomaly

- `run_id`, `phase`, `scenario_id`.
- `code`: e.g. `gateway_offline`, `catalog_rejected`, `publish_failed`, `missing_projection`, `missing_transition`, `sensitive_value_redacted`.
- `severity`: info, warning, error, blocked.
- `message`: actionable diagnosis.
- `source_ref`: checked path, event id, receipt id or log line ref.
- `next_action`: suggested fix.

## Output Files

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

All ordinary output files must be redacted. Full raw payloads may only be represented by `audit_ref`, `raw_payload_ref`, `content_ref`, hash or equivalent references.
