"""Voltpath API access: auth, rate-limit handling, disk caching."""

import getpass
import hashlib
import itertools
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.voltpath.ai"
API_KEY = os.environ.get("VOLTPATH_API_KEY") or getpass.getpass(
    "Voltpath API key (from voltpath.ai): "
)
HEADERS = {"x-api-key": API_KEY} if API_KEY else {}

# One level up from this package (articles/.cache), shared across all articles
# and across the api.py -> common/api.py split so existing caches keep working.
CACHE_DIR = Path(__file__).parent.parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)


def _cache_path(date_from: str, date_to: str, resolution: str | None) -> Path:
    key = hashlib.sha1(f"{date_from}|{date_to}|{resolution}".encode()).hexdigest()
    return CACHE_DIR / f"{key}.parquet"


def fetch_flows(
    date_from: str, date_to: str, resolution: str | None = None, refresh: bool = False
) -> pd.DataFrame:
    """Fetch one date range from /api/v1/flows, cached to disk by request params.

    Re-running a notebook top to bottom is the normal workflow, so by default
    this reuses whatever's already on disk instead of re-hitting the API.
    Pass refresh=True to bypass the cache for one call (e.g. checking for new data).
    """
    cache_file = _cache_path(date_from, date_to, resolution)
    if cache_file.exists() and not refresh:
        return pd.read_parquet(cache_file)

    params = {"datetime_from": date_from, "datetime_to": date_to}
    if resolution:
        params["resolution"] = resolution

    # Server is a token bucket, capacity 200, refill 2 req/sec per API key
    # (apps/api/src/api/main.py:97-98). A 429 response carries an exact
    # Retry-After (seconds) - honor that instead of guessing a backoff.
    resp = requests.get(
        f"{BASE_URL}/api/v1/flows", headers=HEADERS, params=params, timeout=60
    )
    for _ in range(10):
        if resp.status_code != 429:
            break
        # + jitter: concurrent workers all sleeping the same Retry-After
        # wake up together and re-collide on the 2/sec bucket otherwise.
        time.sleep(float(resp.headers.get("Retry-After", 1)) + random.uniform(0, 0.5))
        resp = requests.get(
            f"{BASE_URL}/api/v1/flows", headers=HEADERS, params=params, timeout=60
        )
    resp.raise_for_status()

    df = pd.DataFrame(resp.json()["data"])
    if df.empty:
        df.to_parquet(cache_file)
        return df
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["border"] = df["bidding_zone_from"] + " -> " + df["bidding_zone_to"]

    diffs_h = (
        df.sort_values("datetime")
        .groupby("border")["datetime"]
        .diff()
        .dt.total_seconds()
        / 3600
    )
    median_cadence = diffs_h.groupby(df["border"]).transform("median")
    df["duration_h"] = diffs_h.fillna(median_cadence)

    df["volume_mwh"] = df["net_flow_mw"].abs() * df["duration_h"]
    df["value_eur"] = df["price_delta"] * df["net_flow_mw"] * df["duration_h"]

    df.to_parquet(cache_file)
    return df


def fetch_flows_range(
    date_from: str, date_to: str, chunk_days: int = 1, max_workers: int = 2
) -> pd.DataFrame:
    """Native-resolution fetch over a wide range, chunked day by day, fetched in parallel.

    The API's default resolution aggregates to ~daily points, which makes
    hour-counts meaningless (every border active at all gets capped at
    "days in range"). `resolution=native` gives real 15-min data, but the
    backing Lambda has a 30s timeout and a 6MB response cap with no
    pagination (see voltpath-api issue), so wide ranges 502 once the
    payload gets too big. Safe chunk size depends on how much data exists
    for that period, not just day count, so day-by-day is the only size
    that's reliably safe across any range - fetched with a thread pool
    since a year is ~365 sequential requests otherwise.

    Rate limit is a per-key token bucket: 200 capacity, 2 req/sec refill
    (apps/api/src/api/main.py:97-98). A year of requests burns the 200
    burst instantly then throttles to 2/sec (~80s for the remaining ~165).
    `fetch_flows` reads the exact `Retry-After` header on 429, but with too
    many concurrent workers they all wake up from the same Retry-After and
    re-collide on the bucket - keep max_workers low (default 2, matching
    the refill rate) so retries stay rare instead of retry-storming.

    Each day is cached individually by `fetch_flows`, so re-running over a
    range you've already pulled costs no API calls at all.
    """
    days = pd.date_range(date_from, date_to, freq=f"{chunk_days}D")
    ranges = [
        (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        for start, end in itertools.pairwise(days)
    ]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        frames = list(
            pool.map(lambda r: fetch_flows(r[0], r[1], resolution="native"), ranges)
        )
    return pd.concat(frames, ignore_index=True)
