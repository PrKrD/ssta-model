"""Local request validation, responsive status and single-active-run lifecycle."""

import json
import time
import tomllib
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

from ssta_model.api import create_app
from ssta_model.interactive import DEFAULT_GAMMA, request_configuration, validate_gamma


def finished(client, run_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/status/{run_id}")
        assert response.status_code == 200
        state = response.json()
        if state["status"] in ("completed", "failed"):
            return state
        Event().wait(0.01)
    pytest.fail("Background request did not finish")


@pytest.mark.parametrize(
    "value", [-1, 41, float("nan"), float("inf"), True, "10", None]
)
def test_damping_validation(value):
    with pytest.raises(ValueError):
        validate_gamma(value)


def test_api_validation_handles_nonfinite_and_extra_parameters(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        for body in [
            '{"gamma_w_m2_k":NaN}',
            '{"gamma_w_m2_k":Infinity}',
            '{"gamma_w_m2_k":true}',
            '{"gamma_w_m2_k":"10"}',
            '{"gamma_w_m2_k":-1}',
            '{"gamma_w_m2_k":41}',
            "{}",
            '{"gamma_w_m2_k":10,"kappa":0}',
        ]:
            response = client.post(
                "/api/run", content=body, headers={"Content-Type": "application/json"}
            )
            assert response.status_code == 422
            assert "finite number" in response.json()["detail"]
        assert client.get("/api/status/unknown").status_code == 404


def test_single_active_run_status_results_and_unique_directories(tmp_path):
    started, release = Event(), Event()
    calls = []

    def execute(root, folder, gamma):
        calls.append((folder, gamma))
        started.set()
        assert release.wait(4)
        (folder / "display/frames").mkdir(parents=True)
        (folder / "display/manifest.json").write_text(json.dumps({"gamma": gamma}))
        (folder / "display/frames/0000.bin").write_bytes(b"frame")

    with TestClient(create_app(tmp_path, execute)) as client:
        first = client.post("/api/run", json={"gamma_w_m2_k": 10})
        assert first.status_code == 202 and first.json()["status"] == "queued"
        run_id = first.json()["run_id"]
        try:
            assert started.wait(2)
            assert client.get(f"/api/status/{run_id}").json()["status"] == "running"
            assert client.post("/api/run", json={"gamma_w_m2_k": 20}).status_code == 409
            assert client.get(f"/api/results/{run_id}").status_code == 409
        finally:
            release.set()
        assert finished(client, run_id)["status"] == "completed"
        result = client.get(f"/api/results/{run_id}").json()
        assert result["gamma_w_m2_k"] == 10
        assert client.get(result["dataset_url"]).json() == {"gamma": 10}
        assert client.get(f"/api/results/{run_id}/frames/0000.bin").content == b"frame"
        assert client.get(f"/api/results/{run_id}/request.toml").status_code == 404
        assert client.get(f"/api/results/{run_id}/frames/0024.bin").status_code == 404
        second = client.post("/api/run", json={"gamma_w_m2_k": 20})
        assert second.status_code == 202
        assert second.json()["run_id"] != run_id
        assert finished(client, second.json()["run_id"])["status"] == "completed"
    assert calls[0][0] != calls[1][0]
    assert [c[1] for c in calls] == [10, 20]


def test_failed_run_reports_error_and_missing_inputs(tmp_path):
    def fail(*args):
        raise RuntimeError("Controlled solver failure")

    with TestClient(create_app(tmp_path, fail)) as client:
        run_id = client.post("/api/run", json={"gamma_w_m2_k": 10}).json()["run_id"]
        state = finished(client, run_id)
        assert (
            state["status"] == "failed"
            and "Controlled solver failure" in state["error"]
        )
        assert client.get(f"/api/results/{run_id}").status_code == 409
        assert client.post("/api/run", json={"gamma_w_m2_k": 0}).status_code == 202
    with TestClient(create_app(tmp_path)) as client:
        run_id = client.post("/api/run", json={"gamma_w_m2_k": 10}).json()["run_id"]
        assert "Missing required local inputs" in finished(client, run_id)["error"]


def test_configuration_exposes_only_gamma_and_preserves_precise_default(tmp_path):
    (tmp_path / "configs").mkdir()
    template = Path(__file__).resolve().parents[1] / "configs/interactive_damping.toml"
    (tmp_path / "configs/interactive_damping.toml").write_text(template.read_text())
    folder = tmp_path / "runs/interactive_damping/test"
    default = tomllib.loads(request_configuration(tmp_path, folder, DEFAULT_GAMMA))
    selected = tomllib.loads(request_configuration(tmp_path, folder, 10))
    assert default["surface_damping"]["gamma_w_m2_k"] == DEFAULT_GAMMA
    assert selected["surface_damping"]["gamma_w_m2_k"] == 10
    selected["surface_damping"]["gamma_w_m2_k"] = DEFAULT_GAMMA
    assert default == selected
    assert default["experiment"]["start_month"] == "1979-01"
    assert default["experiment"]["end_month"] == "1980-12"
    assert default["mixed_layer_depth"]["variant"] == "era5_bilinear"
    assert default["parameters"] == {
        "rho_kg_m3": 1025.0,
        "cp_j_kg_k": 3990.0,
        "kappa_m2_s": 1000.0,
    }
    assert all(default["physics"].values())
