"""Plotly figure builders. Every chart-producing function lives here, not in a notebook."""

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .metrics import SEASON_ORDER, hourly_border_counts, period_label
from .regions import (
    CCR_MECHANISM_COLORS,
    REGION_COLORS,
    border_ccr_mechanism,
    border_country,
    border_region,
)

FLOW_COLORS = {
    "Convergence": "#08415C",
    "Congestion": "#CC2936",
    "Counter-intuitive": "#6B818C",
    "Outage": "#F1BF98",
}

# Distinct from all flow-type colors above, used for the avg-price overlay line.
PRICE_LINE = {"color": "#000000", "dash": "dot"}

# Matches the voltpath web app's chart style (apps/web/src/hooks/colors.ts, Recharts +
# D3 Tableau10 for categorical series) so static article charts read as the same product.
CHART_FONT = "Geist Sans, -apple-system, sans-serif"
CATEGORICAL_PALETTE = px.colors.qualitative.T10
QUADRANT_COLORS = {"intuitive": "#16A765", "counter_intuitive": "#CC3A21"}


def _apply_web_style(fig: go.Figure) -> go.Figure:
    """Shared axis/legend/font styling to match the web app's Recharts charts.

    Three rounds of a custom top-horizontal legend (positioned via paper
    y-fractions) all ended up overlapping the title, the subplot titles, or
    the plot itself at some figure size - title/legend/subplot-titles share
    the same whole-canvas coordinate space, so "sits above the plot" isn't a
    fixed offset, it depends on figure height and on per-chart quirks (e.g.
    a pulled pie slice extending past its own domain). Plotly's default
    legend - vertical, docked outside the right edge of the plot - has none
    of these failure modes, so that's what this uses; it's a deliberate
    departure from the web app's top-aligned legend, not an oversight.
    """
    fig.update_layout(font={"family": CHART_FONT}, plot_bgcolor="white")
    fig.update_xaxes(showline=False, ticks="", zeroline=False)
    fig.update_yaxes(showline=False, ticks="", zeroline=False, showticklabels=True)
    return fig


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


def net_position_bar(
    position: pd.DataFrame, title: str, category_order: list[str] | None = None
) -> go.Figure:
    """Grouped bar of % hours each border's `bidding_zone_from` net-exports, by period
    (from `net_position_by_period`) - the direction-of-flow counterpart to
    `flow_type_stacked_bar`'s per-border flow-type mix, for spotting a seasonal
    reversal that a single all-time `flow_duration_curve` split averages away.
    """
    colors = _border_color_map(position["border"].unique().tolist())
    fig = px.bar(
        position,
        x="period",
        y="pct_exporting",
        color="border",
        barmode="group",
        title=title,
        labels={"pct_exporting": "Hours net-exporting (%)", "period": "Period"},
        color_discrete_map=colors,
        category_orders={"period": category_order} if category_order else None,
    )
    fig.add_hline(y=50, line={"color": "#9CA3AF", "dash": "dot"})
    fig.update_layout(xaxis={"tickangle": -45})
    return _apply_web_style(fig)


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
    unconstrained_flow = (demand_intercept - supply_intercept) / (demand_slope + supply_slope)
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
        fig.add_annotation(x=5, y=y, text=text, showarrow=False, xanchor="left", bgcolor="white")
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
        line_shape="hv",
    )
    fig.update_traces(name=f"Borders {flow_type.lower()}", showlegend=True)
    fig.add_scatter(
        x=avg_price.index.to_pydatetime(),
        y=avg_price.values,
        name="Avg price (EUR/MWh)",
        yaxis="y2",
        line=PRICE_LINE,
        line_shape="hv",
    )
    fig.update_layout(
        yaxis2={"title": "Avg price (EUR/MWh)", "overlaying": "y", "side": "right"},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
    )
    if peak_vline:
        fig.add_vline(x=peak_vline, line_dash="dash", annotation_text=peak_label)
    return fig


# Shared by flow_type_stacked_bar and flow_type_grouped_bar so every CCR chart
# - solo or combined - renders at the same height and same per-bar pixel width,
# rather than stretching to fill a fixed figure width.
FLOW_TYPE_BAR_PX = 54
FLOW_TYPE_CHART_HEIGHT = 400


