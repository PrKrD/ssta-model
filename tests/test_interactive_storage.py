"""Retention only touches recognised, finished local interactive directories."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from ssta_model.api import create_app
from ssta_model.interactive_storage import (
    completed_runs,
    discard_failed_products,
    prune_completed,
    write_state,
)

from .test_interactive_api import finished


def completion(base, number, order=None):
    folder = base / f"{number:032x}"
    (folder / "display").mkdir(parents=True)
    (folder / "display/manifest.json").write_text("{}")
    write_state(
        folder,
        "completed",
        gamma_w_m2_k=10,
        error=None,
        completed_at=(
            datetime(2026, 1, 1, tzinfo=UTC)
            + timedelta(seconds=number if order is None else order)
        ).isoformat(),
    )
    return folder


@pytest.mark.parametrize("count", [0, 3, 5, 6, 8])
def test_limit_and_protected_domain(tmp_path, count):
    base = tmp_path / "runs/interactive_damping"
    folders = [completion(base, i) for i in range(count)]
    historical = tmp_path / "runs/historical_surface_flux_bilinear_h"
    historical.mkdir(parents=True, exist_ok=True)
    (historical / "science.nc").write_bytes(b"preserve")
    for number, status in [(100, "running"), (101, "queued"), (102, "failed")]:
        folder = base / f"{number:032x}"
        folder.mkdir(parents=True)
        write_state(folder, status)
    unknown = base / "unknown_science"
    unknown.mkdir()
    prune_completed(base)
    assert [p.exists() for p in folders] == [
        i >= max(0, count - 5) for i in range(count)
    ]
    assert all((base / f"{i:032x}").exists() for i in (100, 101, 102))
    assert unknown.exists() and (historical / "science.nc").read_bytes() == b"preserve"


def test_completion_order_and_inflight_response_protection(tmp_path):
    newest = completion(tmp_path, 0, 99)
    others = [completion(tmp_path, i) for i in range(1, 7)]
    # Protect the oldest completion while its response is being transmitted.
    prune_completed(tmp_path, {others[0].name, others[1].name})
    assert newest.exists() and others[0].exists()
    prune_completed(tmp_path, {newest.name})
    assert not others[0].exists() and not others[1].exists()
    assert len(completed_runs(tmp_path)) == 5


def test_failed_products_and_symlink_safety(tmp_path):
    base = tmp_path / "runs/interactive_damping"
    folder = base / ("a" * 32)
    for name in ("model", "display"):
        (folder / name).mkdir(parents=True)
        (folder / name / "partial.nc").write_bytes(b"partial")
    (folder / "execution.log").write_text("useful failure")
    discard_failed_products(folder)
    assert not (folder / "model").exists() and not (folder / "display").exists()
    assert (folder / "execution.log").read_text() == "useful failure"
    outside = tmp_path / "historical"
    outside.mkdir()
    (base / ("b" * 32)).symlink_to(outside, target_is_directory=True)
    assert completed_runs(base) == []
    assert outside.exists()


def test_legacy_completion_fallback(tmp_path):
    folder = tmp_path / ("a" * 32)
    (folder / "model").mkdir(parents=True)
    (folder / "display/frames").mkdir(parents=True)
    (folder / "request.toml").write_text('[experiment]\nname="interactive_damping"\n')
    (folder / "model/summary.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "configuration": {"experiment": {"name": "interactive_damping"}},
            }
        )
    )
    for h in ("north", "south"):
        (folder / f"model/{h}_sst.nc").write_bytes(b"native")
    for i in range(24):
        (folder / f"display/frames/{i:04d}.bin").write_bytes(b"frame")
    manifest = folder / "display/manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "format": "sst-interactive-f32-v1",
                "gamma_w_m2_k": 10,
                "frames": [{}] * 24,
            }
        )
    )
    items = completed_runs(tmp_path)
    assert len(items) == 1
    assert abs(items[0][0].timestamp() - manifest.stat().st_mtime) < 1e-6
    assert items[0][2]["completion_source"] == "legacy display manifest mtime"
    (folder / "display/frames/0023.bin").unlink()
    assert completed_runs(tmp_path) == []


def test_expiry_persists_and_new_results_accessible(tmp_path):
    base = tmp_path / "runs/interactive_damping"
    folders = [completion(base, i) for i in range(5)]

    def execute(root, folder, gamma):
        (folder / "display").mkdir()
        (folder / "display/manifest.json").write_text("{}")

    with TestClient(create_app(tmp_path, execute)) as client:
        run_id = client.post("/api/run", json={"gamma_w_m2_k": 10}).json()["run_id"]
        assert finished(client, run_id)["status"] == "completed"
        assert client.get(f"/api/results/{run_id}/manifest.json").status_code == 200
        assert client.get(f"/api/status/{folders[0].name}").status_code == 410
        assert client.get(f"/api/results/{folders[0].name}").status_code == 410
    with TestClient(create_app(tmp_path, execute)) as client:
        assert client.get(f"/api/status/{folders[0].name}").status_code == 410
        assert client.get(f"/api/results/{run_id}/manifest.json").status_code == 200


def test_cleanup_failure_does_not_fail_new_science(tmp_path):
    def execute(root, folder, gamma):
        (folder / "display").mkdir()
        (folder / "display/manifest.json").write_text("{}")

    with patch("ssta_model.api.prune_completed", side_effect=OSError("permission")):
        with TestClient(create_app(tmp_path, execute)) as client:
            run_id = client.post("/api/run", json={"gamma_w_m2_k": 10}).json()["run_id"]
            assert finished(client, run_id)["status"] == "completed"
            assert client.get(f"/api/results/{run_id}/manifest.json").status_code == 200


def test_failed_api_job_discards_partial_native_products(tmp_path):
    def fail(root, folder, gamma):
        (folder / "model").mkdir()
        (folder / "model/partial.nc").write_bytes(b"large partial")
        (folder / "execution.log").write_text("solver failed")
        raise RuntimeError("solver failed")

    with TestClient(create_app(tmp_path, fail)) as client:
        run_id = client.post("/api/run", json={"gamma_w_m2_k": 10}).json()["run_id"]
        assert finished(client, run_id)["status"] == "failed"
    folder = tmp_path / "runs/interactive_damping" / run_id
    assert not (folder / "model").exists()
    assert (folder / "execution.log").read_text() == "solver failed"


def test_deletion_error_preserves_success_and_does_not_expire_undeleted_run(tmp_path):
    base = tmp_path / "runs/interactive_damping"
    oldest = completion(base, 0)
    for number in range(1, 5):
        completion(base, number)

    def execute(root, folder, gamma):
        (folder / "display").mkdir()
        (folder / "display/manifest.json").write_text("{}")

    with patch(
        "ssta_model.interactive_storage.shutil.rmtree", side_effect=OSError("read-only")
    ):
        with TestClient(create_app(tmp_path, execute)) as client:
            run_id = client.post("/api/run", json={"gamma_w_m2_k": 10}).json()["run_id"]
            assert finished(client, run_id)["status"] == "completed"
            assert client.get(f"/api/results/{run_id}/manifest.json").status_code == 200
            assert (
                client.get(f"/api/results/{oldest.name}/manifest.json").status_code
                == 200
            )
    assert oldest.exists() and not (base / ".expired" / oldest.name).exists()
    assert len(completed_runs(base)) == 6  # Deferred until filesystem access works.
    prune_completed(base)
    assert not oldest.exists() and len(completed_runs(base)) == 5
