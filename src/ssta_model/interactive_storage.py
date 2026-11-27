"""Bounded local interactive outputs, independent of scientific model calculations."""

import json
import re
import shutil
import tomllib
from datetime import UTC, datetime

RUN_ID = re.compile(r"[0-9a-f]{32}")
KEEP_COMPLETED = 5


def write_state(folder, status, **details):
    state = {"run_id": folder.name, "status": status, **details}
    temporary = folder / "state.tmp"
    temporary.write_text(json.dumps(state) + "\n")
    temporary.replace(folder / "state.json")
    return state


def completed_runs(base):
    """Recognise recorded completions or verified legacy interactive products only."""
    found = []
    if base.resolve() != base.absolute() or not base.is_dir():
        return found
    for folder in base.iterdir():
        if not RUN_ID.fullmatch(folder.name) or not folder.is_dir():
            continue
        # Refuse links anywhere in a deletable tree, including linked data products.
        if folder.is_symlink() or any(p.is_symlink() for p in folder.rglob("*")):
            continue
        try:
            state_path = folder / "state.json"
            if state_path.exists():
                state = json.loads(state_path.read_text())
                if state["status"] != "completed":
                    continue
                when = datetime.fromisoformat(state["completed_at"])
                if when.tzinfo is None:
                    continue
            else:
                request = tomllib.loads((folder / "request.toml").read_text())
                summary = json.loads((folder / "model/summary.json").read_text())
                manifest_path = folder / "display/manifest.json"
                manifest = json.loads(manifest_path.read_text())
                if (
                    request["experiment"]["name"] != "interactive_damping"
                    or summary["status"] != "complete"
                    or summary["configuration"]["experiment"]["name"]
                    != "interactive_damping"
                    or manifest["format"] != "sst-interactive-f32-v1"
                    or len(manifest["frames"]) != 24
                    or not all(
                        (folder / f"model/{h}_sst.nc").is_file()
                        for h in ("north", "south")
                    )
                    or not all(
                        (folder / f"display/frames/{i:04d}.bin").is_file()
                        for i in range(24)
                    )
                ):
                    continue
                # Manifest is written last, after the model and all frames succeed.
                when = datetime.fromtimestamp(manifest_path.stat().st_mtime, UTC)
                state = {
                    "run_id": folder.name,
                    "status": "completed",
                    "gamma_w_m2_k": manifest["gamma_w_m2_k"],
                    "error": None,
                    "completed_at": when.isoformat(),
                    "completion_source": "legacy display manifest mtime",
                }
            found.append((when, folder, state))
        except (OSError, ValueError, KeyError, TypeError):
            continue  # Unrecognised/incomplete directories need manual review.
    return sorted(found, key=lambda item: (item[0], item[1].name), reverse=True)


def prune_completed(base, protected=()):
    """Delete only old verified completions; callers serialise with the API lock.

    Protect active/queued IDs and responses currently transmitting display assets.
    Errors propagate to the API's warning handler, never the scientific worker.
    """
    removed = []
    for _, folder, _ in completed_runs(base)[KEEP_COMPLETED:]:
        if folder.name in protected:
            continue
        expired = base / ".expired"
        if expired.is_symlink():
            raise OSError("Refusing linked interactive expiry directory")
        expired.mkdir(exist_ok=True)
        marker = expired / folder.name
        marker.touch()
        try:
            shutil.rmtree(folder)
        except OSError:
            marker.unlink(missing_ok=True)
            raise
        removed.append(folder.name)
    return removed


def discard_failed_products(folder):
    """Keep request/log/state, remove only this finished job's incomplete products."""
    for name in ("model", "display"):
        path = folder / name
        if path.is_symlink():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
