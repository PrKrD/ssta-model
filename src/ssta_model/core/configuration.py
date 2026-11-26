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
    diffusion = config["physics"].setdefault("horizontal_diffusion", False)
    if type(diffusion) is not bool:
        raise ValueError("horizontal_diffusion must be boolean")
    kappa = config["parameters"].get("kappa_m2_s", 0.0)
    if type(kappa) not in (float, int) or not np.isfinite(kappa) or kappa < 0:
        raise ValueError("kappa_m2_s must be finite and nonnegative")
    if diffusion and "kappa_m2_s" not in config["parameters"]:
        raise ValueError("Diffusion requires explicit kappa_m2_s")
    solver = config.setdefault("solver", {})
    if diffusion:
        defaults = {
            "rtol": 1e-12,
            "maxiter": 500,
            "relative_limit": 1e-10,
            "budget_limit": 1e-6,
        }
        if set(solver) - set(defaults):
            raise ValueError("Unknown diffusion solver setting")
        for key, default in defaults.items():
            value = solver.setdefault(key, default)
            if type(value) not in (int, float) or not np.isfinite(value) or value <= 0:
                raise ValueError(f"Invalid solver {key}")
        if type(solver["maxiter"]) is not int:
            raise ValueError("maxiter must be integer")
    for key in ("rho_kg_m3", "cp_j_kg_k"):
        value = config["parameters"][key]
        if type(value) not in (int, float) or not np.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be finite and positive")
    initial = config["initial_conditions"]["temperature_anomaly_k"]
    if type(initial) not in (int, float) or not np.isfinite(initial):
        raise ValueError("Initial anomaly must be finite")
    initial_config = config["initial_conditions"]
    if initial_config.get("kind", "scalar") == "era5":
        if initial_config["month"] != config["experiment"]["start_month"]:
            raise ValueError("ERA5 initial month must equal experiment start month")
        initial_config["directory"] = str(
            (root / initial_config.get("directory", "data/processed")).resolve()
        )
    elif initial_config.get("kind", "scalar") != "scalar":
        raise ValueError("Unknown initial-condition kind")
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
