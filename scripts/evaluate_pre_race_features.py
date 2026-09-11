"""Audit current pre-race features and run the grid/form ablation.

The evaluation deliberately keeps the established 2018-2024 train split,
2025-onward test split, train-only form imputation, and default logistic
regression configuration.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sklearn.linear_model import LogisticRegression


REPO_ROOT = Path(__file__).resolve().parent.parent
RACE_RESULTS = REPO_ROOT / "data" / "raw" / "race_results"
TRAIN_END_SEASON = 2024
TEST_START_SEASON = 2025
FORM_WINDOW = 5


def require(condition: bool, message: str) -> None:
    """Raise a clear error when an integrity condition is not met."""
    if not condition:
        raise ValueError(message)


def validate_race_order(df: pd.DataFrame) -> None:
    """Verify that season/round order is a valid chronological lag order."""
    required = {"driverId", "season", "round", "raceDate"}
    missing = required.difference(df.columns)
    require(not missing, f"missing chronology columns: {sorted(missing)}")
    require(
        not df[list(required)].isna().any().any(),
        "chronology columns contain missing values",
    )
    require(
        not df.duplicated(["driverId", "season", "round"]).any(),
        "duplicate driver-season-round rows found",
    )

    race_dates = pd.to_datetime(df["raceDate"], errors="raise")
    race_order = (
        df.assign(raceDate=race_dates)[["season", "round", "raceDate"]]
        .drop_duplicates()
        .sort_values(["season", "round"])
    )
    dates_per_race = race_order.groupby(["season", "round"])["raceDate"].nunique()
    require((dates_per_race == 1).all(), "a season-round maps to multiple dates")
    require(
        race_order["raceDate"].is_monotonic_increasing,
        "season-round order does not follow race dates",
    )

    for season, rounds in race_order.groupby("season", sort=False)["round"]:
        expected = list(range(1, int(rounds.max()) + 1))
        require(
            rounds.tolist() == expected,
            f"season {season} does not contain contiguous rounds from one",
        )

    ordered = df.assign(raceDate=race_dates).sort_values(
        ["driverId", "season", "round"]
    )
    driver_dates_increase = ordered.groupby("driverId")["raceDate"].apply(
        lambda dates: dates.is_monotonic_increasing
    )
    require(
        driver_dates_increase.all(),
        "a driver's season-round history does not follow race dates",
    )


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build the two currently approved pre-race features."""
    required = {"driverId", "season", "round", "position", "grid"}
    missing = required.difference(df.columns)
    require(not missing, f"missing feature columns: {sorted(missing)}")
    require(
        not df[list(required)].isna().any().any(),
        "feature source columns contain missing values",
    )

    featured = df.copy()
    featured["top10"] = (featured["position"] <= 10).astype(int)
    featured = featured.sort_values(["driverId", "season", "round"]).reset_index(
        drop=True
    )
    featured["top10_rate_last5"] = featured.groupby("driverId")["top10"].transform(
        lambda values: values.shift(1).rolling(FORM_WINDOW).mean()
    )

    featured["grid_effective"] = featured["grid"]
    race_max_grid = featured.groupby(["season", "round"])["grid"].transform("max")
    pit_lane_start = featured["grid"] == 0
    featured.loc[pit_lane_start, "grid_effective"] = race_max_grid + 1
    return featured


def validate_features(df: pd.DataFrame) -> dict[str, int]:
    """Check feature values independently against their intended definitions."""
    expected_form = pd.Series(index=df.index, dtype="float64")
    for _, driver_races in df.groupby("driverId", sort=False):
        outcomes = driver_races["top10"].tolist()
        values = [
            float("nan")
            if index < FORM_WINDOW
            else sum(outcomes[index - FORM_WINDOW : index]) / FORM_WINDOW
            for index in range(len(outcomes))
        ]
        expected_form.loc[driver_races.index] = values

    require(
        df["top10_rate_last5"].round(12).equals(expected_form.round(12)),
        "top10_rate_last5 does not equal the prior five driver outcomes",
    )
    non_missing_form = df["top10_rate_last5"].dropna()
    require(
        non_missing_form.between(0, 1).all(),
        "top10_rate_last5 contains a value outside [0, 1]",
    )

    pit_lane_start = df["grid"] == 0
    race_max_grid = df.groupby(["season", "round"])["grid"].transform("max")
    require(
        df.loc[pit_lane_start, "grid_effective"].equals(
            (race_max_grid + 1).loc[pit_lane_start]
        ),
        "a zero grid was not recoded to its race maximum plus one",
    )
    require(
        df.loc[~pit_lane_start, "grid_effective"].equals(
            df.loc[~pit_lane_start, "grid"]
        ),
        "a non-zero grid value changed",
    )
    require(not df["grid_effective"].isna().any(), "grid_effective contains NaN")
    require(not (df["grid_effective"] == 0).any(), "grid_effective still contains zero")

    train = df["season"] <= TRAIN_END_SEASON
    test = df["season"] >= TEST_START_SEASON
    return {
        "form_missing_total": int(df["top10_rate_last5"].isna().sum()),
        "form_missing_train": int(df.loc[train, "top10_rate_last5"].isna().sum()),
        "form_missing_test": int(df.loc[test, "top10_rate_last5"].isna().sum()),
        "grid_zero_total": int(pit_lane_start.sum()),
        "grid_zero_train": int((pit_lane_start & train).sum()),
        "grid_zero_test": int((pit_lane_start & test).sum()),
    }


