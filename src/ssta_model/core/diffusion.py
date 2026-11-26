"""Symmetric implicit finite-volume solve, separated from input/output and forcing."""

import numpy as np
from scipy.sparse import diags
from scipy.sparse.linalg import LinearOperator, cg, splu


class DiffusionStepper:
    def __init__(
        self,
        geometry,
        depth,
        area,
        rho,
        cp,
        gamma,
        *,
        rtol=1e-12,
        maxiter=500,
        relative_limit=1e-10,
        budget_limit=1e-6,
    ):
        if not (
            np.isfinite(rho)
            and rho > 0
            and np.isfinite(cp)
            and cp > 0
            and np.isfinite(gamma)
            and gamma >= 0
        ):
            raise ValueError(
                "Positive rho/cp and nonnegative gamma are required for an SPD system"
            )
        self.geometry = geometry
        self.native_mass = (np.asarray(area) * depth).ravel()[geometry.active]
        self.native_area = np.asarray(area).ravel()[geometry.active]
        self.rho_cp = rho * cp
        self.gamma = gamma
        self.rtol = rtol
        self.maxiter = maxiter
        self.relative_limit = relative_limit
        self.budget_limit = budget_limit
        self.systems = {}

    def step(self, temperature, forcing, dt):
        g = self.geometry
        temperature = np.asarray(temperature, dtype="f8")
        forcing = np.asarray(forcing, dtype="f8")
        if temperature.shape != g.shape or forcing.shape != g.shape:
            raise ValueError("Diffusion state/forcing shapes differ from the geometry")
        if not np.isfinite(dt) or dt <= 0:
            raise ValueError("Invalid timestep")
        if (
            not np.isfinite(np.asarray(temperature).ravel()[g.active]).all()
            or not np.isfinite(np.asarray(forcing).ravel()[g.active]).all()
        ):
            raise ValueError("Non-finite active temperature or forcing")
        old = g.reduce(temperature, self.native_mass) / g.mass
        source = g.reduce(forcing, self.native_area) / self.rho_cp
        diagonal = g.mass / dt + g.area * self.gamma / self.rho_cp
        if dt not in self.systems:
            scale = diags(1 / g.area)
            matrix = (scale @ (g.matrix + diags(diagonal)) @ scale).tocsr()
            line = (scale @ (g.line_matrix + diags(diagonal)) @ scale).tocsc()
            inverse = splu(line, permc_spec="NATURAL", diag_pivot_thresh=0)
            preconditioner = LinearOperator(
                matrix.shape, matvec=inverse.solve, dtype="f8"
            )
            self.systems[dt] = (matrix, preconditioner)
        matrix, preconditioner = self.systems[dt]
        rhs = (g.mass * old / dt + source) / g.area
        iterations = 0

        def count(_):
            nonlocal iterations
            iterations += 1

        x, info = cg(
            matrix,
            rhs,
            x0=g.area * old,
            M=preconditioner,
            rtol=self.rtol,
            atol=0,
            maxiter=self.maxiter,
            callback=count,
        )
        if info != 0:
            raise RuntimeError(
                f"Diffusion CG failed: info={info}, iterations={iterations}"
            )
        new = x / g.area
        # Face differences give physical flux closure without cancellation of L's row sum.
        residual = (
            self.rho_cp
            * (g.mass * (new - old) / dt + g.exchange(new) - source)
            / g.area
            + self.gamma * new
        )
        denominator = np.linalg.norm(self.rho_cp * rhs)
        relative = (
            float(np.linalg.norm(residual) / denominator)
            if denominator
            else float(np.linalg.norm(residual))
        )
        maximum = float(np.max(abs(residual)))
        if (
            not np.isfinite(new).all()
            or relative > self.relative_limit
            or maximum > self.budget_limit
        ):
            raise RuntimeError(
                f"Diffusion budget verification failed: relative={relative:.3g}, maximum={maximum:.3g} W m-2"
            )
        return g.expand(new), {
            "solver_iterations": iterations,
            "solver_relative_residual": relative,
            "maximum_budget_residual_w_m2": maximum,
        }
