import unittest
from datetime import datetime, timedelta, timezone

from rubin_clock.astro_core import (
    Site,
    SkyState,
    classify_sky_state,
    compute_solar_altitude,
    compute_true_solar_time,
    equation_of_time_minutes,
    next_transition,
)


class AstroCoreTests(unittest.TestCase):
    def test_equation_of_time_reasonable_range(self) -> None:
        # NOAA approximation is usually inside roughly +/-17 minutes.
        for month in range(1, 13):
            dt = datetime(2025, month, 15, 12, 0, tzinfo=timezone.utc)
            eot = equation_of_time_minutes(dt)
            self.assertGreater(eot, -20.0)
            self.assertLess(eot, 20.0)

    def test_true_solar_time_monotonic_short_interval(self) -> None:
        lon = -70.7494
        t1 = datetime(2025, 6, 1, 0, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(minutes=10)

        s1 = compute_true_solar_time(t1, lon)
        s2 = compute_true_solar_time(t2, lon)
        delta = (s2 - s1).total_seconds()

        self.assertGreater(delta, 9 * 60)
        self.assertLess(delta, 11 * 60)

    def test_solar_altitude_day_night_sign(self) -> None:
        # Near equinox at Greenwich, noon should be high and midnight low.
        noon = datetime(2025, 3, 20, 12, 0, tzinfo=timezone.utc)
        midnight = datetime(2025, 3, 20, 0, 0, tzinfo=timezone.utc)

        noon_alt = compute_solar_altitude(noon, 0.0, 0.0)
        night_alt = compute_solar_altitude(midnight, 0.0, 0.0)

        self.assertGreater(noon_alt, 70.0)
        self.assertLess(night_alt, -70.0)

    def test_classification_boundaries(self) -> None:
        self.assertEqual(classify_sky_state(0.0), SkyState.DAY)
        self.assertEqual(classify_sky_state(-0.01), SkyState.CIVIL_TWILIGHT)

        self.assertEqual(classify_sky_state(-6.0), SkyState.CIVIL_TWILIGHT)
        self.assertEqual(classify_sky_state(-6.01), SkyState.NAUTICAL_TWILIGHT)

        self.assertEqual(classify_sky_state(-12.0), SkyState.NAUTICAL_TWILIGHT)
        self.assertEqual(classify_sky_state(-12.01), SkyState.ASTRONOMICAL_TWILIGHT)

        self.assertEqual(classify_sky_state(-18.0), SkyState.ASTRONOMICAL_TWILIGHT)
        self.assertEqual(classify_sky_state(-18.01), SkyState.ASTRONOMICAL_NIGHT)

    def test_next_transition_is_future(self) -> None:
        site = Site(
            id="rubin_cerro_pachon",
            name="Rubin (Cerro Pachon)",
            lat=-30.2446,
            lon=-70.7494,
            elevation_m=2663.0,
        )
        now = datetime(2025, 6, 1, 0, 0, tzinfo=timezone.utc)
        transition = next_transition(now, site)

        self.assertGreater(transition.at_utc, now)
        self.assertEqual(
            transition.from_state,
            classify_sky_state(compute_solar_altitude(now, site.lat, site.lon)),
        )
        if transition.found:
            self.assertNotEqual(transition.from_state, transition.to_state)


if __name__ == "__main__":
    unittest.main()
