"""Per-border/per-flow-type aggregations used to build leaderboards."""

import pandas as pd

SEASON_LABELS = {
    12: "Winter (DJF)",
    1: "Winter (DJF)",
    2: "Winter (DJF)",
    3: "Spring (MAM)",
    4: "Spring (MAM)",
    5: "Spring (MAM)",
    6: "Summer (JJA)",
    7: "Summer (JJA)",
    8: "Summer (JJA)",
    9: "Autumn (SON)",
    10: "Autumn (SON)",
    11: "Autumn (SON)",
}
SEASON_ORDER = ["Winter (DJF)", "Spring (MAM)", "Summer (JJA)", "Autumn (SON)"]


def period_label(dt: pd.Series, freq: str) -> pd.Series:
    """Calendar-month ("2026-01") or meteorological-season ("Winter (DJF)") label for a
    datetime column - the period grouping shared by `net_position_by_period` and any
    per-period `flow_type_shares` breakdown. `freq` is "M" or "season".
    """
    if freq == "season":
        return dt.dt.month.map(SEASON_LABELS)
    return dt.dt.to_period("M").astype(str)


def net_position_by_period(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Share of hours each border's `bidding_zone_from` is net-exporting
    (net_flow_mw > 0), grouped by `freq` ("M" or "season") - the seasonal
    breakdown of the direction split that `flow_duration_curve` averages
    away into one all-time curve.
    """
    out = df.copy()
    out["period"] = period_label(out["datetime"], freq)
    return (
        out.groupby(["border", "period"])["net_flow_mw"]
        .apply(lambda s: (s > 0).mean() * 100)
        .rename("pct_exporting")
        .reset_index()
    )


def net_volume_by_period(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Average signed net_flow_mw per border, grouped by `freq` ("M" or "season") -
    the quantitative counterpart to `net_position_by_period`'s % of hours exporting,
    since a border can export 90% of hours at a trickle or 51% of hours at full tilt.
    """
    out = df.copy()
    out["period"] = period_label(out["datetime"], freq)
    return out.groupby(["border", "period"])["net_flow_mw"].mean().rename("avg_net_flow_mw").reset_index()


def hourly_border_counts(df: pd.DataFrame, flow_type: str) -> pd.DataFrame:
    subset = df[df["flow_type"] == flow_type]
    return subset.groupby("datetime")["border"].nunique().rename("n_borders").reset_index()


def before_after_convergence(df: pd.DataFrame, event_date: str) -> pd.Series:
    """Mean `share_converged` before vs. after `event_date` - the mechanical
    before/after check every structural-change notebook runs first.
    """
    before = df[df["datetime"] < event_date]
    after = df[df["datetime"] >= event_date]
    return pd.Series(
        {
            "share_converged_before": convergence_summary(before)["share_converged"].mean(),
            "share_converged_after": convergence_summary(after)["share_converged"].mean(),
        }
    )


def peak(counts: pd.DataFrame) -> pd.Series:
    return counts.loc[counts["n_borders"].idxmax()]


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


def flow_type_shares(df: pd.DataFrame) -> pd.DataFrame:
    """Per-border % of hours in each flow_type - the data behind the web app's
    "Flow Types per Border" chart (100%-stacked bar). One row per border,
    one column per flow_type (values sum to 100 across a row).
    """
    hours = df.groupby(["border", "flow_type"])["duration_h"].sum().unstack(fill_value=0)
    return (hours.div(hours.sum(axis=1), axis=0) * 100).reset_index()


def convergence_summary(df: pd.DataFrame) -> pd.DataFrame:
    total_hours = df.groupby("border")["duration_h"].sum()
    conv = df[df["flow_type"] == "Convergence"]
    out = conv.groupby("border").agg(volume_mwh=("volume_mwh", "sum"), converged_hours=("duration_h", "sum"))
    out["share_converged"] = out["converged_hours"] / total_hours.reindex(out.index)
    return out.sort_values("volume_mwh", ascending=False).reset_index()


def drop_ukraine(leaderboard: pd.DataFrame) -> pd.DataFrame:
    """Drop UA_IPS borders from a `flow_type_summary` leaderboard.

    Ukraine's borders (HU/PL/RO/SK -> UA_IPS) have been a special case since
    2022: wartime grid conditions and emergency EU synchronisation drive their
    numbers, not ordinary market congestion, so they can top a leaderboard for
    reasons unrelated to everything else on it.
    """
    return leaderboard[~leaderboard["border"].str.contains("UA_IPS")]


def congestion_rent(df: pd.DataFrame, peak_datetime) -> pd.Series:
    """Congestion rent (EUR) and border count at one MTU.

    Same definition as `flow_type_summary`'s implied_value_eur - abs(price_delta
    x net_flow_mw x duration_h) - but for a single timestamp rather than a whole
    leaderboard, for spotlighting one peak-congestion moment.
    """
    congested = df[(df["datetime"] == peak_datetime) & (df["flow_type"] == "Congestion")]
    return pd.Series({"rent_eur": congested["value_eur"].abs().sum(), "n_borders": len(congested)})


def congestion_rent_table(
    df: pd.DataFrame, snapshots: dict[str, pd.Timestamp], window_h: float = 1.0
) -> pd.DataFrame:
    """Congestion rent (EUR) for several snapshots side by side, windowed the
    same way as `zone_price_summary` (peak MTU / +/-`window_h` / all day) -
    for comparing how "hot" several congestion peaks were, not just how wide.

    `snapshots` maps a label (e.g. a date string) to the peak MTU timestamp
    for that snapshot.
    """
    congested = df[df["flow_type"] == "Congestion"]

    def rent(window: pd.DataFrame) -> float:
        return window["value_eur"].abs().sum()

    out = {}
    for label, peak_datetime in snapshots.items():
        peak_datetime = pd.Timestamp(peak_datetime)
        half_window = pd.Timedelta(hours=window_h)
        out[label] = pd.Series(
            {
                "Peak MTU": rent(congested[congested["datetime"] == peak_datetime]),
                f"+/-{window_h:g}h": rent(
                    congested[
                        congested["datetime"].between(
                            peak_datetime - half_window, peak_datetime + half_window
                        )
                    ]
                ),
                "All day": rent(congested[congested["datetime"].dt.date == peak_datetime.normalize().date()]),
            }
        )
    return pd.DataFrame(out).map(lambda eur: f"{eur / 1000:,.1f}k")


def ci_flow_value_table(
    df: pd.DataFrame, snapshots: dict[str, pd.Timestamp], window_h: float = 1.0
) -> pd.DataFrame:
    """Implied value (EUR) of Counter-intuitive flows for several snapshots side
    by side, windowed like `congestion_rent_table` (peak MTU / +/-`window_h` /
    all day) - for comparing how "hot" several counter-intuitive peaks were.

    `snapshots` maps a label (e.g. a date string) to the peak MTU timestamp
    for that snapshot.
    """
    ci = df[df["flow_type"] == "Counter-intuitive"]

    def value(window: pd.DataFrame) -> float:
        return window["value_eur"].abs().sum()

    out = {}
    for label, peak_datetime in snapshots.items():
        peak_datetime = pd.Timestamp(peak_datetime)
        half_window = pd.Timedelta(hours=window_h)
        out[label] = pd.Series(
            {
                "Peak MTU": value(ci[ci["datetime"] == peak_datetime]),
                f"+/-{window_h:g}h": value(
                    ci[ci["datetime"].between(peak_datetime - half_window, peak_datetime + half_window)]
                ),
                "All day": value(ci[ci["datetime"].dt.date == peak_datetime.normalize().date()]),
            }
        )
    return pd.DataFrame(out).map(lambda eur: f"{eur / 1000:,.1f}k")


def zone_border_breakdown(df: pd.DataFrame, zone: str, peak_datetime) -> pd.DataFrame:
    """Per-border breakdown for one zone at one MTU, oriented from that zone's
    perspective (export_mw > 0 means `zone` is exporting on that border),
    plus a Total row - for spotlighting one zone's net position during a
    congestion peak (e.g. Poland acting as a transit hub).

    `value_eur` is each border's congestion rent (price gap x volume), signed
    by export direction - positive while `zone` exports on that border
    (selling into the higher price), negative while it imports (paying it) -
    and formatted like `congestion_rent_table`'s (e.g. "41.9k").
    """
    peak_datetime = pd.Timestamp(peak_datetime)
    touches_zone = (df["bidding_zone_from"] == zone) | (df["bidding_zone_to"] == zone)
    rows = df[(df["datetime"] == peak_datetime) & touches_zone].copy()
    is_from = rows["bidding_zone_from"] == zone

    export_mw = rows["net_flow_mw"].where(is_from, -rows["net_flow_mw"])
    out = pd.DataFrame(
        {
            "counterparty": rows["bidding_zone_from"].where(~is_from, rows["bidding_zone_to"]),
            "export_mw": export_mw,
            "zone_price": rows["price_from"].where(is_from, rows["price_to"]),
            "counterparty_price": rows["price_to"].where(is_from, rows["price_from"]),
            "value_eur": rows["value_eur"] * export_mw.apply(lambda mw: 1 if mw >= 0 else -1),
        }
    ).sort_values("export_mw", ascending=False)

    total = pd.DataFrame(
        [{"counterparty": "Total", "export_mw": out["export_mw"].sum(), "value_eur": out["value_eur"].sum()}]
    )
    out = pd.concat([out, total], ignore_index=True)
    out["value_eur"] = out["value_eur"].map(lambda eur: f"{eur / 1000:,.1f}k")
    return out


def zone_price_summary(
    df: pd.DataFrame,
    highlight_zones: set[str],
    highlight_label: str,
    peak_datetime,
    window_h: float = 1.0,
) -> pd.DataFrame:
    """Average day-ahead price, highlighted zones vs. the rest of Europe, at the
    peak MTU, a +/-`window_h` window around it, and the full day - for
    spotlighting a regional price decoupling around one congestion peak.

    `df` is a flows dataframe; zonal prices are derived from its per-border
    price_from/price_to columns (deduped per zone/timestamp, since every
    border touching a zone carries the same price for it).
    """
    prices = pd.concat(
        [
            df[["datetime", "bidding_zone_from", "price_from"]].rename(
                columns={"bidding_zone_from": "zone", "price_from": "price"}
            ),
            df[["datetime", "bidding_zone_to", "price_to"]].rename(
                columns={"bidding_zone_to": "zone", "price_to": "price"}
            ),
        ]
    ).drop_duplicates(["datetime", "zone"])

    def avg(window: pd.DataFrame) -> pd.Series:
        return pd.Series(
            {
                "All BZs": window["price"].mean(),
                highlight_label: window[window["zone"].isin(highlight_zones)]["price"].mean(),
                f"Excl. {highlight_label}": window[~window["zone"].isin(highlight_zones)]["price"].mean(),
            }
        )

    peak_datetime = pd.Timestamp(peak_datetime)
    half_window = pd.Timedelta(hours=window_h)
    return pd.DataFrame(
        {
            "Peak MTU": avg(prices[prices["datetime"] == peak_datetime]),
            f"+/-{window_h:g}h": avg(
                prices[prices["datetime"].between(peak_datetime - half_window, peak_datetime + half_window)]
            ),
            "All day": avg(prices[prices["datetime"].dt.date == peak_datetime.normalize().date()]),
        }
    ).T


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