def flow_type_stacked_bar(shares: pd.DataFrame, title: str) -> go.Figure:
    """100%-stacked bar of per-border flow_type share (see `flow_type_shares`).

    Matches the web app's "Flow Types per Border" chart (`CIFlowsBarChart`):
    same stack order/colors (`FLOW_TYPE_ORDER`/`FLOW_COLORS`), 0-100% y-axis.
    """
    fig = go.Figure()
    for flow_type in FLOW_TYPE_ORDER:
        y = shares[flow_type] if flow_type in shares.columns else [0] * len(shares)
        fig.add_bar(x=shares["border"], y=y, name=flow_type, marker_color=FLOW_COLORS[flow_type])
    fig.update_layout(
        barmode="stack",
        title=title,
        yaxis={"title": "Frequency (%)", "range": [0, 100]},
        xaxis={"tickangle": -45},
        width=max(500, FLOW_TYPE_BAR_PX * len(shares)),
        height=FLOW_TYPE_CHART_HEIGHT,
        bargap=0.3,
    )
    return _apply_web_style(fig)


def flow_type_grouped_bar(groups: list[tuple[str, pd.DataFrame]], title: str) -> go.Figure:
    """`flow_type_stacked_bar`, but combining several CCRs' borders into one chart,
    bracket-labelled per CCR - for mechanisms (e.g. NTC-radial, NTC-lineset) shared
    by multiple CCRs, matching scratch/media/price-coupled-ntc-radial-*.png.

    `groups` is `[(ccr_label, shares_df), ...]` in display order (each
    `shares_df` from `flow_type_shares`); a bracket line is only drawn over
    groups with 3+ borders (2 or fewer reads fine from the centered label alone).
    """
    all_shares = pd.concat([shares for _, shares in groups], ignore_index=True)
    borders = all_shares["border"].tolist()

    fig = go.Figure()
    for flow_type in FLOW_TYPE_ORDER:
        y = all_shares[flow_type] if flow_type in all_shares.columns else [0] * len(all_shares)
        fig.add_bar(x=borders, y=y, name=flow_type, marker_color=FLOW_COLORS[flow_type])

    pos = 0
    for label, shares in groups:
        n = len(shares)
        start, end = pos, pos + n - 1
        if n >= 3:
            fig.add_shape(
                type="line",
                x0=start - 0.4,
                x1=end + 0.4,
                y0=108,
                y1=108,
                xref="x",
                yref="y",
                line={"color": "#1F2937", "width": 1.5},
            )
        fig.add_annotation(x=(start + end) / 2, y=114, text=label, showarrow=False, font={"size": 13})
        pos += n

    fig.update_layout(
        barmode="stack",
        title=title,
        yaxis={"title": "Frequency (%)", "range": [0, 122], "tickvals": [0, 20, 40, 60, 80, 100]},
        xaxis={"tickangle": -45},
        width=max(500, FLOW_TYPE_BAR_PX * len(all_shares)),
        height=FLOW_TYPE_CHART_HEIGHT,
        bargap=0.3,
    )
    return _apply_web_style(fig)


def flow_type_stacked_bar_by_period(df: pd.DataFrame, freq: str, title: str) -> go.Figure:
    """100%-stacked bar of flow_type share per period (month or season), one subplot
    per border - the seasonal counterpart to `flow_type_stacked_bar`, which only shows
    the all-time mix. `freq` is "M" or "season" (see `period_label`).

    Not built on `flow_type_grouped_bar`: that function's x-axis is the border name,
    which only works when every group has distinct borders (e.g. comparing CCRs). Here
    the same borders repeat in every period, so Plotly would collapse same-named bars
    across periods onto a single x position - hence the per-border subplot instead.
    """
    working = df.assign(period=period_label(df["datetime"], freq))
    order = SEASON_ORDER if freq == "season" else sorted(working["period"].unique())
    borders = sorted(working["border"].unique())

    fig = make_subplots(rows=1, cols=len(borders), subplot_titles=borders, shared_yaxes=True)
    for col, border in enumerate(borders, start=1):
        subset = working[working["border"] == border]
        hours = subset.groupby(["period", "flow_type"])["duration_h"].sum().unstack(fill_value=0)
        shares = (hours.div(hours.sum(axis=1), axis=0) * 100).reindex(order)
        for flow_type in FLOW_TYPE_ORDER:
            y = shares[flow_type] if flow_type in shares.columns else [0] * len(shares)
            fig.add_bar(
                x=shares.index,
                y=y,
                name=flow_type,
                marker_color=FLOW_COLORS[flow_type],
                showlegend=(col == 1),
                row=1,
                col=col,
            )
    fig.update_layout(
        barmode="stack",
        title=title,
        width=max(500, 300 * len(borders)),
        height=FLOW_TYPE_CHART_HEIGHT,
    )
    fig.update_xaxes(tickangle=-45)
    fig.update_yaxes(title="Frequency (%)", range=[0, 100], row=1, col=1)
    return _apply_web_style(fig)


