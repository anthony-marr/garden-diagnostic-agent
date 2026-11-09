"""Open-Meteo client. Open-Meteo is free and needs no API key."""
from __future__ import annotations

import httpx

from .schemas import Coordinates, DailyWeather, WeatherReport

DAILY_VARIABLES = (
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "et0_fao_evapotranspiration",
    "wind_speed_10m_max",
)


class OpenMeteoError(RuntimeError):
    pass


class OpenMeteoClient:
    def __init__(self, base_url: str = "https://api.open-meteo.com/v1",
                 transport: httpx.BaseTransport | None = None, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def _new_client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=self._timeout)

    def get_daily(self, latitude: float, longitude: float,
                  past_days: int = 7, forecast_days: int = 7) -> WeatherReport:
        coords = Coordinates(latitude=latitude, longitude=longitude)
        if not 0 <= past_days <= 92:
            raise ValueError("past_days must be between 0 and 92")
        if not 1 <= forecast_days <= 16:
            raise ValueError("forecast_days must be between 1 and 16")
        params = {
            "latitude": coords.latitude,
            "longitude": coords.longitude,
            "daily": ",".join(DAILY_VARIABLES),
            "past_days": past_days,
            "forecast_days": forecast_days,
            "timezone": "auto",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
        }
        with self._new_client() as client:
            resp = client.get(f"{self.base_url}/forecast", params=params)
        if resp.status_code != 200:
            raise OpenMeteoError(
                f"Open-Meteo returned HTTP {resp.status_code}: {resp.text[:200]}"
            )
        data = resp.json()
        daily = data.get("daily")
        if not daily or "time" not in daily:
            raise OpenMeteoError("Open-Meteo response missing daily data")

        days: list[DailyWeather] = []
        for i, day in enumerate(daily["time"]):
            days.append(DailyWeather(
                date=day,
                temp_max_c=_at(daily.get("temperature_2m_max"), i),
                temp_min_c=_at(daily.get("temperature_2m_min"), i),
                precipitation_mm=_at(daily.get("precipitation_sum"), i) or 0.0,
                precipitation_probability_pct=_at(daily.get("precipitation_probability_max"), i),
                et0_mm=_at(daily.get("et0_fao_evapotranspiration"), i),
                wind_max_kmh=_at(daily.get("wind_speed_10m_max"), i),
            ))
        return WeatherReport(
            latitude=coords.latitude,
            longitude=coords.longitude,
            timezone=data.get("timezone", ""),
            past=days[:past_days],
            forecast=days[past_days:],
        )


def _at(series, i):
    if not series or i >= len(series):
        return None
    return series[i]
