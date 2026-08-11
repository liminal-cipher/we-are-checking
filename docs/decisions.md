# Decisions

Non-obvious choices, newest last. Each entry states the situation, the call,
the reason, and the condition that should make us reopen it.

Obvious choices are not recorded here. If a reasonable person would have made
the same call without thinking, it does not need an entry.

## 2026-08-11 Data source is Jolpica through FastF1's Ergast interface

**Context.** Race results 2018 to present are needed, one row per driver per
race. Three routes exist: FastF1's session timing data, raw HTTP against
Jolpica, or FastF1's `Ergast` wrapper around Jolpica.

**Decision.** Use `fastf1.ergast.Ergast`. Despite the name, FastF1 points this
class at Jolpica (`api.jolpi.ca/ergast/f1/`) since the original Ergast API was
deprecated at the end of 2024.

**Why.** Session timing data is per-lap telemetry: far heavier than needed for
a classification label, and it requires one session load per race. The Ergast
endpoint returns a whole season of classifications in about five requests. Raw
HTTP would mean reimplementing pagination, response parsing, type casting, and
rate limiting, all of which FastF1 already does.

**Revisit if.** We need data the classification endpoint does not carry (tire
compounds, sector times, weather). Those live in session data, not here, and
would be a second loader rather than a replacement for this one.

## 2026-08-11 Parsed results are committed, the HTTP cache is not

**Context.** The pull produces two artifacts: FastF1's raw HTTP cache and
parsed per-season parquet files. Predictions are generated in GitHub Actions
before each round, so CI also needs the history.

**Decision.** Commit `data/raw/race_results/season=YYYY.parquet`. Gitignore
`cache/`.

**Why.** If the parquet is not committed, every CI run refetches nine seasons
from a volunteer-run API to predict one race. Committing it means CI fetches
only the current season. The files are small (roughly four thousand rows total,
well under a megabyte) so the usual objection to data in git does not apply.
The HTTP cache is machine-local, larger, and rebuildable, so it stays out.

**Revisit if.** The committed data grows past a few megabytes, or we start
storing per-lap data. At that point this becomes a release artifact or a cache
restored by `actions/cache`, not a tracked file.

## 2026-08-11 Completed seasons are never refetched

**Context.** Jolpica is volunteer-run with a sustained limit of 500 requests
per hour. A naive loop refetches all seasons on every run.

**Decision.** A season parquet that already exists on disk is skipped unless
`--refresh` is passed. Only the current season is refetched by default, because
it is the only one that can still change.

**Why.** Past classifications are immutable in practice. Refetching them costs
the API and buys nothing. A season is about five requests, so this is the
difference between roughly 45 requests per run and roughly five.

**Revisit if.** A historical result is amended after the fact (post-season
appeals and disqualifications do happen). `--refresh 2019` handles the one-off
case without weakening the default.

## 2026-08-11 Repo is MIT, the data under it is not

**Context.** Committing the parquet means redistributing Jolpica's data.
Jolpica licenses its data CC BY-NC-SA 4.0, which is share-alike and
non-commercial. The repo's own code is MIT.

**Decision.** Keep MIT in `LICENSE` for the code. State the data's separate
license and its attribution in the README's Data section and in
`data/raw/README.md`, next to the files it covers.

**Why.** Relicensing someone else's data by dropping it into an MIT repo is not
something we get to do. Two licenses in one repo is normal as long as the
boundary is written down where a reader will hit it.

**Revisit if.** This project is ever used commercially, which the NC clause
forbids. That would mean dropping the committed data and fetching at runtime,
or moving to a differently-licensed source.

## 2026-08-11 Lagged features come before pulling qualifying data

**Context.** The race results table holds one column that is knowable before a
race starts: `grid`. Everything else is either an identifier or an outcome.
There are two ways to get more input: derive it from earlier rounds, or pull
Jolpica's qualifying endpoint for Q1/Q2/Q3 lap times.

**Decision.** Build the lagged features first. The qualifying loader waits
until they exist and have been scored.

**Why.** Qualifying times are strong enough that adding them at the same time
as the first hand-built features would make the two indistinguishable: if the
model improves, we would not know which change did it. Starting with a thin
input set also makes leakage easier to see, because there are few enough
columns to check each one by hand.

**Revisit if.** The lagged features fail to beat a grid-only baseline. That
would be a signal that the information is not in the results table, which is
the case for adding qualifying rather than an argument against it.

## 2026-08-11 Pagination is driven by an explicit offset

**Context.** FastF1's response objects expose `is_complete` and
`get_next_result_page()`, which read like the intended pagination loop. They
are not. `is_complete` asks whether *this response* holds every result, so on
any season that spans pages it stays `False` even on the last page, and the
follow-up call then raises `ValueError: No more data after this response`.

Separately, Jolpica caps a page at 100 rows and silently clamps a larger
`limit`. The documented maximum of 1000 was Ergast's, and asking for it yields
100 with no error and no warning.

**Decision.** Track `offset` and the row count in the loop, and stop when
`offset >= total_results`. Assert the assembled row count matches
`total_results` and log loudly if it does not.

**Why.** The library's own helpers produce a crash on any multi-page season,
which is every season. The row-count assertion exists because the failure this
guards against is silent: a season short by one page looks like a gap in the
sport's history to everything downstream, not like an error.

**Revisit if.** FastF1 changes what `is_complete` means, or Jolpica raises the
page cap. Neither would break this loop, so this is worth revisiting only to
reduce request count.

## 2026-08-11 One parquet per season, not one file for everything

**Context.** The pull could write a single `race_results.parquet` or one file
per season.

**Decision.** One file per season, named `season=YYYY.parquet`.

**Why.** It makes "skip what we already have" a file-existence check rather
than a read-filter-append cycle, and it keeps the diff of a mid-season update
to a single file instead of rewriting the whole history on every round. The
`season=YYYY` naming is the Hive partition convention, so pandas and pyarrow
can read the directory as one partitioned dataset later without renaming.

**Revisit if.** We start needing cross-season reads often enough that opening
nine files is friction. `pd.read_parquet` on the directory already handles it,
so this is unlikely.
