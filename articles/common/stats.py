"""Power-law / heavy-tail fitting (Clauset-Shalizi-Newman MLE + likelihood-ratio
test), via the `powerlaw` package. Separate from metrics.py (pandas leaderboard
aggregations) and charts.py (figure builders) - this is statistical inference,
not data prep or plotting.
"""

import hashlib
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import powerlaw

# Same level as api.py's CACHE_DIR (articles/.cache) - the xmin search behind
# fit_distribution() can take minutes on the widest-dynamic-range columns
# (e.g. value_eur spans 5e-7 to 9e7), so re-running a notebook cell shouldn't
# recompute it; disk-cache the whole Fit object, keyed by the actual data.
_FIT_CACHE_DIR = Path(__file__).parent.parent / ".cache" / "fits"


def fit_distribution(
    values: pd.Series, name: str, discrete: bool = False, subsample: int | None = None, seed: int = 0
) -> dict:
    """CSN MLE fit of `values` against power-law, lognormal, and exponential,
    plus likelihood-ratio comparisons. `values` must be strictly positive -
    filter zeros/negatives before calling.

    `subsample` caps the xmin search cost for large n (powerlaw's xmin scan is
    worse than linear in n); the MLE alpha/xmin stabilize well before 1M points,
    so a fixed-seed subsample is a legitimate approximation, not a shortcut that
    changes the result.
    """
    data = values.to_numpy()
    n_total = len(data)
    if subsample is not None and n_total > subsample:
        data = np.random.default_rng(seed).choice(data, size=subsample, replace=False)

    data_hash = hashlib.sha256(np.ascontiguousarray(data).tobytes()).hexdigest()[:16]
    safe_name = "".join(c if c.isalnum() else "-" for c in name)
    cache_file = _FIT_CACHE_DIR / f"{safe_name}-{discrete}-{data_hash}.pkl"
    if cache_file.exists():
        cached = pickle.loads(cache_file.read_bytes())
        if "ks_power_law" not in cached:
            cached["ks_power_law"] = cached["fit"].power_law.D
            cached["ks_lognormal"] = cached["fit"].lognormal.D
            cached["ks_exponential"] = cached["fit"].exponential.D
        if "ks_truncated_power_law" not in cached:
            fit = cached["fit"]
            r_truncated, p_truncated = fit.distribution_compare("power_law", "truncated_power_law")
            cached["ks_truncated_power_law"] = fit.truncated_power_law.D
            cached["r_truncated_power_law"] = r_truncated
            cached["p_truncated_power_law"] = p_truncated
        cache_file.write_bytes(pickle.dumps(cached))
        return cached

    fit = powerlaw.Fit(data, discrete=discrete, verbose=False)
    r_lognormal, p_lognormal = fit.distribution_compare("power_law", "lognormal")
    r_exponential, p_exponential = fit.distribution_compare("power_law", "exponential")
    r_truncated, p_truncated = fit.distribution_compare("power_law", "truncated_power_law")

    result = {
        "name": name,
        "n_total": n_total,
        "n_fit": len(data),
        "xmin": fit.xmin,
        "alpha": fit.alpha,
        "n_tail": int((data >= fit.xmin).sum()),
        "ks_power_law": fit.power_law.D,
        "ks_lognormal": fit.lognormal.D,
        "ks_exponential": fit.exponential.D,
        "ks_truncated_power_law": fit.truncated_power_law.D,
        "r_lognormal": r_lognormal,
        "p_lognormal": p_lognormal,
        "r_exponential": r_exponential,
        "p_exponential": p_exponential,
        "r_truncated_power_law": r_truncated,
        "p_truncated_power_law": p_truncated,
        "fit": fit,
    }
    _FIT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(pickle.dumps(result))
    return result


def fit_verdict(result: dict, alpha: float = 0.05) -> str:
    """Plain-English read of the two likelihood-ratio tests. Power law must
    both beat exponential (rule out thin-tailed/memoryless) and beat lognormal
    decisively (rule out the other common heavy-tailed alternative) to be
    called the preferred model; `p > alpha` means the comparison can't tell
    the two candidates apart on this data, which is reported as such rather
    than defaulting to either.
    """
    if result["p_exponential"] >= alpha or result["r_exponential"] <= 0:
        return "not heavy-tailed (exponential not ruled out)"
    if result["p_lognormal"] >= alpha:
        return "heavy-tailed, power law vs lognormal inconclusive"
    return "power law favored" if result["r_lognormal"] > 0 else "lognormal favored"


def truncation_verdict(result: dict, alpha: float = 0.05) -> str:
    """Does an exponential cutoff improve on the plain power law? A bounded
    system (event duration can't exceed a market day, price is capped, etc.)
    predicts yes - this is a direct test of that mechanistic explanation,
    independent of the power-law-vs-lognormal question `fit_verdict` answers.
    """
    if result["r_truncated_power_law"] < 0 and result["p_truncated_power_law"] < alpha:
        return "truncation favored (bounded)"
    return "no truncation benefit"


