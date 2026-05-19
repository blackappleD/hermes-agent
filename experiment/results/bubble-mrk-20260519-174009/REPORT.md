# Bubble MRK Flow Test Report

- Run ID: `bubble-mrk-20260519-174009`
- Publisher profile: `default`
- Receiver profile: `bubble-mrk-receiver-bubble-mrk-20260519-091525`
- Publisher OS: `3e0a3d1e-5f54-4067-b0de-3bf1091d7a07`
- Receiver OS: `78867306-5f5d-4cd5-b7de-d085c562b2d9`
- Started: `2026-05-19T09:40:09Z`
- Finished: `2026-05-19T09:40:22Z`
- Result: `FAIL`

## Summary

| Metric | Value |
| --- | --- |
| Steps passed | 14 |
| Steps failed | 3 |
| Steps blocked | 0 |
| Steps skipped | 0 |
| Demand bubble | bub_demand_48ccb957-3eee-4cfe-93f9-acf3d54828f9 |
| Task bubble | bub_task_e68ce486-7144-4cc6-93d1-5773f41a9ea1 |
| Mount | mnt_133a5a5e-35f3-42ef-8f9b-aec712c4e241 |
| Publisher profile | default |
| Receiver profile | bubble-mrk-receiver-bubble-mrk-20260519-091525 |

## Step Results

| # | Step | Actor | Status | Duration | Key Result | Error |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | profile discovery | - | PASS | 1181 ms | default -> bubble-mrk-receiver-bubble-mrk-20260519-091525 |  |
| 1 | preflight | - | PASS | 0 ms | preflight ready |  |
| 2 | publish requirement | default | PASS | 426 ms | published mrk.requirement.published |  |
| 3 | create or locate DemandBubble | default | PASS | 590 ms | linz_bubble_create_demand bubble=bub_demand_48ccb957-3eee-4cfe-93f9-acf3d54828f9 produced |  |
| 4 | snapshot DemandBubble | default | PASS | 802 ms | snapshot bub_demand_48ccb957-3eee-4cfe-93f9-acf3d54828f9 produced |  |
| 5 | publish order accepted | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 399 ms | published mrk.order.accepted |  |
| 6 | accept DemandBubble | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 784 ms | linz_bubble_accept_demand bubble=bub_demand_48ccb957-3eee-4cfe-93f9-acf3d54828f9 active |  |
| 7 | locate or create TaskBubble | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 1474 ms | linz_bubble_create_task bubble=bub_task_e68ce486-7144-4cc6-93d1-5773f41a9ea1 produced |  |
| 8 | mount receiver AgentBubble | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 829 ms | linz_bubble_request_mount mount=mnt_133a5a5e-35f3-42ef-8f9b-aec712c4e241 |  |
| 9 | review mount | default | PASS | 909 ms | linz_bubble_review_mount mount=mnt_133a5a5e-35f3-42ef-8f9b-aec712c4e241 |  |
| 10 | submit task artifact | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 774 ms | linz_bubble_submit_artifact bubble=bub_task_e68ce486-7144-4cc6-93d1-5773f41a9ea1 reviewing |  |
| 11 | publish handover delivered | bubble-mrk-receiver-bubble-mrk-20260519-091525 | PASS | 374 ms | published mrk.order.handover.delivered |  |
| 12 | review TaskBubble acceptance | default | FAIL | 1366 ms | linz_bubble_review_task_acceptance failed | 写入 memory 模块泡泡记忆记录失败: pq: invalid input syntax for type json |
| 13 | submit DemandBubble delivery | bubble-mrk-receiver-bubble-mrk-20260519-091525 | FAIL | 500 ms | linz_bubble_submit_demand_delivery failed | DemandBubbleCabin 必须等待所有必需 TaskBubble archived 后才能提交整体交付说明 |
| 14 | review DemandBubble acceptance | default | FAIL | 503 ms | linz_bubble_review_demand_acceptance failed | DemandBubbleCabin 必须处于 reviewing 才能进行需求级确认 |
| 15 | publish settlement requested | default | PASS | 375 ms | published mrk.settlement.requested |  |
| 16 | final DemandBubble snapshot | default | PASS | 1129 ms | snapshot bub_demand_48ccb957-3eee-4cfe-93f9-acf3d54828f9 active |  |

## Receipts

- Receipt rows: `13`

## Snapshots

- Snapshot rows: `3`

## Anomalies

- `FAIL` step `review TaskBubble acceptance`: 写入 memory 模块泡泡记忆记录失败: pq: invalid input syntax for type json
- `FAIL` step `submit DemandBubble delivery`: DemandBubbleCabin 必须等待所有必需 TaskBubble archived 后才能提交整体交付说明
- `FAIL` step `review DemandBubble acceptance`: DemandBubbleCabin 必须处于 reviewing 才能进行需求级确认

## Reproduction Command

```bash
python scripts/linz_bubble_mrk_flow_test.py run --publisher-profile default --run-id bubble-mrk-20260519-174009 --output-root /mnt/d/workspace/hermes-agent/experiment/results --hermes-home /root/.hermes --confirm-mutations
```
