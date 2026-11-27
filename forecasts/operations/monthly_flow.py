"""Deploy this workflow with Metaflow step-functions create."""
import os

from metaflow import FlowSpec, Parameter, batch, step

from forecasts.operations.flow_inputs import delivery_date, settings_from_pin, trace
from forecasts.operations.jobs import fit


class DeLuMonthlyFit(FlowSpec):
    scheduled_at = Parameter("scheduled_at", required=True)
    scheduled_live = Parameter("scheduled_live", default="no")
    config_pin = Parameter("config_pin", default=os.environ.get("FORECAST_CONFIG_PIN"))

    @batch(log_driver="awslogs", log_options=["awslogs-group:/coppersushi/forecast-operations/batch", "awslogs-stream-prefix:forecast"],
           cpu=1, memory=4096)
    @step
    def start(self) -> None:
        day = delivery_date(self.scheduled_at)
        if day.day != 1:
            raise ValueError(f"Monthly training requires first-of-month delivery, got {day}")
        self.fit_result = fit(settings_from_pin(self.config_pin, scheduled_live=self.scheduled_live), day, trace())
        self.next(self.end)

    @batch(log_driver="awslogs", log_options=["awslogs-group:/coppersushi/forecast-operations/batch", "awslogs-stream-prefix:forecast"],
           cpu=1, memory=2048)
    @step
    def end(self) -> None:
        print(self.fit_result)


if __name__ == "__main__":
    DeLuMonthlyFit()