def congestion_ci_chart(df: pd.DataFrame, event: dict) -> go.Figure:
    """Congested vs. counter-intuitive border counts around one structural-change event.

    `event` needs `name`, `date`, `date_from`, `date_to` (a dashed vline
    marks `date`); every structural-change notebook runs this first, so it
    lives here rather than copy-pasted per notebook.
    """
    frames = []
    for flow_type in ("Congestion", "Counter-intuitive"):
        counts = hourly_border_counts(df, flow_type)
        counts["flow_type"] = flow_type
        frames.append(counts)
    combined = pd.concat(frames)

    fig = px.line(
        combined,
        x="datetime",
        y="n_borders",
        color="flow_type",
        title=(
            f"{event['name']}: congested / counter-intuitive borders, "
            f"{event['date_from']} to {event['date_to']}"
        ),
        labels={"n_borders": "Borders", "datetime": "Time", "flow_type": "Flow type"},
        color_discrete_map=FLOW_COLORS,
    )
    fig.add_vline(x=event["date"], line_dash="dash", annotation_text=event["name"])
    return fig


def before_after_convergence_chart(comparison: pd.Series, event: dict) -> go.Figure:
    """Bar chart for the `before_after_convergence` before/after comparison.

    Every structural-change notebook runs `before_after_convergence` first;
    this is the paired chart so the result lands as a chart, not a print.
    """
    plot_df = pd.DataFrame(
        {
            "period": ["Before", "After"],
            "share_converged": [
                comparison["share_converged_before"],
                comparison["share_converged_after"],
            ],
        }
    )
    fig = px.bar(
        plot_df,
        x="period",
        y="share_converged",
        title=(
            f"{event['name']}: share of hours with convergent flow, "
            f"before vs. after {event['date_from']} to {event['date_to']}"
        ),
        labels={"share_converged": "Share converged", "period": "Period"},
        color_discrete_sequence=[FLOW_COLORS["Convergence"]],
    )
    fig.update_yaxes(tickformat=".0%")
    return fig


def _border_color_map(borders: list[str]) -> dict[str, str]:
    palette = CATEGORICAL_PALETTE
    return {b: palette[i % len(palette)] for i, b in enumerate(sorted(borders))}


def flow_duration_curve(df: pd.DataFrame, title: str) -> go.Figure:
    """Per-border duration curve (flow sorted descending vs. % of time at/above it).

    A flat top (curve clipped at a fixed level before it starts sloping down)
    is the border running at its transfer-capacity ceiling a large share of
    the time - the shape to compare before/after a structural change to see
    whether the physical ceiling itself moved. Pass an optional `period`
    column (e.g. "before"/"after") to split into side-by-side subplots on a
    shared y-axis instead of one figure.
    """
    periods: list[str] = df["period"].unique().tolist() if "period" in df.columns else []
    colors = _border_color_map(df["border"].unique().tolist())
    fig = make_subplots(
        rows=1,
        cols=len(periods) or 1,
        subplot_titles=[p.title() for p in periods],
        shared_yaxes=True,
    )
    for col, period in enumerate(periods or [None], start=1):
        subset = df[df["period"] == period] if period else df
        for border, group in subset.groupby("border"):
            sorted_flow = group["net_flow_mw"].sort_values(ascending=False).reset_index(drop=True)
            n = len(sorted_flow)
            pct = (sorted_flow.index / (n - 1) * 100) if n > 1 else [0]
            fig.add_scatter(
                x=pct,
                y=sorted_flow,
                mode="lines",
                name=border,
                legendgroup=border,
                showlegend=(col == 1),
                line={"color": colors[border]},
                row=1,
                col=col,
            )
    fig.add_hline(y=0, line_dash="dash", line_width=1.5, line_color="#9CA3AF")
    fig.update_layout(title=title, width=1120, height=480)
    fig.update_xaxes(title="% of time at or above", showgrid=False)
    fig.update_yaxes(title="Net flow (MW)", col=1, title_standoff=0)
    fig.update_yaxes(showgrid=True, gridcolor="#E5E7EB")
    return _apply_web_style(fig)


