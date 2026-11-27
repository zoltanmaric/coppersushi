"""Issue and witness a forecast through separate Batch task roles."""
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from metaflow import FlowSpec, Parameter, batch, step

from forecasts.operations.artifacts import MissingArtifact
from forecasts.operations.flow_inputs import delivery_date, settings_from_pin, trace
from forecasts.operations.jobs import check, issue, witness


class DeLuDailyIssue(FlowSpec):
    scheduled_at = Parameter("scheduled_at", required=True)
    scheduled_live = Parameter("scheduled_live", default="no")
    config_pin = Parameter("config_pin", default=os.environ.get("FORECAST_CONFIG_PIN"))
    check_only = Parameter("check_only", default="no")

    @batch(log_driver="awslogs", log_options=["awslogs-group:/coppersushi/forecast-operations/batch", "awslogs-stream-prefix:forecast"],
           cpu=1, memory=2048)
    @step
    def start(self) -> None:
        self.day = delivery_date(self.scheduled_at)
        if self.check_only not in ("yes", "no"):
            raise ValueError("check_only must be yes or no")
        if self.check_only == "no":
            settings = settings_from_pin(self.config_pin, scheduled_live=self.scheduled_live)
            while True:
                try:
                    issue(settings, self.day, trace())
                    break
                except MissingArtifact as exc:
                    if (settings.replay or self.day.day != 1 or exc.key != f"fits/{self.day:%Y-%m}.json"
                            or datetime.now(ZoneInfo("Europe/Berlin")) >= settings.deadline(self.day)):
                        raise
                    time.sleep(30)
        self.next(self.end)

    @batch(log_driver="awslogs", log_options=["awslogs-group:/coppersushi/forecast-operations/batch", "awslogs-stream-prefix:forecast"],
           cpu=1, memory=2048, iam_role=os.environ.get("FORECAST_READER_ROLE"))
    @step
    def end(self) -> None:
        settings = settings_from_pin(self.config_pin, scheduled_live=self.scheduled_live)
        if self.check_only == "no":
            witness(settings, self.day, trace())
        else:
            check(settings, self.day, trace())
        print(f"Validated forecast for {self.day}")


if __name__ == "__main__":
    DeLuDailyIssue()
