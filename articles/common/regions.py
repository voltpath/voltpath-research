"""Zone-to-region and zone-to-country mappings for grouping borders geographically."""

from collections import Counter

# Approximate CCR-style regions for voltpath's zone codes, colors eyeballed off
# ENTSO-E's public CCR map (entsoe.eu/bites/ccr-map). This is a best-effort
# geographic grouping for charting, not the real (overlapping) CCR membership
# - several TSOs legally sit in more than one CCR, which a one-region-per-zone
# map can't represent, so borders that cross a region boundary are bucketed
# as "Cross-region" rather than forced into either side.
REGION_COLORS = {
    "Nordic": "#8FBF87",
    "Baltic": "#D98888",
    "Core": "#7EC8D8",
    "Italy North": "#F0A857",
    "Greece-Italy": "#93A6DE",
    "South-East Europe": "#B58FC4",
    "South-West Europe": "#A9D9B0",
    "Cross-region": "#B0B0B0",
}

ZONE_REGIONS = {
    "NO_1": "Nordic",
    "NO_2": "Nordic",
    "NO_3": "Nordic",
    "NO_4": "Nordic",
    "NO_5": "Nordic",
    "SE_1": "Nordic",
    "SE_2": "Nordic",
    "SE_3": "Nordic",
    "SE_4": "Nordic",
    "DK_1": "Nordic",
    "DK_2": "Nordic",
    "FI": "Nordic",
    "EE": "Baltic",
    "LV": "Baltic",
    "LT": "Baltic",
    "DE_LU": "Core",
    "AT": "Core",
    "CH": "Core",
    "CZ": "Core",
    "PL": "Core",
    "HU": "Core",
    "BE": "Core",
    "NL": "Core",
    "SK": "Core",
    "IT_NORD": "Italy North",
    "IT_CNOR": "Greece-Italy",
    "IT_CSUD": "Greece-Italy",
    "IT_SUD": "Greece-Italy",
    "IT_CALA": "Greece-Italy",
    "IT_SICI": "Greece-Italy",
    "IT_SARD": "Greece-Italy",
    "GR": "Greece-Italy",
    "RO": "South-East Europe",
    "BG": "South-East Europe",
    "SI": "South-East Europe",
    "HR": "South-East Europe",
    "RS": "South-East Europe",
    "ME": "South-East Europe",
    "MK": "South-East Europe",
    "AL": "South-East Europe",
    "FR": "South-West Europe",
    "ES": "South-West Europe",
    "PT": "South-West Europe",
}

# Country each zone belongs to - splits multi-zone countries (NO_1..5, SE_1..4,
# DK_1..2, IT_*) back to one country label; DE_LU is voltpath's joint
# Germany-Luxembourg zone, kept as-is rather than guessed apart.
ZONE_COUNTRIES = {
    "NO_1": "Norway",
    "NO_2": "Norway",
    "NO_3": "Norway",
    "NO_4": "Norway",
    "NO_5": "Norway",
    "SE_1": "Sweden",
    "SE_2": "Sweden",
    "SE_3": "Sweden",
    "SE_4": "Sweden",
    "DK_1": "Denmark",
    "DK_2": "Denmark",
    "FI": "Finland",
    "EE": "Estonia",
    "LV": "Latvia",
    "LT": "Lithuania",
    "DE_LU": "Germany-Luxembourg",
    "AT": "Austria",
    "CH": "Switzerland",
    "CZ": "Czechia",
    "PL": "Poland",
    "HU": "Hungary",
    "BE": "Belgium",
    "NL": "Netherlands",
    "SK": "Slovakia",
    "IT_NORD": "Italy",
    "IT_CNOR": "Italy",
    "IT_CSUD": "Italy",
    "IT_SUD": "Italy",
    "IT_CALA": "Italy",
    "IT_SICI": "Italy",
    "IT_SARD": "Italy",
    "GR": "Greece",
    "RO": "Romania",
    "BG": "Bulgaria",
    "SI": "Slovenia",
    "HR": "Croatia",
    "RS": "Serbia",
    "ME": "Montenegro",
    "MK": "North Macedonia",
    "AL": "Albania",
    "FR": "France",
    "ES": "Spain",
    "PT": "Portugal",
    "UA_IPS": "Ukraine",
}