def flow_price_scatter(df: pd.DataFrame, title: str) -> go.Figure:
    """Per-border (net flow, price delta) scatter.

    Flow that tracks the price signal traces a rising curve that saturates
    at the border's capacity; points off that curve are flow moving against
    (or indifferent to) the price gap - loop flow / scheduling artifacts
    rather than commercial arbitrage. Pass an optional `period` column to
    split into side-by-side subplots for a before/after comparison.
    """
    periods: list[str] = df["period"].unique().tolist() if "period" in df.columns else []
    colors = _border_color_map(df["border"].unique().tolist())
    fig = make_subplots(
        rows=1,
        cols=len(periods) or 1,
        subplot_titles=[p.title() for p in periods],
        shared_yaxes=True,
        shared_xaxes=True,
    )
    # Shared across both before/after panels (not per-subset) and padded past the data
    # max, so the quadrant shading fills the full autoranged axes in both panels rather
    # than stopping short wherever one panel's data happens to be smaller.
    x_max = (df["net_flow_mw"].abs().max() or 1) * 1.1
    y_max = (df["price_delta"].abs().max() or 1) * 1.1
    for col, period in enumerate(periods or [None], start=1):
        subset = df[df["period"] == period] if period else df
        # Intuitive: flow and price delta share sign (flow follows the price signal).
        # Counter-intuitive: opposite signs (loop flow / scheduling artifacts).
        fig.add_shape(
            type="rect",
            x0=0,
            x1=x_max,
            y0=0,
            y1=y_max,
            fillcolor=QUADRANT_COLORS["intuitive"],
            opacity=0.06,
            line_width=0,
            layer="below",
            row=1,
            col=col,
        )
        fig.add_shape(
            type="rect",
            x0=-x_max,
            x1=0,
            y0=-y_max,
            y1=0,
            fillcolor=QUADRANT_COLORS["intuitive"],
            opacity=0.06,
            line_width=0,
            layer="below",
            row=1,
            col=col,
        )
        fig.add_shape(
            type="rect",
            x0=0,
            x1=x_max,
            y0=-y_max,
            y1=0,
            fillcolor=QUADRANT_COLORS["counter_intuitive"],
            opacity=0.06,
            line_width=0,
            layer="below",
            row=1,
            col=col,
        )
        fig.add_shape(
            type="rect",
            x0=-x_max,
            x1=0,
            y0=0,
            y1=y_max,
            fillcolor=QUADRANT_COLORS["counter_intuitive"],
            opacity=0.06,
            line_width=0,
            layer="below",
            row=1,
            col=col,
        )
        for border, group in subset.groupby("border"):
            fig.add_scatter(
                x=group["net_flow_mw"],
                y=group["price_delta"],
                mode="markers",
                name=border,
                legendgroup=border,
                showlegend=(col == 1),
                # Thin dark outline keeps dots legible against the light
                # quadrant tint (and each other) instead of washing out at
                # marker opacity 0.5 - the quadrant fill has no such outline.
                marker={
                    "color": colors[border],
                    "opacity": 0.7,
                    "size": 5,
                    "line": {"width": 0.5, "color": "#1F2937"},
                },
                row=1,
                col=col,
            )
        fig.add_hline(y=0, line_width=1.5, line_color="#9CA3AF", row=1, col=col)
        fig.add_vline(x=0, line_width=1.5, line_color="#9CA3AF", row=1, col=col)
        for label, kind, xy in [
            ("Intuitive", "intuitive", (x_max * 0.97, y_max * 0.95)),
            ("Intuitive", "intuitive", (-x_max * 0.97, -y_max * 0.95)),
            ("Counter-intuitive", "counter_intuitive", (-x_max * 0.97, y_max * 0.95)),
            ("Counter-intuitive", "counter_intuitive", (x_max * 0.97, -y_max * 0.95)),
        ]:
            fig.add_annotation(
                x=xy[0],
                y=xy[1],
                text=label,
                showarrow=False,
                font={"size": 11, "color": QUADRANT_COLORS[kind]},
                xanchor="right" if xy[0] > 0 else "left",
                row=1,
                col=col,
            )
    fig.update_layout(title=title, width=1120, height=480)
    fig.update_xaxes(title="Net flow (MW)", showgrid=True, gridcolor="#E5E7EB")
    fig.update_yaxes(title="Price delta (EUR/MWh)", col=1)
    fig.update_yaxes(showgrid=True, gridcolor="#E5E7EB")
    return _apply_web_style(fig)


