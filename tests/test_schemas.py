import pytest
from pydantic import ValidationError

from garden_mcp.schemas import ObservationCreate, PlantingCreate


def test_planting_rejects_bad_date():
    with pytest.raises(ValidationError):
        PlantingCreate(plant_name="tomato", latitude=0, longitude=0,
                       planted_on="April 15th")


def test_planting_normalizes_date():
    p = PlantingCreate(plant_name="tomato", latitude=0, longitude=0,
                       planted_on="2026-4-5")
    assert p.planted_on == "2026-04-05"


def test_planting_rejects_out_of_range_coordinates():
    with pytest.raises(ValidationError):
        PlantingCreate(plant_name="tomato", latitude=91, longitude=0,
                       planted_on="2026-04-05")
    with pytest.raises(ValidationError):
        PlantingCreate(plant_name="tomato", latitude=0, longitude=-181,
                       planted_on="2026-04-05")


def test_planting_rejects_empty_name():
    with pytest.raises(ValidationError):
        PlantingCreate(plant_name="", latitude=0, longitude=0, planted_on="2026-04-05")


def test_observation_validates_optional_date():
    assert ObservationCreate(planting_id=1, note="ok").observed_on is None
    assert ObservationCreate(planting_id=1, note="ok",
                             observed_on="2026-6-1").observed_on == "2026-06-01"
    with pytest.raises(ValidationError):
        ObservationCreate(planting_id=1, note="ok", observed_on="next tuesday")
