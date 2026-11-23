"""Maintained source configuration for the fixed Germany–Luxembourg baseline."""
from typing import NamedTuple


PRICE_LAG_DAYS = (1, 2, 7, 14)


class WeatherLocation(NamedTuple):
    """Named ICON-EU sampling coordinate in degrees north/east."""
    name: str
    latitude: float
    longitude: float


# The baseline adopts the October 7 diagnostic's twelve manually spread points.
# Coordinate provenance: wiki/price-forecasting/data-sources.md#locations
# Comparison with three points and its limits: wiki/price-forecasting/data-sources.md#diagnostics
WEATHER_LOCATIONS: tuple[WeatherLocation, ...] = (
    WeatherLocation('Hamburg', 53.55, 9.99),
    WeatherLocation('Essen', 51.45, 7.01),
    WeatherLocation('Munich', 48.14, 11.58),
    WeatherLocation('Emden', 53.37, 7.21),
    WeatherLocation('Husum', 54.48, 9.05),
    WeatherLocation('Rostock', 54.09, 12.14),
    WeatherLocation('Magdeburg', 52.13, 11.63),
    WeatherLocation('Berlin', 52.52, 13.41),
    WeatherLocation('Leipzig', 51.34, 12.37),
    WeatherLocation('Frankfurt', 50.11, 8.68),
    WeatherLocation('Stuttgart', 48.78, 9.18),
    WeatherLocation('Nuremberg', 49.45, 11.08),
)

FIELDS = {"temperature_2m": "°C", "wind_speed_120m": "km/h", "shortwave_radiation": "W/m²"}
# Diagnostic and feature-table columns retain the archive's location-first order.
WEATHER_TABLE_FIELDS = [f"{variable}_{location.name.lower()}" for location in WEATHER_LOCATIONS for variable in FIELDS]
WEATHER_FIELDS = sorted(WEATHER_TABLE_FIELDS)
