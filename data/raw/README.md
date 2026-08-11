# Raw Data

Files here are produced by `scripts/pull_race_results.py` and are tracked in
git on purpose, so that CI does not refetch nine seasons of history from a
volunteer-run API in order to predict one race.

## Attribution and License

Source: [Jolpica-F1](https://github.com/jolpica/jolpica-f1), the
Ergast-compatible successor to the Ergast Developer API.

Jolpica's data is licensed
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/):
attribution required, non-commercial use only, derivatives share alike.

**That license applies to these files, not the MIT license in the repo root.**
The MIT license covers this repository's code. Anything derived from the data
in this directory carries Jolpica's terms with it, including the
non-commercial restriction.

## Layout

`race_results/season=YYYY.parquet`, one row per driver per race. The
`season=YYYY` naming is the Hive partition convention, so the directory can be
read as a single dataset:

```python
import pandas as pd
df = pd.read_parquet("data/raw/race_results/")
```

Completed seasons are not refetched. See `docs/decisions.md`.