def border_region(border: str) -> str:
    """Approximate CCR-style region for a border (see ZONE_REGIONS)."""
    zone_from, zone_to = border.split(" -> ")
    region_from = ZONE_REGIONS.get(zone_from, "Cross-region")
    region_to = ZONE_REGIONS.get(zone_to, "Cross-region")
    return region_from if region_from == region_to else "Cross-region"


BALTIC_ZONES = {"EE", "LV", "LT"}


def is_baltic_border(border: str) -> bool:
    """Whether either side of the border is a Baltic zone (see BALTIC_ZONES)."""
    return any(zone in BALTIC_ZONES for zone in border.split(" -> "))


_ZONE_COUNTRY_COUNTS = Counter(ZONE_COUNTRIES.values())
# Countries split across several bidding zones (Norway NO_1..5, Italy IT_*,
# etc.) - only these are worth a country-level treemap node between region
# and border; for a single-zone country the country label is just a 1:1
# relabeling of the border, adding a redundant layer.
MULTI_ZONE_COUNTRIES = {c for c, n in _ZONE_COUNTRY_COUNTS.items() if n > 1}


def border_country(border: str) -> str | None:
    """Country pair label for a border, e.g. 'France - Spain'.

    Returns None when neither side is a multi-bidding-zone country (see
    MULTI_ZONE_COUNTRIES) - used to skip the country level of a treemap path
    for borders where it wouldn't add anything over the border label itself.
    """
    zone_from, zone_to = border.split(" -> ")
    country_from = ZONE_COUNTRIES.get(zone_from, zone_from)
    country_to = ZONE_COUNTRIES.get(zone_to, zone_to)
    if country_from not in MULTI_ZONE_COUNTRIES and country_to not in MULTI_ZONE_COUNTRIES:
        return None
    return country_from if country_from == country_to else f"{country_from} - {country_to}"


CCR_OTHER = "Other (not in Iacopo's CCR breakdown)"

# Real per-border CCR capacity-allocation mechanism, transcribed from Iacopo
# Bertelli's "Counterintuitive Flows in 2023, Part 3" (LinkedIn), grouped by
# mechanism rather than geography - see scratch/media/*.png for the source
# charts. Unlike ZONE_REGIONS this is keyed by the actual border pair, not a
# per-zone label, since real CCR membership overlaps (Germany-Luxembourg sits
# in both Core and Hansa, France in both Core and SWE, etc.) in a way a
# one-region-per-zone dict can't represent.
#
# Italy North's borders are folded into Core here rather than kept as their
# own 2023-era group, since ACER decisions 04/2024 and 10/2025 merge the two
# into a single CCR - officially renamed "Central Europe", though "Core" is
# still the term in common use (day-ahead go-live for the merged region isn't
# until 2027). Borders outside Iacopo's breakdown (Western Balkans, Ukraine,
# Sardinia, ...) fall back to CCR_OTHER.
CCR_MECHANISM_COLORS = {
    "Switzerland (explicit allocation)": "#B0B0B0",
    "SWE (price-coupled NTC, radial)": "#A9D9B0",
    "GRIT (price-coupled NTC, radial)": "#93A6DE",
    "SEE (price-coupled NTC, radial)": "#B58FC4",
    "Baltic (price-coupled NTC, radial)": "#D98888",
    "Core (price-coupled, flow-based)": "#7EC8D8",
    "Hansa (price-coupled NTC, lineset)": "#F0A857",
    "Nordic (price-coupled NTC, lineset)": "#8FBF87",
    CCR_OTHER: "#6B818C",
}

