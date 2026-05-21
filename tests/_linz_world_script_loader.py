from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
LINZ_SCRIPTS = ROOT / "scripts" / "linz-world"


def load_linz_world_script(name: str) -> ModuleType:
    module_name = f"_linz_world_script_{name}"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached

    path = LINZ_SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load Linz World script module: {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
