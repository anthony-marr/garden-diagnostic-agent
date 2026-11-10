"""Per-crop stress profiles.

The rules in diagnostics.py are generic; crops differ in how much water they
use, what counts as heat stress, and how much cold they survive. A profile
tunes those rules for one crop, matched from the planting's common name.

Sources, deliberately transparent and conservative:

- Water demand: FAO-56 mid-season crop coefficients (Kc), Allen et al. 1998,
  "Crop evapotranspiration", Table 12. Crop water demand is ET0 x Kc. Crops
  with no FAO-56 entry (most herbs, kale, chard) use the leafy-vegetable
  default Kc = 1.0.
- Frost and heat classes: rule-of-thumb tolerances from university extension
  guides - tender crops damaged at 0C, hardy greens surviving a light frost
  and damaged in a hard frost around -2C, cool-season greens bolting in
  sustained heat around 27C. These are flagging heuristics, not a validated
  agronomic model.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CropProfile:
    kc: float             # FAO-56 mid-season crop coefficient; demand = ET0 x Kc
    heat_c: float         # sustained daily max (C) that stresses the crop
    frost_high_c: float   # daily min (C) at or below which frost damage is likely
    frost_near_c: float   # daily min (C) at or below which frost is possible


# The default matches the generic thresholds the rules used before profiles
# existed: frost damage at 0C, heat stress at 32C, demand equal to ET0.
DEFAULT_PROFILE = CropProfile(kc=1.0, heat_c=32.0, frost_high_c=0.0, frost_near_c=2.0)

# Tender crops are damaged at 0C; hardy greens survive a light frost and are
# damaged only around -2C.
_TENDER = {"frost_high_c": 0.0, "frost_near_c": 2.0}
_HARDY = {"frost_high_c": -2.0, "frost_near_c": 0.0}

# keyword -> profile. Kc values come from FAO-56 Table 12 (mid-season):
# lettuce 1.00, spinach 1.00, tomato 1.15, cucumber 1.00, green beans 1.05,
# radish 0.85. Others default to the leafy-vegetable Kc of 1.0.
_PROFILES: list[tuple[str, CropProfile]] = [
    ("lettuce", CropProfile(kc=1.00, heat_c=27.0, **_HARDY)),
    ("spinach", CropProfile(kc=1.00, heat_c=27.0, **_HARDY)),
    ("kale", CropProfile(kc=1.00, heat_c=29.0, **_HARDY)),
    ("chard", CropProfile(kc=1.00, heat_c=29.0, **_HARDY)),
    ("radish", CropProfile(kc=0.85, heat_c=27.0, **_HARDY)),
    ("dill", CropProfile(kc=1.00, heat_c=29.0, **_HARDY)),
    ("cilantro", CropProfile(kc=1.00, heat_c=27.0, **_HARDY)),
    ("sage", CropProfile(kc=1.00, heat_c=35.0, **_HARDY)),
    ("tomato", CropProfile(kc=1.15, heat_c=35.0, **_TENDER)),
    ("basil", CropProfile(kc=1.00, heat_c=35.0, **_TENDER)),
    ("bean", CropProfile(kc=1.05, heat_c=32.0, **_TENDER)),
    ("cucumber", CropProfile(kc=1.00, heat_c=35.0, **_TENDER)),
    ("squash", CropProfile(kc=1.00, heat_c=35.0, **_TENDER)),
    ("cucurbit", CropProfile(kc=1.00, heat_c=35.0, **_TENDER)),
]


def profile_for(plant_name: str) -> CropProfile:
    """Match a planting's common name to a profile; unknown crops get the
    generic defaults."""
    name = plant_name.lower()
    for keyword, profile in _PROFILES:
        if keyword in name:
            return profile
    return DEFAULT_PROFILE
