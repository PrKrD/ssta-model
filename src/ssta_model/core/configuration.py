"""Small explicit TOML configuration for the historical surface-flux experiment."""

import re
import tomllib
from pathlib import Path

import numpy as np


def load_configuration(path, root=Path(".")):
    """Resolve repository-relative paths and scalar damping, preserving overrides."""
    root = Path(root).resolve()
    path = Path(path).resolve()
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    for key in ("start_month", "end_month"):
        value = config["experiment"][key]
        if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-(0[1-9]|1[0-2])", value
        ):
            raise ValueError(f"{key} must be YYYY-MM")
    if config["experiment"]["start_month"] > config["experiment"]["end_month"]:
        raise ValueError("Start month follows end month")
    for key in ("surface_forcing", "surface_damping"):
        if type(config["physics"][key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    for key in ("rho_kg_m3", "cp_j_kg_k"):
        value = config["parameters"][key]
        if type(value) not in (int, float) or not np.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be finite and positive")
    initial = config["initial_conditions"]["temperature_anomaly_k"]
    if type(initial) not in (int, float) or not np.isfinite(initial):
        raise ValueError("Initial anomaly must be finite")
    damping = config.setdefault("surface_damping", {})
    damping_path = root / damping.get("configuration", "configs/surface_damping.toml")
    with damping_path.open("rb") as stream:
        baseline = tomllib.load(stream)["surface_damping"]
    if baseline["mode"] != "constant":
        raise ValueError("Only constant damping is supported")
    gamma = damping.get("gamma_w_m2_k", baseline["gamma_w_m2_k"])
    if type(gamma) not in (int, float) or not np.isfinite(gamma) or gamma < 0:
        raise ValueError("Damping must be a finite nonnegative scalar")
    damping["gamma_w_m2_k"] = float(gamma)
    damping["configuration"] = str(damping_path.resolve())
    config.setdefault("inputs", {})["directory"] = str(
        (root / config.get("inputs", {}).get("directory", "data/processed")).resolve()
    )
    config["output"]["directory"] = str(
        (root / config["output"]["directory"]).resolve()
    )
    if not Path(config["output"]["directory"]).is_relative_to(
        (root / "runs").resolve()
    ):
        raise ValueError("Generated output must be under runs/")
    return config
