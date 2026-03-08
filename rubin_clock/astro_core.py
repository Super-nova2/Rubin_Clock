from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class SkyState(str, Enum):
    DAY = "DAY"
    CIVIL_TWILIGHT = "CIVIL_TWILIGHT"
    NAUTICAL_TWILIGHT = "NAUTICAL_TWILIGHT"
    ASTRONOMICAL_TWILIGHT = "ASTRONOMICAL_TWILIGHT"
    ASTRONOMICAL_NIGHT = "ASTRONOMICAL_NIGHT"


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    lat: float
    lon: float
    elevation_m: float = 0.0


@dataclass(frozen=True)
class TransitionInfo:
    from_state: SkyState
    to_state: SkyState
    at_utc: datetime
    found: bool = True


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fractional_year_radians(dt_utc: datetime) -> float:
    day_of_year = dt_utc.timetuple().tm_yday
    hour_fraction = dt_utc.hour + (dt_utc.minute / 60.0) + (dt_utc.second / 3600.0) + (dt_utc.microsecond / 3_600_000_000.0)
    return (2.0 * math.pi / 365.0) * (day_of_year - 1 + ((hour_fraction - 12.0) / 24.0))


def equation_of_time_minutes(dt_utc: datetime) -> float:
    """Return equation of time in minutes using NOAA approximation."""
    dt_utc = _to_utc(dt_utc)
    gamma = _fractional_year_radians(dt_utc)
    return 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )


def _solar_declination_radians(dt_utc: datetime) -> float:
    dt_utc = _to_utc(dt_utc)
    gamma = _fractional_year_radians(dt_utc)
    return (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )


def compute_true_solar_time(dt_utc: datetime, lon_deg: float) -> datetime:
    """Return local apparent solar time for longitude (east positive)."""
    dt_utc = _to_utc(dt_utc)
    offset_minutes = (4.0 * lon_deg) + equation_of_time_minutes(dt_utc)
    return dt_utc + timedelta(minutes=offset_minutes)


def compute_solar_altitude(dt_utc: datetime, lat_deg: float, lon_deg: float) -> float:
    """Return solar altitude in degrees."""
    dt_utc = _to_utc(dt_utc)
    decl = _solar_declination_radians(dt_utc)

    minutes_utc = (
        (dt_utc.hour * 60.0)
        + dt_utc.minute
        + (dt_utc.second / 60.0)
        + (dt_utc.microsecond / 60_000_000.0)
    )
    true_solar_minutes = (minutes_utc + equation_of_time_minutes(dt_utc) + (4.0 * lon_deg)) % 1440.0

    hour_angle_deg = (true_solar_minutes / 4.0) - 180.0
    if hour_angle_deg < -180.0:
        hour_angle_deg += 360.0

    lat_rad = math.radians(lat_deg)
    hour_angle_rad = math.radians(hour_angle_deg)

    cos_zenith = (
        math.sin(lat_rad) * math.sin(decl)
        + math.cos(lat_rad) * math.cos(decl) * math.cos(hour_angle_rad)
    )
    cos_zenith = max(-1.0, min(1.0, cos_zenith))

    zenith_deg = math.degrees(math.acos(cos_zenith))
    return 90.0 - zenith_deg


def classify_sky_state(alt_deg: float) -> SkyState:
    if alt_deg >= 0.0:
        return SkyState.DAY
    if alt_deg >= -6.0:
        return SkyState.CIVIL_TWILIGHT
    if alt_deg >= -12.0:
        return SkyState.NAUTICAL_TWILIGHT
    if alt_deg >= -18.0:
        return SkyState.ASTRONOMICAL_TWILIGHT
    return SkyState.ASTRONOMICAL_NIGHT


def _binary_search_transition(left: datetime, right: datetime, site: Site, from_state: SkyState) -> datetime:
    low = _to_utc(left)
    high = _to_utc(right)

    while (high - low).total_seconds() > 1.0:
        mid = low + (high - low) / 2
        mid_state = classify_sky_state(compute_solar_altitude(mid, site.lat, site.lon))
        if mid_state == from_state:
            low = mid
        else:
            high = mid

    return high


def next_transition(dt_utc: datetime, site: Site) -> TransitionInfo:
    """Find the next sky-state transition for a site."""
    dt_utc = _to_utc(dt_utc)
    start_state = classify_sky_state(compute_solar_altitude(dt_utc, site.lat, site.lon))

    horizon = dt_utc + timedelta(hours=48)
    probe_step = timedelta(minutes=1)

    prev_t = dt_utc
    prev_state = start_state
    current = dt_utc + probe_step

    while current <= horizon:
        state = classify_sky_state(compute_solar_altitude(current, site.lat, site.lon))
        if state != prev_state:
            transition_at = _binary_search_transition(prev_t, current, site, prev_state)
            to_state = classify_sky_state(compute_solar_altitude(transition_at, site.lat, site.lon))
            return TransitionInfo(
                from_state=start_state,
                to_state=to_state,
                at_utc=transition_at,
                found=True,
            )

        prev_t = current
        prev_state = state
        current += probe_step

    return TransitionInfo(
        from_state=start_state,
        to_state=start_state,
        at_utc=horizon,
        found=False,
    )


__all__ = [
    "Site",
    "SkyState",
    "TransitionInfo",
    "equation_of_time_minutes",
    "compute_true_solar_time",
    "compute_solar_altitude",
    "classify_sky_state",
    "next_transition",
]
