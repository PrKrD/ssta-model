# Architecture

## Minimal foundation

This repository supports a research model, not a general-purpose modelling
framework. Package docstrings establish boundaries without speculative classes,
registries, solvers or configuration systems. Add modules when their actual
functionality is developed. No scientific calculations are implemented yet.

The model assumes geographically varying but temporally fixed late-winter
mixed-layer depth. Start with surface heat flux forcing and temperature-dependent
damping, validate the simpler model, then introduce processes incrementally.
Sea surface salinity remains an optional extension.

## Responsibilities and dependencies

- [core](../src/ssta_model/core/) will manage configuration, grids, state,
  orchestration and integration. It may call physics and forcing.
- [physics](../src/ssta_model/physics/) will calculate independent process
  tendencies from explicit state, parameters and fields.
- [forcing](../src/ssta_model/forcing/) will supply atmospheric forcing,
  including stochastic forcing informed by estimated spatial patterns.
- [data](../src/ssta_model/data/) will load, standardise and prepare datasets.
- [analysis](../src/ssta_model/analysis/) will diagnose outputs, validate models
  and perform statistical analysis, including parameter estimation when needed.
- [experiments](../experiments/) will connect preparation, configuration,
  integration and diagnostics through thin scripts calling the package.
- [frontend](../frontend/) is an independently runnable TypeScript/Vite/Cesium
  field viewer with in-memory synthetic sequence playback. Its validated data
  boundary separates fixed grid geometry from numerical values and metadata;
  rendering, picking and UI are separate.
  The current input is a deterministic synthetic demo. Future scientific outputs
  can use this boundary independently of their producer. A thin API may be added
  when required; no server or API directory is needed now. See the
  [frontend guide](../frontend/README.md) for the concrete data contract.

Dependencies point from experiments and interfaces toward the scientific
package. Within integration, core calls physics and forcing; those calculations
must not import the simulation orchestrator. Data preparation and analysis are
outside the integration loop. Document shared contracts when implementing them;
avoid reverse imports or a speculative shared framework. The scientific package
must never depend on experiments, an API or frontend.

## Process composition and parameter estimation

Each physical component should calculate one SST tendency from explicit inputs.
The common engine will combine compatible tendencies and advance state using a
documented numerical method. Processes should not independently advance shared
state, load datasets, write files or invoke unrelated processes.

Estimating forcing patterns, damping or other parameters from datasets is a
preparation or analysis task. Applying prepared parameters during integration
is a separate calculation. Do not repeatedly fit parameters or read raw
observations inside timestepping. No parameter values or dataset choices are
established by this foundation.

To add a process, document its assumptions and inputs, implement its calculation
in the relevant package, test it in isolation, then connect it explicitly to the
engine and experiment configuration. Modify only code needed for that connection.
Analytical limits, conservation checks and controlled cases should guide
scientific validation where applicable.

## Future data contracts

Before implementing a scientific component, specify:

- Named array dimensions and ordering, spatial and temporal coordinates,
  coordinate orientation and longitude convention.
- Grid geometry, ocean/land masks, missing values and boundary treatment.
- Units for inputs, state, parameters, forcing and tendencies. Document heat flux
  and tendency sign conventions explicitly. Convert units at clear boundaries;
  combined tendencies must have compatible units.
- How fixed late-winter depth aligns with the state grid and remains constant
  in time, including treatment of invalid or masked depths.
- Metadata describing assumptions, provenance and standardisation.

Choose concrete array libraries and representations when implementation requires
them. This foundation sets no numerical values, dataset specifications, grid
resolution or unvalidated scientific conventions.

## Reproducibility and storage

Track definitions in [experiments](../experiments/) and configurations in
[configs](../configs/). Keep local datasets and intermediates in root
[data](../data/), distinct from the Python package. Write generated outputs
to [runs](../runs/), with a separate directory per run.

Future runs should preserve resolved configuration and parameters with units,
explicit random seeds and random-generator details, input dataset identities
and versions, preprocessing provenance, code revision (including whether local
changes exist), software versions and numerical method settings. Preserve these
alongside outputs so experiments can be repeated independently. Do not introduce
a run manager or schema until needed.

Only the README files in local data and run directories are tracked. Small,
intentional fixtures may live under tests. NumPy, SciPy, xarray and NetCDF
readers will be introduced with functionality that needs them; the current
runtime dependency list is empty.
