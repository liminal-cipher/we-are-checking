"""Pull F1 race classifications from Jolpica into one parquet file per season.

Output is one row per driver per race, written to
``data/raw/race_results/season=YYYY.parquet``.

Jolpica is volunteer-run (burst 4 req/s, sustained 500 req/hour), so this
script is built to be cheap to re-run: a season whose file already exists is
skipped unless it is the current season or is named in ``--refresh``. A season
costs about five requests, so this is the difference between roughly 45
requests per run and roughly five.

Usage::

    python scripts/pull_race_results.py                 # fill gaps + current season
    python scripts/pull_race_results.py --refresh 2019  # refetch one season
    python scripts/pull_race_results.py --refresh all   # refetch everything
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import fastf1
from fastf1.ergast import Ergast

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "data" / "raw" / "race_results"
DEFAULT_CACHE = REPO_ROOT / "cache"

FIRST_SEASON = 2018

# Jolpica allows 4 requests/second in a burst. We stay far below that: the
# whole job is a handful of requests, so there is nothing to gain by crowding
# the limit.
SECONDS_BETWEEN_REQUESTS = 0.5

# Jolpica caps a page at 100 rows and silently clamps anything larger, so a
# season of roughly 420 driver-race rows takes about five requests. (The
# documented 1000 was the old Ergast limit; asking for it here just gets 100.)
PAGE_SIZE = 100

log = logging.getLogger("pull_race_results")


def season_path(out_dir: Path, season: int) -> Path:
    """Hive-style partition name, so the directory reads as one dataset."""
    return out_dir / f"season={season}.parquet"


def fetch_season(ergast: Ergast, season: int) -> pd.DataFrame:
    """Return every driver's classification for every race in one season.

    The endpoint returns a race-level description frame alongside a list of
    per-race result frames. We broadcast the description onto its results so
    that the output is flat: one row per driver per race.
    """
    frames: list[pd.DataFrame] = []
    page = 1
    offset = 0
    total = 0

    while True:
        # Paginate on an explicit offset rather than on `is_complete` or
        # `get_next_result_page()`. Those describe whether one *response* holds
        # everything, so on a paginated season `is_complete` stays False even
        # on the final page and asking for a further page raises.
        response = ergast.get_race_results(
            season=season, limit=PAGE_SIZE, offset=offset
        )
        total = response.total_results
        rows_this_page = 0

        for i, results in enumerate(response.content):
            race = response.description.iloc[[i]].reset_index(drop=True)

            # Race-level and driver-level frames share some column names
            # (season/round are unambiguous, but e.g. 'time' means race start
            # time on one side and finishing time on the other). Prefix the
            # race-level side rather than silently dropping either.
            clashes = [c for c in race.columns if c in results.columns]
            if clashes:
                race = race.rename(columns={c: f"race_{c}" for c in clashes})

            flat = results.copy()
            for col in race.columns:
                flat[col] = race.at[0, col]
            frames.append(flat)
            rows_this_page += len(results)

        log.info(
            "season %d page %d: %d race(s), %d row(s), %d total reported",
            season,
            page,
            len(response.content),
            rows_this_page,
            total,
        )

        offset += rows_this_page
        if rows_this_page == 0 or offset >= total:
            break
        time.sleep(SECONDS_BETWEEN_REQUESTS)
        page += 1

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    if len(df) != total:
        # A page boundary can cut a race in half, which is fine, but a mismatch
        # here means rows were lost or doubled. Loud, because a silently short
        # season would look like a real gap in the sport's history downstream.
        log.warning(
            "season %d: assembled %d rows but the API reported %d",
            season,
            len(df),
            total,
        )
    return df


def seasons_to_pull(
    start: int,
    end: int,
    out_dir: Path,
    refresh: set[int] | None,
    current_season: int,
) -> list[int]:
    """Decide which seasons actually need a request.

    A completed season's classifications do not change, so an existing file is
    treated as final. The current season is always refetched because rounds
    keep being added to it.
    """
    wanted = []
    for season in range(start, end + 1):
        path = season_path(out_dir, season)
        if refresh is not None and (not refresh or season in refresh):
            reason = "explicitly refreshed"
        elif not path.exists():
            reason = "missing"
        elif season >= current_season:
            reason = "current season, may have new rounds"
        else:
            log.info("season %d: up to date, skipping", season)
            continue
        log.info("season %d: fetching (%s)", season, reason)
        wanted.append(season)
    return wanted


def parse_refresh(value: str | None) -> set[int] | None:
    """``None`` means no refresh; an empty set means refresh everything."""
    if value is None:
        return None
    if value.strip().lower() == "all":
        return set()
    return {int(part) for part in value.replace(",", " ").split()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=int, default=FIRST_SEASON)
    parser.add_argument(
        "--end",
        type=int,
        default=None,
        help="last season to pull, inclusive (default: current year)",
    )
    parser.add_argument(
        "--refresh",
        default=None,
        metavar="SEASONS",
        help="'all', or a list of seasons to refetch even if already on disk",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    current_season = datetime.now(timezone.utc).year
    end = args.end if args.end is not None else current_season

    args.cache.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    # Caches the HTTP responses themselves, so a re-run within the cache's
    # lifetime costs nothing even when it does decide to refetch.
    fastf1.Cache.enable_cache(str(args.cache))

    ergast = Ergast(result_type="pandas", auto_cast=True)

    written = 0
    for season in seasons_to_pull(
        args.start, end, args.out, parse_refresh(args.refresh), current_season
    ):
        df = fetch_season(ergast, season)
        if df.empty:
            log.info("season %d: no races returned, nothing written", season)
            continue
        path = season_path(args.out, season)
        df.to_parquet(path, index=False)
        log.info("season %d: wrote %d rows to %s", season, len(df), path.name)
        written += 1
        time.sleep(SECONDS_BETWEEN_REQUESTS)

    log.info("done, %d season file(s) written", written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
