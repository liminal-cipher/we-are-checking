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

Today only the first of these exists. The rest are tracked in Roadmap.

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
| Split strategy | not yet designed |

**Data license differs from this repo's.** The code here is MIT. Jolpica's data
is licensed CC BY-NC-SA 4.0, which is share-alike and non-commercial, and that
license travels with the parquet files under `data/`. Jolpica is volunteer-run
and rate limited to 4 requests per second and 500 per hour, which is why the
pull script is built to skip work rather than repeat it.

## Evaluation

Not yet designed. This section is deliberately empty rather than deleted: the
evaluation protocol is the part of the project being written by hand, and it
will record the metric and why it was chosen, the train and test split, the
leakage controls, the baseline being beaten, and the seeds and run count.

The one thing already fixed is that the season's scoring runs against the
committed prediction files, not against predictions regenerated later.

## Results

Not yet measured. No model has been trained and no prediction has been
committed.

## Model & Inference

Classifier not yet selected. Inference is intended to run in GitHub Actions
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
- [ ] Pre-race feature set, with a written argument that each feature is knowable before the race
- [ ] Train and test split that respects time order
- [ ] Baseline to beat (grid position alone)
- [ ] Calibration report, committed predictions vs. results
- [ ] GitHub Actions workflow that commits predictions before each round

## Status

In progress. Personal project, started 2026-08-11. Only the data loader runs
today; no model has been trained and no prediction has been committed. Last
updated 2026-08-11.

## License

MIT, see [LICENSE](LICENSE). This covers the code. Data under `data/` is
Jolpica's and is licensed CC BY-NC-SA 4.0, see
[data/raw/README.md](data/raw/README.md).
