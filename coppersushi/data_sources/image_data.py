"""Validate the image’s bundled inputs and build its derived country outlines."""
from coppersushi.data_sources import jao, osm_locator, zone_shapes


def prepare() -> None:
    if jao.read_element_ends().empty:
        raise ValueError("endpoint seed is empty; run the seed command before building")
    osm_locator.read_csvs()
    zone_shapes.build()


if __name__ == "__main__":
    prepare()
