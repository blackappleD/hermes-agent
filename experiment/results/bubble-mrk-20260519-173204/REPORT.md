# Bubble MRK Flow Test Report

- Run ID: `bubble-mrk-20260519-173204`
- Publisher profile: `default`
- Receiver profile: `bubble-mrk-receiver-bubble-mrk-20260519-091525`
- Publisher OS: `3e0a3d1e-5f54-4067-b0de-3bf1091d7a07`
- Receiver OS: `78867306-5f5d-4cd5-b7de-d085c562b2d9`
- Started: `2026-05-19T09:32:04Z`
- Finished: `2026-05-19T09:32:14Z`
- Result: `FAIL`

## Summary

| Metric | Value |
| --- | --- |
| Steps passed | 11 |
| Steps failed | 4 |
| Steps blocked | 1 |
| Steps skipped | 1 |
| Demand bubble | bub_demand_72d9284d-b6c5-4b70-84c4-e51217a1987d |
| Task bubble | bub_task_6b2bc884-638f-4a3f-bf2f-d8df22df3d0d |
| Mount |  |
| Publisher profile | default |
| Receiver profile | bubble-mrk-receiver-bubble-mrk-20260519-091525 |

## Step Results

| # | Step | Actor | Status | Duration | Key Result | Error |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | profile discovery | - | PASS | 1035 ms | default -> bubble-mrk-receiver-bubble-mrk-20260519-091525 |  |
| 1 | preflight | - | PASS | 0 ms | preflight ready |  |
| 2 | publish requirement | default | PASS | 397 ms | published mrk.requirement.published |  |
| 3 | create or locate DemandBubble | default | PASS | 595 ms | linz_bubble_create_demand bubble=bub_demand_72d9284d-b6c5-4b70-84c4-e51217a1987d produced |  |
| 4 | snapshot DemandBubble | default | PASS | 801 ms | snapshot bub_demand_72d9284d-b6c5-4b70-84c4-e51217a1987d produced |  |
| 5 | publish order accepted | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 375 ms | published mrk.order.accepted |  |
| 6 | accept DemandBubble | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 646 ms | linz_bubble_accept_demand bubble=bub_demand_72d9284d-b6c5-4b70-84c4-e51217a1987d active |  |
| 7 | locate or create TaskBubble | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 1420 ms | linz_bubble_create_task bubble=bub_task_6b2bc884-638f-4a3f-bf2f-d8df22df3d0d produced |  |
| 8 | mount receiver AgentBubble | bubble-mrk-receiver-bubble-mrk-20260519-091525 | FAIL | 537 ms | linz_bubble_request_mount failed | 挂载 Bubble 类型不匹配: 期望 ，实际 agent |
| 9 | review mount | default | SKIPPED | 0 ms | mount review skipped | No mount_id is available. |
| 10 | submit task artifact | bubble-mrk-receiver-bubble-mrk-20260519-091525 | BLOCKED | 0 ms | artifact blocked | task_bubble_id or mount_id is missing. |
| 11 | publish handover delivered | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 365 ms | published mrk.order.handover.delivered |  |
| 12 | review TaskBubble acceptance | default | FAIL | 459 ms | linz_bubble_review_task_acceptance failed | TaskBubble 必须处于 reviewing 才能验收 |
| 13 | submit DemandBubble delivery | bubble-mrk-receiver-bubble-mrk-20260519-091525 | FAIL | 592 ms | linz_bubble_submit_demand_delivery failed | DemandBubbleCabin 必须等待所有必需 TaskBubble archived 后才能提交整体交付说明 |
| 14 | review DemandBubble acceptance | default | FAIL | 474 ms | linz_bubble_review_demand_acceptance failed | DemandBubbleCabin 必须处于 reviewing 才能进行需求级确认 |
| 15 | publish settlement requested | default | PASS | 364 ms | published mrk.settlement.requested |  |
| 16 | final DemandBubble snapshot | default | PASS | 1128 ms | snapshot bub_demand_72d9284d-b6c5-4b70-84c4-e51217a1987d active |  |

## Receipts

- Receipt rows: `11`

## Snapshots

- Snapshot rows: `3`

## Anomalies

- `FAIL` step `mount receiver AgentBubble`: 挂载 Bubble 类型不匹配: 期望 ，实际 agent
- `BLOCKED` step `submit task artifact`: task_bubble_id or mount_id is missing.
- `FAIL` step `review TaskBubble acceptance`: TaskBubble 必须处于 reviewing 才能验收
- `FAIL` step `submit DemandBubble delivery`: DemandBubbleCabin 必须等待所有必需 TaskBubble archived 后才能提交整体交付说明
- `FAIL` step `review DemandBubble acceptance`: DemandBubbleCabin 必须处于 reviewing 才能进行需求级确认

## Reproduction Command

```bash
python scripts/linz_bubble_mrk_flow_test.py run --publisher-profile default --run-id bubble-mrk-20260519-173204 --output-root /mnt/d/workspace/hermes-agent/experiment/results --hermes-home /root/.hermes --confirm-mutations
```
