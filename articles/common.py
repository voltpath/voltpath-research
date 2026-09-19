import getpass
import hashlib
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.voltpath.ai"
API_KEY = os.environ.get("VOLTPATH_API_KEY") or getpass.getpass("Voltpath API key (from voltpath.ai): ")
HEADERS = {"x-api-key": API_KEY} if API_KEY else {}

FLOW_COLORS = {
    "Convergence": "#08415C",
    "Congestion": "#CC2936",
    "Counter-intuitive": "#6B818C",
    "Outage": "#F1BF98",
}

# Distinct from all flow-type colors above, used for the avg-price overlay line.
PRICE_LINE = {"color": "#000000", "dash": "dot"}

CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)


def _cache_path(date_from: str, date_to: str, resolution: str | None) -> Path:
    key = hashlib.sha1(f"{date_from}|{date_to}|{resolution}".encode()).hexdigest()
    return CACHE_DIR / f"{key}.parquet"


def fetch_flows(date_from: str, date_to: str, resolution: str | None = None, refresh: bool = False) -> pd.DataFrame:
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
    resp = requests.get(f"{BASE_URL}/api/v1/flows", headers=HEADERS, params=params, timeout=60)
    for _ in range(10):
        if resp.status_code != 429:
            break
        # + jitter: concurrent workers all sleeping the same Retry-After
        # wake up together and re-collide on the 2/sec bucket otherwise.
        time.sleep(float(resp.headers.get("Retry-After", 1)) + random.uniform(0, 0.5))
        resp = requests.get(f"{BASE_URL}/api/v1/flows", headers=HEADERS, params=params, timeout=60)
    resp.raise_for_status()

    df = pd.DataFrame(resp.json()["data"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["border"] = df["bidding_zone_from"] + " -> " + df["bidding_zone_to"]

    diffs_h = df.sort_values("datetime").groupby("border")["datetime"].diff().dt.total_seconds() / 3600
    median_cadence = diffs_h.groupby(df["border"]).transform("median")
    df["duration_h"] = diffs_h.fillna(median_cadence)

    df["volume_mwh"] = df["net_flow_mw"].abs() * df["duration_h"]
    df["value_eur"] = df["price_delta"] * df["net_flow_mw"] * df["duration_h"]

    df.to_parquet(cache_file)
    return df


def fetch_flows_range(date_from: str, date_to: str, chunk_days: int = 1, max_workers: int = 2) -> pd.DataFrame:
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
    ranges = [(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")) for start, end in zip(days[:-1], days[1:])]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        frames = list(pool.map(lambda r: fetch_flows(r[0], r[1], resolution="native"), ranges))
    return pd.concat(frames, ignore_index=True)


def hourly_border_counts(df: pd.DataFrame, flow_type: str) -> pd.DataFrame:
    subset = df[df["flow_type"] == flow_type]
    return subset.groupby("datetime")["border"].nunique().rename("n_borders").reset_index()


def peak(counts: pd.DataFrame) -> pd.Series:
    return counts.loc[counts["n_borders"].idxmax()]


def border_count_price_chart(
    df: pd.DataFrame, flow_type: str, title: str, peak_vline: str | None = None
) -> go.Figure:
    """Hourly border count for one flow_type vs. average day-ahead price, dual y-axis.

    `title` should already describe the flow_type and date; `peak_vline`
    (e.g. "2023-02-22 13:00:00") draws a dashed marker at a reference hour.
    """
    counts = hourly_border_counts(df, flow_type)
    avg_price = df.groupby("datetime")[["price_from", "price_to"]].mean().mean(axis=1)

    fig = px.line(
        counts,
        x="datetime",
        y="n_borders",
        title=title,
        labels={"n_borders": f"Borders {flow_type.lower()}", "datetime": "Time"},
        color_discrete_sequence=[FLOW_COLORS[flow_type]],
    )
    fig.update_traces(name=f"Borders {flow_type.lower()}", showlegend=True)
    fig.add_scatter(
        x=avg_price.index.to_pydatetime(),
        y=avg_price.values,
        name="Avg price (EUR/MWh)",
        yaxis="y2",
        line=PRICE_LINE,
    )
    fig.update_layout(
        yaxis2=dict(title="Avg price (EUR/MWh)", overlaying="y", side="right"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    if peak_vline:
        fig.add_vline(x=peak_vline, line_dash="dash", annotation_text="Bertelli's reported peak")
    return fig


def flow_type_summary(df: pd.DataFrame, flow_type: str) -> pd.DataFrame:
    """Per-border leaderboard metrics for one flow_type, over whatever date range `df` covers.

    Returns one row per border with four unsorted metrics; sort by whichever
    fits the question you're asking:

    - n_hours: total hours the border spent in this flow_type (sum of
      duration_h, so it's correct regardless of the API's time resolution -
      counting rows instead would inflate this at sub-hourly resolutions).
      This is the metric Bertelli's articles rank by, but count alone
      conflates a border that's flagged often at trivial volume/price with
      one flagged rarely but at huge cost - it answers "how often" not
      "how much it matters".
    - volume_mwh: total MW x duration flagged. Answers "how much energy
      moved while flagged", regardless of price.
    - implied_value_eur: total abs(price_delta x net_flow_mw x duration_h).
      The welfare/cost measure - price x volume - answers "how much this
      was worth economically", which is the one that actually matters for
      "is this a real problem" framing.
    - avg_value_per_hour_eur: implied_value_eur / n_hours. Surfaces borders
      that are rarely flagged but brutally expensive when they are, which
      both n_hours and the cumulative implied_value_eur can hide (a border
      hit once a year for EUR 500k ranks low on count and can rank low on
      cumulative value too, but is arguably the most urgent single case).
    """
    subset = df[df["flow_type"] == flow_type]
    out = (
        subset.groupby("border")
        .agg(
            n_hours=("duration_h", "sum"),
            volume_mwh=("volume_mwh", "sum"),
            implied_value_eur=("value_eur", lambda s: s.abs().sum()),
        )
        .reset_index()
    )
    out["avg_value_per_hour_eur"] = out["implied_value_eur"] / out["n_hours"]
    return out


def convergence_summary(df: pd.DataFrame) -> pd.DataFrame:
    total_hours = df.groupby("border")["duration_h"].sum()
    conv = df[df["flow_type"] == "Convergence"]
    out = conv.groupby("border").agg(volume_mwh=("volume_mwh", "sum"), converged_hours=("duration_h", "sum"))
    out["share_converged"] = out["converged_hours"] / total_hours.reindex(out.index)
    return out.sort_values("volume_mwh", ascending=False).reset_index()
