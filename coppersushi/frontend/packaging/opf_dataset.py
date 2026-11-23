"""Prepare a solved network and preview its OPF page locally."""
import argparse
from pathlib import Path

from coppersushi.frontend.packaging.preview import create_app
from coppersushi.pipelines.powerflow.data_sources.dataset import publish


def main() -> None:
    """Prepare browser data and serve its OPF page."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("network", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bucket", help="Also publish the prepared dataset to this S3 bucket")
    args = parser.parse_args()
    publish(args.network, args.output, args.bucket)
    app = create_app(production_data=True)
    app.config["OPF_PREVIEW_DIRECTORY"] = args.output.resolve()
    app.run(host="127.0.0.1", port=8050)


if __name__ == "__main__":
    main()
