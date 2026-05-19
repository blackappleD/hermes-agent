# Bubble MRK Flow Test Report

- Run ID: `bubble-mrk-20260519-172921`
- Publisher profile: `default`
- Receiver profile: `bubble-mrk-receiver-bubble-mrk-20260519-091525`
- Publisher OS: `3e0a3d1e-5f54-4067-b0de-3bf1091d7a07`
- Receiver OS: `78867306-5f5d-4cd5-b7de-d085c562b2d9`
- Started: `2026-05-19T09:29:21Z`
- Finished: `2026-05-19T09:29:31Z`
- Result: `FAIL`

## Summary

| Metric | Value |
| --- | --- |
| Steps passed | 10 |
| Steps failed | 4 |
| Steps blocked | 2 |
| Steps skipped | 1 |
| Demand bubble | bub_demand_abe9c9f0-82da-495e-abec-61fbf35eec6d |
| Task bubble | bub_task_23fd28ef-ae48-47fa-a22f-78e930f8b9e2 |
| Mount |  |
| Publisher profile | default |
| Receiver profile | bubble-mrk-receiver-bubble-mrk-20260519-091525 |

## Step Results

| # | Step | Actor | Status | Duration | Key Result | Error |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | profile discovery | - | PASS | 1043 ms | default -> bubble-mrk-receiver-bubble-mrk-20260519-091525 |  |
| 1 | preflight | - | PASS | 0 ms | preflight ready |  |
| 2 | publish requirement | default | PASS | 451 ms | published mrk.requirement.published |  |
| 3 | create or locate DemandBubble | default | PASS | 632 ms | linz_bubble_create_demand bubble=bub_demand_abe9c9f0-82da-495e-abec-61fbf35eec6d produced |  |
| 4 | snapshot DemandBubble | default | PASS | 832 ms | snapshot bub_demand_abe9c9f0-82da-495e-abec-61fbf35eec6d produced |  |
| 5 | publish order accepted | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 367 ms | published mrk.order.accepted |  |
| 6 | accept DemandBubble | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 658 ms | linz_bubble_accept_demand bubble=bub_demand_abe9c9f0-82da-495e-abec-61fbf35eec6d active |  |
| 7 | locate or create TaskBubble | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 1444 ms | linz_bubble_create_task bubble=bub_task_23fd28ef-ae48-47fa-a22f-78e930f8b9e2 produced |  |
| 8 | mount receiver AgentBubble | bubble-mrk-receiver-bubble-mrk-20260519-091525 | FAIL | 534 ms | linz_bubble_request_mount failed | 挂载 Bubble 类型不匹配: 期望 ，实际 agent |
| 9 | review mount | default | SKIPPED | 0 ms | mount review skipped | No mount_id is available. |
| 10 | submit task artifact | bubble-mrk-receiver-bubble-mrk-20260519-091525 | BLOCKED | 0 ms | artifact blocked | task_bubble_id or mount_id is missing. |
| 11 | publish handover delivered | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 363 ms | published mrk.order.handover.delivered |  |
| 12 | review TaskBubble acceptance | default | FAIL | 460 ms | linz_bubble_review_task_acceptance failed | TaskBubble 必须处于 reviewing 才能验收 |
| 13 | submit DemandBubble delivery | bubble-mrk-receiver-bubble-mrk-20260519-091525 | FAIL | 481 ms | linz_bubble_submit_demand_delivery failed | DemandBubbleCabin 必须等待所有必需 TaskBubble archived 后才能提交整体交付说明 |
| 14 | review DemandBubble acceptance | default | FAIL | 459 ms | linz_bubble_review_demand_acceptance failed | DemandBubbleCabin 必须处于 reviewing 才能进行需求级确认 |
| 15 | publish settlement completed | default | BLOCKED | 199 ms | rejected mrk.settlement.completed | Linz World subject/event_type is not authorized for publish. |
| 16 | final DemandBubble snapshot | default | PASS | 1123 ms | snapshot bub_demand_abe9c9f0-82da-495e-abec-61fbf35eec6d active |  |

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
- `BLOCKED` step `publish settlement completed`: Linz World subject/event_type is not authorized for publish.

## Reproduction Command

```bash
python scripts/linz_bubble_mrk_flow_test.py run --publisher-profile default --run-id bubble-mrk-20260519-172921 --output-root /mnt/d/workspace/hermes-agent/experiment/results --hermes-home /root/.hermes --confirm-mutations
```
