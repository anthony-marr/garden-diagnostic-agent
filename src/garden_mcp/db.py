"""SQLite-backed planting log."""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
from pathlib import Path
from typing import Optional

from .schemas import Observation, ObservationCreate, Planting, PlantingCreate

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plantings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_name TEXT NOT NULL,
    variety TEXT,
    latitude REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    planted_on TEXT,
    notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    planting_id INTEGER NOT NULL REFERENCES plantings (id) ON DELETE CASCADE,
    observed_on TEXT NOT NULL,
    note TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_observations_planting ON observations (planting_id);
"""

DEFAULT_DB_PATH = os.environ.get("GARDEN_DB_PATH", "garden.db")


class PlantingNotFoundError(KeyError):
    pass


class GardenDB:
    """Thin repository over the planting log. All writes/reads go through
    the pydantic models in schemas.py, so rows are validated both ways."""

    def __init__(self, path: str | os.PathLike = DEFAULT_DB_PATH):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def add_planting(self, data: PlantingCreate) -> Planting:
        cur = self._conn.execute(
            "INSERT INTO plantings (plant_name, variety, latitude, longitude, planted_on, notes)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (data.plant_name, data.variety, data.latitude, data.longitude,
             data.planted_on, data.notes),
        )
        self._conn.commit()
        return self.get_planting(cur.lastrowid)

    def get_planting(self, planting_id: int) -> Planting:
        row = self._conn.execute(
            "SELECT * FROM plantings WHERE id = ?", (planting_id,)
        ).fetchone()
        if row is None:
            raise PlantingNotFoundError(f"no planting with id {planting_id}")
        return Planting(**dict(row))

    def list_plantings(self) -> list[Planting]:
        rows = self._conn.execute("SELECT * FROM plantings ORDER BY id").fetchall()
        return [Planting(**dict(r)) for r in rows]

    def add_observation(self, data: ObservationCreate) -> Observation:
        self.get_planting(data.planting_id)  # raises if missing
        observed_on = data.observed_on or dt.date.today().isoformat()
        cur = self._conn.execute(
            "INSERT INTO observations (planting_id, observed_on, note) VALUES (?, ?, ?)",
            (data.planting_id, observed_on, data.note),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM observations WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return Observation(**dict(row))

    def list_observations(self, planting_id: Optional[int] = None) -> list[Observation]:
        if planting_id is None:
            rows = self._conn.execute(
                "SELECT * FROM observations ORDER BY observed_on, id"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM observations WHERE planting_id = ? ORDER BY observed_on, id",
                (planting_id,),
            ).fetchall()
        return [Observation(**dict(r)) for r in rows]
