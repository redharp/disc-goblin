import asyncio
from pathlib import Path

import pytest

from disc_goblin.config import Settings
from disc_goblin.db import Database
from disc_goblin.makemkv import SimulationBackend
from disc_goblin.service import RipperService


@pytest.mark.asyncio
async def test_simulated_disc_rips_then_waits_for_safe_publish(tmp_path: Path) -> None:
    settings = Settings(
        library_root=tmp_path / "library",
        movie_root=tmp_path / "library" / "Movies",
        tv_root=tmp_path / "library" / "TV",
        database_url=f"sqlite:///{tmp_path / 'service.db'}",
        poll_interval=999,
        eject_on_success=False,
        udev_discovery=False,
        firmware_audit=True,
        simulate=True,
    )
    database = Database(settings.database_url)
    database.initialize()
    settings.library_root.mkdir(parents=True)
    settings.staging_root.mkdir(parents=True)
    service = RipperService(settings, database, SimulationBackend())

    await service.poll_once()
    running = list(service._tasks.values())
    await asyncio.gather(*running)

    overview = database.overview()
    assert len(overview["active_jobs"]) == 1
    job = overview["active_jobs"][0]
    assert job["status"] == "needs_review"
    detail = database.job_detail(job["id"])
    assert detail is not None
    selected = [title["id"] for title in detail["titles"] if title["selected"]]

    published = await service.update_metadata(
        job["id"],
        media_type="movie",
        title="Dune Part Two",
        year=2024,
        season=None,
        episode_start=None,
        edition="",
        selected_title_ids=selected,
    )
    assert published["status"] == "complete"
    destination = settings.movie_root / "Dune Part Two (2024)" / "Dune Part Two (2024).mkv"
    assert destination.is_file()
