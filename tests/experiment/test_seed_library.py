from experiment.collectors.mappings import ACTION_FIELDS, LIFE_FIELDS, TENSION_FIELDS
from experiment.seeds import REQUIRED_SEED_IDS, load_seeds


def test_required_seed_library_is_complete() -> None:
    seeds = load_seeds()
    assert REQUIRED_SEED_IDS <= set(seeds)
    for seed_id in REQUIRED_SEED_IDS:
        seed = seeds[seed_id]
        assert seed["seed_id"] == seed_id
        assert seed["name"]
        assert seed["role"]
        assert isinstance(seed["bo_bias"], float)
        assert isinstance(seed["yue_bias"], float)
        assert set(LIFE_FIELDS) <= set(seed["initial_life_state"])
        assert set(TENSION_FIELDS) <= set(seed["tension_weights"])
        expected_thresholds = {field.removeprefix("AP_") for field in ACTION_FIELDS}
        assert expected_thresholds <= set(seed["action_thresholds"])
