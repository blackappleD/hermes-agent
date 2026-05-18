from __future__ import annotations

LIFE_FIELDS = ("energy", "stability", "confidence", "credit", "trust", "curiosity", "stress", "fatigue")
TENSION_FIELDS = ("T_value", "T_risk", "T_consensus", "T_creation", "T_survival", "T_reputation", "T_resource", "T_governance")
ACTION_FIELDS = ("AP_accept_task", "AP_ask_clarify", "AP_submit", "AP_refuse", "AP_seek_help", "AP_review", "AP_negotiate", "AP_learn")
ARBITRATION_DECISIONS = ("auto_execute", "sandbox_execute", "require_approval", "report_only", "reject")


def missing_fields(values: dict[str, object], required: tuple[str, ...]) -> list[str]:
    return [field for field in required if field not in values]


def delta(before: dict[str, float], after: dict[str, float], required: tuple[str, ...]) -> dict[str, float]:
    return {field: round(float(after.get(field, 0.0)) - float(before.get(field, 0.0)), 4) for field in required}


def ranked_action_potential(action_potential: dict[str, float]) -> list[dict[str, float | str | int]]:
    ordered = sorted(ACTION_FIELDS, key=lambda key: float(action_potential.get(key, 0.0)), reverse=True)
    return [{"rank": idx + 1, "action": key, "score": round(float(action_potential.get(key, 0.0)), 4)} for idx, key in enumerate(ordered)]