def fit_results_table(results: list[dict]) -> pd.DataFrame:
    """Drop the `fit` object (powerlaw.Fit, not displayable) and tabulate the rest,
    with plain-English verdict columns appended.
    """
    rows = []
    for r in results:
        row = {k: v for k, v in r.items() if k != "fit"}
        row["verdict"] = fit_verdict(r)
        row["truncation"] = truncation_verdict(r)
        rows.append(row)
    return pd.DataFrame(rows).set_index("name")


def scaling_relation(size: pd.Series, duration_h: pd.Series, name: str) -> dict:
    """Log-log OLS of event size against duration - the avalanche
    size-duration scaling exponent (gamma), a signature tested between two
    variables rather than read off a single marginal distribution's tail.
    """
    from scipy.stats import linregress

    mask = (size > 0) & (duration_h > 0)
    x = np.log10(duration_h[mask])
    y = np.log10(size[mask])
    slope, intercept, r, p, _ = linregress(x, y)
    return {
        "name": name,
        "n": int(mask.sum()),
        "gamma": slope,
        "intercept": intercept,
        "r_squared": r**2,
        "p": p,
    }


def border_clustering_test(
    events: pd.DataFrame,
    lag_h: float = 6.0,
    n_perm: int = 1000,
    quantile: float = 0.75,
    seed: int = 0,
) -> dict:
    """Permutation test for cascade/propagation: do large events on adjacent
    borders (sharing a zone endpoint) coincide or follow each other within
    `lag_h` hours more often than a circular-shift null? The null randomly
    rotates each border's own event timeline within the overall study window
    - this preserves each border's event count and internal spacing but
    scrambles cross-border alignment, so a common external driver (e.g. a
    continent-wide price shock) hitting many borders at once does NOT by
    itself inflate the observed count; only genuine propagation between
    adjacent borders does.
    """
    large = events[events["value_eur"] >= events["value_eur"].quantile(quantile)].copy()
    zone_from = large["border"].str.split(" -> ").str[0]
    zone_to = large["border"].str.split(" -> ").str[1]
    large = large.assign(zone_from=zone_from, zone_to=zone_to)

    zone_borders: dict[str, set[str]] = {}
    for border, zf, zt in (
        large[["border", "zone_from", "zone_to"]].drop_duplicates("border").itertuples(index=False)
    ):
        zone_borders.setdefault(zf, set()).add(border)
        zone_borders.setdefault(zt, set()).add(border)
    adjacent_pairs = {
        tuple(sorted((b1, b2)))
        for borders in zone_borders.values()
        for b1 in borders
        for b2 in borders
        if b1 != b2
    }

    window_start = large["start"].min()
    window_h = (large["end"].max() - window_start) / pd.Timedelta(hours=1)
    lag = pd.Timedelta(hours=lag_h)

    def to_arrays(df: pd.DataFrame) -> dict[str, np.ndarray]:
        return {b: g[["start", "end"]].sort_values("start").to_numpy() for b, g in df.groupby("border")}

    def count_cooccurrences(timings: dict[str, np.ndarray]) -> int:
        total = 0
        for b1, b2 in adjacent_pairs:
            if b1 not in timings or b2 not in timings:
                continue
            s1, e1 = timings[b1][:, 0], timings[b1][:, 1]
            s2 = timings[b2][:, 0]
            lo = np.searchsorted(s2, s1 - lag)
            hi = np.searchsorted(s2, e1 + lag)
            total += int((hi - lo).sum())
        return total

    observed = count_cooccurrences(to_arrays(large))

    rng = np.random.default_rng(seed)
    borders = large["border"].unique()
    window_len = pd.Timedelta(hours=window_h)
    null_counts = np.empty(n_perm)
    for i in range(n_perm):
        offsets = pd.Series(rng.uniform(0, window_h, size=len(borders)), index=borders).map(
            lambda h: pd.Timedelta(hours=h)
        )
        shifted = large.copy()
        rel_start = (shifted["start"] - window_start + shifted["border"].map(offsets)) % window_len
        duration = shifted["end"] - shifted["start"]
        shifted["start"] = window_start + rel_start
        shifted["end"] = shifted["start"] + duration
        null_counts[i] = count_cooccurrences(to_arrays(shifted))

    return {
        "n_large_events": len(large),
        "n_adjacent_pairs": len(adjacent_pairs),
        "observed_cooccurrences": observed,
        "null_mean": float(null_counts.mean()),
        "null_p95": float(np.quantile(null_counts, 0.95)),
        "p_value": float((null_counts >= observed).mean()),
    }
