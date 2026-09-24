import getpass
import hashlib
import itertools
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from dotenv import load_dotenv
from plotly.subplots import make_subplots

load_dotenv()

BASE_URL = "https://api.voltpath.ai"
API_KEY = os.environ.get("VOLTPATH_API_KEY") or getpass.getpass(
    "Voltpath API key (from voltpath.ai): "
)
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

# Approximate CCR-style regions for voltpath's zone codes, colors eyeballed off
# ENTSO-E's public CCR map (entsoe.eu/bites/ccr-map). This is a best-effort
# geographic grouping for charting, not the real (overlapping) CCR membership
# - several TSOs legally sit in more than one CCR, which a one-region-per-zone
# map can't represent, so borders that cross a region boundary are bucketed
# as "Cross-region" rather than forced into either side.
REGION_COLORS = {
    "Nordic": "#8FBF87",
    "Baltic": "#D98888",
    "Core": "#7EC8D8",
    "Italy North": "#F0A857",
    "Greece-Italy": "#93A6DE",
    "South-East Europe": "#B58FC4",
    "South-West Europe": "#A9D9B0",
    "Cross-region": "#B0B0B0",
}

ZONE_REGIONS = {
    "NO_1": "Nordic",
    "NO_2": "Nordic",
    "NO_3": "Nordic",
    "NO_4": "Nordic",
    "NO_5": "Nordic",
    "SE_1": "Nordic",
    "SE_2": "Nordic",
    "SE_3": "Nordic",
    "SE_4": "Nordic",
    "DK_1": "Nordic",
    "DK_2": "Nordic",
    "FI": "Nordic",
    "EE": "Baltic",
    "LV": "Baltic",
    "LT": "Baltic",
    "DE_LU": "Core",
    "AT": "Core",
    "CH": "Core",
    "CZ": "Core",
    "PL": "Core",
    "HU": "Core",
    "BE": "Core",
    "NL": "Core",
    "SK": "Core",
    "IT_NORD": "Italy North",
    "IT_CNOR": "Greece-Italy",
    "IT_CSUD": "Greece-Italy",
    "IT_SUD": "Greece-Italy",
    "IT_CALA": "Greece-Italy",
    "IT_SICI": "Greece-Italy",
    "IT_SARD": "Greece-Italy",
    "GR": "Greece-Italy",
    "RO": "South-East Europe",
    "BG": "South-East Europe",
    "SI": "South-East Europe",
    "HR": "South-East Europe",
    "RS": "South-East Europe",
    "ME": "South-East Europe",
    "MK": "South-East Europe",
    "AL": "South-East Europe",
    "FR": "South-West Europe",
    "ES": "South-West Europe",
    "PT": "South-West Europe",
}

# Country each zone belongs to - splits multi-zone countries (NO_1..5, SE_1..4,
# DK_1..2, IT_*) back to one country label; DE_LU is voltpath's joint
# Germany-Luxembourg zone, kept as-is rather than guessed apart.
ZONE_COUNTRIES = {
    "NO_1": "Norway",
    "NO_2": "Norway",
    "NO_3": "Norway",
    "NO_4": "Norway",
    "NO_5": "Norway",
    "SE_1": "Sweden",
    "SE_2": "Sweden",
    "SE_3": "Sweden",
    "SE_4": "Sweden",
    "DK_1": "Denmark",
    "DK_2": "Denmark",
    "FI": "Finland",
    "EE": "Estonia",
    "LV": "Latvia",
    "LT": "Lithuania",
    "DE_LU": "Germany-Luxembourg",
    "AT": "Austria",
    "CH": "Switzerland",
    "CZ": "Czechia",
    "PL": "Poland",
    "HU": "Hungary",
    "BE": "Belgium",
    "NL": "Netherlands",
    "SK": "Slovakia",
    "IT_NORD": "Italy",
    "IT_CNOR": "Italy",
    "IT_CSUD": "Italy",
    "IT_SUD": "Italy",
    "IT_CALA": "Italy",
    "IT_SICI": "Italy",
    "IT_SARD": "Italy",
    "GR": "Greece",
    "RO": "Romania",
    "BG": "Bulgaria",
    "SI": "Slovenia",
    "HR": "Croatia",
    "RS": "Serbia",
    "ME": "Montenegro",
    "MK": "North Macedonia",
    "AL": "Albania",
    "FR": "France",
    "ES": "Spain",
    "PT": "Portugal",
    "UA_IPS": "Ukraine",
}


def border_region(border: str) -> str:
    """Approximate CCR-style region for a border (see ZONE_REGIONS)."""
    zone_from, zone_to = border.split(" -> ")
    region_from = ZONE_REGIONS.get(zone_from, "Cross-region")
    region_to = ZONE_REGIONS.get(zone_to, "Cross-region")
    return region_from if region_from == region_to else "Cross-region"


