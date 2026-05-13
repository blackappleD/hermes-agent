# 数据模型: 模块 4 行动势能与认知经济

## ActionPotential

来源: 现有 `agent/os_runtime/domain.py::ActionPotential`，允许最小扩展。

字段要求:

- `intent_id`: 候选行动或评估对象 id，可为空。
- `value_potential`: 0.0-1.0，目标/价值/需求收益。
- `mutual_benefit_potential`: 0.0-1.0，用户、Linz World 关系或协作互利收益。
- `learning_potential`: 0.0-1.0，不确定性降低、经验学习或规则结晶收益。
- `risk_cost`: 0.0-1.0，工具、授权、审批、结算、疲劳和 restraint 成本。
- `overall_score`: 0.0-1.0，收益减风险后的总分。
- `recommended_depth`: `none | report | draft | continue_turn | sandbox | tool | world_publish | bubble`。
- `rationale`: 可读解释。
- `metadata`: 保存 `score_evidence`、`thresholds`、`risk_reasons`、`downgrade_reasons`。

## CognitiveEconomyRecommendation

可新增为 dataclass，也可先作为 JSON-friendly dict 返回；若进入 domain，应支持 `to_dict()`/`from_dict()`。

字段要求:

- `selected_path`: `rule_path | auxiliary_small | main_model | world_compute | high_reasoning`。
- `reason`: 可读原因。
- `budget_hint`: 可选预算提示，例如 `none`、`low`、`normal`、`high`。
- `action_potential`: 评分快照或 `overall_score` 摘要。
- `downgrade_reasons`: 降级原因列表。
- `receipt_id`: world compute receipt id，可为空。
- `receipt_status`: `published | rejected | failed | skipped` 等摘要值。
- `evidence`: signal/tension/life_state/config 来源列表。
- `metadata`: 保留 thresholds、world_compute_eligibility、stub result。

## WorldComputeEligibility

可作为内部 dataclass 或 recommendation metadata。

字段要求:

- `configured`: 是否配置允许。
- `logged_in`: 是否处于登录状态。
- `token_ref_available`: 是否有 token ref 且 secret 可解析。
- `soul_memory_summary_available`: 是否存在 Soul Memory summary。
- `authorization_state`: authorization/map 摘要。
- `eligible`: 最终是否允许建议 world compute。
- `reasons`: 未满足条件或允许原因。

## Evidence Shape

评分 evidence 使用字符串或 dict 均可，但必须稳定可测。建议格式:

- `signal:<group>:<code>`
- `tension:<tension_id>:<tension_type>`
- `life_state:<field>`
- `config:<threshold_name>`
- `world_compute:<receipt_status>`
