"""Fit the prices and calendar model and benchmark for a single month."""
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
import json
from pathlib import Path
from typing import Annotated, cast

from catboost import CatBoostError, CatBoostRegressor
import numpy as np
from pandera.typing.polars import DataFrame
import polars as pl
from pydantic import StringConstraints, TypeAdapter

from forecasts.config import RunConfig
from forecasts.inputs.selection import InputReader
from forecasts.market import cutoff, require_quarters
from forecasts.model.contracts import FittedMonth, FloatArray, Predictor, TrainingData
from forecasts.model.coverage import require_static_features
from forecasts.model.features import feature_matrix
from forecasts.model.labels import select_labels
from forecasts.model.reference import fit_reference
from forecasts.model.tables import Features


_FAILURES = TypeAdapter(dict[str, Annotated[str, StringConstraints(pattern=r"\S")]])


def fit_month(reader: InputReader, features: DataFrame[Features], fit_day: date,
              config: RunConfig, directory: Path,
              restore_models: Path | None = None) -> FittedMonth:
    """Fit and save a month's models using labels eligible at its first issue.

    Require complete eligible price labels and inputs before fitting. Reproduction
    loads the fixed models and recalibrates the reference from eligible history.
    """
    training = select_training_data(reader, features, fit_day, config.train_start)
    reference = fit_reference(reader, training.rows, training.targets, fit_day, config)
    if restore_models is None:
        models = _fit_models(training.rows, training.targets, config, directory, fit_day)
    else:
        models = load_models(restore_models, config)
        directory.mkdir(parents=True, exist_ok=True)
    (directory / "reference.json").write_text(json.dumps(reference, sort_keys=True))
    (directory / "failures.json").write_text("{}")
    return FittedMonth(models, reference, len(training.rows), {})


def select_training_data(reader: InputReader, features: DataFrame[Features],
                         fit_day: date, start: date) -> TrainingData:
    """Pair earlier features with label versions eligible at this fit's cutoff.

    Feature rows retain their own historical cutoffs. Scoring truth is never
    used here. Require eligible labels on the entire training grid.
    """
    labels = select_labels(reader, fit_day)
    training_rows = cast(DataFrame[Features], features.filter(
        (pl.col("delivery_date") >= start) & (pl.col("delivery_date") < fit_day)
    ))
    require_static_features(training_rows, start, fit_day)
    require_quarters((timestamp for timestamp in training_rows["delivery_utc"] if labels.get(timestamp) is not None),
                     start, fit_day, f"Eligible SMARD training labels at {cutoff(fit_day).isoformat()} for fit {fit_day}")
    return TrainingData(training_rows, np.array([labels[timestamp] for timestamp in training_rows["delivery_utc"]], dtype=float))


def load_models(source: Path, config: RunConfig, *,
                verify_model: Callable[[Path], None] | None = None) -> dict[str, Predictor]:
    """Load all saved models and reject earlier fits that recorded failures."""
    failures = _FAILURES.validate_json((source / "failures.json").read_bytes(), strict=True)
    unknown = failures.keys() - config.features.keys()
    if unknown:
        raise ValueError(f"Saved model failures name unknown feature sets: {', '.join(sorted(unknown))}")
    if failures:
        detail = "; ".join(f"{name}: {message}" for name, message in sorted(failures.items()))
        raise ValueError(f"Failed model fits recorded in {source / 'failures.json'}: {detail}")
    model_paths = {name: source / f"{name}.cbm" for name in config.features}
    if verify_model is not None:
        for path in model_paths.values():
            verify_model(path)
    return {name: CatBoostRegressor().load_model(str(path)) for name, path in model_paths.items()}


def _fit_models(rows: DataFrame[Features], y: FloatArray, config: RunConfig,
                directory: Path, fit_day: date) -> dict[str, Predictor]:
    models = {}
    for name, fields in config.features.items():
        model = CatBoostRegressor(**asdict(config.catboost))
        try:
            model.fit(feature_matrix(rows, fields), y)
        except (CatBoostError, ValueError) as error:
            raise ValueError(f"{name} CatBoost fit failed for {fit_day}: {error}") from error
        models[name] = model
    directory.mkdir(parents=True, exist_ok=True)
    for name, model in models.items():
        model.save_model(str(directory / f"{name}.cbm"))
    return dict(models)
