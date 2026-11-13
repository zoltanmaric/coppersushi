"""Export a solved network as validated numeric data, with no Plotly figures."""
import argparse
from pathlib import Path

from coppersushi.opf.export import extract
from coppersushi.opf.data_sources import networks

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('network', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    dataset = extract(networks.load(args.network))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(dataset.model_dump_json())


if __name__ == '__main__':
    main()
