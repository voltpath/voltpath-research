"""Graph-building and robustness helpers for flow-network analysis."""

from collections import defaultdict

import networkx as nx
import pandas as pd

from .metrics import drop_ukraine


def build_flow_graph(flows: pd.DataFrame) -> nx.DiGraph:
    """Directed, flow-weighted graph: each border becomes up to two edges.

    `net_flow_mw` is signed and `bidding_zone_from`/`bidding_zone_to` are a
    fixed nominal pair, not the actual flow direction - summing the positive
    and negative parts separately recovers the real directed throughput each
    way. Collapsing on the nominal column direction instead would zero out
    every border that mostly flows "backward".
    """
    flows = drop_ukraine(flows)
    G = nx.DiGraph()
    for (zone_from, zone_to), sub in flows.groupby(["bidding_zone_from", "bidding_zone_to"]):
        forward = sub.loc[sub["net_flow_mw"] > 0, "net_flow_mw"].sum()
        backward = -sub.loc[sub["net_flow_mw"] < 0, "net_flow_mw"].sum()
        if forward > 0:
            G.add_edge(zone_from, zone_to, weight=forward)
        if backward > 0:
            G.add_edge(zone_to, zone_from, weight=backward)
    return G


def build_rent_graph(flows: pd.DataFrame) -> nx.DiGraph:
    """Same direction convention as `build_flow_graph`, weighted by congestion rent (`value_eur`), not MW."""
    flows = drop_ukraine(flows)
    G = nx.DiGraph()
    for (zone_from, zone_to), sub in flows.groupby(["bidding_zone_from", "bidding_zone_to"]):
        forward = sub.loc[sub["net_flow_mw"] > 0, "value_eur"].abs().sum()
        backward = sub.loc[sub["net_flow_mw"] < 0, "value_eur"].abs().sum()
        if forward > 0:
            G.add_edge(zone_from, zone_to, weight=forward)
        if backward > 0:
            G.add_edge(zone_to, zone_from, weight=backward)
    return G


def giant_component_fraction(G: nx.DiGraph, n_total: int) -> float:
    """Largest weakly-connected component's share of all `n_total` original nodes."""
    if G.number_of_nodes() == 0:
        return 0.0
    return max(len(c) for c in nx.weakly_connected_components(G)) / n_total


def node_robustness_curve(G: nx.DiGraph, order: list[str]) -> list[float]:
    """Giant-component fraction after removing nodes one at a time, in `order`."""
    G = G.copy()
    n_total = G.number_of_nodes()
    sizes = [giant_component_fraction(G, n_total)]
    for node in order:
        G.remove_node(node)
        sizes.append(giant_component_fraction(G, n_total))
    return sizes


def edge_robustness_curve(G: nx.DiGraph, order: list[tuple[str, str]]) -> list[float]:
    """Giant-component fraction after removing edges one at a time, in `order`.

    Misleading on this graph: a bidirectional border is two directed edges
    (`build_flow_graph` adds one each way), so this removes a single
    physical asset as two separate events at two different ranks, instead
    of taking out both directions at once like a real outage would. That
    understates each removal's impact and roughly doubles the apparent
    number of failures needed to collapse the network. Use
    `border_robustness_curve` instead, which removes both directions of a
    border atomically. Kept for reference/comparison, not for new analysis.
    """
    G = G.copy()
    n_total = G.number_of_nodes()
    sizes = [giant_component_fraction(G, n_total)]
    for edge in order:
        G.remove_edge(*edge)
        sizes.append(giant_component_fraction(G, n_total))
    return sizes


def border_robustness_curve(G: nx.DiGraph, order: list[frozenset[str]]) -> list[float]:
    """Giant-component fraction after removing borders one at a time, in `order`.

    Each border is a `frozenset({u, v})`; both directed edges between u and
    v (if present) are removed together as one event, matching a real
    physical outage taking out the whole interconnector at once.
    """
    G = G.copy()
    n_total = G.number_of_nodes()
    sizes = [giant_component_fraction(G, n_total)]
    for border in order:
        u, v = tuple(border) if len(border) == 2 else (next(iter(border)),) * 2
        for a, b in ((u, v), (v, u)):
            if G.has_edge(a, b):
                G.remove_edge(a, b)
        sizes.append(giant_component_fraction(G, n_total))
    return sizes


def border_betweenness(edge_betweenness: dict[tuple[str, str], float]) -> dict[frozenset[str], float]:
    """Collapse directed-edge betweenness into one score per border (sum of both directions)."""
    scores: dict[frozenset[str], float] = defaultdict(float)
    for (u, v), score in edge_betweenness.items():
        scores[frozenset((u, v))] += score
    return dict(scores)
