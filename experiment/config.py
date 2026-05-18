from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

Phase = Literal["P0", "P1", "P2", "P3", "P4", "P5", "all"]
Mode = Literal["mock", "runtime"]

VALID_PHASES: tuple[str, ...] = ("P0", "P1", "P2", "P3", "P4", "P5", "all")
VALID_MODES: tuple[str, ...] = ("mock", "runtime")


def make_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


@dataclass(frozen=True)
class ExperimentRunConfig:
    phase: Phase = "all"
    mode: Mode = "mock"
    repeat: int = 3
    run_id: str = field(default_factory=make_run_id)
    output_root: Path = Path("experiment/results")
    profile: str | None = None

    @property
    def phases(self) -> list[str]:
        if self.phase == "all":
            return ["P0", "P1", "P2", "P3", "P4", "P5"]
        return [self.phase]

    @property
    def run_dir(self) -> Path:
        return self.output_root / self.run_id


def parse_args(argv: list[str] | None = None) -> ExperimentRunConfig:
    parser = argparse.ArgumentParser(description="Run P0-P5 raw transition experiments.")
    parser.add_argument("--phase", choices=VALID_PHASES, default="all")
    parser.add_argument("--mode", choices=VALID_MODES, default="mock")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-root", type=Path, default=Path("experiment/results"))
    parser.add_argument("--profile", default=None)
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be >= 1")
    return ExperimentRunConfig(
        phase=args.phase,
        mode=args.mode,
        repeat=args.repeat,
        run_id=args.run_id or make_run_id(),
        output_root=args.output_root,
        profile=args.profile,
    )
