# Local interactive damping experiment

This proof of concept exposes **only surface damping gamma**, from 0 to 40
W m-2 K-1. The default remains exactly 16.072239642825945. The slider moves in
steps of one; the adjacent numerical input preserves the precise default and
allows fractional values. Changing an input does not run the model until the
user presses **Run Simulation**.

## Start locally

From the repository root, using the project Python environment:

```sh
python -m pip install -e ".[api]"
python -m uvicorn ssta_model.api:app --reload
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open the URL printed by Vite (normally http://127.0.0.1:5173). Its `/api` proxy
forwards to http://127.0.0.1:8000. A freshly started `npm run preview` also uses
that proxy, after `npm run build`. This is local execution; nothing is deployed.

Existing processed scientific inputs and the current historical comparison
manifest/assets are required. They are local, Git-ignored products, not bundled
observations. Use the existing [historical export](h_sensitivity.md) if assets
need generating from saved runs. The API reports missing files rather than
restoring raw data, rebuilding H or running the full historical experiment.

Use **one Uvicorn process/worker**. Active/failed status is held in memory. Completed runs are rediscovered from
local completion records on restart; generated files survive. Avoid editing/reloading the Python service
while a run is active. There is no job recovery or run-history interface. These
are deliberate limits of this small local implementation.

## Fixed scientific settings

[interactive_damping.toml](../configs/interactive_damping.toml) fixes:

- January 1979 ERA5 SSTA as the observed initial state, assigned to 1 February.
- February 1979–December 1980 integration: 23 intervals and 24 displayed states.
- Existing historical ordered 12-PC forcing and raw year-round turbulent maps,
  without intercept or feedback adjustment.
- Existing ERA5-targeted bilinear H, original active domain and polar retention.
- Diffusion enabled with kappa=1000 m2/s, rho=1025 kg/m3 and cp=3990 J/kg/K.
- Existing monthly backward Euler, spherical conservative diffusion, harmonic
  face H, polar cap, CG and convergence/budget thresholds.

The API changes only the damping override and unique output location. It never
rewrites the baseline damping file or candidate H. Original input validation,
initialisation support and source/output provenance checks remain active.

## Request, computation and result

The optional [FastAPI adapter](../src/ssta_model/api.py) accepts:

| Endpoint | Behaviour |
|---|---|
| `POST /api/run` | JSON `{"gamma_w_m2_k":10}`; 202 with unique run ID |
| `GET /api/status/{run_id}` | `queued`, `running`, `completed` or `failed`, selected gamma and any error |
| `GET /api/results/{run_id}` | Completed dataset URL; 409 while incomplete/failed |

Results use the same prefix for `manifest.json` and `frames/NNNN.bin` assets.
The `sst-interactive-f32-v1` manifest identifies gamma, the existing grid,
calendar labels and source hashes. Each monthly file contains one little-endian
float32 array in that grid's cell order; NaN means missing.
Only those display assets are served, not arbitrary files. Invalid, non-finite,
negative/out-of-range or extra parameter requests receive 422. A concurrent
submission receives 409. Expired run IDs receive 410 (Gone), including after restart; unknown IDs/assets
receive 404. Failures remain visible
in status and permit another run.

A single background thread launches one child process for the existing model
and export. The API remains available for status requests. The child uses one
BLAS thread, avoiding local threading overhead. No new equations, solver,
database, persistent queue, API authentication or generic task framework is added.

Each run writes a new `runs/interactive_damping/<run_id>/` directory containing
its request TOML, execution log, `model/` scientific outputs/provenance and
`display/` manifest/binary frames. Existing historical runs and their display
assets are never overwritten. After each successful completion the API records an explicit UTC completion time
in `state.json` and keeps the **five most recent successfully completed runs**,
including the new run. Older completed interactive directories are removed in
full. Native scientific outputs and display assets are both retained for those
five. Active/queued jobs and display responses currently transmitting are
protected; deferred deletion is retried when the response finishes. Cleanup
errors are logged without turning a successful scientific run into a failure.

For pre-policy directories, only a matching interactive request, complete model
summary, both native outputs, and a 24-frame interactive display export establish
completion. The display manifest modification time (written last) is the fallback
completion time; unrecognised/incomplete folders and symlinked trees are left for
manual review. Small `.expired/<run_id>` markers preserve HTTP 410 responses.
A failed job removes its partial `model/` and `display/` products, retaining the
request, failure state and execution log. Filesystem permission failures are
logged and require manual attention. Historical experiments and processed inputs
are outside retention's scope. Longer periods produce proportionally larger
outputs and may eventually need a separate temporary-output policy; this task
retains the existing numerical formats and accuracy.

## Cesium integration

The export reuses the current 0.5° grid and native ocean-area-weighted
aggregation. Missing values remain NaN in binary files, decoded as missing in
the viewer. Land/tropics never contribute. The frontend validates matching cell
IDs/bounds/order and the exact 24-state calendar before accepting the result.

On completion it adds/replaces a single **Interactive model SSTA — gamma = …**
selection and loads it automatically, paused at January's initial state. Press
Play or scrub to later months to inspect the damping response. The existing
Cesium geometry, picking, tooltip, colour and playback components are reused.
Interactive SSTA shares the historical fixed SSTA colour population so changing
gamma does not silently rescale colours. There is no monthly auto-rescaling.

The original historical comparison and both static H layers remain available.
Historical and interactive timeline positions are remembered separately; static
H still pauses playback and preserves the historical month. Only the latest
interactive result appears in the selector, while up to five completed runs remain on disk.
Leaving the page stops polling; it does not cancel the running Python computation.

## Verification

Install `.[dev,api]` for the full Python test suite, then run pytest and Ruff;
run frontend tests/build from `frontend/`. CI installs the API extra as well.
Tests cover input validation, responsive status/single-run admission, completion,
failures, fixed configuration, missing inputs and bounded asset serving. A tiny
controlled child-process integration verifies selected damping analytically,
unchanged initial values/masks, and correct 24-state output labels at two gamma
values. Frontend tests cover polling, errors, geometry/calendar validation and
completed-sequence decoding without requiring WebGL or scientific data.

Actual browser verification changes the precise default to gamma=10, presses
Run, observes the new completed sequence, checks later-month values and compares
the saved native fields with the existing default-gamma run. Execution audits
are written under ignored `runs/`; they do not replace scientific inputs.

See the [storage audit and cleanup](repository_cleanup.md) for measured local
sizes, preserved scientific products and manual-review candidates.
