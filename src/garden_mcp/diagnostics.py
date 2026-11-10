"""Rule-based stress diagnostics over recent and forecast daily weather.

The rules are tuned per crop through CropProfile (see crops.py): water
demand is ET0 x Kc (FAO-56), and frost/heat thresholds follow the crop's
tolerance. With the default profile they behave exactly as the original
generic rules.
"""
from __future__ import annotations

from .crops import DEFAULT_PROFILE, CropProfile
from .schemas import DailyWeather, Severity, StressFlag, StressKind

DRY_RATIO_MODERATE = 0.5   # precip < 50% of crop water demand over the window
DRY_RATIO_HIGH = 0.2
WET_MM_MODERATE = 60.0     # 7-day precipitation totals, mm
WET_MM_HIGH = 100.0
WIND_KMH_MODERATE = 40.0
WIND_KMH_HIGH = 60.0

_RECOMMENDATIONS = {
    StressKind.FROST: "Protect plants with frost cloth or move containers indoors overnight.",
    StressKind.HEAT: "Water early in the morning and add shade cloth during peak afternoon heat.",
    StressKind.DRY: "Increase watering frequency; soil moisture is not keeping up with evapotranspiration.",
    StressKind.EXCESS_WATER: "Hold off watering and check drainage; prolonged saturation risks root rot.",
    StressKind.WIND: "Stake tall plants and secure row covers ahead of high winds.",
}


def assess(past: list[DailyWeather], forecast: list[DailyWeather],
           profile: CropProfile = DEFAULT_PROFILE) -> tuple[list[StressFlag], list[str]]:
    """Return (flags, recommendations) for a planting's weather window."""
    flags: list[StressFlag] = []

    recent = past[-2:] + forecast[:2]
    frost_days = [d for d in recent if d.temp_min_c is not None and d.temp_min_c <= profile.frost_high_c]
    near_frost_days = [d for d in recent
                       if d.temp_min_c is not None and profile.frost_high_c < d.temp_min_c <= profile.frost_near_c]
    if frost_days:
        flags.append(StressFlag(kind=StressKind.FROST, severity=Severity.HIGH, detail=(
            f"{len(frost_days)} day(s) at or below {profile.frost_high_c:.0f}C in the current window "
            f"(lowest {min(d.temp_min_c for d in frost_days)}C on "
            f"{min(frost_days, key=lambda d: d.temp_min_c).date}).")))
    elif near_frost_days:
        flags.append(StressFlag(kind=StressKind.FROST, severity=Severity.MODERATE, detail=(
            f"{len(near_frost_days)} day(s) between {profile.frost_high_c:.0f}C and "
            f"{profile.frost_near_c:.0f}C; frost is possible in exposed spots.")))

    hot_window = past[-3:] + forecast[:3]
    hot_days = [d for d in hot_window if d.temp_max_c is not None and d.temp_max_c >= profile.heat_c]
    if len(hot_days) >= 3:
        flags.append(StressFlag(kind=StressKind.HEAT, severity=Severity.HIGH, detail=(
            f"{len(hot_days)} days at or above {profile.heat_c:.0f}C "
            f"(peak {max(d.temp_max_c for d in hot_days)}C).")))
    elif len(hot_days) >= 2:
        flags.append(StressFlag(kind=StressKind.HEAT, severity=Severity.MODERATE, detail=(
            f"{len(hot_days)} days at or above {profile.heat_c:.0f}C.")))

    week = past[-7:]
    precip = sum(d.precipitation_mm for d in week)
    et0_vals = [d.et0_mm for d in week if d.et0_mm is not None]
    et0 = sum(et0_vals)
    demand = et0 * profile.kc
    if demand > 0:
        ratio = precip / demand
        if profile.kc != 1.0:
            demand_txt = (f"{demand:.1f} mm crop-adjusted demand "
                          f"({et0:.1f} mm ET0 x Kc {profile.kc:g})")
        else:
            demand_txt = f"{demand:.1f} mm evapotranspiration"
        if ratio < DRY_RATIO_HIGH:
            flags.append(StressFlag(kind=StressKind.DRY, severity=Severity.HIGH, detail=(
                f"Only {precip:.1f} mm of rain against {demand_txt} "
                f"over the past {len(week)} days ({ratio:.0%} of demand).")))
        elif ratio < DRY_RATIO_MODERATE:
            flags.append(StressFlag(kind=StressKind.DRY, severity=Severity.MODERATE, detail=(
                f"{precip:.1f} mm of rain against {demand_txt} "
                f"over the past {len(week)} days ({ratio:.0%} of demand).")))
    if precip >= WET_MM_HIGH:
        flags.append(StressFlag(kind=StressKind.EXCESS_WATER, severity=Severity.HIGH, detail=(
            f"{precip:.1f} mm of rain in the past {len(week)} days.")))
    elif precip >= WET_MM_MODERATE:
        flags.append(StressFlag(kind=StressKind.EXCESS_WATER, severity=Severity.MODERATE, detail=(
            f"{precip:.1f} mm of rain in the past {len(week)} days.")))

    windy = [d for d in hot_window if d.wind_max_kmh is not None and d.wind_max_kmh >= WIND_KMH_MODERATE]
    if windy:
        peak = max(d.wind_max_kmh for d in windy)
        flags.append(StressFlag(
            kind=StressKind.WIND,
            severity=Severity.HIGH if peak >= WIND_KMH_HIGH else Severity.MODERATE,
            detail=f"Peak wind of {peak} km/h in the current window."))

    recs = [_RECOMMENDATIONS[f.kind] for f in flags]
    if not flags:
        recs = ["No stress signals detected; keep monitoring soil moisture."]
    return flags, recs


def summarize(flags: list[StressFlag], plant_name: str) -> str:
    if not flags:
        return f"{plant_name}: no significant stress signals in the current weather window."
    parts = ", ".join(f"{f.kind.value} ({f.severity.value})" for f in flags)
    return f"{plant_name}: {len(flags)} stress signal(s) - {parts}."
