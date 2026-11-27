# Fixed-depth surface heat budget with conservative diffusion

The model follows the fixed-layer diffusion term specified in equation (16) of
A. Czaja, *Notes on slab mixed layer heat and salt budgets: long timescales*,
25 November 2026. Advection and subduction/obduction remain omitted.

```text
 dTheta/dt = (F - gamma*Theta)/(rho*cp*H) + div_h(kappa*H*grad_h(Theta))/H
 F(x,y,n)  = sum(k=1..12, beta_k(x,y)*PC_k(n))
```

Theta is the vertically averaged fixed-layer temperature anomaly (K), used here
as the model SST-anomaly proxy. F is positive downward (W m-2); positive forcing
warms, and positive gamma damps either anomaly sign. H is in m, kappa in m2 s-1,
rho in kg m-3 and cp in J kg-1 K-1. Historical raw turbulent forcing is not the
complete observed net surface heat flux and has no SST-feedback correction.

## Fixed H and parameters

H is the existing maximum of 12 monthly **de Boyer Montégut (2023)** MLD maps:
original product `mld_dr003_ref10m_v2023.nc`, density threshold 0.03 kg m-3 from
10 m. See [DOI 10.17882/91774](https://doi.org/10.17882/91774) and
[product documentation](https://www.seanoe.org/data/00806/91774/data/103668.pdf).
The source 1-degree field was transferred to native 0.25-degree ERA5 centres by
containing-cell mapping, with no interpolation. These processed values remain
unchanged. Maximum monthly climatology approximates late-winter H; it is not an
independently verified winter-depth selection and never evolves seasonally.

A [separate H rebuild](h_rebuild.md) first compared a source-mask-targeted
alternative. The later [ERA5-targeted product](h_era5_candidate.md) is used in
the [controlled H sensitivity](h_sensitivity.md), selected with
`mixed_layer_depth.variant="era5_bilinear"`. Original inputs and their complete
active mask are validated first; candidate H must cover that exact domain and
preserve polar baseline depths. Only H is replaced in memory. The observed
initialisation support, parameters, diffusion solver and saved A/B runs remain
unchanged. The operator's heat capacity and harmonic face conductances are rebuilt
with selected H. Interpolation adds no resolution to the original 1° climatology.

The diffusion experiment uses kappa=1000 m2 s-1, a provisional constant eddy
diffusivity, not a fit to ERA5. rho=1025 and cp=3990 remain configuration choices.
Gamma is read from [surface_damping.toml](../configs/surface_damping.toml), remains
16.072239642825945 W m-2 K-1, and is not recalibrated.

## Conservative spherical finite volumes

A native active control volume has horizontal area A_i and volume M_i=A_i H_i.
For each active shared face, conductance is

```text
 g_ij = kappa * harmonic_mean(H_i,H_j) * face_length / centre_distance
 (L Theta)_i = sum_j g_ij*(Theta_i-Theta_j)
 [M/dt + gamma*A/(rho*cp) + L] Theta_new
     = M*Theta_old/dt + A*F/(rho*cp)
```

Conductance is symmetric/nonnegative, L has positive diagonal and nonpositive
neighbour entries, and exchanges are equal and opposite. H inside the divergence
makes integrated heat content proportional to sum(A*H*Theta); replacing this
operator with kappa times a temperature Laplacian would not preserve that budget
when H varies. No dense matrix is built.

The grid is spherical. East/west face lengths are R times latitude extent and
centre distances R*cos(latitude)*longitude separation. North/south faces use
R*cos(face latitude)*longitude width and distances R*latitude separation. The
radius cancels from these ratios; areas use the existing saved spherical areas.
Longitude is cyclic, including the 0/360 seam. Only immediate face neighbours
connect; no diagonal links or valid-neighbour searches cross land barriers.
Inactive/missing cells and domain edges are impermeable. Inclusive +/-20-degree
centres retain the original native cell footprints (outer edges at +/-19.875);
there is no exchange with omitted tropical neighbours. This artificial no-flux
boundary is a modelling limitation.

At an exactly polar row, all longitude centres are co-located. A fully active
row becomes **one polar cap unknown** with summed area, summed A*H, summed
forcing and meridional face exchanges; its temperature is expanded back onto
the original grid. Native H is never altered. Old cap temperature is reduced
with A*H weights, conserving its initial heat content. The actual northern
initial field is already uniform at the pole. There are no zero-distance zonal
edges. Fully inactive poles have no unknown. Ambiguous partially active exact
polar rows are rejected instead of connecting water through inactive sectors.
The actual domain has a complete northern cap and an inactive southern pole.

## Implicit solver and verification

The complete surface/diffusion system is backward Euler, with both damping and
diffusion evaluated at the new state. Its positive mass diagonal makes the
symmetric matrix positive definite. Core solves a symmetric area-scaled system
`A^-1 K A^-1 x = A^-1 rhs`, with `x=A*Theta`, using SciPy conjugate gradient.
The preconditioner is longitude-line block Jacobi: full diagonal and zonal
neighbours, inverted with sparse LU. Each block and its inverse are SPD; omitted
meridional off-diagonals leave their positive diagonal contributions in place.
Geometry/L are built once; matrices and preconditioners are cached for each of
the four calendar-month durations. No global solver framework is introduced.

The [primary configuration](../configs/historical_surface_flux_bilinear_h.toml)
sets CG rtol=1e-12, maxiter=500, independently verified relative flux residual
<=1e-10 and maximum absolute budget residual <=1e-6 W m-2. Every solve must return
converged status and pass both independent checks; failures abort the run.
The unrounded physical residual is

```text
 rho*cp*[M*(Theta_new-Theta_old)/dt + L*Theta_new]/A - F + gamma*Theta_new
```

Face differences evaluate L*Theta for this check, avoiding row-sum cancellation
for uniform fields. Checks apply to independent control volumes; the polar
residual is the bulk-cap budget, not fictitious budgets for co-located wedges.
Iteration count and residuals are saved per month. Float64 state is retained;
float32 output rounding is checked and never feeds back into the integration.

With diffusion off, or kappa=0, the original independent-cell
[backward_euler](../src/ssta_model/core/integration.py) path is used unchanged.
Forcing/damping switches still replace their respective terms with zero.

Controlled tests verify symmetry, paired fluxes, conservation of sum(A*H*Theta),
uniform states, warm-anomaly spreading, no new pure-diffusion extrema, variable H,
land/domain/seam/pole behaviour, failed-solver rejection and exact runner recovery
for disabled/zero diffusion. Numerical verification is distinct from agreement
with ERA5, which is assessed without parameter tuning.

## Historical timing and limitations

January 1979 ERA5 SSTA initializes the state at 1 February; February is the first
integrated forcing month. There are 573 integrations through October 2026.
The same observed-initial mask and initial values as the no-diffusion baseline
are used. Later ERA5 values never enter the dynamics. Calendar months have their
actual Gregorian durations. State `time` is interval end, while `forcing_month`
and bounds preserve calendar association. Comparisons match labels against ERA5
monthly means by explicit approximation; initialized January is excluded from
skill. See [ERA5 conventions](era5_comparison.md).

No advection, diffusion tuning, subduction/obduction, seasonal H, salinity,
stochastic forcing, new sea-ice treatment or damping correction is added.
The conservative process redistributes heat but cannot by itself repair missing
forcing or guarantee better ERA5 agreement. The original zero/scalar initial
condition remains available in the runner; retired demonstration configurations
and frontend routes have been removed.
