import datetime as dt

import pytest
from pydantic import ValidationError

from conftest import build_openmeteo_payload, make_client
from garden_mcp.weather import OpenMeteoError


def test_get_daily_splits_past_and_forecast():
    client = make_client(past_days=7, forecast_days=5)
    report = client.get_daily(38.9, -77.03, past_days=7, forecast_days=5)
    assert len(report.past) == 7
    assert len(report.forecast) == 5
    assert report.timezone == "America/New_York"
    assert report.past[-1].date == (dt.date.today() - dt.timedelta(days=1)).isoformat()
    assert report.forecast[0].date == dt.date.today().isoformat()


def test_values_are_parsed():
    client = make_client(temp_max=31.5, precip=4.2, et0=5.5, wind=33.0)
    report = client.get_daily(38.9, -77.03)
    day = report.past[0]
    assert day.temp_max_c == 31.5
    assert day.precipitation_mm == 4.2
    assert day.et0_mm == 5.5
    assert day.wind_max_kmh == 33.0


def test_missing_series_values_become_none():
    payload = build_openmeteo_payload()
    payload["daily"]["et0_fao_evapotranspiration"] = []
    client = make_client(payload=payload)
    report = client.get_daily(38.9, -77.03)
    assert all(d.et0_mm is None for d in report.past)


def test_http_error_raises():
    client = make_client(payload={"error": True}, status=500)
    with pytest.raises(OpenMeteoError):
        client.get_daily(38.9, -77.03)


def test_response_without_daily_raises():
    client = make_client(payload={"latitude": 38.9})
    with pytest.raises(OpenMeteoError):
        client.get_daily(38.9, -77.03)


def test_invalid_coordinates_rejected():
    client = make_client()
    with pytest.raises(ValidationError):
        client.get_daily(123.0, -77.03)
    with pytest.raises(ValidationError):
        client.get_daily(38.9, -999.0)


def test_invalid_windows_rejected():
    client = make_client()
    with pytest.raises(ValueError):
        client.get_daily(38.9, -77.03, past_days=200)
    with pytest.raises(ValueError):
        client.get_daily(38.9, -77.03, forecast_days=0)
