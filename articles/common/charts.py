"""Plotly figure builders. Every chart-producing function lives here, not in a notebook."""

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .metrics import hourly_border_counts
from .regions import REGION_COLORS, border_country, border_region

FLOW_COLORS = {
    "Convergence": "#08415C",
    "Congestion": "#CC2936",
    "Counter-intuitive": "#6B818C",
    "Outage": "#F1BF98",
}

# Distinct from all flow-type colors above, used for the avg-price overlay line.
PRICE_LINE = {"color": "#000000", "dash": "dot"}


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


def daily_rent_chart(congested: pd.DataFrame) -> go.Figure:
    """Daily total congestion rent, resampled from a `rent_eur`-bearing flow frame."""
    daily = (
        congested.set_index("datetime")["rent_eur"].resample("1D").sum().reset_index()
    )
    fig = px.bar(
        daily,
        x="datetime",
        y="rent_eur",
        title="Daily congestion rent, all borders",
        labels={"datetime": "Date", "rent_eur": "Congestion rent (EUR)"},
        color_discrete_sequence=[FLOW_COLORS["Congestion"]],
    )
    return fig


def concentration_pie_chart(
    month_split: pd.DataFrame,
    year_split: pd.DataFrame,
    month_label: str,
    year_label: str,
) -> go.Figure:
    """Side-by-side pies of top-10-vs-rest congestion rent, for a month and a year."""
    fig = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "domain"}, {"type": "domain"}]],
        subplot_titles=[month_label, year_label],
    )
    fig.add_pie(
        labels=month_split["label"],
        values=month_split["implied_value_eur"],
        row=1,
        col=1,
    )
    fig.add_pie(
        labels=year_split["label"], values=year_split["implied_value_eur"], row=1, col=2
    )
    fig.update_layout(
        title="Top 10 borders vs. everyone else, ranked by congestion rent",
        width=1400,
        height=600,
    )
    return fig


def region_treemap(leaderboard: pd.DataFrame, year: str) -> go.Figure:
    """Congestion rent by region, with a country sub-level for multi-zone countries.

    Built as an explicit id/parent hierarchy (go.Treemap) rather than
    `px.treemap(path=...)`: the country level only exists for some borders
    (multi-bidding-zone countries like Norway or Italy), so the hierarchy has
    variable depth per branch, which px.treemap's fixed-column path can't
    express - a border with no country either gets a fabricated column value
    (an extra visible layer) or a null one, and plotly refuses to mix null
    and non-null values at the same path level ("None entries cannot have
    not-None children").
    """
    data = leaderboard.copy()
    data["region"] = data["border"].map(border_region)
    data["country"] = data["border"].map(border_country)

    ids, labels, parents, values, colors = [], [], [], [], []
    for region, region_rows in data.groupby("region"):
        ids.append(f"region:{region}")
        labels.append(region)
        parents.append("")
        values.append(region_rows["implied_value_eur"].sum())
        colors.append(REGION_COLORS[region])

        has_country = region_rows["country"].notna()
        for country, country_rows in region_rows[has_country].groupby("country"):
            ids.append(f"country:{region}:{country}")
            labels.append(country)
            parents.append(f"region:{region}")
            values.append(country_rows["implied_value_eur"].sum())
            colors.append(REGION_COLORS[region])

        for _, row in region_rows.iterrows():
            parent = (
                f"country:{region}:{row['country']}"
                if pd.notna(row["country"])
                else f"region:{region}"
            )
            ids.append(f"border:{row['border']}")
            labels.append(row["border"])
            parents.append(parent)
            values.append(row["implied_value_eur"])
            colors.append(REGION_COLORS[region])

    fig = go.Figure(
        go.Treemap(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            marker={"colors": colors},
        )
    )
    fig.update_layout(
        title=f"Congestion rent by region and country, {year} (EUR)",
        width=1400,
        height=800,
    )
    return fig
