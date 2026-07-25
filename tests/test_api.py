import json
from datetime import UTC, datetime

from disc_goblin.api import websocket_payload


def test_websocket_payload_serializes_database_datetimes() -> None:
    payload = websocket_payload(
        {
            "drives": [{"id": "drive-1", "updated_at": datetime(2026, 7, 25, tzinfo=UTC)}],
            "active_jobs": [],
            "history": [],
        }
    )

    assert payload["drives"][0]["updated_at"] == "2026-07-25T00:00:00+00:00"
    json.dumps(payload)
