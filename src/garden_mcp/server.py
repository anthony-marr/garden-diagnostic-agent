"""MCP server exposing the garden tools.

Run over stdio (what MCP hosts like Claude Desktop use):

    python -m garden_mcp.server

Every tool validates its arguments with pydantic before touching the database
or the network, and returns a validated model serialized to JSON.
"""
from __future__ import annotations

import os
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from . import crops, diagnostics
from .db import DEFAULT_DB_PATH, GardenDB, PlantingNotFoundError
from .schemas import (Diagnosis, ObservationCreate, PlantingCreate)
from .weather import OpenMeteoClient

Lat = Annotated[float, Field(ge=-90, le=90, description="Latitude in decimal degrees")]
Lon = Annotated[float, Field(ge=-180, le=180, description="Longitude in decimal degrees")]


def create_server(db_path: Optional[str] = None,
                  weather_client: Optional[OpenMeteoClient] = None) -> FastMCP:
    db = GardenDB(db_path or DEFAULT_DB_PATH)
    weather = weather_client or OpenMeteoClient()

    mcp = FastMCP(
        "garden-diagnostic",
        instructions=(
            "Garden diagnostic tools: log plantings and observations, look up "
            "Open-Meteo weather, and diagnose plant stress from recent weather."
        ),
    )

    @mcp.tool()
    def log_planting(
        plant_name: Annotated[str, Field(min_length=1, description="Common name, e.g. 'tomato'")],
        latitude: Lat,
        longitude: Lon,
        planted_on: Optional[Annotated[str, Field(description="ISO date, YYYY-MM-DD")]] = None,
        variety: Optional[str] = None,
        notes: str = "",
    ) -> dict:
        """Record a planting in the garden log and return the stored row."""
        payload = PlantingCreate(plant_name=plant_name, variety=variety,
                                 latitude=latitude, longitude=longitude,
                                 planted_on=planted_on, notes=notes)
        return db.add_planting(payload).model_dump()

    @mcp.tool()
    def list_plantings() -> list[dict]:
        """List every planting in the garden log."""
        return [p.model_dump() for p in db.list_plantings()]

    @mcp.tool()
    def log_observation(
        planting_id: Annotated[int, Field(ge=1)],
        note: Annotated[str, Field(min_length=1, description="Free-text field note")],
        observed_on: Optional[str] = None,
    ) -> dict:
        """Attach a dated observation (e.g. 'leaves curling') to a planting."""
        payload = ObservationCreate(planting_id=planting_id, note=note, observed_on=observed_on)
        return db.add_observation(payload).model_dump()

    @mcp.tool()
    def list_observations(planting_id: Optional[int] = None) -> list[dict]:
        """List observations, optionally filtered to one planting."""
        return [o.model_dump() for o in db.list_observations(planting_id)]

    @mcp.tool()
    def get_weather(
        latitude: Lat,
        longitude: Lon,
        past_days: Annotated[int, Field(ge=0, le=92)] = 7,
        forecast_days: Annotated[int, Field(ge=1, le=16)] = 7,
    ) -> dict:
        """Fetch daily weather (past and forecast) from Open-Meteo for a location."""
        return weather.get_daily(latitude, longitude, past_days, forecast_days).model_dump()

    @mcp.tool()
    def diagnose_planting(
        planting_id: Annotated[int, Field(ge=1)],
        past_days: Annotated[int, Field(ge=3, le=92)] = 7,
    ) -> dict:
        """Diagnose one planting: pulls its coordinates from the log, fetches
        recent and forecast weather, and flags frost / heat / water / wind stress."""
        try:
            planting = db.get_planting(planting_id)
        except PlantingNotFoundError as exc:
            raise ValueError(str(exc))
        report = weather.get_daily(planting.latitude, planting.longitude,
                                   past_days=past_days, forecast_days=3)
        profile = crops.profile_for(planting.plant_name)
        flags, recommendations = diagnostics.assess(report.past, report.forecast, profile)
        return Diagnosis(
            planting_id=planting.id,
            plant_name=planting.plant_name,
            flags=flags,
            summary=diagnostics.summarize(flags, planting.plant_name),
            recommendations=recommendations,
        ).model_dump()

    return mcp


def main() -> None:
    create_server(os.environ.get("GARDEN_DB_PATH") or None).run()


if __name__ == "__main__":
    main()
