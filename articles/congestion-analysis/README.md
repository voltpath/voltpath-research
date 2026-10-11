# Congestion Analysis

Estimates the **congestion rent** of Europe's grid bottlenecks from Voltpath data (`|price delta| x |flow| x duration`) &ndash; the price gap x volume the market captures while a border stays constrained, which is not the same thing as economic cost or lost welfare.

Builds a rolling 30-day leaderboard of the highest-rent borders, a case study of 2025's most widely congested moment, monthly and yearly leaderboards across four competing metrics, a concentration check on whether a few borders really dominate the total, and a breakdown by region and country.

Open [`congestion_analysis.ipynb`](congestion_analysis.ipynb) and run top to bottom. See the root [README](../../README.md) for setup.

`media/` holds the reference screenshot of the VoltPath dashboard embedded in the notebook; charts the notebook generates are written to a gitignored `output/`.

## CCR mechanism grouping: what's changed since 2023

The notebook's CCR-mechanism treemap follows Iacopo Bertelli's per-border groupings from ["Counterintuitive Flows in 2023, Part 3"](https://www.linkedin.com/pulse/counterintuitive-flows-2023-part-3-iacopo-bertelli-xjetf/), with two updates for changes since then:

- **Core + Italy North merger.** ACER is merging the Core and Italy North capacity calculation regions into a single "Central Europe" CCR (Decisions [04/2024](https://www.acer.europa.eu/news/acer-decide-changes-core-and-italy-north-electricity-capacity-calculation-regions) and [10/2025](https://www.acer.europa.eu/news/acer-introduces-new-central-europe-electricity-capacity-calculation-region), see also ENTSO-E's [explanatory note](https://eepublicdownloads.entsoe.eu/clean-documents/nc-tasks/250702_CCR%20Proposal%20for%20amendment_Explanatory%20Note_All%20TSOs%20approved.pdf)). Day-ahead go-live for the merged region isn't until 2027, and "Core" is still the term in common use, so Italy North's borders are folded into the "Core" label rather than kept separate or renamed.
- **Baltic synchronization.** Estonia, Latvia and Lithuania desynchronized from the Russia/Belarus grid and synchronized with the Continental European grid on 8&ndash;9 February 2025 ([EU Commission](https://cyprus.representation.ec.europa.eu/news/baltic-states-join-european-continental-electricity-grid-after-fully-disconnecting-russian-and-2025-02-09_en), [background](https://en.wikipedia.org/wiki/Baltic_states_synchronization_with_CESA)). This is a physical/frequency change, not a market one &ndash; the Baltic CCR's price-coupled NTC-radial mechanism is unchanged, so the treemap grouping itself didn't need updating for it.
