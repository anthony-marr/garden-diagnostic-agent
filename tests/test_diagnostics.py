from conftest import build_openmeteo_payload
from garden_mcp.diagnostics import assess
from garden_mcp.schemas import StressKind, WeatherReport


def report_from_payload(payload):
    from garden_mcp.schemas import DailyWeather
    daily = payload["daily"]
    days = [DailyWeather(
        date=daily["time"][i],
        temp_max_c=daily["temperature_2m_max"][i],
        temp_min_c=daily["temperature_2m_min"][i],
        precipitation_mm=daily["precipitation_sum"][i],
        precipitation_probability_pct=daily["precipitation_probability_max"][i],
        et0_mm=daily["et0_fao_evapotranspiration"][i],
        wind_max_kmh=daily["wind_speed_10m_max"][i],
    ) for i in range(len(daily["time"]))]
    return WeatherReport(latitude=0, longitude=0, past=days[:7], forecast=days[7:])


def kinds(flags):
    return {f.kind for f in flags}


def test_healthy_conditions_no_flags():
    flags, recs = assess(*[getattr(report_from_payload(build_openmeteo_payload()), part)
                           for part in ("past", "forecast")])
    assert flags == []
    assert recs == ["No stress signals detected; keep monitoring soil moisture."]


def test_frost_flagged_high():
    payload = build_openmeteo_payload(temp_min=-2.0)
    r = report_from_payload(payload)
    flags, recs = assess(r.past, r.forecast)
    assert StressKind.FROST in kinds(flags)
    assert any("frost cloth" in r_ for r_ in recs)


def test_near_frost_flagged_moderate():
    payload = build_openmeteo_payload(temp_min=1.5)
    r = report_from_payload(payload)
    flags, _ = assess(r.past, r.forecast)
    frost = next(f for f in flags if f.kind == StressKind.FROST)
    assert frost.severity.value == "moderate"


def test_heat_flagged():
    payload = build_openmeteo_payload(temp_max=35.0)
    r = report_from_payload(payload)
    flags, _ = assess(r.past, r.forecast)
    assert StressKind.HEAT in kinds(flags)


def test_dry_flagged_when_rain_below_et0():
    payload = build_openmeteo_payload(precip=0.0, et0=4.0)
    r = report_from_payload(payload)
    flags, recs = assess(r.past, r.forecast)
    assert StressKind.DRY in kinds(flags)
    assert any("watering" in r_ for r_ in recs)


def test_excess_water_flagged():
    payload = build_openmeteo_payload(precip=20.0)
    r = report_from_payload(payload)
    flags, _ = assess(r.past, r.forecast)
    assert StressKind.EXCESS_WATER in kinds(flags)


def test_wind_flagged():
    payload = build_openmeteo_payload(wind=65.0)
    r = report_from_payload(payload)
    flags, _ = assess(r.past, r.forecast)
    wind = next(f for f in flags if f.kind == StressKind.WIND)
    assert wind.severity.value == "high"


def test_balanced_rain_not_dry():
    payload = build_openmeteo_payload(precip=3.0, et0=3.5)
    r = report_from_payload(payload)
    flags, _ = assess(r.past, r.forecast)
    assert StressKind.DRY not in kinds(flags)
