"""Local surface heat budget; heat flux is positive downward into the ocean."""

import numpy as np


def heat_capacity(depth, rho, cp):
    """Return areal heat capacity (J m-2 K-1) for positive finite depths."""
    depth = np.asarray(depth, dtype=np.float64)
    if not (
        np.ndim(rho) == np.ndim(cp) == 0
        and np.isfinite(rho)
        and rho > 0
        and np.isfinite(cp)
        and cp > 0
    ):
        raise ValueError("Density and specific heat must be finite and positive")
    if not (np.isfinite(depth).all() and np.all(depth > 0)):
        raise ValueError("Active depth must be finite and positive")
    capacity = rho * cp * depth
    if not np.isfinite(capacity).all():
        raise ValueError("Non-finite heat capacity")
    return capacity


def surface_tendency(temperature, forcing, capacity, gamma):
    """Surface tendency in K s-1; evaluate at the new state for backward Euler."""
    return (forcing - gamma * temperature) / capacity
