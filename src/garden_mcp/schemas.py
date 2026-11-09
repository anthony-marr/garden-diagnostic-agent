"""Pydantic models that define the checked I/O boundary for every tool."""
from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


def _iso_date(value: object) -> str:
    if isinstance(value, dt.datetime):
        raise ValueError("expected a date (YYYY-MM-DD), got a datetime")
    if isinstance(value, dt.date):
        return value.isoformat()
    text = str(value)
    for parser in (dt.date.fromisoformat,
                   lambda s: dt.datetime.strptime(s, "%Y-%m-%d").date()):
        try:
            return parser(text).isoformat()
        except ValueError:
            continue
    raise ValueError(f"expected ISO date (YYYY-MM-DD), got {value!r}")


class Coordinates(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class PlantingCreate(BaseModel):
    plant_name: str = Field(min_length=1, max_length=120)
    variety: Optional[str] = Field(default=None, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    planted_on: str
    notes: str = ""

    @field_validator("planted_on")
    @classmethod
    def _check_planted_on(cls, v: str) -> str:
        return _iso_date(v)


class Planting(PlantingCreate):
    id: int


class ObservationCreate(BaseModel):
    planting_id: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=2000)
    observed_on: Optional[str] = None

    @field_validator("observed_on")
    @classmethod
    def _check_observed_on(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else _iso_date(v)


class Observation(BaseModel):
    id: int
    planting_id: int
    observed_on: str
    note: str


class DailyWeather(BaseModel):
    date: str
    temp_max_c: Optional[float] = None
    temp_min_c: Optional[float] = None
    precipitation_mm: float = 0.0
    precipitation_probability_pct: Optional[float] = None
    et0_mm: Optional[float] = None
    wind_max_kmh: Optional[float] = None


class WeatherReport(BaseModel):
    latitude: float
    longitude: float
    timezone: str = ""
    past: list[DailyWeather] = []
    forecast: list[DailyWeather] = []


class StressKind(str, Enum):
    FROST = "frost"
    HEAT = "heat"
    DRY = "dry"
    EXCESS_WATER = "excess_water"
    WIND = "wind"


class Severity(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class StressFlag(BaseModel):
    kind: StressKind
    severity: Severity
    detail: str


class Diagnosis(BaseModel):
    planting_id: int
    plant_name: str
    flags: list[StressFlag] = []
    summary: str
    recommendations: list[str] = []


class GardenCheckReport(BaseModel):
    checked_plantings: int
    diagnoses: list[Diagnosis] = []
    summary: str
