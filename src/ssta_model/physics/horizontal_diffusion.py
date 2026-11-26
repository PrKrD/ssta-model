"""Conservative spherical face exchanges for (1/H) div(kappa H grad(theta)).

No file/xarray dependencies. L is a symmetric graph Laplacian in m3 s-1.
Only shared faces of active cells exchange heat; every flux has an opposite pair.
"""

from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix


@dataclass
class DiffusionGeometry:
    shape: tuple
    active: np.ndarray
    mapping: np.ndarray
    mass: np.ndarray
    area: np.ndarray
    matrix: object
    line_matrix: object
    left: np.ndarray
    right: np.ndarray
    conductance: np.ndarray

    def reduce(self, values, weights):
        return np.bincount(
            self.mapping,
            weights=np.asarray(values).ravel()[self.active] * weights,
            minlength=len(self.mass),
        )

    def expand(self, values):
        field = np.full(np.prod(self.shape), np.nan)
        field[self.active] = values[self.mapping]
        return field.reshape(self.shape)

    def exchange(self, temperature):
        """L theta evaluated as paired differences, avoiding uniform-field cancellation."""
        flux = self.conductance * (temperature[self.left] - temperature[self.right])
        return np.bincount(
            self.left, weights=flux, minlength=len(self.mass)
        ) - np.bincount(self.right, weights=flux, minlength=len(self.mass))


def build_diffusion(latitude, longitude, area, depth, valid, kappa):
    """Construct the reusable finite-volume geometry on a complete cyclic longitude axis.

    A fully active row exactly at a pole is one cap DOF with summed A*H, A,
    forcing and meridional face conductances. No zero-length zonal edges exist.
    Partial active polar rows are rejected as geometrically ambiguous, rather
    than connecting disconnected sectors through land. Original H is untouched.
    """
    lat, lon = np.asarray(latitude, dtype=float), np.asarray(longitude, dtype=float)
    area, depth, valid = np.asarray(area), np.asarray(depth), np.asarray(valid)
    if (
        valid.dtype != np.bool_
        or valid.shape != (len(lat), len(lon))
        or area.shape != valid.shape
        or depth.shape != valid.shape
    ):
        raise ValueError("Diffusion grid/boolean mask shapes differ")
    if (
        len(lat) < 2
        or len(lon) < 2
        or not np.all(np.diff(lat) < 0)
        or not np.all(np.diff(lon) > 0)
        or lon[-1] - lon[0] >= 360
    ):
        raise ValueError("Expected descending latitude and increasing cyclic longitude")
    if (
        not np.isfinite(lat).all()
        or np.any(abs(lat) > 90)
        or not np.isfinite(lon).all()
    ):
        raise ValueError("Invalid spherical coordinates")
    if np.any((lat < 20) & (lat > -20)) or not (
        np.all(lat >= 20) or np.all(lat <= -20)
    ):
        raise ValueError("Build each extratropical hemisphere independently")
    if np.ndim(kappa) != 0 or not np.isfinite(kappa) or kappa < 0:
        raise ValueError("Diffusivity must be a finite nonnegative scalar")
    if not valid.any() or not np.all(
        np.isfinite(depth[valid])
        & (depth[valid] > 0)
        & np.isfinite(area[valid])
        & (area[valid] > 0)
    ):
        raise ValueError("Active depth and area must be positive and finite")
    active = np.flatnonzero(valid.ravel())
    ids = np.full(valid.shape, -1, dtype=int)
    ids.ravel()[active] = np.arange(len(active))
    for y in np.flatnonzero(abs(lat) == 90):
        if valid[y].any() and not valid[y].all():
            raise ValueError(
                "Partial active polar row is ambiguous; no cross-land cap is constructed"
            )
        if valid[y].all():
            ids[y, :] = ids[y, 0]
    _, first, mapping = np.unique(
        ids.ravel()[active], return_index=True, return_inverse=True
    )
    ids.ravel()[active] = mapping
    dof_rows = active[first] // len(lon)
    mass = np.bincount(mapping, weights=(area * depth).ravel()[active])
    pooled_area = np.bincount(mapping, weights=area.ravel()[active])
    lat_edges = np.clip(
        np.r_[
            lat[0] + (lat[0] - lat[1]) / 2,
            (lat[:-1] + lat[1:]) / 2,
            lat[-1] - (lat[-2] - lat[-1]) / 2,
        ],
        -90,
        90,
    )
    gaps = np.diff(np.r_[lon, lon[0] + 360])
    widths = (gaps + np.roll(gaps, 1)) / 2
    left, right, coefficients = [], [], []

    def add(i, j, h_i, h_j, metric):
        use = (i >= 0) & (j >= 0) & (i != j)
        face_depth = 2 / (1 / h_i[use] + 1 / h_j[use])
        left.append(i[use])
        right.append(j[use])
        coefficients.append(kappa * face_depth * np.broadcast_to(metric, i.shape)[use])

    # East faces: meridional face length / parallel distance between centres.
    # Zero-distance polar zonal faces are omitted; cap DOFs replace those rows.
    zonal_metric = np.zeros(valid.shape)
    nonpolar = abs(lat) < 90
    zonal_metric[nonpolar] = np.deg2rad(abs(np.diff(lat_edges)))[nonpolar, None] / (
        np.cos(np.deg2rad(lat[nonpolar, None])) * np.deg2rad(gaps)[None, :]
    )
    add(ids, np.roll(ids, -1, axis=1), depth, np.roll(depth, -1, axis=1), zonal_metric)
    # North/south faces: parallel face length / meridional centre distance.
    meridional_metric = (
        np.cos(np.deg2rad((lat[:-1] + lat[1:]) / 2))[:, None]
        * np.deg2rad(widths)[None, :]
        / np.deg2rad(lat[:-1] - lat[1:])[:, None]
    )
    add(ids[:-1], ids[1:], depth[:-1], depth[1:], meridional_metric)
    i, j, g = map(np.concatenate, (left, right, coefficients))
    if not np.all(np.isfinite(g) & (g >= 0)):
        raise ValueError("Invalid face conductance")
    n = len(mass)
    matrix = coo_matrix(
        (np.r_[g, g, -g, -g], (np.r_[i, j, i, j], np.r_[i, j, j, i])), shape=(n, n)
    ).tocsr()
    matrix.eliminate_zeros()
    # Longitude-line block Jacobi: retain full diagonal and only same-row neighbours.
    entries = matrix.tocoo()
    same_row = dof_rows[entries.row] == dof_rows[entries.col]
    line = coo_matrix(
        (entries.data[same_row], (entries.row[same_row], entries.col[same_row])),
        shape=(n, n),
    ).tocsr()
    return DiffusionGeometry(
        valid.shape, active, mapping, mass, pooled_area, matrix, line, i, j, g
    )