_CCR_BORDERS: dict[str, list[tuple[str, str]]] = {
    "Switzerland (explicit allocation)": [
        ("AT", "CH"),
        ("CH", "DE_LU"),
        ("CH", "FR"),
        ("CH", "IT_NORD"),
    ],
    "SWE (price-coupled NTC, radial)": [("ES", "PT"), ("ES", "FR")],
    "GRIT (price-coupled NTC, radial)": [
        ("IT_CALA", "IT_SICI"),
        ("IT_CALA", "IT_SUD"),
        ("IT_CNOR", "IT_CSUD"),
        ("IT_CNOR", "IT_NORD"),
        ("IT_CSUD", "IT_SUD"),
        ("GR", "IT_SUD"),
    ],
    "SEE (price-coupled NTC, radial)": [("BG", "RO")],
    "Baltic (price-coupled NTC, radial)": [
        ("EE", "FI"),
        ("EE", "LV"),
        ("LT", "LV"),
        ("LT", "SE_4"),
        ("LT", "PL"),
    ],
    "Core (price-coupled, flow-based)": [
        ("AT", "CZ"),
        ("AT", "DE_LU"),
        ("AT", "HU"),
        ("AT", "SI"),
        ("BE", "DE_LU"),
        ("BE", "FR"),
        ("BE", "NL"),
        ("CZ", "DE_LU"),
        ("CZ", "SK"),
        ("DE_LU", "FR"),
        ("DE_LU", "NL"),
        ("HR", "HU"),
        ("HR", "SI"),
        ("HU", "RO"),
        ("HU", "SI"),
        ("HU", "SK"),
        ("CZ", "PL"),
        ("DE_LU", "PL"),
        ("PL", "SK"),
        ("AT", "IT_NORD"),
        ("FR", "IT_NORD"),
        ("IT_NORD", "SI"),
    ],
    "Hansa (price-coupled NTC, lineset)": [
        ("DE_LU", "DK_1"),
        ("DE_LU", "DK_2"),
        ("DE_LU", "NO_2"),
        ("DE_LU", "SE_4"),
        ("DK_1", "NL"),
        ("NL", "NO_2"),
        ("PL", "SE_4"),
    ],
    "Nordic (price-coupled NTC, lineset)": [
        ("DK_1", "DK_2"),
        ("DK_1", "NO_2"),
        ("DK_1", "SE_3"),
        ("DK_2", "SE_4"),
        ("FI", "SE_1"),
        ("FI", "SE_3"),
        ("NO_1", "NO_2"),
        ("NO_1", "NO_3"),
        ("NO_1", "NO_5"),
        ("NO_1", "SE_3"),
        ("NO_2", "NO_5"),
        ("NO_3", "NO_4"),
        ("NO_3", "NO_5"),
        ("NO_3", "SE_2"),
        ("NO_4", "SE_1"),
        ("NO_4", "SE_2"),
        ("SE_1", "SE_2"),
        ("SE_2", "SE_3"),
        ("SE_3", "SE_4"),
    ],
}

BORDER_CCR = {frozenset(pair): mechanism for mechanism, pairs in _CCR_BORDERS.items() for pair in pairs}


def border_ccr_mechanism(border: str) -> str:
    """CCR capacity-allocation mechanism for a border (see BORDER_CCR)."""
    zone_from, zone_to = border.split(" -> ")
    return BORDER_CCR.get(frozenset((zone_from, zone_to)), CCR_OTHER)


# The 9 virtual bidding zones Core's Advanced Hybrid Coupling (AHC) go-live
# (2026-06-11) added to its topology: 6 HVDC links to the Nordics plus the
# DE-DK1, PL-LT and RO-BG external borders. BORDER_CCR/border_ccr_mechanism
# isn't date-aware and still reports these under their pre-AHC regional
# mechanism (Hansa/Baltic/SEE) - kept that way deliberately so existing
# per-CCR charts aren't affected. Use this set alongside, not instead of,
# border_ccr_mechanism when the question is specifically "is this one of
# AHC's new VBZs".
CORE_AHC_VBZ_BORDERS = [
    ("DE_LU", "SE_4"),  # Baltic Cable
    ("DE_LU", "NO_2"),  # NordLink
    ("DK_1", "NL"),  # Cobra
    ("DE_LU", "DK_2"),  # Kontek
    ("NL", "NO_2"),  # NorNed
    ("PL", "SE_4"),  # SwePol
    ("DE_LU", "DK_1"),  # DE-DK1
    ("LT", "PL"),  # PL-LT
    ("BG", "RO"),  # RO-BG
]
CORE_AHC_VBZ_BORDER_SET = {frozenset(pair) for pair in CORE_AHC_VBZ_BORDERS}


def is_core_ahc_vbz(border: str) -> bool:
    """Whether `border` is one of Core AHC's 9 new virtual bidding zones (see CORE_AHC_VBZ_BORDERS)."""
    zone_from, zone_to = border.split(" -> ")
    return frozenset((zone_from, zone_to)) in CORE_AHC_VBZ_BORDER_SET
