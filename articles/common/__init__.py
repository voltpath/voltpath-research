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
    border_count_price_chart,
    concentration_pie_chart,
    congestion_rent_schematic,
    daily_rent_chart,
    leaderboard_subplots,
    region_treemap,
    save_chart,
    top_n_bar,
)
from .metrics import (
    convergence_summary,
    drop_ukraine,
    flow_type_summary,
    hourly_border_counts,
    peak,
    top_vs_rest,
)
from .regions import (
    REGION_COLORS,
    ZONE_COUNTRIES,
    ZONE_REGIONS,
    border_country,
    border_region,
)

__all__ = [
    "API_KEY",
    "BASE_URL",
    "FLOW_COLORS",
    "HEADERS",
    "LEADERBOARD_METRICS",
    "PRICE_LINE",
    "REGION_COLORS",
    "ZONE_COUNTRIES",
    "ZONE_REGIONS",
    "border_count_price_chart",
    "border_country",
    "border_region",
    "concentration_pie_chart",
    "congestion_rent_schematic",
    "convergence_summary",
    "daily_rent_chart",
    "drop_ukraine",
    "fetch_flows",
    "fetch_flows_range",
    "flow_type_summary",
    "hourly_border_counts",
    "leaderboard_subplots",
    "peak",
    "region_treemap",
    "save_chart",
    "top_n_bar",
    "top_vs_rest",
]
