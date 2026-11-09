import pytest

from garden_mcp.db import GardenDB, PlantingNotFoundError
from garden_mcp.schemas import ObservationCreate, PlantingCreate


def make_planting(**overrides):
    base = dict(plant_name="basil", variety=None, latitude=38.9,
                longitude=-77.03, planted_on="2026-05-01", notes="")
    base.update(overrides)
    return PlantingCreate(**base)


def test_add_and_get_planting(db):
    created = db.add_planting(make_planting())
    assert created.id == 1
    fetched = db.get_planting(created.id)
    assert fetched.plant_name == "basil"
    assert fetched.planted_on == "2026-05-01"


def test_get_missing_planting_raises(db):
    with pytest.raises(PlantingNotFoundError):
        db.get_planting(999)


def test_list_plantings_ordered(db):
    db.add_planting(make_planting(plant_name="tomato"))
    db.add_planting(make_planting(plant_name="basil"))
    names = [p.plant_name for p in db.list_plantings()]
    assert names == ["tomato", "basil"]


def test_observations_round_trip(db):
    planting = db.add_planting(make_planting())
    obs = db.add_observation(ObservationCreate(
        planting_id=planting.id, note="leaves curling", observed_on="2026-06-01"))
    assert obs.observed_on == "2026-06-01"
    listed = db.list_observations(planting.id)
    assert [o.note for o in listed] == ["leaves curling"]
    assert db.list_observations(planting.id + 1) == []


def test_observation_defaults_to_today(db):
    import datetime as dt
    planting = db.add_planting(make_planting())
    obs = db.add_observation(ObservationCreate(planting_id=planting.id, note="check"))
    assert obs.observed_on == dt.date.today().isoformat()


def test_observation_requires_existing_planting(db):
    with pytest.raises(PlantingNotFoundError):
        db.add_observation(ObservationCreate(planting_id=42, note="orphan"))


def test_rows_persist_across_connections(tmp_path):
    path = tmp_path / "persist.db"
    first = GardenDB(path)
    first.add_planting(make_planting(plant_name="pepper"))
    first.close()
    second = GardenDB(path)
    assert [p.plant_name for p in second.list_plantings()] == ["pepper"]
    second.close()


def test_planting_date_optional(db):
    created = db.add_planting(PlantingCreate(
        plant_name="dill", latitude=38.92, longitude=-77.03))
    assert created.planted_on is None
