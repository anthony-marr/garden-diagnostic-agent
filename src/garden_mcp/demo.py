"""End-to-end demo: seeds sample garden data, then runs an agent garden check
against live Open-Meteo weather. Prints the report as JSON.

    python -m garden_mcp.demo
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session

from .agent import GardenAgent
from .db import GardenDB
from .seed import seed
from .server import create_server

SAMPLE = {
    "plantings": [
        {"plant_name": "tomato", "variety": "Roma",
         "latitude": 38.9072, "longitude": -77.0369,
         "planted_on": "2026-04-15", "notes": "raised bed, full sun"},
        {"plant_name": "basil", "variety": "Genovese",
         "latitude": 38.9072, "longitude": -77.0369,
         "planted_on": "2026-05-01", "notes": "container"},
        {"plant_name": "bell pepper",
         "latitude": 38.9072, "longitude": -77.0369,
         "planted_on": "2026-04-20"},
    ],
    "observations": [
        {"planting_index": 0, "observed_on": "2026-06-10",
         "note": "first flowers on the Roma vines"},
    ],
}


async def run() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "demo.db")
        db = GardenDB(db_path)
        seed(db, SAMPLE)
        db.close()
        server = create_server(db_path=db_path)
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            await session.initialize()
            agent = GardenAgent(session)
            report = await agent.garden_check()
            return report.model_dump()


def main() -> None:
    print(json.dumps(asyncio.run(run()), indent=2))


if __name__ == "__main__":
    main()
