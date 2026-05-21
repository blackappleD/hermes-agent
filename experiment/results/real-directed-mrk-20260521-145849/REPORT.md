# Bubble MRK Flow Test Report

- Run ID: `real-directed-mrk-20260521-145849`
- Mode: `real`
- Publisher profile: `default`
- Receiver profile: `bubble-mrk-receiver-bubble-mrk-20260519-091525`
- Publisher OS: `3e0a3d1e-5f54-4067-b0de-3bf1091d7a07`
- Receiver OS: `78867306-5f5d-4cd5-b7de-d085c562b2d9`
- Started: `2026-05-21T06:58:51Z`
- Finished: `2026-05-21T07:00:50Z`
- Result: `FAIL`

## Summary

| Metric | Value |
| --- | --- |
| Steps passed | 6 |
| Steps failed | 1 |
| Steps blocked | 0 |
| Steps skipped | 0 |
| Demand bubble | REQ-real-directed-mrk-20260521-145849 |
| Task bubble |  |
| Mount |  |
| Publisher profile | default |
| Receiver profile | bubble-mrk-receiver-bubble-mrk-20260519-091525 |

## Step Results

| # | Step | Actor | Status | Duration | Key Result | Error |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | profile discovery | - | PASS | 1069 ms | default -> bubble-mrk-receiver-bubble-mrk-20260519-091525 |  |
| 1 | real preflight | - | PASS | 0 ms | real preflight ready |  |
| 2 | publisher gateway ready | default | PASS | 10802 ms | gateway started |  |
| 3 | receiver gateway ready | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 10115 ms | gateway started |  |
| 4 | external requirement input to publisher | default | PASS | 66136 ms | publisher agent accepted external input |  |
| 5 | receiver gateway consumes requirement | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 11 ms | receiver gateway consumed requirement |  |
| 6 | wait for real autonomous completion | - | FAIL | 30812 ms |  | TypeError: 'NoneType' object is not iterable |

## Receipts

- Receipt rows: `0`

## Real Runtime Evidence

- Agent run rows: `1`
- Gateway record rows: `1`
- Session evidence rows: `0`
- Observation rows: `3`

## Snapshots

- Snapshot rows: `0`

## Anomalies

- `FAIL` step `wait for real autonomous completion`: TypeError: 'NoneType' object is not iterable

## Reproduction Command

```bash
python scripts/linz-world/linz_bubble_mrk_flow_test.py real --publisher-profile default --receiver-profile bubble-mrk-receiver-bubble-mrk-20260519-091525 --run-id real-directed-mrk-20260521-145849 --output-root /mnt/d/workspace/hermes-agent/experiment/results --hermes-home /root/.hermes --confirm-mutations --start-missing-gateways --timeout-seconds 1500 --gateway-event-timeout 420 --agent-timeout-seconds 900 --poll-interval 10
```
