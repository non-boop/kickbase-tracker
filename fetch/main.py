"""Daily Kickbase scan: log in, pull the market + league state, compute
top movers, buy recommendations and per-manager budget estimates, and
write the result to data/latest.json for the GitHub Action to commit.

Run by .github/workflows/kickbase-scan.yml with KICK_EMAIL / KICK_PASSWORD
as repo secrets. Never logs the password; on any failure it still writes
a JSON file (with an "error" field) so the workflow's commit step has
something to push and the dashboard can show a clear "last run failed"
state instead of silently going stale.
"""
import json
import os
import sys
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

import kickbase_client as kb
from fields import player_from, find_list, pick, FIELD
import budget as bud

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "latest.json")
LEAGUE_RULES = {"start_budget": int(os.environ.get("KICK_START_BUDGET", "50000000"))}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def safe(fn, *args, default=None, label=""):
    try:
        return fn(*args)
    except Exception as e:
        log(f"[warn] {label or fn.__name__} failed: {e}")
        return default


def team_value_and_reserves(squad_raw):
    players_raw = find_list(squad_raw, "it", "players", "squad")
    players = [player_from(p) for p in players_raw]
    players = [p for p in players if p]
    team_value = sum(p["market_value"] or 0 for p in players)
    # total_gain (mvgl) is Kickbase's own "gain since you bought this
    # player" figure when present; fall back to mv - buy_price.
    reserves = 0
    for p in players:
        if p["total_gain"] is not None:
            reserves += p["total_gain"]
        elif p["buy_price"] is not None and p["market_value"] is not None:
            reserves += p["market_value"] - p["buy_price"]
    return team_value, reserves, players


def main():
    email = os.environ.get("KICK_EMAIL")
    password = os.environ.get("KICK_PASSWORD")
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "error": None,
    }

    if not email or not password:
        result["error"] = "KICK_EMAIL / KICK_PASSWORD not set"
        write(result)
        sys.exit(1)

    try:
        token, login_data = kb.login(email, password)
        log("login ok")

        leagues = kb.get_leagues(token)
        if not leagues:
            raise kb.KickbaseError("no leagues returned for this account")
        league_raw = leagues[0]
        league_id = pick(league_raw, "i", "id", "leagueId")
        league_name = pick(league_raw, "n", "name")
        if not league_id:
            raise kb.KickbaseError(f"could not find league id in: {league_raw}")
        log(f"league: {league_name} ({league_id})")

        me_raw = safe(kb.get_me, token, default={}, label="get_me")
        my_id = pick(me_raw, "id", "i", "userId") or pick(login_data, "id", "i")

        # --- market (buyable players) ---
        market_raw = safe(kb.get_market, token, league_id, default={}, label="get_market")
        market_players_raw = find_list(market_raw, "it", "market", "players")
        market_players = [player_from(p) for p in market_players_raw]
        market_players = [p for p in market_players if p]
        log(f"market players: {len(market_players)}")

        # --- my squad + budget ---
        my_squad_raw = safe(kb.get_squad, token, league_id, default={}, label="get_squad")
        my_team_value, my_reserves, my_players = team_value_and_reserves(my_squad_raw)

        my_dashboard = safe(kb.get_manager_dashboard, token, league_id, my_id, default={}, label="get_manager_dashboard") if my_id else {}
        my_actual_budget = pick(my_dashboard, *FIELD["budget"])

        calib = bud.calibrate(my_team_value, 0, my_reserves, my_actual_budget, LEAGUE_RULES)
        log(f"budget calibration: {calib}")

        # --- other managers ---
        ranking_raw = safe(kb.get_ranking, token, league_id, default={}, label="get_ranking")
        ranking_list = find_list(ranking_raw, "us", "users", "managers", "it")
        managers = []
        for m in ranking_list:
            uid = pick(m, *FIELD["user_id"])
            name = pick(m, *FIELD["name"])
            if not uid:
                continue
            if my_id and str(uid) == str(my_id):
                team_value, reserves = my_team_value, my_reserves
                est_budget = my_actual_budget
                trusted = True
            else:
                sq = safe(kb.get_manager_squad, token, league_id, uid, default=None, label=f"squad({uid})")
                if sq is None:
                    managers.append({"id": uid, "name": name, "estimated_budget": None, "trusted": False})
                    continue
                team_value, reserves, _ = team_value_and_reserves(sq)
                est_budget = bud.derive_budget(team_value, 0, reserves, LEAGUE_RULES, calib["reading"])
                trusted = calib["trusted"]
            managers.append({
                "id": uid,
                "name": name,
                "team_value": team_value,
                "estimated_budget": est_budget,
                "trusted": trusted,
            })
        log(f"managers: {len(managers)}")

        activities_raw = safe(kb.get_activities_feed, token, league_id, default=None, label="get_activities_feed")

        # --- top gainers / losers across everything we could see (market + all squads) ---
        all_seen = {p["id"]: p for p in market_players if p.get("id")}
        for p in my_players:
            if p.get("id"):
                all_seen.setdefault(p["id"], p)
        movers = [p for p in all_seen.values() if p.get("day_delta") is not None]
        gainers = sorted(movers, key=lambda p: p["day_delta"], reverse=True)[:20]
        losers = sorted(movers, key=lambda p: p["day_delta"])[:20]

        # --- buy recommendations: value momentum + underpriced + affordable ---
        buyable = [p for p in market_players if p.get("price")]
        deltas_day = [p["day_delta"] for p in buyable if p.get("day_delta") is not None] or [0]
        max_day = max(abs(d) for d in deltas_day) or 1

        def score(p):
            momentum = (p.get("day_delta") or 0) / max_day
            momentum += 0.5 * ((p.get("week_delta") or 0) / max_day)
            ppm = 0.0
            if p.get("average") and p.get("price"):
                ppm = (p["average"] / (p["price"] / 1_000_000.0))  # avg points per million
            return momentum, ppm

        for p in buyable:
            m, ppm = score(p)
            p["_momentum"] = round(m, 4)
            p["_points_per_million"] = round(ppm, 4)
            p["affordable"] = (my_actual_budget is None) or (p["price"] <= my_actual_budget)

        recommendations = sorted(
            buyable,
            key=lambda p: (p["affordable"], p["_momentum"] + p["_points_per_million"] / 10.0),
            reverse=True,
        )[:20]

        result.update({
            "ok": True,
            "league": {"id": league_id, "name": league_name},
            "me": {
                "id": my_id,
                "budget": my_actual_budget,
                "team_value": my_team_value,
                "reserves": my_reserves,
            },
            "budget_calibration": calib,
            "gainers": gainers,
            "losers": losers,
            "buy_recommendations": recommendations,
            "managers": sorted(managers, key=lambda m: (m["estimated_budget"] is None, -(m["estimated_budget"] or 0))),
            "debug": {
                "market_count": len(market_players),
                "my_squad_count": len(my_players),
                "manager_count": len(managers),
                "has_activities_feed": activities_raw is not None,
            },
        })
    except Exception as e:
        log("FATAL:", e)
        log(traceback.format_exc())
        result["error"] = str(e)

    write(result)
    if not result["ok"]:
        sys.exit(1)


def write(result):
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    log(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
