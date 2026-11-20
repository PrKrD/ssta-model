"""Vectorised backward Euler without file, calendar or xarray dependencies."""

import numpy as np

from ssta_model.physics.surface_flux import heat_capacity


def backward_euler(temperature, forcing, depth, valid, dt_seconds, rho, cp, gamma):
    """Advance one constant-forcing interval; inactive cells always return NaN.

    Inputs have identical spatial shapes, avoiding accidental broadcasting.
    Only active depths enter divisions. The returned state is always float64.
    """
    temperature, forcing, depth = (
        np.asarray(value, dtype=np.float64) for value in (temperature, forcing, depth)
    )
    valid = np.asarray(valid)
    if valid.dtype != np.bool_ or any(
        value.shape != valid.shape for value in (temperature, forcing, depth)
    ):
        raise ValueError("State, forcing, depth and boolean mask shapes must match")
    if not (np.ndim(gamma) == 0 and np.isfinite(gamma) and gamma >= 0):
        raise ValueError("Damping must be a finite nonnegative scalar")
    if not (np.ndim(dt_seconds) == 0 and np.isfinite(dt_seconds) and dt_seconds > 0):
        raise ValueError("Timestep must be finite and positive")
    if not (
        np.isfinite(temperature[valid]).all() and np.isfinite(forcing[valid]).all()
    ):
        raise ValueError("Non-finite active state or forcing")
    capacity = heat_capacity(depth[valid], rho, cp)
    result = np.full(valid.shape, np.nan, dtype=np.float64)
    factor = dt_seconds / capacity
    result[valid] = (temperature[valid] + factor * forcing[valid]) / (
        1 + factor * gamma
    )
    if not np.isfinite(result[valid]).all():
        raise FloatingPointError("Non-finite active temperature after integration")
    return result
