"""Compare a saved SMARD price archive with direct Electricity Maps auction results."""
import argparse
from datetime import date, datetime, UTC
from pathlib import Path

from coppersushi.pipelines.data_sources.electricity_maps_auction_prices import api_token, fetch_zone
from coppersushi.pipelines.market_day import MarketDay
from forecasts.inputs.sources import load_prices


def main() -> None:
    """Print coverage and agreement for each requested DE–LU delivery day."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("smard_archive", type=Path)
    parser.add_argument("delivery_days", type=date.fromisoformat, nargs="+")
    args = parser.parse_args()
    prices = load_prices(args.smard_archive)
    token = api_token()
    for day in args.delivery_days:
        market = MarketDay.on(day)
        if market.market_time_unit != "15min":
            parser.error("The SMARD forecast archive requires quarter-hourly delivery days")
        payload = fetch_zone("DE", market, token)
        received = datetime.now(UTC)
        observed = {row.datetime: row.value for row in payload.data}
        expected = set(market.market_time_units())
        if len(observed) != len(payload.data) or observed.keys() - expected:
            raise ValueError(f"Duplicate or unexpected Electricity Maps intervals for {day}")
        overlap = [t for t in observed if prices.get(t) is not None]
        mismatches = sum(prices[t] != observed[t] for t in overlap)
        print(f"{day} received={received.isoformat()} expected={len(expected)} "
              f"smard={sum(prices.get(t) is not None for t in expected)} "
              f"electricity_maps={len(observed)} overlap={len(overlap)} different={mismatches}")


if __name__ == "__main__":
    main()
