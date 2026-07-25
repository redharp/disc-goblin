from pathlib import Path

from disc_goblin.db import Database


def test_overview_round_trip(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'disc-goblin.db'}")
    database.initialize()
    database.upsert_drive(
        {
            "id": "drive-1",
            "disc_index": 0,
            "name": "Pioneer",
            "device": "/dev/sr0",
            "disc_name": "MOVIE_2026",
            "state": "ready",
            "status_text": "Disc ready",
        }
    )
    database.create_job(
        {
            "id": "job-1",
            "drive_id": "drive-1",
            "disc_name": "MOVIE_2026",
            "fingerprint": "abc",
            "title": "Movie",
            "year": 2026,
            "status": "needs_review",
        }
    )
    overview = database.overview()
    assert overview["drives"][0]["name"] == "Pioneer"
    assert overview["active_jobs"][0]["id"] == "job-1"
    assert overview["totals"]["all_jobs"] == 1