FLOW_TYPE_ORDER = ["Convergence", "Congestion", "Counter-intuitive", "Outage"]


def flow_type_share_pies(df: pd.DataFrame, event_date: str, title: str) -> go.Figure:
    """Before/after pair of pies, each showing flow_type's share of total duration_h.

    Makes `before_after_convergence`'s printed numbers visual: pulls the
    Convergence slice out on both pies so the same before/after comparison
    that check reports as text is visible at a glance here too.
    """
    labelled = df.copy()
    labelled["period"] = labelled["datetime"].lt(event_date).map({True: "Before", False: "After"})
    fig = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "domain"}, {"type": "domain"}]],
        subplot_titles=["Before", "After"],
    )
    for col, period in enumerate(["Before", "After"], start=1):
        totals = (
            labelled[labelled["period"] == period]
            .groupby("flow_type")["duration_h"]
            .sum()
            .reindex(FLOW_TYPE_ORDER)
            .fillna(0)
        )
        fig.add_pie(
            labels=totals.index,
            values=totals.values,
            sort=False,
            marker={"colors": [FLOW_COLORS[t] for t in FLOW_TYPE_ORDER]},
            pull=[0.08 if t == "Convergence" else 0 for t in FLOW_TYPE_ORDER],
            textinfo="percent",
            texttemplate="%{percent} (%{value:,.0f}h)",
            hovertemplate="%{label}: %{percent} (%{value:,.0f}h)<extra></extra>",
            showlegend=(col == 1),
            row=1,
            col=col,
        )
    fig.update_layout(title=title, width=1000, height=550)
    return _apply_web_style(fig)


def litgrid_capacity_plan_chart(observed_2026: tuple[float, float] | None = None) -> go.Figure:
    """LT-PL allocated capacity: pre-sync, post-sync, and Litgrid's own recovery plan.

    Figures are Litgrid's press-statement numbers (see markdown above for
    sources), not our own fetched flow data - solid bars are what Litgrid
    reported as already observed, hatched bars are its forward-looking plan.

    Pass `observed_2026` as `(avg_export_mw, avg_import_mw)` from our own
    fetched LT-PL flow data to add a bar checking Litgrid's "end of 2026:
    365/200 MW" target against how the year's actually gone so far.
    """
    rows = [
        {"stage": "Pre-sync (historical)", "kind": "Observed", "direction": "Export", "capacity_mw": 350},
        {"stage": "Pre-sync (historical)", "kind": "Observed", "direction": "Import", "capacity_mw": 492},
        {
            "stage": "Post-sync avg (since Feb 2025)",
            "kind": "Observed",
            "direction": "Export",
            "capacity_mw": 170,
        },
        {
            "stage": "Post-sync avg (since Feb 2025)",
            "kind": "Observed",
            "direction": "Import",
            "capacity_mw": 150,
        },
        {
            "stage": "Plan: end of 2026",
            "kind": "Litgrid's planned trajectory",
            "direction": "Export",
            "capacity_mw": 365,
        },
        {
            "stage": "Plan: end of 2026",
            "kind": "Litgrid's planned trajectory",
            "direction": "Import",
            "capacity_mw": 200,
        },
        {
            "stage": "Plan: from 2027",
            "kind": "Litgrid's planned trajectory",
            "direction": "Export",
            "capacity_mw": 500,
        },
        {
            "stage": "Plan: from 2027",
            "kind": "Litgrid's planned trajectory",
            "direction": "Import",
            "capacity_mw": 353,
        },
    ]
    stage_order = ["Pre-sync (historical)", "Post-sync avg (since Feb 2025)"]
    if observed_2026 is not None:
        avg_export, avg_import = observed_2026
        rows += [
            {
                "stage": "2026 so far (our data)",
                "kind": "Observed",
                "direction": "Export",
                "capacity_mw": avg_export,
            },
            {
                "stage": "2026 so far (our data)",
                "kind": "Observed",
                "direction": "Import",
                "capacity_mw": avg_import,
            },
        ]
        stage_order.append("2026 so far (our data)")
    stage_order += ["Plan: end of 2026", "Plan: from 2027"]
    capacity = pd.DataFrame(rows)
    capacity["stage"] = pd.Categorical(capacity["stage"], categories=stage_order, ordered=True)
    fig = px.bar(
        capacity.sort_values("stage"),
        x="stage",
        y="capacity_mw",
        color="direction",
        pattern_shape="kind",
        pattern_shape_map={"Observed": "", "Litgrid's planned trajectory": "/"},
        barmode="group",
        title="LT–PL allocated capacity: before sync, since sync, and Litgrid's recovery plan",
        labels={
            "capacity_mw": "Allocated capacity (MW)",
            "stage": "",
            "direction": "Direction",
            "kind": "Basis",
        },
    )
    return fig


