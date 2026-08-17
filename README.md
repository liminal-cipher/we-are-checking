# We Are Checking

> Pre-race top-10 predictions committed before every round, calibration tracked across the season

![Python](https://img.shields.io/badge/python-3.12-blue)
![Data](https://img.shields.io/badge/data-Jolpica--F1-e10600)
![License](https://img.shields.io/badge/license-MIT-green)

## Motivation

A prediction that is written down after the race is not a prediction. Most
casual forecasting fails this way: the reasoning feels right in hindsight, and
nothing ever gets scored.

This project takes one narrow, repeatable question, will this driver finish in
the top 10, and forces an answer into a commit before the lights go out. Every
round leaves a timestamped record that cannot be edited after the result is
known. Across a season those records are enough to ask the question that
actually matters: when the model says 70 percent, does it happen 70 percent of
the time?

Top 10 is the target because it is the points boundary, so it is the split the
sport itself cares about, and because it stays close enough to balanced that
accuracy is not trivially gamed by always guessing "no".

The name is team radio boilerplate: what an engineer says when a driver asks
whether a rival is under investigation, usually meaning nobody has checked yet.

*Here, we really are.*

## What It Does

- Pulls race classifications from 2018 to the present, one row per driver per
  race, and caches them locally as parquet.
- Builds pre-race features, using only information available before the race
  starts.
- Emits a top-10 probability per driver, committed to the repo before each
  round.
- Scores the season's committed predictions for calibration, not just accuracy.

Today the first exists as a script, and the second is taking shape in the
exploration notebook along with a time split, a baseline, and a first
fitted model. No prediction has been committed yet. The rest is tracked in
Roadmap.

## Architecture

```
Jolpica (Ergast-compatible API)
        |
        v
scripts/pull_race_results.py     one request per season, cached
        |
        v
data/raw/race_results/           season=YYYY.parquet, committed
        |
        v
feature engineering              pre-race only
        |
        v
classifier                       P(top 10) per driver
        |
        v
predictions/YYYY/round-NN.csv    committed before the race
        |
        v
calibration report               committed predictions vs. actual results
```

## Tech Decisions

| Component | Choice | Why this over alternatives |
|---|---|---|
| Data source | FastF1's `Ergast` class, pointed at Jolpica | Session timing data is per-lap telemetry, far heavier than a finishing position needs. Raw HTTP would mean rewriting pagination, parsing, and rate limiting that FastF1 already has |
| Storage | One parquet per season, committed to git | Lets "already have it" be a file-existence check, and keeps a mid-season update to a one-file diff. Committed so CI does not refetch nine seasons of history to predict one race |
| Refetch policy | Completed seasons are never refetched | Past classifications are immutable in practice. Steady-state cost of a pull is about 5 requests instead of 45, which matters against a volunteer-run API |
| Prediction storage | Plain CSV in git, one file per round | The commit timestamp is the evidence that the prediction preceded the race. A database would need a separate trust story |

Fuller versions of these, with the conditions that should reopen them, are in
[docs/decisions.md](docs/decisions.md).

## Intended Use / Out of Scope

This is a personal exercise in running an ML workflow end to end, with the
calibration discipline made explicit.

It does not advise betting, and it is not built to. Nothing here models odds,
stakes, or the bookmaker's margin, and a model that is well calibrated on
historical races is not thereby profitable on a betting market.

It also does not predict finishing order, race pace, incidents, or anything
about a specific driver's future. It answers one binary question per driver per
race, and only for races on the Jolpica calendar.

## Data

| | |
|---|---|
| Source | [Jolpica-F1](https://github.com/jolpica/jolpica-f1), the Ergast-compatible successor to the deprecated Ergast API |
| Accessed via | `fastf1.ergast.Ergast` |
| Coverage | 2018 to present, one row per driver per race |
| Scale | roughly 20 drivers x 21 to 24 rounds per season |
| Committed | yes, `data/raw/race_results/` is tracked (see decisions.md) |
| Split strategy | time split: train through 2024, test 2025 onward (721 rows), scored pooled and per season |

**Data license differs from this repo's.** The code here is MIT. Jolpica's data
is licensed CC BY-NC-SA 4.0, which is share-alike and non-commercial, and that
license travels with the parquet files under `data/`. Jolpica is volunteer-run
and rate limited to 4 requests per second and 500 per hour, which is why the
pull script is built to skip work rather than repeat it.

## Evaluation

Partly in place, written by hand in the notebook and recorded in
decisions.md:

- **Metric**: accuracy for now, because the baseline is a hard rule that
  cannot produce probabilities. Calibration becomes the metric once
  predicted probabilities are committed.
- **Split**: train is every season through 2024 (2,979 rows), test is 2025
  onward (721 rows). Every score is read pooled and per season, so the
  2026 regulation reset is never averaged away.
- **Leakage controls**: features use only pre-race information; the lagged
  feature is verified against a plain-Python rebuild in the notebook; and
  any number a model consumes (such as the NaN fill value) is computed on
  train only.
- **Baseline**: predict a top-10 finish exactly when `grid <= 10`.

Still open: seeds and run counts (nothing stochastic is in use yet), and
the calibration protocol itself.

The one thing fixed from the start is that the season's scoring runs
against the committed prediction files, not against predictions
regenerated later.

## Results

First numbers, measured on the test set (2025 onward, 721 rows):

| Model | Pooled | 2025 | 2026 |
|---|---|---|---|
| Rule: `grid <= 10` | **0.7725** | 0.779 | 0.760 |
| Logistic regression: form only | 0.6976 | 0.685 | 0.723 |

Form is the share of the driver's previous five races that ended in the
top 10, with a driver's first five races filled by the train base rate.
Losing by 7.5 points reads as "where you start this weekend carries more
information than how your last five races went", not as form being
useless. Whether form adds anything on top of grid is the comparison
currently in progress.

No prediction has been committed yet.

## Model & Inference

Classifier not yet selected; the first candidate under test is a plain
logistic regression. Inference is intended to run in GitHub Actions
before each round, so the constraint it will be chosen under is that a full
refit plus prediction fits comfortably in a free-tier runner without a GPU.

## Getting Started

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows; use source .venv/bin/activate elsewhere
pip install -r requirements.txt

python scripts/pull_race_results.py
```

The first run fetches every season from 2018 and writes
`data/raw/race_results/season=YYYY.parquet`. Later runs refetch only the
current season. `--refresh 2019` forces one season, `--refresh all` forces all
of them. HTTP responses are cached under `cache/`, which is not tracked.

No API key or environment variable is needed. Jolpica is open and
unauthenticated.

For exploration, `pip install -r requirements-dev.txt` adds JupyterLab, and
`notebooks/01-explore.ipynb` loads the parquet directory into one frame.
Notebooks are scratch space: anything worth keeping graduates to `scripts/`.
Run `nbstripout --install` once after cloning; it activates the filter that
keeps notebook outputs out of commits (outputs stay in your working copy).

## Responsible AI

The data is public sporting results. It carries the names of professional
drivers acting in their public capacity, and no personal data beyond that, so
there is nothing here to anonymize or expire.

The live risk in a project like this is not privacy but overclaiming. A
probability presented without its calibration record invites more confidence
than it has earned, which is the specific failure this repo is built to make
visible rather than to avoid mentioning. Committed predictions are never
edited or deleted after the fact, including the bad ones.

## Roadmap

- [x] Repo scaffolding, data pull, one parquet per season
- [ ] Pre-race feature set, with a written argument that each feature is knowable before the race (first feature built and scored)
- [x] Train and test split that respects time order
- [x] Baseline to beat (grid position alone)
- [ ] Calibration report, committed predictions vs. results
- [ ] GitHub Actions workflow that commits predictions before each round

## Status

In progress. Personal project, started 2026-08-11. The data loader runs; the
first feature, the time split, the grid-rule baseline, and a first fitted
model live in the exploration notebook. No prediction has been committed
yet. Last updated 2026-08-17.

## License

MIT, see [LICENSE](LICENSE). This covers the code. Data under `data/` is
Jolpica's and is licensed CC BY-NC-SA 4.0, see
[data/raw/README.md](data/raw/README.md).
