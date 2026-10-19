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
            cache_file.write_bytes(pickle.dumps(cached))
        return cached

    fit = powerlaw.Fit(data, discrete=discrete, verbose=False)
    r_lognormal, p_lognormal = fit.distribution_compare("power_law", "lognormal")
    r_exponential, p_exponential = fit.distribution_compare("power_law", "exponential")

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
        "r_lognormal": r_lognormal,
        "p_lognormal": p_lognormal,
        "r_exponential": r_exponential,
        "p_exponential": p_exponential,
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


def fit_results_table(results: list[dict]) -> pd.DataFrame:
    """Drop the `fit` object (powerlaw.Fit, not displayable) and tabulate the rest,
    with a plain-English verdict column appended.
    """
    rows = []
    for r in results:
        row = {k: v for k, v in r.items() if k != "fit"}
        row["verdict"] = fit_verdict(r)
        rows.append(row)
    return pd.DataFrame(rows).set_index("name")
