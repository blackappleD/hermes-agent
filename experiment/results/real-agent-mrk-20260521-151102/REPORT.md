# Bubble MRK Flow Test Report

- Run ID: `real-agent-mrk-20260521-151102`
- Mode: `real`
- Publisher profile: `default`
- Receiver profile: `bubble-mrk-receiver-bubble-mrk-20260519-091525`
- Publisher OS: `3e0a3d1e-5f54-4067-b0de-3bf1091d7a07`
- Receiver OS: `78867306-5f5d-4cd5-b7de-d085c562b2d9`
- Started: `2026-05-21T07:11:08Z`
- Finished: `2026-05-21T07:21:35Z`
- Result: `PASS`

## Summary

| Metric | Value |
| --- | --- |
| Steps passed | 13 |
| Steps failed | 0 |
| Steps blocked | 0 |
| Steps skipped | 0 |
| Demand bubble | REQ-real-agent-mrk-20260521-151102 |
| Task bubble | task_REQ-real-agent-mrk-20260521-151102_78867306-5f5d-4cd5-b7de-d085c562b2d9 |
| Mount |  |
| Publisher profile | default |
| Receiver profile | bubble-mrk-receiver-bubble-mrk-20260519-091525 |

## Step Results

| # | Step | Actor | Status | Duration | Key Result | Error |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | profile discovery | - | PASS | 921 ms | default -> bubble-mrk-receiver-bubble-mrk-20260519-091525 |  |
| 1 | real preflight | - | PASS | 0 ms | real preflight ready |  |
| 2 | publisher gateway ready | default | PASS | 10797 ms | gateway started |  |
| 3 | receiver gateway ready | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 10128 ms | gateway started |  |
| 4 | external requirement input to publisher | default | PASS | 68517 ms | publisher agent accepted external input |  |
| 5 | receiver gateway consumes requirement | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 14 ms | receiver gateway consumed requirement |  |
| 6 | receiver agent accepts and delivers | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 91582 ms | receiver agent accepted external input |  |
| 7 | publisher gateway consumes handover | default | PASS | 26 ms | publisher gateway consumed handover |  |
| 8 | publisher agent reviews task handover | default | PASS | 68573 ms | publisher agent accepted external input |  |
| 9 | demand ready for final delivery | - | PASS | 228551 ms | demand ready for final delivery |  |
| 10 | receiver agent submits demand delivery | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 81789 ms | receiver agent accepted external input |  |
| 11 | publisher agent reviews demand | default | PASS | 64780 ms | publisher agent accepted external input |  |
| 12 | wait for real agent completion | - | PASS | 527 ms | real autonomous flow completed |  |

## Receipts

- Receipt rows: `0`

## Real Runtime Evidence

- Agent run rows: `5`
- Gateway record rows: `8`
- Session evidence rows: `93`
- Observation rows: `24`

## Snapshots

- Snapshot rows: `2`

## Anomalies

- None

## Reproduction Command

```bash
python scripts/linz-world/linz_bubble_mrk_flow_test.py real --publisher-profile default --receiver-profile bubble-mrk-receiver-bubble-mrk-20260519-091525 --run-id real-agent-mrk-20260521-151102 --output-root /mnt/d/workspace/hermes-agent/experiment/results --hermes-home /root/.hermes --confirm-mutations --start-missing-gateways --timeout-seconds 1500 --gateway-event-timeout 420 --agent-timeout-seconds 900 --poll-interval 10
```
