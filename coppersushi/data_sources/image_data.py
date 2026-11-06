"""Validate the image’s bundled inputs and build its derived country outlines."""
from coppersushi.data_sources import runtime_data
from coppersushi.grid_catalog.data_sources import zone_shapes
from coppersushi.opf.data_sources import opf_bundle


def prepare() -> None:
    runtime_data.check(sources_only=True)
    zone_shapes.build()
    opf_bundle.build()
    runtime_data.check()


if __name__ == "__main__":
    prepare()
