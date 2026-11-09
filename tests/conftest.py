import datetime as dt
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from garden_mcp.db import GardenDB  # noqa: E402
from garden_mcp.weather import OpenMeteoClient  # noqa: E402


def build_openmeteo_payload(past_days=7, forecast_days=7, *, temp_max=24.0,
                            temp_min=12.0, precip=3.0, precip_prob=20.0,
                            et0=3.5, wind=12.0):
    today = dt.date.today()
    dates = [today - dt.timedelta(days=past_days - i) for i in range(past_days)]
    dates += [today + dt.timedelta(days=i) for i in range(forecast_days)]

    def series(value):
        if isinstance(value, list):
            assert len(value) == len(dates)
            return value
        return [value] * len(dates)

    return {
        "latitude": 38.9,
        "longitude": -77.03,
        "timezone": "America/New_York",
        "daily": {
            "time": [d.isoformat() for d in dates],
            "temperature_2m_max": series(temp_max),
            "temperature_2m_min": series(temp_min),
            "precipitation_sum": series(precip),
            "precipitation_probability_max": series(precip_prob),
            "et0_fao_evapotranspiration": series(et0),
            "wind_speed_10m_max": series(wind),
        },
    }


def make_client(payload=None, status=200, past_days=7, forecast_days=7, **kwargs):
    body = payload if payload is not None else build_openmeteo_payload(
        past_days=past_days, forecast_days=forecast_days, **kwargs)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.open-meteo.com"
        assert request.url.path == "/v1/forecast"
        return httpx.Response(status, content=json.dumps(body).encode())

    return OpenMeteoClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def db(tmp_path):
    database = GardenDB(tmp_path / "test.db")
    yield database
    database.close()


@pytest.fixture
def wx():
    return make_client()


@pytest.fixture
def sample_planting(db):
    from garden_mcp.schemas import PlantingCreate
    return db.add_planting(PlantingCreate(
        plant_name="tomato", variety="Roma",
        latitude=38.9072, longitude=-77.0369, planted_on="2026-04-15"))
