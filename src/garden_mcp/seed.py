"""Load plantings and observations from a JSON file into the log.

Format:
{
  "plantings": [{"plant_name": "...", "latitude": ..., "longitude": ...,
                 "planted_on": "YYYY-MM-DD", "variety": "...", "notes": "..."}],
  "observations": [{"planting_index": 0, "observed_on": "YYYY-MM-DD", "note": "..."}]
}
`planting_index` refers to the position of the planting in the same file.
"""
from __future__ import annotations

import argparse
import json

from .db import DEFAULT_DB_PATH, GardenDB
from .schemas import ObservationCreate, PlantingCreate


def seed(db: GardenDB, data: dict) -> dict:
    ids = []
    for raw in data.get("plantings", []):
        ids.append(db.add_planting(PlantingCreate(**raw)).id)
    for raw in data.get("observations", []):
        raw = dict(raw)
        idx = raw.pop("planting_index")
        db.add_observation(ObservationCreate(planting_id=ids[idx], **raw))
    return {"plantings_added": len(ids),
            "observations_added": len(data.get("observations", []))}


def main() -> None:
    parser = argparse.ArgumentParser(prog="garden-seed")
    parser.add_argument("json_path")
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    with open(args.json_path) as fh:
        data = json.load(fh)
    db = GardenDB(args.db)
    try:
        print(seed(db, data))
    finally:
        db.close()


if __name__ == "__main__":
    main()
