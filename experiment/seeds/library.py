from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_SEED_IDS = {
    "seed_neutral_001",
    "seed_bold_001",
    "seed_prudent_001",
    "seed_social_001",
    "seed_competitive_001",
    "seed_fragile_001",
}

_SEED_FILE = Path(__file__).with_name("default_seeds.json")


def load_seeds(path: Path = _SEED_FILE) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        seeds = json.load(fh)
    return {seed["seed_id"]: seed for seed in seeds}


def load_seed(seed_id: str) -> dict[str, Any]:
    seeds = load_seeds()
    try:
        return seeds[seed_id]
    except KeyError as exc:
        raise KeyError(f"unknown experiment seed: {seed_id}") from exc
