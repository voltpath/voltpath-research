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
    if (
        country_from not in MULTI_ZONE_COUNTRIES
        and country_to not in MULTI_ZONE_COUNTRIES
    ):
        return None
    return (
        country_from if country_from == country_to else f"{country_from} - {country_to}"
    )
