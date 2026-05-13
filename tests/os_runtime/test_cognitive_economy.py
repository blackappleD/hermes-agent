from agent.linz_world.models import ComputeReceipt, ReceiptStatus
from agent.os_runtime.domain import (
    ActionPotential,
    AgentContextView,
    CognitiveEconomyPath,
    CognitiveEconomyRecommendation,
    LifeState,
    RecommendedDepth,
    SignalSet,
    Tension,
    TensionSet,
    TensionType,
    WorldIdentityRef,
)
from agent.os_runtime.engine.cognitive_economy import CognitiveEconomyController


def _potential(
    *,
    score=0.5,
    learning=0.2,
    risk=0.1,
    depth=RecommendedDepth.DRAFT,
):
    return ActionPotential(
        value_potential=score,
        mutual_benefit_potential=0.2,
        learning_potential=learning,
        risk_cost=risk,
        overall_score=score,
        recommended_depth=depth,
        metadata={
            "score_evidence": {
                "overall_score": ["config:threshold:main_model_score_at"],
                "risk_cost": ["signal:risks:low"],
            }
        },
    )


def _world_context(*, logged_in=True, token_ref=True, secret=True, memory=True, authorization="current"):
    identity = WorldIdentityRef(
        os_id="os-1",
        soul_id="soul-1",
        authorization_state=authorization,
        memory_summary_available=memory,
        metadata={
            "login_state": "logged_in" if logged_in else "logged_out",
            "token_ref": "secret://linz/token" if token_ref else "",
            "token_secret_available": secret,
        },
    )
    return AgentContextView(
        agent_id="agent-1",
        world_identity=identity,
        memory_summary="soul summary" if memory else "",
    )


def _uncertain_tensions():
    return TensionSet(
        dynamic_tensions=[
            Tension(
                tension_id="uncertainty:task",
                tension_type=TensionType.UNCERTAINTY,
                intensity=0.8,
                activation=0.75,
                metadata={"status": "active"},
            )
        ]
    )


def test_recommendation_path_values_are_limited_to_spec_allowlist():
    recommendation = CognitiveEconomyRecommendation(selected_path=CognitiveEconomyPath.AUXILIARY_SMALL)

    assert [item.value for item in CognitiveEconomyPath] == [
        "rule_path",
        "auxiliary_small",
        "main_model",
        "world_compute",
        "high_reasoning",
    ]
    assert CognitiveEconomyRecommendation.from_dict(recommendation.to_dict()).selected_path == CognitiveEconomyPath.AUXILIARY_SMALL


def test_low_score_uses_rule_path_without_world_compute():
    called = []

    def compute_stub(*args, **kwargs):
        called.append((args, kwargs))
        return ComputeReceipt("req-1", ReceiptStatus.PUBLISHED)

    recommendation = CognitiveEconomyController(
        config={"allow_world_compute": True},
        compute_gateway=compute_stub,
    ).recommend(
        action_potential=_potential(score=0.12, depth=RecommendedDepth.NONE),
        signal_set=SignalSet(agent_context=_world_context()),
        life_state=LifeState(restraint=0.2),
    )

    assert recommendation.selected_path == CognitiveEconomyPath.RULE_PATH
    assert not called


def test_main_model_is_recommended_for_mid_value_mainline_work():
    recommendation = CognitiveEconomyController().recommend(
        action_potential=_potential(score=0.52, learning=0.18, depth=RecommendedDepth.DRAFT),
        signal_set=SignalSet(),
        life_state=LifeState(restraint=0.2),
    )

    assert recommendation.selected_path == CognitiveEconomyPath.MAIN_MODEL
    assert recommendation.budget_hint == "standard"