def border_country(border: str) -> str:
    """Country pair label for a border, e.g. 'France - Spain'."""
    zone_from, zone_to = border.split(" -> ")
    country_from = ZONE_COUNTRIES.get(zone_from, zone_from)
    country_to = ZONE_COUNTRIES.get(zone_to, zone_to)
    return (
        country_from if country_from == country_to else f"{country_from} - {country_to}"
    )


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


def save_chart(fig: go.Figure, name: str, **kwargs) -> None:
    """Write `fig` to this article's `output/` dir as `<name>.png`.

    `output/` is gitignored (see CLAUDE.md) - these are reproducible run
    artifacts, not published assets, so every notebook cell that produces a
    chart should call this alongside (not instead of) `fig.show()`. `name`
    should bake in whatever parameters the cell lets the user vary (e.g.
    the selected month/border/date) so re-running with the same selection
    overwrites the same file instead of piling up duplicates.
    """
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    fig.write_image(out_dir / f"{name}.png", **kwargs)


def drop_ukraine(leaderboard: pd.DataFrame) -> pd.DataFrame:
    """Drop UA_IPS borders from a `flow_type_summary` leaderboard.

    Ukraine's borders (HU/PL/RO/SK -> UA_IPS) have been a special case since
    2022: wartime grid conditions and emergency EU synchronisation drive their
    numbers, not ordinary market congestion, so they can top a leaderboard for
    reasons unrelated to everything else on it.
    """
    return leaderboard[~leaderboard["border"].str.contains("UA_IPS")]


LEADERBOARD_METRICS = [
    ("n_hours", "Hours flagged congested"),
    ("volume_mwh", "Volume flagged (MWh)"),
    ("implied_value_eur", "Congestion rent (EUR)"),
    ("avg_value_per_hour_eur", "Avg rent/hour when congested (EUR, intensity)"),
]


def leaderboard_subplots(
    leaderboard: pd.DataFrame,
    title: str,
    color: str | None = None,
    top_n: int = 10,
    metrics: list[tuple[str, str]] | None = None,
) -> go.Figure:
    """2x2 grid of horizontal top-N bars, one panel per `flow_type_summary` metric.

    The four metrics answer different questions and don't agree with each other
    (see `flow_type_summary`'s docstring), which is the point of showing them
    side by side rather than picking one.
    """
    metrics = metrics or LEADERBOARD_METRICS
    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=[label for _, label in metrics],
        horizontal_spacing=0.15,
        vertical_spacing=0.15,
    )
    for i, (metric, _) in enumerate(metrics):
        top = leaderboard.sort_values(metric, ascending=False).head(top_n)
        row, col = i // 2 + 1, i % 2 + 1
        fig.add_bar(
            x=top[metric],
            y=top["border"],
            orientation="h",
            marker_color=color or FLOW_COLORS["Congestion"],
            row=row,
            col=col,
        )
        fig.update_yaxes(autorange="reversed", row=row, col=col)
    # width matters: static export defaults to 700px and clips the right column.
    fig.update_layout(title=title, width=1400, height=900, showlegend=False)
    return fig


def top_n_bar(
    leaderboard: pd.DataFrame,
    metric: str,
    label: str,
    title: str,
    color: str,
    top_n: int = 10,
) -> go.Figure:
    """Single horizontal bar chart of the top `top_n` borders by one metric."""
    top = leaderboard.sort_values(metric, ascending=False).head(top_n)
    fig = px.bar(
        top,
        x=metric,
        y="border",
        orientation="h",
        title=title,
        labels={metric: label, "border": "Border"},
        color_discrete_sequence=[color],
    )
    fig.update_layout(yaxis={"autorange": "reversed"})
    return fig


def top_vs_rest(
    leaderboard: pd.DataFrame, metric: str = "implied_value_eur", top_n: int = 10
) -> pd.DataFrame:
    """Collapse a leaderboard to the top `top_n` borders plus one "everyone else" row.

    For answering "do a few borders dominate this metric?" without eyeballing
    a bar chart's tail.
    """
    ranked = leaderboard.sort_values(metric, ascending=False)
    labels = [
        *ranked.head(top_n)["border"],
        f"All other borders ({len(ranked) - top_n})",
    ]
    values = [*ranked.head(top_n)[metric], ranked.iloc[top_n:][metric].sum()]
    return pd.DataFrame({"label": labels, metric: values})


