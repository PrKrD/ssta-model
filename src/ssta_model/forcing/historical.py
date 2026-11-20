"""Prescribed historical forcing, independently reconstructed per hemisphere."""

import numpy as np


def reconstruct_month(pc, coefficient):
    """Sum the 12 ordered beta_k PC_k terms, without intercept or PC rescaling.

    The loader validates labelled modes 1–12. This array kernel requires exactly
    one PC vector and one (mode, latitude, longitude) coefficient array. Missing
    coefficients propagate only within their own cell.
    """
    pc = np.asarray(pc, dtype=np.float64)
    coefficient = np.asarray(coefficient, dtype=np.float64)
    if pc.shape != (12,) or coefficient.ndim != 3 or coefficient.shape[0] != 12:
        raise ValueError("Expected PC shape (12,) and coefficients (12, lat, lon)")
    if not np.isfinite(pc).all():
        raise ValueError("PCs must be finite")
    return np.einsum("k,kij->ij", pc, coefficient, optimize=False)
