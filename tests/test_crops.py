"""Per-crop profile tests: keyword matching, and how the same weather window
produces different flags for different crops."""
import asyncio

from mcp.shared.memory import create_connected_server_and_client_session

from conftest import build_openmeteo_payload, make_client
from garden_mcp.crops import DEFAULT_PROFILE, profile_for
from garden_mcp.diagnostics import assess
from garden_mcp.schemas import DailyWeather, PlantingCreate, StressKind
from garden_mcp.server import create_server
from garden_mcp.db import GardenDB


def assess_payload(profile, **kwargs):
    payload = build_openmeteo_payload(**kwargs)
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
    return assess(days[:7], days[7:], profile)


def kinds(flags):
    return {f.kind for f in flags}


def test_profile_matches_garden_log_names():
    assert profile_for("lettuce (green leaf)").kc == 1.00
    assert profile_for("tomato").kc == 1.15
    assert profile_for("cucumber/squash (cucurbit)").heat_c == 35.0
    assert profile_for("radish").kc == 0.85


def test_unknown_crop_gets_default_profile():
    assert profile_for("zz plant") == DEFAULT_PROFILE


def test_tender_crop_flags_light_frost_hardy_crop_does_not():
    tomato_flags, _ = assess_payload(profile_for("tomato"), temp_min=1.0)
    assert StressKind.FROST in kinds(tomato_flags)
    kale_flags, _ = assess_payload(profile_for("kale"), temp_min=1.0)
    assert StressKind.FROST not in kinds(kale_flags)


def test_hardy_crop_flags_only_hard_frost():
    kale_flags, _ = assess_payload(profile_for("kale"), temp_min=-3.0)
    frost = next(f for f in kale_flags if f.kind == StressKind.FROST)
    assert frost.severity.value == "high"
    assert "-2C" in frost.detail


def test_heat_threshold_differs_by_crop():
    # 30C sustained: bolting weather for lettuce, fine for a tomato.
    lettuce_flags, _ = assess_payload(profile_for("lettuce"), temp_max=30.0)
    assert StressKind.HEAT in kinds(lettuce_flags)
    tomato_flags, _ = assess_payload(profile_for("tomato"), temp_max=30.0)
    assert StressKind.HEAT not in kinds(tomato_flags)


def test_water_demand_scaled_by_crop_coefficient():
    # 1.9 mm rain against 3.5 mm ET0 x 7 days: 54% of demand for a Kc 1.0
    # crop (no flag) but 47% for a tomato at Kc 1.15 (moderate dry flag).
    lettuce_flags, _ = assess_payload(profile_for("lettuce"), precip=1.9, et0=3.5)
    assert StressKind.DRY not in kinds(lettuce_flags)
    tomato_flags, _ = assess_payload(profile_for("tomato"), precip=1.9, et0=3.5)
    dry = next(f for f in tomato_flags if f.kind == StressKind.DRY)
    assert dry.severity.value == "moderate"
    assert "Kc 1.15" in dry.detail


def test_default_profile_keeps_generic_thresholds():
    flags, _ = assess_payload(DEFAULT_PROFILE, temp_min=1.5)
    frost = next(f for f in flags if f.kind == StressKind.FROST)
    assert frost.severity.value == "moderate"


def test_server_diagnoses_with_crop_profile(tmp_path):
    from garden_mcp.agent import _payload

    db_path = str(tmp_path / "srv.db")
    db = GardenDB(db_path)
    tomato = db.add_planting(PlantingCreate(
        plant_name="tomato", latitude=38.9, longitude=-77.0))
    kale = db.add_planting(PlantingCreate(
        plant_name="kale", latitude=38.9, longitude=-77.0))
    db.close()
    server = create_server(db_path=db_path, weather_client=make_client(temp_min=1.0))

    async def go():
        async with create_connected_server_and_client_session(server._mcp_server) as s:
            await s.initialize()
            t = _payload(await s.call_tool("diagnose_planting", {"planting_id": tomato.id}))
            k = _payload(await s.call_tool("diagnose_planting", {"planting_id": kale.id}))
            return t, k

    tomato_diag, kale_diag = asyncio.run(go())
    assert any(f["kind"] == "frost" for f in tomato_diag["flags"])
    assert not any(f["kind"] == "frost" for f in kale_diag["flags"])
