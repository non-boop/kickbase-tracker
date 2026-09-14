"""Budget estimation for managers we can't query directly.

Kickbase's API only ever tells you YOUR OWN current budget. For every
other manager in the league we have to derive it:

    budget = start_capital + realized_profit + reserves - team_value

where `reserves` is included only under one of two possible readings of
"profit" (Kickbase doesn't document which). We calibrate by computing
both readings for OURSELVES (whose real budget we do know from the
dashboard endpoint) and keeping whichever one matches — then apply that
same reading to everyone else. This is the same technique used by the
existing open-source Kickbase trading tools; it's an estimate, not a
guarantee, and is flagged untrusted when it's off by more than 1% of
starting capital.

v1 note: we don't yet parse the activities feed into a reliable
realized-profit-per-manager number (the feed's field layout is one of
the least documented parts of the API), so `profit` is treated as 0 for
everyone for now. That means the estimate below is really just "cash
not currently tied up in your squad", which ignores trading gains/losses
and periodic income — directionally useful, not exact. Once we've seen
real feed data from a live run we can refine this.
"""

START_BUDGET_DEFAULT = 50_000_000


def start_capital(rules):
    return rules.get("start_budget", START_BUDGET_DEFAULT)


def derive_budget(team_value, profit, unrealized, rules, reading):
    if team_value is None or profit is None:
        return None
    reserves = unrealized if reading == "with_reserves" else 0
    if reserves is None:
        reserves = 0
    return start_capital(rules) + profit + reserves - team_value


def calibrate(me_team_value, me_profit, me_unrealized, actual_budget, rules):
    if actual_budget is None or me_team_value is None:
        return {"reading": "no_reserves", "error": None, "trusted": False}
    candidates = []
    for reading in ("no_reserves", "with_reserves"):
        derived = derive_budget(me_team_value, me_profit, me_unrealized, rules, reading)
        if derived is not None:
            candidates.append((reading, derived - actual_budget))
    if not candidates:
        return {"reading": "no_reserves", "error": None, "trusted": False}
    candidates.sort(key=lambda c: abs(c[1]))
    reading, error = candidates[0]
    tolerance = start_capital(rules) * 0.01
    return {"reading": reading, "error": error, "trusted": abs(error) <= tolerance}
