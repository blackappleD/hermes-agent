from collections import Counter

from experiment.scenarios.registry import list_scenarios


def test_scenario_registry_covers_required_counts() -> None:
    scenarios = list_scenarios()
    counts = Counter(scenario.phase for scenario in scenarios)
    assert counts["P2"] >= 6
    assert counts["P3"] >= 5
    assert counts["P4"] >= 5
    assert counts["P5"] >= 6


def test_p5_scenarios_use_multiple_seeds() -> None:
    p5 = [scenario for scenario in list_scenarios() if scenario.phase == "P5"]
    assert p5
    assert all(len(scenario.seed_ids) >= 2 for scenario in p5)
