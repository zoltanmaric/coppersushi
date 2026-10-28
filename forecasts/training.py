"""Fit the three feature-set models and reference for a single month."""
from datetime import date
from dataclasses import asdict
import json
from pathlib import Path

from catboost import CatBoostError, CatBoostRegressor
import polars as pl
from typing import cast
from pandera.typing.polars import DataFrame
from forecasts.tables import Features

from forecasts.config import RunConfig
from forecasts.contracts import FittedMonth, FloatArray, Predictor, TrainingData
from forecasts.features import feature_matrix
from forecasts.reference import fit_reference
from forecasts.snapshot import InputReader
from forecasts.labels import select_labels


def fit_month(reader: InputReader, features: DataFrame[Features], fit_day: date,
              config: RunConfig, directory: Path,
              restore_models: Path | None = None) -> FittedMonth:
    """Fit and save a month's models using labels eligible at its first issue.

    Model failures are recorded for explicit prediction fallback. Reproduction
    loads preserved models instead of refitting them, but recalibrates the
    reference from the same eligible history.
    """
    training = select_training_data(reader, features, fit_day, config.train_start)
    reference = fit_reference(reader, training.rows, training.targets, fit_day, config)
    if restore_models is None:
        models, failures = _fit_models(training.rows, training.targets, config, directory)
    else:
        models, failures = _restore_models(restore_models, config)
        directory.mkdir(parents=True, exist_ok=True)
    (directory / "reference.json").write_text(json.dumps(reference, sort_keys=True))
    (directory / "failures.json").write_text(json.dumps(failures, sort_keys=True))
    return FittedMonth(models, reference, len(training.rows), failures)


def select_training_data(reader: InputReader, features: DataFrame[Features],
                         fit_day: date, start: date) -> TrainingData:
    """Pair earlier features with label versions eligible at this fit's cutoff.

    Feature rows retain their own historical cutoffs. Scoring truth is never
    used here. Raise ValueError if no eligible labels remain.
    """
    labels = select_labels(reader, fit_day)
    outcomes = pl.DataFrame({"delivery_utc": list(labels), "_label": list(labels.values())},
                            schema={"delivery_utc": pl.Datetime("us", "UTC"), "_label": pl.Float64})
    paired = (features.filter((pl.col("delivery_date") >= start) & (pl.col("delivery_date") < fit_day))
              .join(outcomes, on="delivery_utc", how="left", maintain_order="left")
              .filter(pl.col("_label").is_not_null()))
    if paired.is_empty():
        raise ValueError("No eligible training labels")
    return TrainingData(cast(DataFrame[Features], paired.drop("_label")), paired["_label"].to_numpy())


def _fit_models(rows: DataFrame[Features], y: FloatArray, config: RunConfig,
                directory: Path) -> tuple[dict[str, Predictor], dict[str, str]]:
    directory.mkdir(parents=True, exist_ok=True)
    models, failures = {}, {}
    for name, fields in config.features.items():
        model = CatBoostRegressor(**asdict(config.catboost))
        try:
            model.fit(feature_matrix(rows, fields), y)
            model.save_model(str(directory / f"{name}.cbm"))
            models[name] = model
        except (CatBoostError, ValueError) as error:
            failures[name] = str(error)
    return models, failures



def _restore_models(source: Path, config: RunConfig) -> tuple[dict[str, Predictor], dict[str, str]]:
    failures = json.loads((source / "failures.json").read_text())
    models = {name: CatBoostRegressor().load_model(str(source / f"{name}.cbm"))
              for name in config.features if name not in failures}
    return models, failures
