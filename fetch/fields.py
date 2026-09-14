"""Kickbase's v4 API uses short, undocumented field abbreviations that
occasionally differ between endpoints/app versions. Each logical field
lists every abbreviation seen across community projects; pick() takes
the first one present.
"""

def pick(d, *keys, default=None):
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


FIELD = {
    "id": ("i", "id", "pi"),
    "first_name": ("fn", "firstName"),
    "last_name": ("n", "ln", "lastName"),
    "position": ("pos",),
    "market_value": ("mv", "marketValue"),
    "points": ("p", "totalPoints"),
    "average": ("ap", "averagePoints"),
    "day_delta": ("tfhmvt",),
    "week_delta": ("sdmvt",),
    "total_gain": ("mvgl",),
    "buy_price": ("prs", "buyPrice"),
    "status": ("st", "status"),
    "team_id": ("tid", "teamId"),
    "team_name": ("tn", "teamName"),
    "price": ("prc", "price"),
    "expiry": ("exs", "expiry"),
    "seller_name": ("unm", "usnm"),
    "user_id": ("uid", "userId", "id"),
    "name": ("n", "name"),
    "budget": ("b", "budget", "bg"),
    "team_value": ("tv", "teamValue"),
}

POSITION_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def player_from(raw):
    if not isinstance(raw, dict):
        return None
    g = lambda key: pick(raw, *FIELD[key])
    first = g("first_name") or ""
    last = g("last_name") or ""
    name = (f"{first} {last}").strip() or last or first or "Unknown"
    pos = g("position")
    return {
        "id": g("id"),
        "name": name,
        "position": POSITION_NAMES.get(pos, pos),
        "team_id": g("team_id"),
        "team_name": g("team_name"),
        "market_value": g("market_value"),
        "day_delta": g("day_delta"),
        "week_delta": g("week_delta"),
        "total_gain": g("total_gain"),
        "points": g("points"),
        "average": g("average"),
        "status": g("status"),
        "price": g("price"),
        "expiry": g("expiry"),
        "seller_name": g("seller_name"),
        "buy_price": g("buy_price"),
    }


def find_list(container, *candidate_keys):
    """Kickbase list responses are usually {"<key>": [...]} with the key
    varying by endpoint/version. Return the first list found, trying the
    given candidate keys first, then any list-valued key at all."""
    if isinstance(container, list):
        return container
    if not isinstance(container, dict):
        return []
    for k in candidate_keys:
        if isinstance(container.get(k), list):
            return container[k]
    for v in container.values():
        if isinstance(v, list):
            return v
    return []