def test_world_compute_requires_login_token_secret_memory_and_receipt():
    called = []

    def compute_stub(task, input_data=None, repository=None):
        called.append((task, input_data, repository))
        return ComputeReceipt(
            "req-world",
            ReceiptStatus.PUBLISHED,
            provider="world",
            model="reasoner",
            provider_summary="world/reasoner",
        )

    recommendation = CognitiveEconomyController(
        config={"allow_world_compute": True},
        compute_gateway=compute_stub,
    ).recommend(
        action_potential=_potential(score=0.82, learning=0.56, risk=0.1, depth=RecommendedDepth.DRAFT),
        signal_set=SignalSet(agent_context=_world_context()),
        tension_set=_uncertain_tensions(),
        life_state=LifeState(restraint=0.2),
        world_input={"task": "analyze high-value uncertain path"},
    )

    assert recommendation.selected_path == CognitiveEconomyPath.WORLD_COMPUTE
    assert recommendation.receipt_summary["request_id"] == "req-world"
    assert recommendation.receipt_summary["status"] == "published"
    assert called
    assert called[0][1] == {"task": "analyze high-value uncertain path"}


def test_world_compute_fails_closed_without_login_or_soul_memory_summary():
    controller = CognitiveEconomyController(config={"allow_world_compute": True})

    logged_out = controller.recommend(
        action_potential=_potential(score=0.84, learning=0.6, risk=0.1),
        signal_set=SignalSet(agent_context=_world_context(logged_in=False)),
        tension_set=_uncertain_tensions(),
        life_state=LifeState(restraint=0.2),
    )
    no_memory = controller.recommend(
        action_potential=_potential(score=0.84, learning=0.6, risk=0.1),
        signal_set=SignalSet(agent_context=_world_context(memory=False)),
        tension_set=_uncertain_tensions(),
        life_state=LifeState(restraint=0.2),
    )

    assert logged_out.selected_path != CognitiveEconomyPath.WORLD_COMPUTE
    assert logged_out.downgrade_reason == "not_logged_in"
    assert no_memory.selected_path != CognitiveEconomyPath.WORLD_COMPUTE
    assert no_memory.downgrade_reason == "missing_soul_memory_summary"


def test_missing_token_secret_and_explicit_credentials_block_world_compute():
    called = []

    def compute_stub(*args, **kwargs):
        called.append((args, kwargs))
        return ComputeReceipt("req-1", ReceiptStatus.PUBLISHED)

    controller = CognitiveEconomyController(
        config={"allow_world_compute": True},
        compute_gateway=compute_stub,
    )
    no_secret = controller.recommend(
        action_potential=_potential(score=0.84, learning=0.6, risk=0.1),
        signal_set=SignalSet(agent_context=_world_context(secret=False)),
        tension_set=_uncertain_tensions(),
        life_state=LifeState(restraint=0.2),
    )
    explicit_secret = controller.recommend(
        action_potential=_potential(score=0.84, learning=0.6, risk=0.1),
        signal_set=SignalSet(agent_context=_world_context()),
        tension_set=_uncertain_tensions(),
        life_state=LifeState(restraint=0.2),
        world_input={"token": "raw-secret", "task": "must not be sent"},
    )

    assert no_secret.selected_path != CognitiveEconomyPath.WORLD_COMPUTE
    assert no_secret.downgrade_reason == "token_secret_unavailable"
    assert explicit_secret.selected_path != CognitiveEconomyPath.WORLD_COMPUTE
    assert explicit_secret.downgrade_reason == "explicit_credentials_rejected"
    assert not called


def test_rejected_or_failed_world_compute_receipt_downgrades_and_records_status():
    def rejected_stub(task, input_data=None, repository=None):
        return ComputeReceipt("req-rejected", ReceiptStatus.REJECTED, message="governance rejected")

    recommendation = CognitiveEconomyController(
        config={"allow_world_compute": True},
        compute_gateway=rejected_stub,
    ).recommend(
        action_potential=_potential(score=0.86, learning=0.6, risk=0.1),
        signal_set=SignalSet(agent_context=_world_context()),
        tension_set=_uncertain_tensions(),
        life_state=LifeState(restraint=0.2),
    )

    assert recommendation.selected_path == CognitiveEconomyPath.HIGH_REASONING
    assert recommendation.downgrade_reason == "world_compute_receipt_rejected"
    assert recommendation.receipt_summary["status"] == "rejected"
    assert recommendation.metadata["world_compute_eligibility"]["receipt_status"] == "rejected"
