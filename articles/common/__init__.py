"""Shared code for all article notebooks, split by concern:

- api.py: Voltpath API access, auth, rate-limit handling, disk caching.
- regions.py: zone-to-region / zone-to-country mappings for grouping borders geographically.
- metrics.py: pandas aggregations that build leaderboards from raw flow data.
- charts.py: every Plotly figure builder.

Re-exported here so `from common import X` keeps working unchanged for notebooks.
"""

from .api import API_KEY, BASE_URL, HEADERS, fetch_flows, fetch_flows_range
from .charts import (
    FLOW_COLORS,
    LEADERBOARD_METRICS,
    PRICE_LINE,
    ast_price_convergence_chart,
    before_after_convergence_chart,
    border_count_price_chart,
    ccr_mechanism_treemap,
    concentration_pie_chart,
    congestion_ci_chart,
    congestion_rent_schematic,
    daily_rent_chart,
    flow_duration_curve,
    flow_price_scatter,
    flow_type_share_pies,
    leaderboard_subplots,
    litgrid_capacity_plan_chart,
    region_treemap,
    save_chart,
    top_n_bar,
    voltpath_convergence_chart,
)
from .metrics import (
    before_after_convergence,
    convergence_summary,
    drop_ukraine,
    flow_type_summary,
    hourly_border_counts,
    peak,
    top_vs_rest,
)
from .regions import (
    BALTIC_ZONES,
    BORDER_CCR,
    CCR_MECHANISM_COLORS,
    REGION_COLORS,
    ZONE_COUNTRIES,
    ZONE_REGIONS,
    border_ccr_mechanism,
    border_country,
    border_region,
    is_baltic_border,
)

__all__ = [
    "API_KEY",
    "BALTIC_ZONES",
    "BASE_URL",
    "BORDER_CCR",
    "CCR_MECHANISM_COLORS",
    "FLOW_COLORS",
    "HEADERS",
    "LEADERBOARD_METRICS",
    "PRICE_LINE",
    "REGION_COLORS",
    "ZONE_COUNTRIES",
    "ZONE_REGIONS",
    "ast_price_convergence_chart",
    "before_after_convergence",
    "before_after_convergence_chart",
    "border_ccr_mechanism",
    "border_count_price_chart",
    "border_country",
    "border_region",
    "ccr_mechanism_treemap",
    "concentration_pie_chart",
    "congestion_ci_chart",
    "congestion_rent_schematic",
    "convergence_summary",
    "daily_rent_chart",
    "drop_ukraine",
    "fetch_flows",
    "fetch_flows_range",
    "flow_duration_curve",
    "flow_price_scatter",
    "flow_type_share_pies",
    "flow_type_summary",
    "hourly_border_counts",
    "is_baltic_border",
    "leaderboard_subplots",
    "litgrid_capacity_plan_chart",
    "peak",
    "region_treemap",
    "save_chart",
    "top_n_bar",
    "top_vs_rest",
    "voltpath_convergence_chart",
]