def voltpath_convergence_chart(convergence: pd.DataFrame) -> go.Figure:
    """Our own `share_converged`, 2024 vs 2025, per border pair - the Voltpath-data counterpart
    to `ast_price_convergence_chart`. Takes a `pair`/`year`/`share_pct` frame (see
    the notebook cell that builds it from `fetch_flows` + `convergence_summary`);
    measures flow-direction convergence, not identical day-ahead price, so it's a
    same-direction check against AST's figures, not a like-for-like reproduction.
    """
    fig = px.bar(
        convergence,
        x="pair",
        y="share_pct",
        color="year",
        barmode="group",
        title="Share of hours with convergent flow (our data), by border pair",
        labels={"share_pct": "% of hours converged", "pair": "Border pair", "year": "Year"},
    )
    return fig


def ast_price_convergence_chart() -> go.Figure:
    """Share of trading intervals with identical day-ahead prices, 2024 vs 2025, per border pair.

    Numbers are AST's own year-in-review figures (Latvian electricity market
    overview), not our own fetched data. AST attributes LV-EE's 21pp drop to
    Estonian line maintenance, not Baltic sync - LV-LT barely moving in the
    same period is the contrast that shows this isn't a Baltic-wide effect.
    """
    convergence = pd.DataFrame(
        [
            {"pair": "FI & EE", "year": "2024", "share_pct": 32.1},
            {"pair": "FI & EE", "year": "2025", "share_pct": 19.6},
            {"pair": "EE & LV", "year": "2024", "share_pct": 97.2},
            {"pair": "EE & LV", "year": "2025", "share_pct": 75.9},
            {"pair": "LV & LT", "year": "2024", "share_pct": 99.1},
            {"pair": "LV & LT", "year": "2025", "share_pct": 98.7},
            {"pair": "LT & SE4", "year": "2024", "share_pct": 22.0},
            {"pair": "LT & SE4", "year": "2025", "share_pct": 3.3},
        ]
    )
    fig = px.bar(
        convergence,
        x="pair",
        y="share_pct",
        color="year",
        barmode="group",
        title="Share of trading intervals with identical day-ahead price, by border pair",
        labels={"share_pct": "% of intervals at identical price", "pair": "Border pair", "year": "Year"},
    )
    return fig


def daily_rent_chart(congested: pd.DataFrame) -> go.Figure:
    """Daily total congestion rent, resampled from a `rent_eur`-bearing flow frame."""
    daily = congested.set_index("datetime")["rent_eur"].resample("1D").sum().reset_index()
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
    fig.add_pie(labels=year_split["label"], values=year_split["implied_value_eur"], row=1, col=2)
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
            parent = f"country:{region}:{row['country']}" if pd.notna(row["country"]) else f"region:{region}"
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


def ccr_mechanism_treemap(leaderboard: pd.DataFrame, year: str) -> go.Figure:
    """Congestion rent grouped by real CCR capacity-allocation mechanism (see BORDER_CCR).

    Every row gets a mechanism label (falling back to CCR_OTHER), so unlike
    `region_treemap` this is a plain two-level px.treemap - no variable-depth
    hierarchy to build by hand.
    """
    data = leaderboard.copy()
    data["mechanism"] = data["border"].map(border_ccr_mechanism)
    fig = px.treemap(
        data,
        path=["mechanism", "border"],
        values="implied_value_eur",
        color="mechanism",
        color_discrete_map=CCR_MECHANISM_COLORS,
        title=f"Congestion rent by CCR capacity-allocation mechanism, {year} (EUR)",
    )
    fig.update_layout(width=1400, height=800)
    return fig
