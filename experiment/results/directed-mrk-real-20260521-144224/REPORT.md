# Bubble MRK Flow Test Report

- Run ID: `directed-mrk-real-20260521-144224`
- Mode: `directed`
- Publisher profile: `bubble-mrk-receiver-directed-mrk-20260521-144117`
- Receiver profile: `bubble-mrk-receiver-directed-mrk-real-20260521-144224`
- Publisher OS: `82ed1cc2-fc77-4b09-9969-92f8990ea982`
- Receiver OS: `3fc1570b-2185-4504-a49c-0509813ba5c4`
- Started: `2026-05-21T06:42:25Z`
- Finished: `2026-05-21T06:58:13Z`
- Result: `FAIL`

## Summary

| Metric | Value |
| --- | --- |
| Steps passed | 6 |
| Steps failed | 1 |
| Steps blocked | 0 |
| Steps skipped | 0 |
| Demand bubble | REQ-directed-mrk-real-20260521-144224 |
| Task bubble |  |
| Mount |  |
| Publisher profile | bubble-mrk-receiver-directed-mrk-20260521-144117 |
| Receiver profile | bubble-mrk-receiver-directed-mrk-real-20260521-144224 |

## Step Results

| # | Step | Actor | Status | Duration | Key Result | Error |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | profile discovery | - | PASS | 6345 ms | bubble-mrk-receiver-directed-mrk-20260521-144117 -> bubble-mrk-receiver-directed-mrk-real-20260521-144224 |  |
| 1 | directed preflight | - | PASS | 0 ms | directed preflight ready |  |
| 2 | publisher gateway ready | bubble-mrk-receiver-directed-mrk-20260521-144117 | PASS | 11341 ms | gateway started |  |
| 3 | receiver gateway ready | bubble-mrk-receiver-directed-mrk-real-20260521-144224 | PASS | 10921 ms | gateway started |  |
| 4 | publish directed MRK requirement | bubble-mrk-receiver-directed-mrk-20260521-144117 | PASS | 1023 ms | published mrk.requirement.published |  |
| 5 | receiver gateway consumes directed requirement | bubble-mrk-receiver-directed-mrk-real-20260521-144224 | PASS | 10019 ms | receiver consumed directed requirement |  |
| 6 | verify directed MRK order path | - | FAIL | 906619 ms | directed formal MRK flow incomplete | Missing evidence: receiver published mrk.order.accepted, default TaskBubble task_REQ-directed-mrk-real-20260521-144224_3fc1570b-2185-4504-a49c-0509813ba5c4, ... |

## Receipts

- Receipt rows: `2`

## Real Runtime Evidence

- Agent run rows: `0`
- Gateway record rows: `2`
- Session evidence rows: `1`
- Observation rows: `76`

## Snapshots

- Snapshot rows: `1`

## Anomalies

- `FAIL` step `verify directed MRK order path`: Missing evidence: receiver published mrk.order.accepted, default TaskBubble task_REQ-directed-mrk-real-20260521-144224_3fc1570b-2185-4504-a49c-0509813ba5c4, ...

## Reproduction Command

```bash
python.exe scripts\linz-world\linz_bubble_mrk_flow_test.py directed --publisher-profile bubble-mrk-receiver-directed-mrk-20260521-144117 --receiver-profile bubble-mrk-receiver-directed-mrk-real-20260521-144224 --run-id directed-mrk-real-20260521-144224 --confirm-mutations --output-root experiment/results
```
