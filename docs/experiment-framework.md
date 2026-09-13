# Experiment Framework

This document defines how model experiments should be structured, compared, and evaluated.

It is not a record of individual technical decisions. Those belong in `docs/decisions.md`. Instead, this document describes the shared framework used to decide which features, models, and configurations are worth keeping.

## Goal

Predict the probability that a Formula 1 driver will finish in the top 10 using only information that would have been available before the race starts.

The project should improve predictive performance without sacrificing temporal integrity or making results difficult to explain.

## Prediction Cutoff

The intended prediction cutoff is after the official starting grid is known and before the formation lap begins.

Every feature used for prediction must be available by this point.

Historical availability and live availability are separate questions. A value may describe something that was known before a historical race while still requiring a different data source to obtain it before a future race.

## Core Principles

### Pre-race information only

Post-race information may be used to create labels and historical lagged features, but the current race's outcome must never enter its own feature values.

A feature is valid only if all information used to construct it would have been available by the prediction cutoff.

### Time-aware evaluation

Formula 1 data has a natural time order. Training or validation must never use information from races that occur after the race being predicted.

Random train/test splits are therefore not appropriate for the main evaluation.

### Change one question at a time

Experiments should be structured so that a performance change has a clear interpretation.

For example, compare two feature sets using the same model before comparing model families. Avoid simultaneously changing features, preprocessing, model type, and hyperparameters unless the experiment specifically studies their interaction.

### Prefer simple baselines first

A more complex model should earn its complexity by outperforming a simpler alternative under the same evaluation procedure.

The purpose of an experiment is not only to improve a score, but also to understand where the improvement came from.

## Experiment Dimensions

Each experiment can vary along several dimensions.

They should generally be considered in this order:

| Dimension | Main question | Current starting point | Examples of later experiments |
| --- | --- | --- | --- |
| Feature set | What information does the model receive? | `grid_effective`, `top10_rate_last5` | constructor form, qualifying, circuit history |
| Feature parameters | How is that information defined? | 5-race lookback | 3, 5, 10 races; season reset rules |
| Preprocessing | How is the input prepared? | train-only base-rate imputation | scaling, alternative missing-value strategies |
| Model family | How is the relationship learned? | Logistic Regression | tree-based and boosting models |
| Hyperparameters | How is that model configured? | model defaults | regularization, tree depth, learning rate |
| Decision threshold | How does probability become a decision? | 0.5 | thresholds selected for a defined decision objective |

These dimensions should not all be optimized at once.

The initial value of a parameter does not imply that it is optimal. For example, the five-race lookback used by `top10_rate_last5` is a starting heuristic and can later be treated as an experimental parameter.

The evaluation scheme itself is not an experiment dimension. It is the common rule used to compare experiments fairly.

## Feature Roles

Features should be distinguishable from labels and post-race outcomes.

Current important values include:

- `grid`: raw starting-grid value from the historical race result source.
- `grid_effective`: derived numeric representation of starting position that moves pit-lane starts behind the normal grid.
- `position`: post-race finishing position and therefore not a pre-race model input.
- `top10`: target label derived from finishing position.
- `top10_rate_last5`: derived pre-race feature based only on a driver's previous five observed race outcomes.

A derived value is not automatically unsafe, and a raw value is not automatically safe. Temporal availability determines whether a value may be used as a model input.

## Model Selection and Validation

Model development should use historical data in chronological order.

Rather than relying on a single validation season, use expanding-window walk-forward validation where practical.

The initial validation scheme is:

```text
2018-2021 -> validate on 2022
2018-2022 -> validate on 2023
2018-2023 -> validate on 2024
```

Each validation season acts as a historical simulation of deployment. The model learns only from information that would have existed before that season.

Results should be considered across folds rather than selecting a model because it performed unusually well in one season.

After a configuration has been selected, it may be refit on all historical development data available before the evaluation period.

## Current Historical Holdout

The existing project split trains through 2024 and evaluates on 2025 onward.

Results from this holdout have already been inspected during development. It remains useful as an out-of-time reference and sanity check, but it should no longer be described as a completely untouched final test set.

