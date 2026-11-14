"""Guard the weather request contract without making network calls."""

import httpx
import pytest

from conftest import build_openmeteo_payload
from garden_mcp.weather import DAILY_VARIABLES, OpenMeteoClient


@pytest.mark.parametrize("past_days,forecast_days", [(0, 1), (0, 16), (92, 1)])
def test_request_uses_explicit_units_and_supports_window_boundaries(
    past_days, forecast_days,
):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200, json=build_openmeteo_payload(past_days, forecast_days),
        )

    client = OpenMeteoClient(transport=httpx.MockTransport(handler))
    report = client.get_daily(38.9, -77.03, past_days, forecast_days)

    assert len(requests) == 1
    params = requests[0].url.params
    assert params["latitude"] == "38.9"
    assert params["longitude"] == "-77.03"
    assert params["daily"].split(",") == list(DAILY_VARIABLES)
    assert params["past_days"] == str(past_days)
    assert params["forecast_days"] == str(forecast_days)
    assert params["timezone"] == "auto"
    assert params["wind_speed_unit"] == "kmh"
    assert params["precipitation_unit"] == "mm"
    assert len(report.past) == past_days
    assert len(report.forecast) == forecast_days


@pytest.mark.parametrize("window", [
    {"past_days": -1},
    {"past_days": 93},
    {"forecast_days": 0},
    {"forecast_days": 17},
])
def test_invalid_window_is_rejected_before_any_http_request(window):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=build_openmeteo_payload())

    client = OpenMeteoClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="must be between"):
        client.get_daily(38.9, -77.03, **window)
    assert requests == []
