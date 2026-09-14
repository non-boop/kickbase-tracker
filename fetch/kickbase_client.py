"""Thin client for the unofficial Kickbase v4 API.

Endpoint paths and login payload are reverse-engineered from community
projects (kevinskyba/kickbase-api-doc, MarcGriese/kickbase-dashboard).
Kickbase can change these without notice, so every call tries a short
list of known-plausible paths and raises with the response body on
failure so a run's logs are actually debuggable.
"""
import requests

BASE_URL = "https://api.kickbase.com"
TIMEOUT = 20


class KickbaseError(Exception):
    pass


def login(email: str, password: str):
    url = f"{BASE_URL}/v4/user/login"
    r = requests.post(
        url,
        json={"em": email, "pass": password},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        raise KickbaseError(f"login failed: {r.status_code} {r.text[:300]}")
    data = r.json()
    token = data.get("tkn") or data.get("token") or data.get("accessToken")
    if not token:
        for k in ("u", "user"):
            inner = data.get(k)
            if isinstance(inner, dict):
                token = inner.get("tkn") or inner.get("token")
                if token:
                    break
    if not token:
        raise KickbaseError(f"login ok but no token found; top-level keys: {list(data.keys())}")
    return token, data


def _get(token: str, path: str, params=None):
    url = f"{BASE_URL}{path}"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        params=params,
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        raise KickbaseError(f"GET {path} -> {r.status_code} {r.text[:300]}")
    try:
        return r.json()
    except ValueError:
        raise KickbaseError(f"GET {path} -> non-JSON response: {r.text[:300]}")


def get_first_working(token: str, paths, params=None):
    last_err = None
    for p in paths:
        try:
            return p, _get(token, p, params)
        except KickbaseError as e:
            last_err = e
            continue
    raise last_err or KickbaseError(f"all candidate paths failed: {paths}")


def get_me(token: str):
    try:
        _, data = get_first_working(token, ["/v4/user/settings", "/v4/user/me"])
        return data
    except KickbaseError:
        return {}


def get_leagues(token: str):
    _, data = get_first_working(token, ["/v4/leagues/selection", "/v4/leagues", "/v4/leagues/list"])
    if isinstance(data, dict):
        for key in ("leagues", "items", "it", "data"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return data


def get_market(token: str, league_id: str):
    return _get(token, f"/v4/leagues/{league_id}/market")


def get_squad(token: str, league_id: str):
    return _get(token, f"/v4/leagues/{league_id}/squad")


def get_manager_dashboard(token: str, league_id: str, user_id: str):
    return _get(token, f"/v4/leagues/{league_id}/managers/{user_id}/dashboard")


def get_manager_squad(token: str, league_id: str, user_id: str):
    return _get(token, f"/v4/leagues/{league_id}/managers/{user_id}/squad")


def get_ranking(token: str, league_id: str):
    return _get(token, f"/v4/leagues/{league_id}/ranking")


def get_activities_feed(token: str, league_id: str):
    try:
        return _get(token, f"/v4/leagues/{league_id}/activitiesFeed")
    except KickbaseError:
        return None
