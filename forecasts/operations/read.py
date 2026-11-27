"""Retrieve the forecast for a Berlin delivery date through its verified reader path."""
import argparse
from datetime import date
import json
from pathlib import Path

from forecasts.operations.flow_inputs import settings_from_pin
from forecasts.operations.jobs import read


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-pin", type=Path, required=True)
    parser.add_argument("--delivery-date", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    print(json.dumps(read(settings_from_pin(args.config_pin.read_text()), args.delivery_date), allow_nan=False))
