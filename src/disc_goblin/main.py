from __future__ import annotations

import uvicorn


def run() -> None:
    uvicorn.run(
        "disc_goblin.api:create_app",
        host="0.0.0.0",
        port=8080,
        factory=True,
        proxy_headers=True,
    )


if __name__ == "__main__":
    run()
