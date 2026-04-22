from __future__ import annotations

from urllib.parse import urlencode
import re
import requests

from backend.config import (
    STEAM_API_KEY,
    BACKEND_BASE_URL,
    FRONTEND_BASE_URL,
    STEAM_OPENID_URL,
    STEAM_API_BASE,
)

STEAM_ID_PATTERN = re.compile(r"^https://steamcommunity\.com/openid/id/(\d+)$")
STEAM_ID64_ONLY_PATTERN = re.compile(r"^\d{17}$")
STEAM_PROFILE_URL_PATTERN = re.compile(
    r"^https?://steamcommunity\.com/profiles/(\d{17})(?:/.*)?$",
    re.IGNORECASE,
)
STEAM_VANITY_URL_PATTERN = re.compile(
    r"^https?://steamcommunity\.com/id/([^/?#]+)(?:/.*)?$",
    re.IGNORECASE,
)


def build_steam_login_url() -> str:
    """Build the OpenID redirect URL to Steam."""
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": f"{BACKEND_BASE_URL}/auth/steam/callback",
        "openid.realm": BACKEND_BASE_URL,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return f"{STEAM_OPENID_URL}/login?{urlencode(params)}"


def verify_openid_response(query_params: dict[str, str]) -> bool:
    """
    Verify Steam OpenID callback by posting back with mode=check_authentication.
    """
    verification_params = dict(query_params)
    verification_params["openid.mode"] = "check_authentication"

    response = requests.post(
        f"{STEAM_OPENID_URL}/login",
        data=verification_params,
        timeout=20,
    )
    response.raise_for_status()

    return "is_valid:true" in response.text


def extract_steam_id(claimed_id: str) -> str | None:
    """Extract SteamID64 from the claimed_id URL."""
    match = STEAM_ID_PATTERN.match(claimed_id or "")
    return match.group(1) if match else None


def resolve_vanity_url(vanity: str) -> str | None:
    """Resolve a vanity profile name to SteamID64 via Steam Web API."""
    if not STEAM_API_KEY:
        raise ValueError("STEAM_API_KEY is missing")

    url = f"{STEAM_API_BASE}/ISteamUser/ResolveVanityURL/v0001/"
    params = {
        "key": STEAM_API_KEY,
        "vanityurl": vanity,
        "format": "json",
    }
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()

    data = response.json().get("response", {})
    if data.get("success") == 1:
        return data.get("steamid")
    return None


def resolve_steam_input_to_id(steam_input: str) -> str:
    """
    Accept SteamID64, Steam profile URL, or vanity profile URL and return SteamID64.
    Supported examples:
    - 7656119...
    - https://steamcommunity.com/profiles/7656119...
    - https://steamcommunity.com/id/someVanityName
    """
    raw = (steam_input or "").strip()
    if not raw:
        raise ValueError("Steam input is empty")

    if STEAM_ID64_ONLY_PATTERN.match(raw):
        return raw

    if not raw.startswith(("http://", "https://")) and raw.startswith("steamcommunity.com/"):
        raw = f"https://{raw}"

    profile_match = STEAM_PROFILE_URL_PATTERN.match(raw)
    if profile_match:
        return profile_match.group(1)

    vanity_match = STEAM_VANITY_URL_PATTERN.match(raw)
    if vanity_match:
        vanity_name = vanity_match.group(1)
        resolved = resolve_vanity_url(vanity_name)
        if resolved:
            return resolved
        raise ValueError("Could not resolve vanity profile URL to SteamID")

    # Optional convenience: allow passing vanity slug directly.
    if re.match(r"^[A-Za-z0-9_-]{2,64}$", raw):
        resolved = resolve_vanity_url(raw)
        if resolved:
            return resolved

    raise ValueError(
        "Invalid Steam input. Use SteamID64, steamcommunity.com/profiles/<id>, "
        "or steamcommunity.com/id/<vanity>."
    )


def get_player_summary(steam_id: str) -> dict:
    """Fetch basic public profile info."""
    if not STEAM_API_KEY:
        raise ValueError("STEAM_API_KEY is missing")

    url = f"{STEAM_API_BASE}/ISteamUser/GetPlayerSummaries/v0002/"
    params = {
        "key": STEAM_API_KEY,
        "steamids": steam_id,
        "format": "json",
    }
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()

    players = response.json().get("response", {}).get("players", [])
    return players[0] if players else {}


def get_owned_games(steam_id: str) -> list[dict]:
    """
    Fetch owned games. Works only if the user's game details are visible.
    Returns a list of dicts with appid, name, playtime_forever, playtime_2weeks, etc.
    """
    if not STEAM_API_KEY:
        raise ValueError("STEAM_API_KEY is missing")

    url = f"{STEAM_API_BASE}/IPlayerService/GetOwnedGames/v0001/"
    params = {
        "key": STEAM_API_KEY,
        "steamid": steam_id,
        "include_appinfo": 1,
        "include_played_free_games": 1,
        "format": "json",
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    data = response.json().get("response", {})
    return data.get("games", [])


def get_recently_played_games(steam_id: str) -> list[dict]:
    """Fetch recently played games."""
    if not STEAM_API_KEY:
        raise ValueError("STEAM_API_KEY is missing")

    url = f"{STEAM_API_BASE}/IPlayerService/GetRecentlyPlayedGames/v0001/"
    params = {
        "key": STEAM_API_KEY,
        "steamid": steam_id,
        "format": "json",
    }
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()

    data = response.json().get("response", {})
    return data.get("games", [])


def build_frontend_redirect_url(steam_id: str) -> str:
    """Redirect the browser back to Streamlit with the SteamID in the query string."""
    return f"{FRONTEND_BASE_URL}?steam_id={steam_id}"