def congestion_rent_schematic() -> go.Figure:
    """Textbook supply/demand schematic contrasting congestion rent with deadweight loss.

    Illustrative only - the curves are made-up straight lines chosen to make
    both areas visible at once, not a fit to any real border's bid curves.
    Congestion rent is the rectangle (observed price gap x observed flow, which
    this repo does compute); deadweight loss is the triangle between the two
    flow levels (which needs bid-curve data we don't have).
    """
    demand_intercept, demand_slope = 80, 0.5
    supply_intercept, supply_max, q_max = 10, 51.5, 110
    supply_slope = (supply_max - supply_intercept) / q_max
    actual_flow = 50  # an arbitrary "interconnector is full here" point

    q = np.linspace(0, q_max, 200)
    demand_price = demand_intercept - demand_slope * q
    supply_price = supply_intercept + supply_slope * q

    sink_price = demand_intercept - demand_slope * actual_flow
    source_price = supply_intercept + supply_slope * actual_flow
    unconstrained_flow = (demand_intercept - supply_intercept) / (
        demand_slope + supply_slope
    )
    unconstrained_price = demand_intercept - demand_slope * unconstrained_flow
    centroid_x = (actual_flow * 2 + unconstrained_flow) / 3
    centroid_y = (sink_price + source_price + unconstrained_price) / 3

    fig = go.Figure()
    fig.add_shape(
        type="rect",
        x0=0,
        x1=actual_flow,
        y0=source_price,
        y1=sink_price,
        fillcolor=FLOW_COLORS["Congestion"],
        opacity=0.25,
        line_width=0,
        layer="below",
    )
    fig.add_scatter(
        x=[actual_flow, actual_flow, unconstrained_flow, actual_flow],
        y=[sink_price, source_price, unconstrained_price, sink_price],
        fill="toself",
        fillcolor=FLOW_COLORS["Outage"],
        opacity=0.4,
        line_width=0,
        mode="lines",
        showlegend=False,
        hoverinfo="skip",
    )
    fig.add_scatter(
        x=q,
        y=demand_price,
        mode="lines",
        name="Demand curve",
        line={"color": FLOW_COLORS["Convergence"]},
    )
    fig.add_scatter(
        x=q,
        y=supply_price,
        mode="lines",
        name="Supply curve",
        line={"color": FLOW_COLORS["Counter-intuitive"]},
    )
    fig.add_vline(x=actual_flow, line_dash="dash")
    fig.add_vline(x=unconstrained_flow, line_dash="dot")
    # bgcolor="white" so the label hides the vline segment behind it.
    for x, text in [
        (actual_flow, "Actual flow"),
        (unconstrained_flow, "Unconstrained flow"),
    ]:
        fig.add_annotation(x=x, y=75, text=text, showarrow=False, bgcolor="white")
    for y, text in [
        (sink_price + 2, "Sink price (P<sub>d</sub>)"),
        (source_price - 2, "Source price (P<sub>s</sub>)"),
    ]:
        fig.add_annotation(
            x=5, y=y, text=text, showarrow=False, xanchor="left", bgcolor="white"
        )
    fig.add_annotation(
        x=actual_flow / 2,
        y=(sink_price + source_price) / 2,
        text="Congestion rent<br>(price gap x actual flow)",
        showarrow=False,
        font={"size": 12},
    )
    fig.add_annotation(
        x=centroid_x,
        y=centroid_y,
        text="Deadweight loss<br>(not computed here)",
        showarrow=False,
        font={"size": 11},
    )
    fig.update_layout(
        title="Electricity market grid bottleneck economy (schematic)",
        xaxis_title="Quantity (MW)",
        yaxis_title="Price (EUR/MWh)",
        width=1400,
        height=700,
    )
    return fig


def hourly_border_counts(df: pd.DataFrame, flow_type: str) -> pd.DataFrame:
    subset = df[df["flow_type"] == flow_type]
    return (
        subset.groupby("datetime")["border"].nunique().rename("n_borders").reset_index()
    )


def peak(counts: pd.DataFrame) -> pd.Series:
    return counts.loc[counts["n_borders"].idxmax()]


def border_count_price_chart(
    df: pd.DataFrame,
    flow_type: str,
    title: str,
    peak_vline: str | None = None,
    peak_label: str = "Peak",
) -> go.Figure:
    """Hourly border count for one flow_type vs. average day-ahead price, dual y-axis.

    `title` should already describe the flow_type and date; `peak_vline`
    (e.g. "2023-02-22 13:00:00") draws a dashed marker at a reference hour,
    labelled `peak_label`.
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
        yaxis2={"title": "Avg price (EUR/MWh)", "overlaying": "y", "side": "right"},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
    )
    if peak_vline:
        fig.add_vline(x=peak_vline, line_dash="dash", annotation_text=peak_label)
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
    - implied_value_eur: total abs(price_delta x net_flow_mw x duration_h) -
      the congestion rent (price gap x volume), matching ENTSO-E/ACER's
      "congestion income" under Regulation (EU) 2019/943 Art. 19. This is
      NOT a welfare or economic-cost measure (that's the deadweight-loss
      triangle, which needs bid-curve data we don't have) - it's the
      observed rent, which is the one that actually matters for
      "is this a real problem" framing. See ENTSO-E's TSOs' proposal for
      the Use of Congestion Income - explanatory document:
      https://eepublicdownloads.entsoe.eu/clean-documents/cep/200703_Use_of_Congestion_Income_-_Explanatory_Document.pdf
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
    out = conv.groupby("border").agg(
        volume_mwh=("volume_mwh", "sum"), converged_hours=("duration_h", "sum")
    )
    out["share_converged"] = out["converged_hours"] / total_hours.reindex(out.index)
    return out.sort_values("volume_mwh", ascending=False).reset_index()
