"""Archive input decisions reach the same feature path in replay and issuance."""
from datetime import date, datetime, timedelta
from decimal import Decimal
import unittest
from unittest.mock import patch
from uuid import UUID

from polars.testing import assert_frame_equal

from coppersushi.pipelines.market_data.resolution import Evidence, FORECAST_POLICY, PublishedPrice, SourcePolicy
from forecasts.inputs.fresh_sources import required_lag_dates
from forecasts.inputs.market_archive import ArchiveHistory
from forecasts.market import cutoff, quarters
from forecasts.model.features import build_day_features


class ArchiveFeaturesTests(unittest.TestCase):
    def test_archive_selection_is_pinned_for_both_feature_paths(self) -> None:
        day = date(2026, 10, 26)
        deadline = cutoff(day)

        def resolve(client: object, bucket: str, lag_day: date, zones: tuple[str, ...],
                    selected_at: datetime, policy: SourcePolicy) -> list[PublishedPrice]:
            self.assertEqual((bucket, zones, selected_at, policy), ("market", ("DE-LU",), deadline, FORECAST_POLICY))
            return [
                PublishedPrice(interval=ts, zone="DE-LU", price=Decimal(i), policy_id=policy.id, evidence=(
                    Evidence(publisher="smard", attempt_id=UUID(int=1), edition_key="example",
                             interval=ts, zone="DE-LU", destination=None, value=Decimal(i),
                             received_at=deadline - timedelta(minutes=2), visible_at=deadline - timedelta(minutes=1),
                             source_updated_at=None, upstream_source=None),
                ))
                for i, ts in enumerate(quarters(lag_day, lag_day + timedelta(days=1)))
            ]

        with patch("forecasts.inputs.market_archive.boto3.client"), patch(
            "forecasts.inputs.market_archive.resolve_day", side_effect=resolve,
        ) as reader:
            archive = ArchiveHistory("market", day, deadline)
        self.assertEqual([call.args[2] for call in reader.call_args_list], list(required_lag_dates(day)))
        self.assertEqual(len(archive.input_manifest()["prices"]), 388)  # October 25 has 100 quarters.
        self.assertEqual(archive.input_manifest()["prices"][0]["evidence"][0]["edition_key"], "example")
        assert_frame_equal(build_day_features(archive, day, live=True, issue_time=deadline, require_complete=True),
                           build_day_features(archive, day, require_complete=True))
