# Congestion Analysis

Estimates the **congestion rent** of Europe's grid bottlenecks from Voltpath data (`|price delta| x |flow| x duration`) &ndash; the price gap x volume the market captures while a border stays constrained, which is not the same thing as economic cost or lost welfare.

Builds a rolling 30-day leaderboard of the highest-rent borders, a case study of 2025's most widely congested moment, monthly and yearly leaderboards across four competing metrics, a concentration check on whether a few borders really dominate the total, and a breakdown by region and country.

Open [`congestion_analysis.ipynb`](congestion_analysis.ipynb) and run top to bottom. See the root [README](../../README.md) for setup.

`media/` holds the reference screenshot of the VoltPath dashboard embedded in the notebook; charts the notebook generates are written to a gitignored `output/`.