def evaluate(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float | int]]:
    """Score grid alone and grid plus form on the fixed temporal holdout."""
    train = df[df["season"] <= TRAIN_END_SEASON].copy()
    test = df[df["season"] >= TEST_START_SEASON].copy()
    require(not train.empty, "training split is empty")
    require(not test.empty, "test split is empty")

    train_positive_rate = float(train["top10"].mean())
    feature_sets = {
        "Logistic regression: grid_effective only": ["grid_effective"],
        "Logistic regression: grid_effective + top10_rate_last5": [
            "grid_effective",
            "top10_rate_last5",
        ],
    }

    rows: list[dict[str, float | str]] = []
    predictions: dict[str, pd.Series] = {}
    for model_name, features in feature_sets.items():
        x_train = train[features].copy()
        x_test = test[features].copy()
        if "top10_rate_last5" in features:
            x_train["top10_rate_last5"] = x_train["top10_rate_last5"].fillna(
                train_positive_rate
            )
            x_test["top10_rate_last5"] = x_test["top10_rate_last5"].fillna(
                train_positive_rate
            )

        model = LogisticRegression()
        model.fit(x_train, train["top10"])
        prediction = pd.Series(model.predict(x_test), index=test.index)
        predictions[model_name] = prediction
        correct = prediction.eq(test["top10"])

        row: dict[str, float | str] = {
            "model": model_name,
            "pooled": float(correct.mean()),
        }
        for season, season_correct in correct.groupby(test["season"]):
            row[str(int(season))] = float(season_correct.mean())
        rows.append(row)

    scores = pd.DataFrame(rows).set_index("model")
    grid_name, grid_form_name = feature_sets
    grid_prediction = predictions[grid_name]
    grid_form_prediction = predictions[grid_form_name]
    target = test["top10"]
    hard_baseline = test["grid"] <= 10
    comparison: dict[str, float | int] = {
        "train_rows": len(train),
        "test_rows": len(test),
        "train_positive_rate": train_positive_rate,
        "grid_hard_baseline_matches": int(
            grid_prediction.eq(hard_baseline).sum()
        ),
        "grid_hard_baseline_mismatches": int(
            grid_prediction.ne(hard_baseline).sum()
        ),
        "prediction_disagreements": int(
            (grid_prediction != grid_form_prediction).sum()
        ),
        "grid_correct_form_wrong": int(
            ((grid_prediction == target) & (grid_form_prediction != target)).sum()
        ),
        "grid_wrong_form_correct": int(
            ((grid_prediction != target) & (grid_form_prediction == target)).sum()
        ),
        "pooled_accuracy_delta": float(
            scores.loc[grid_form_name, "pooled"] - scores.loc[grid_name, "pooled"]
        ),
    }
    return scores, comparison


def main() -> int:
    raw = pd.read_parquet(RACE_RESULTS)
    validate_race_order(raw)
    featured = build_features(raw)
    audit = validate_features(featured)
    scores, comparison = evaluate(featured)

    print("Feature integrity: PASS")
    for name, value in audit.items():
        print(f"  {name}: {value}")
    print(f"  train_positive_rate: {comparison['train_positive_rate']:.12f}")
    print("\nAccuracy")
    print(scores.to_string(float_format=lambda value: f"{value:.4f}"))
    print("\nPaired prediction comparison")
    for name in (
        "grid_hard_baseline_matches",
        "grid_hard_baseline_mismatches",
        "prediction_disagreements",
        "grid_correct_form_wrong",
        "grid_wrong_form_correct",
        "pooled_accuracy_delta",
    ):
        value = comparison[name]
        if isinstance(value, float):
            print(f"  {name}: {value:.4f}")
        else:
            print(f"  {name}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
