# Development guidance

- Respect the boundaries in [architecture](docs/architecture.md). Keep scientific
  logic independent of the frontend and any future API.
- Keep scripts thin and reusable calculations inside the Python package. Avoid
  duplicate workflows, speculative modules and unnecessary abstractions.
- Add dependencies only with a concrete justification. Prefer incremental,
  understandable changes and avoid unrelated edits.
- Preserve the geographically varying, temporally fixed late-winter mixed-layer
  depth framework unless explicitly instructed otherwise. Salinity is optional.
- Never invent scientific parameter values or dataset specifications. Document
  units, coordinates, masks, assumptions and physical sign conventions.
- Prioritise scientific correctness, numerical stability and reproducibility.
  Add or update relevant tests when implementing functionality, using analytical
  or controlled cases where possible.
- Keep generated data, diagnostics and results out of version control. Track
  experiment definitions and configurations; write generated outputs to `runs/`.

## macOS toolchain troubleshooting

Command Line Tools is installed on this Mac. Sandboxed commands have previously
reported misleading errors such as "invalid active developer path", missing
executables and unavailable npm. Before diagnosing missing software, retry the
failing command outside the sandbox through the normal approval process and
compare results. Do not recommend reinstalling tools based solely on a sandbox
failure.
