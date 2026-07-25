from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import Settings
from .db import Database
from .makemkv import (
    DriveInfo,
    MakeMKVBackend,
    RipperBackend,
    SimulationBackend,
)
from .service import RipperService


class MetadataUpdate(BaseModel):
    media_type: str = Field(pattern="^(movie|tv)$")
    title: str = Field(min_length=1, max_length=180)
    year: int | None = Field(default=None, ge=1888, le=2200)
    season: int | None = Field(default=None, ge=0, le=999)
    episode_start: int | None = Field(default=None, ge=0, le=9999)
    edition: str = Field(default="", max_length=120)
    selected_title_ids: list[int] | None = None


class FirmwareFlashRequest(BaseModel):
    confirmation: str


def create_app(
    settings: Settings | None = None,
    backend: RipperBackend | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    database = Database(settings.database_url)
    if backend is None:
        backend = SimulationBackend() if settings.simulate else MakeMKVBackend(settings.makemkv_bin)
    service = RipperService(settings, database, backend)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await service.start()
        yield
        await service.stop()

    app = FastAPI(
        title="Disc Goblin",
        description="Automatic MakeMKV ingest for Plex and Jellyfin libraries",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.database = database
    app.state.service = service

    static_root = Path(__file__).parent / "static"
    app.mount("/assets", StaticFiles(directory=static_root), name="assets")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(static_root / "index.html")

    @app.get("/healthz")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "simulation": settings.simulate,
            "library_root": str(settings.library_root),
            "movie_root": str(settings.movie_root),
            "tv_root": str(settings.tv_root),
            "database": "postgresql"
            if settings.database_url.startswith("postgresql")
            else "sqlite",
            "database_ready": database.ping(),
            "discovery": "udev+makemkv" if settings.udev_discovery else "makemkv-polling",
        }

    @app.get("/api/overview")
    async def overview() -> dict[str, Any]:
        return database.overview()

    @app.get("/api/jobs/{job_id}")
    async def job_detail(job_id: str) -> dict[str, Any]:
        job = database.job_detail(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        return job

    @app.post("/api/jobs/{job_id}/metadata")
    async def update_metadata(job_id: str, payload: MetadataUpdate) -> dict[str, Any]:
        if not database.job_detail(job_id):
            raise HTTPException(404, "Job not found")
        try:
            return await service.update_metadata(job_id, **payload.model_dump())
        except (ValueError, FileExistsError, FileNotFoundError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/jobs/{job_id}/retry", status_code=202)
    async def retry(job_id: str) -> dict[str, str]:
        try:
            await service.retry_job(job_id)
        except KeyError as exc:
            raise HTTPException(404, "Job not found") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"status": "queued"}

    @app.post("/api/jobs/{job_id}/cancel", status_code=202)
    async def cancel(job_id: str) -> dict[str, str]:
        try:
            await service.cancel_job(job_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"status": "cancelling"}

    @app.post("/api/drives/{drive_id}/rip", status_code=202)
    async def rip_drive(drive_id: str) -> dict[str, str]:
        row = database.fetchone("SELECT * FROM drives WHERE id=?", (drive_id,))
        if not row:
            raise HTTPException(404, "Drive not found")
        if not row["disc_name"]:
            raise HTTPException(409, "There is no disc in this drive")
        drive = DriveInfo(
            id=row["id"],
            disc_index=row["disc_index"],
            name=row["name"],
            device=row["device"],
            disc_name=row["disc_name"],
            state=row["state"],
            status_text=row["status_text"],
        )
        return {"job_id": service.queue_drive(drive)}

    @app.post("/api/drives/{drive_id}/eject", status_code=202)
    async def eject_drive(drive_id: str) -> dict[str, str]:
        try:
            await service.eject_drive(drive_id)
        except KeyError as exc:
            raise HTTPException(404, "Drive not found") from exc
        return {"status": "ejected"}

    @app.post("/api/drives/{drive_id}/firmware/audit")
    async def audit_firmware(drive_id: str) -> dict[str, Any]:
        try:
            return await service.audit_drive(drive_id)
        except KeyError as exc:
            raise HTTPException(404, "Drive not found") from exc

    @app.post("/api/drives/{drive_id}/firmware/flash")
    async def flash_firmware(drive_id: str, payload: FirmwareFlashRequest) -> dict[str, Any]:
        expected = f"FLASH {drive_id}"
        if payload.confirmation != expected:
            raise HTTPException(400, f"Confirmation must exactly match: {expected}")
        try:
            return await service.flash_drive(drive_id, automatic=False)
        except KeyError as exc:
            raise HTTPException(404, "Drive not found") from exc
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/poll", status_code=202)
    async def poll_now(
        _: Annotated[dict[str, Any] | None, Body()] = None,
    ) -> dict[str, str]:
        await service.poll_once()
        return {"status": "complete"}

    @app.websocket("/api/ws")
    async def websocket(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            async for snapshot in service.subscribe():
                await websocket.send_json(snapshot)
        except WebSocketDisconnect:
            return

    return app
