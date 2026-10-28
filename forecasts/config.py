"""Parse serialized settings once; use immutable domain values during execution."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import math
from types import MappingProxyType
from typing import Any, ClassVar, Literal, Mapping

QUANTILES = (.025, .25, .5, .75, .975)
QUANTILE_LOSS = "MultiQuantile:alpha=0.025,0.25,0.5,0.75,0.975"


@dataclass(frozen=True)
class RunConfig:
    """Validated execution settings; dates are dates, not serialized strings.

    The refit schedule, feature inventories and quantiles are implementation
    constants. Saved JSON includes them for provenance and compatibility checks.
    """
    snapshot_id: SnapshotId
    history_start: date
    train_start: date
    evaluation_start: date
    end_exclusive: date
    catboost: CatBoostSettings
    reference_min_errors: int
    reference_min_per_quarter: int
    bootstrap: BootstrapSettings
    tolerance: Tolerance

    schema_version: ClassVar[Literal[1]] = 1
    refit: ClassVar[Literal["monthly_expanding"]] = "monthly_expanding"
    quantiles: ClassVar[tuple[float, ...]] = QUANTILES

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunConfig:
        """Validate JSON settings and convert dates/identifiers at the boundary.

        Accept the initial config without a feature inventory, or a preserved
        run with the exact inventory. Reject unsupported schedules, inventories,
        unknown settings and invalid values before any fitting or run creation.
        """
        expected = set(cls.__dataclass_fields__) | {"features"}
        if not isinstance(data, dict) or set(data) - expected:
            raise ValueError("Unknown run configuration fields")
        if type(data.get("schema_version")) is not int or data["schema_version"] != cls.schema_version:
            raise ValueError("Unsupported configuration schema")
        if data.get("refit") != cls.refit or data.get("quantiles") != list(QUANTILES):
            raise ValueError("Unsupported refit or quantile contract")
        try:
            config = cls(
                snapshot_id=SnapshotId(data["snapshot_id"]),
                history_start=_date(data["history_start"]),
                train_start=_date(data["train_start"]),
                evaluation_start=_date(data["evaluation_start"]),
                end_exclusive=_date(data["end_exclusive"]),
                catboost=CatBoostSettings(**data["catboost"]),
                reference_min_errors=data["reference_min_errors"],
                reference_min_per_quarter=data["reference_min_per_quarter"],
                bootstrap=BootstrapSettings(**data["bootstrap"]),
                tolerance=Tolerance(**data["tolerance"]),
            )
        except (KeyError, TypeError) as error:
            raise ValueError(f"Incomplete or invalid run configuration: {error}") from error
        if "features" in data and data["features"] != {name: list(fields) for name, fields in config.features.items()}:
            raise ValueError("Feature inventory differs from the implementation")
        return config

    def to_dict(self) -> dict[str, Any]:
        """Serialize settings and fixed contracts as JSON values."""
        data = asdict(self)
        for name in ("history_start", "train_start", "evaluation_start", "end_exclusive"):
            data[name] = getattr(self, name).isoformat()
        data.update(schema_version=self.schema_version, refit=self.refit,
                    quantiles=list(self.quantiles),
                    features={name: list(fields) for name, fields in self.features.items()})
        return data

    @property
    def features(self) -> Mapping[str, tuple[str, ...]]:
        """Expose the fixed feature inventory without allowing callers to mutate it."""
        from forecasts.features import FEATURES
        return MappingProxyType({name: tuple(fields) for name, fields in FEATURES.items()})

    def __post_init__(self) -> None:
        for name in ("history_start", "train_start", "evaluation_start", "end_exclusive"):
            if type(getattr(self, name)) is not date:
                raise ValueError(f"{name} must be a date")
        if not self.history_start <= self.train_start < self.evaluation_start < self.end_exclusive:
            raise ValueError("Invalid chronological monthly fold dates")
        if self.evaluation_start.day != 1 or self.end_exclusive.day != 1:
            raise ValueError("Evaluation boundaries must be first days of months")
        for name, kind in (("snapshot_id", SnapshotId), ("catboost", CatBoostSettings),
                           ("bootstrap", BootstrapSettings), ("tolerance", Tolerance)):
            if not isinstance(getattr(self, name), kind):
                raise ValueError(f"{name} must be a validated {kind.__name__}")
        _integer("reference_min_errors", self.reference_min_errors, minimum=1)
        _integer("reference_min_per_quarter", self.reference_min_per_quarter, minimum=1)


class SnapshotId(str):
    """A snapshot's validated lowercase SHA-256 content identifier."""

    def __new__(cls, value: str) -> SnapshotId:
        if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("Snapshot ID must be a lowercase SHA-256 digest")
        return super().__new__(cls, value)


@dataclass(frozen=True)
class CatBoostSettings:
    """Typed CatBoost options for the supported deterministic quantile fit."""
    iterations: int
    depth: int
    learning_rate: float
    l2_leaf_reg: float
    random_seed: int
    thread_count: int
    task_type: Literal["CPU"]
    nan_mode: Literal["Min"]
    bootstrap_type: Literal["No"]
    random_strength: float
    allow_writing_files: bool
    verbose: bool
    loss_function: Literal["MultiQuantile:alpha=0.025,0.25,0.5,0.75,0.975"]

    def __post_init__(self) -> None:
        for name in ("iterations", "depth", "thread_count"):
            _integer(name, getattr(self, name), minimum=1)
        if self.depth > 16:
            raise ValueError("CatBoost depth must be at most 16")
        _integer("random_seed", self.random_seed, minimum=0)
        _number("learning_rate", self.learning_rate, positive=True)
        for name in ("l2_leaf_reg", "random_strength"):
            _number(name, getattr(self, name))
        for name in ("allow_writing_files", "verbose"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        for name, expected in (("task_type", "CPU"), ("nan_mode", "Min"),
                               ("bootstrap_type", "No"), ("loss_function", QUANTILE_LOSS)):
            if getattr(self, name) != expected:
                raise ValueError(f"Unsupported CatBoost {name}")


@dataclass(frozen=True)
class BootstrapSettings:
    """Settings for paired resampling of contiguous whole-day blocks."""
    seed: int
    samples: int
    block_days: int

    def __post_init__(self) -> None:
        _integer("seed", self.seed, minimum=0)
        _integer("samples", self.samples, minimum=1)
        _integer("block_days", self.block_days, minimum=1)


@dataclass(frozen=True)
class Tolerance:
    """Finite, nonnegative tolerances for saved-run numerical comparisons."""
    absolute: float
    relative: float

    def __post_init__(self) -> None:
        _number("absolute", self.absolute)
        _number("relative", self.relative)


def _date(value: str) -> date:
    if not isinstance(value, str):
        raise ValueError("Serialized dates must be ISO date strings")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Dates must use YYYY-MM-DD")
    return parsed


def _integer(name: str, value: int, *, minimum: int) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _number(name: str, value: float, *, positive: bool = False) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
