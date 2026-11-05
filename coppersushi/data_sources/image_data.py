"""Validate the image’s bundled inputs and build its derived country outlines."""
from coppersushi import REPO
from coppersushi.data_sources import element_catalog, jao, osm_locator, zone_shapes, opf_bundle


def prepare() -> None:
    if jao.read_element_ends().empty:
        raise ValueError("endpoint seed is empty; run the seed command before building")
    osm_locator.read_csvs()
    with element_catalog.load(REPO/'data/element-catalog'):
        pass
    zone_shapes.build()
    opf_bundle.build()


if __name__ == "__main__":
    prepare()
