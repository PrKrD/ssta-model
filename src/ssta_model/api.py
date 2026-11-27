"""Single-process local API for one fixed damping experiment at a time."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask

from ssta_model.interactive import execute_run
from ssta_model.interactive_storage import (
    RUN_ID,
    completed_runs,
    discard_failed_products,
    prune_completed,
    write_state,
)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gamma_w_m2_k: float = Field(strict=True, ge=0, le=40, allow_inf_nan=False)


def create_app(root=None, execute=execute_run):
    root = Path(root or Path(__file__).resolve().parents[2]).resolve()
    base = root / "runs/interactive_damping"
    records = {folder.name: state for _, folder, state in completed_runs(base)}
    serving = {}
    lock = Lock()
    active = None

    @asynccontextmanager
    async def lifespan(app):
        with ThreadPoolExecutor(max_workers=1) as executor:
            app.state.executor = executor
            yield

    app = FastAPI(title="Local SST damping experiment", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request must contain only gamma_w_m2_k: a finite number from 0 to 40 W m-2 K-1."
            },
        )

    def cleanup():
        try:
            for expired in prune_completed(base, set(serving) | {active}):
                records.pop(expired, None)
        except OSError:
            logging.getLogger(__name__).exception(
                "Interactive retention cleanup failed"
            )

    def release(run_id):
        with lock:
            serving[run_id] -= 1
            if not serving[run_id]:
                del serving[run_id]
            cleanup()

    def persist(folder, run_id):
        write_state(
            folder, **{k: v for k, v in records[run_id].items() if k != "run_id"}
        )

    def record(run_id):
        with lock:
            if RUN_ID.fullmatch(run_id) and (base / ".expired" / run_id).is_file():
                raise HTTPException(
                    410, "Interactive run expired under the five-run retention policy."
                )
            if run_id not in records:
                raise HTTPException(
                    404,
                    "Unknown run ID; local run status resets when the API restarts.",
                )
            return dict(records[run_id])

    def work(run_id, folder, gamma):
        nonlocal active
        with lock:
            records[run_id]["status"] = "running"
        try:
            execute(root, folder, gamma)
            if not (folder / "display/manifest.json").is_file():
                raise RuntimeError("Simulation produced no display manifest")
        except Exception as error:
            try:
                discard_failed_products(folder)
            except OSError:
                logging.getLogger(__name__).exception(
                    "Failed-run product cleanup failed"
                )
            with lock:
                records[run_id].update(status="failed", error=str(error))
                try:
                    persist(folder, run_id)
                except OSError:
                    logging.getLogger(__name__).exception("Could not record failed run")
                active = None
        else:
            with lock:
                records[run_id].update(
                    status="completed", completed_at=datetime.now(UTC).isoformat()
                )
                try:
                    persist(folder, run_id)
                    cleanup()
                except OSError:
                    logging.getLogger(__name__).exception(
                        "Could not record completion/retention; results preserved"
                    )
                active = None

    @app.post("/api/run", status_code=202)
    async def run(body: RunRequest):
        nonlocal active
        with lock:
            if active is not None:
                raise HTTPException(
                    409,
                    "A simulation is already queued or running. Wait for it to finish.",
                )
            run_id = uuid4().hex
            folder = base / run_id
            folder.mkdir(parents=True, exist_ok=False)
            result = {
                "run_id": run_id,
                "gamma_w_m2_k": body.gamma_w_m2_k,
                "status": "queued",
                "error": None,
            }
            records[run_id] = dict(result)
            active = run_id
            app.state.executor.submit(work, run_id, folder, body.gamma_w_m2_k)
        return result

    @app.get("/api/status/{run_id}")
    async def status(run_id: str):
        return record(run_id)

    def completed(run_id):
        result = record(run_id)
        if result["status"] != "completed":
            raise HTTPException(409, result["error"] or f"Run is {result['status']}")
        return result

    @app.get("/api/results/{run_id}")
    async def results(run_id: str):
        return {
            **completed(run_id),
            "dataset_url": f"/api/results/{run_id}/manifest.json",
        }

    @app.get("/api/results/{run_id}/{asset:path}")
    async def asset(run_id: str, asset: str):
        if not re.fullmatch(r"manifest\.json|frames/[0-9]{4}\.bin", asset):
            raise HTTPException(404, "Unknown display asset")
        completed(run_id)
        with lock:
            # Recheck expiry under the deletion lock; pin through transmission.
            if (base / ".expired" / run_id).is_file():
                raise HTTPException(
                    410, "Interactive run expired under the five-run retention policy."
                )
            path = base / run_id / "display" / asset
            if not path.is_file():
                raise HTTPException(404, "Display asset missing")
            serving[run_id] = serving.get(run_id, 0) + 1
        return FileResponse(
            path,
            background=BackgroundTask(release, run_id),
            media_type="application/json"
            if asset == "manifest.json"
            else "application/octet-stream",
        )

    return app


app = create_app()
