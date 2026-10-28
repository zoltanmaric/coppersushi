"""Maintained source configuration for the fixed Germany–Luxembourg baseline."""
from typing import NamedTuple


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