This distinction matters more as the number of experiments grows. Repeatedly choosing features, models, preprocessing choices, or hyperparameters based on performance on the same holdout gradually turns that holdout into part of the development process.

## Prospective Evaluation

Future races provide the strongest test of the system because their outcomes cannot be observed when predictions are created.

The intended cycle is:

```text
Freeze model version
        ↓
Create and store pre-race prediction
        ↓
Race happens
        ↓
Score prediction against actual result
        ↓
Analyze errors
        ↓
Form a hypothesis about a possible improvement
        ↓
Validate the proposed change on historical data
        ↓
Freeze the next model version
        ↓
Evaluate it on a new future race
```

Once the result of a race influences a model change, that race is no longer unseen evidence for the new model version. The next future race becomes the new prospective test.

A live race may trigger an investigation, but a model change should be adopted only when it is supported by historical validation or repeated prospective evidence.

An unusual race should not automatically cause the model to change.

## Evaluation Metrics

Accuracy is the primary comparison metric during the current classification experiments.

Scores should be reported both pooled and per season so that changes between regulation eras are not hidden by aggregation.

As the project moves toward probability prediction, evaluation should expand beyond classification accuracy.

Brier score and calibration should become the main tools for judging probability quality. Log loss may also be reported as a supporting metric.

Decision-threshold metrics should be evaluated separately from probability quality.

A well-calibrated probability model and a useful operational threshold are related but distinct problems. The threshold determines how a predicted probability becomes a binary decision. It does not change the probability produced by the model itself.

## Experiment Order

Experiments should progress from simple and interpretable questions toward larger search spaces.

### Phase 1: Feature integrity

Verify that every current input is genuinely available before the prediction cutoff and that lagged features cannot see the current race outcome.

### Phase 2: Incremental feature value

Using the same Logistic Regression setup, compare:

```text
grid_effective
```

against:

```text
grid_effective
+ top10_rate_last5
```

This answers whether recent driver form adds information beyond starting position.

### Phase 3: Feature engineering

If recent form shows value, test alternative definitions such as different lookback windows.

Examples:

```text
last 3 races
last 5 races
last 10 races
```

Additional feature families should then be introduced incrementally so their contribution remains measurable.

### Phase 4: Preprocessing

Once a useful feature set exists, evaluate preprocessing choices only where they are necessary or likely to matter.

Examples include scaling and alternative missing-value strategies.

Preprocessing decisions must be fit using training data only.

### Phase 5: Model comparison

Compare model families under the same feature definitions, preprocessing, and validation procedure.

Start with interpretable models and add complexity only when it provides repeatable improvement.

### Phase 6: Hyperparameter tuning

Tune the selected model family only after the feature and model-family comparisons are stable.

Hyperparameter search should use validation data, not prospective test results.

### Phase 7: Probability and decision quality

Evaluate probability quality using calibration-aware metrics and determine whether the default classification threshold of `0.5` is appropriate for the eventual decision objective.

Threshold selection should happen only after the probability model itself is reasonably stable.

### Phase 8: Live prediction

Build a reproducible workflow that obtains all required pre-race inputs, generates probabilities before the prediction cutoff, stores the prediction artifact, and scores it after the result becomes available.

## Experiment Records

As the number of experiments grows, each run should eventually record enough information to reproduce the comparison:

```text
feature set
feature parameters
preprocessing
training period
validation periods
model family
hyperparameters
decision threshold
pooled metrics
per-season metrics
model/code version
```

This should ultimately be generated from code rather than maintained manually in documentation.

## Current Priority

Phase 1 feature integrity, the Phase 2 grid-versus-form comparison, and the
initial expanding-window walk-forward validation are complete. The current
five-race form feature improves two validation seasons but regresses in 2024,
so it does not show consistent incremental accuracy across all three folds.
The result and its interpretation are recorded in `docs/decisions.md`.

Do not use the repeatedly inspected 2025-onward holdout to choose the next
configuration; it remains an out-of-time reference. Before implementation,
define one focused modeling hypothesis and change only the experiment dimension
needed to test that question. Do not select a final feature set or model from
the current mixed form result alone.
