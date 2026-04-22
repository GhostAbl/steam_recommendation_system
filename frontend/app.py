from __future__ import annotations

import json
import requests
import streamlit as st

st.set_page_config(page_title="Steam Personalized Recommender", layout="wide")

st.markdown("""
<style>
/* Main app background */
.stApp {
    background-color: #1b2838;
    color: #c7d5e0;
}

/* Main text */
html, body, [class*="css"] {
    color: #c7d5e0;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #171a21;
}

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, #66c0f4, #39a9ea);
    color: #102031;
    border: 1px solid #8fd3ff;
    border-radius: 8px;
    font-weight: bold;
    box-shadow: 0 2px 12px rgba(60, 160, 220, 0.35);
    transition: transform 0.12s ease, box-shadow 0.12s ease, filter 0.12s ease;
}

.stButton > button:hover {
    filter: brightness(1.05);
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(60, 160, 220, 0.45);
    color: #102031;
}

.stButton > button:active {
    transform: translateY(0);
}

/* Text input */
.stTextInput input {
    background-color: #2a475e;
    color: #ffffff;
    border: 1px solid #66c0f4;
    border-radius: 8px;
}

/* Number input */
.stNumberInput input {
    background-color: #2a475e;
    color: #ffffff;
    border: 1px solid #66c0f4;
    border-radius: 8px;
}

/* Expanders */
.streamlit-expanderHeader {
    background-color: #2a475e;
    color: #c7d5e0;
    border-radius: 6px;
}

/* Dataframe / table container */
div[data-testid="stDataFrame"] {
    background-color: #2a475e;
    border-radius: 8px;
    padding: 6px;
}

/* Success/info/warning boxes */
div[data-baseweb="notification"] {
    border-radius: 8px;
}

/* Headings */
h1, h2, h3 {
    color: #ffffff;
}

/* Links */
a {
    color: #66c0f4 !important;
}

/* Steam login button (custom link styled as button) */
.steam-login-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    padding: 0.55rem 0.9rem;
    border-radius: 8px;
    border: 1px solid #8fd3ff;
    background: linear-gradient(135deg, #66c0f4, #39a9ea);
    color: #102031 !important;
    font-weight: 700;
    text-decoration: none !important;
    box-shadow: 0 2px 12px rgba(60, 160, 220, 0.35);
    transition: transform 0.12s ease, box-shadow 0.12s ease, filter 0.12s ease;
}

.steam-login-btn:hover {
    filter: brightness(1.05);
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(60, 160, 220, 0.45);
}

.steam-login-btn:active {
    transform: translateY(0);
}

</style>
""", unsafe_allow_html=True)



BACKEND_BASE_URL = "http://127.0.0.1:8000"
HIDDEN_RECENT_GAME_COLUMNS = {
    "appid",
    "img_icon_url",
    "playtime_windows_forever",
    "playtime_mac_forever",
    "playtime_linux_forever",
    "playtime_deck_forever",
}
PLAYTIME_COLUMNS = {"playtime_2weeks", "playtime_forever"}
RECOMMENDATION_COLUMN_LABELS = {
    "avg_playtime": "avg_playtime (min)",
    "price": "price (USD)",
}


def get_query_param(name: str, default: str = "") -> str:
    value = st.query_params.get(name, default)

    if isinstance(value, list):
        return value[0] if value else default

    return value


def set_query_param(name: str, value: str) -> None:
    st.query_params[name] = value


def load_library(steam_id: str) -> dict | None:
    response = requests.get(
        f"{BACKEND_BASE_URL}/api/user/library",
        params={"steam_id": steam_id},
        timeout=60,
    )
    if response.ok:
        return response.json()
    st.error(get_error_message(response))
    return None


def load_recommendations(steam_id: str, n: int) -> dict | None:
    response = requests.get(
        f"{BACKEND_BASE_URL}/api/recommendations",
        params={"steam_id": steam_id, "n": n},
        timeout=60,
    )
    if response.ok:
        return response.json()
    st.error(get_error_message(response))
    return None


def resolve_steam_input(steam_input: str) -> str | None:
    response = requests.get(
        f"{BACKEND_BASE_URL}/api/resolve-steam-id",
        params={"steam_input": steam_input},
        timeout=20,
    )
    if response.ok:
        return response.json().get("steam_id")
    st.error(get_error_message(response))
    return None


def format_playtime_value(value):
    try:
        minutes = int(float(value))
        return f"{minutes:,} mins"
    except (TypeError, ValueError):
        return value


def format_price_value(value):
    try:
        price = float(value)
        return f"${price:,.2f}"
    except (TypeError, ValueError):
        return value


def format_column_label(raw_name: str) -> str:
    parts = raw_name.replace("_", " ").split()
    fixed_parts = []
    for p in parts:
        lp = p.lower()
        if lp in {"usd", "id"}:
            fixed_parts.append(lp.upper())
        else:
            fixed_parts.append(p[:1].upper() + p[1:])
    return " ".join(fixed_parts)


def build_steam_header_image_url(app_id) -> str | None:
    try:
        app_id_int = int(app_id)
    except (TypeError, ValueError):
        return None
    return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id_int}/header.jpg"


def to_user_friendly_error(message: str) -> str:
    msg = (message or "").strip()
    low = msg.lower()

    if "steam profile not found" in low:
        return "We couldn't find that Steam profile. Cause: wrong ID/link or the profile does not exist."
    if "could not resolve vanity profile url" in low:
        return "That custom Steam profile link is invalid. Cause: the vanity name was not found."
    if "invalid steam input" in low:
        return "Invalid input format. Use a Steam profile link or a 17-digit SteamID64."
    if "steam_api_key is missing" in low:
        return "Service is temporarily unavailable. Cause: Steam API key is not configured on the server."
    if "timed out" in low or "timeout" in low:
        return "Steam took too long to respond. Cause: network timeout, please try again."
    if "connection" in low and "refused" in low:
        return "Cannot reach the backend service. Cause: server is not running."

    return msg if msg else "Something went wrong. Please try again."


def get_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return response.text or f"Request failed with status {response.status_code}"

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return to_user_friendly_error(detail)

    fallback = response.text or f"Request failed with status {response.status_code}"
    return to_user_friendly_error(fallback)


st.title("Steam Personalized Recommender")

steam_id_from_url = get_query_param("steam_id", "")

if "steam_id" not in st.session_state:
    st.session_state.steam_id = ""
if "steam_input" not in st.session_state:
    st.session_state.steam_input = ""
if "last_steam_id_from_url" not in st.session_state:
    st.session_state.last_steam_id_from_url = ""

# Sync from URL only when URL value changes (e.g., fresh login callback),
# so we don't overwrite what the user is currently typing.
if steam_id_from_url and steam_id_from_url != st.session_state.last_steam_id_from_url:
    st.session_state.steam_id = steam_id_from_url
    st.session_state.steam_input = steam_id_from_url
    st.session_state.last_steam_id_from_url = steam_id_from_url

with st.sidebar:
    st.header("Login")
    st.markdown(
        f'<a class="steam-login-btn" href="{BACKEND_BASE_URL}/login/steam" target="_self">'
        f"Sign in with Steam"
        f"</a>",
        unsafe_allow_html=True,
    )

    st.divider()
    st.write("Or paste a Steam profile link:")
    st.text_input(
        "Steam profile URL or SteamID64",
        key="steam_input",
        placeholder="Profile URL / SteamID64",
    )
    if st.button("Use this profile"):
        candidate = st.session_state.steam_input.strip()
        if not candidate:
            st.error("Please enter a Steam profile link or SteamID64.")
        else:
            try:
                resolved = resolve_steam_input(candidate)
                if resolved:
                    st.session_state.steam_id = resolved
                    set_query_param("steam_id", resolved)
                    st.session_state.last_steam_id_from_url = resolved
                    library = load_library(resolved)
                    if library:
                        st.session_state.library = library
                        st.session_state.pop("recs", None)
            except requests.RequestException:
                st.error("Cannot connect right now. Cause: network/backend request failed.")
            except Exception:
                st.error("Could not load this profile. Cause: unexpected app error.")

steam_id = st.session_state.steam_id.strip()

if not steam_id:
    st.info("Sign in with Steam or paste a Steam profile link to continue.")
    st.stop()

st.success(f"Using SteamID: {steam_id}")

num_recs = st.number_input("Number of recommendations", min_value=1, max_value=20, value=10, step=1)
if st.button("Get Personalized Recommendations", use_container_width=True):
    recs = load_recommendations(steam_id, int(num_recs))
    if recs:
        st.session_state.recs = recs

if "library" in st.session_state:
    library = st.session_state.library
    profile = library.get("profile", {})

    st.subheader("Steam Profile")
    left, right = st.columns([1, 3])

    with left:
        avatar = profile.get("avatarfull")
        if avatar:
            st.image(avatar, width=120)

    with right:
        st.write("**Profile Name:**", profile.get("personaname", "Unknown"))
        st.write("**Owned Games Count:**", library.get("owned_games_count", 0))
        st.write("**Recently Played Count:**", library.get("recent_games_count", 0))

    with st.expander("Show recently played games"):
        recent = library.get("recent_games", [])
        if recent:
            st.caption("Playtime values are shown in minutes.")
            filtered_recent = [
                {k: v for k, v in game.items() if k not in HIDDEN_RECENT_GAME_COLUMNS}
                for game in recent
            ]
            display_recent = [
                {
                    "cover": build_steam_header_image_url(game.get("appid")),
                    **{
                        format_column_label(f"{k} (min)" if k in PLAYTIME_COLUMNS else k): (
                            format_playtime_value(v) if k in PLAYTIME_COLUMNS else v
                        )
                        for k, v in game.items()
                    },
                }
                for game in filtered_recent
            ]
            st.dataframe(
                display_recent,
                use_container_width=True,
                column_config={
                    "cover": st.column_config.ImageColumn(
                        "Cover",
                        help="Steam game cover image",
                        width="medium",
                    )
                },
            )
        else:
            st.write("No recently played games returned.")

if "recs" in st.session_state:
    recs = st.session_state.recs

    st.subheader("Recommendations")

    if recs.get("used_fallback"):
        st.warning("Could not build a personalized profile from your library. Showing fallback recommendations instead.")

    st.write("**Matched games from your library in our dataset:**", recs.get("matched_games_count", 0))
    st.write("**Owned games returned by Steam:**", recs.get("owned_games_count", 0))

    recommendations = recs.get("recommendations", [])
    if recommendations:
        display_recommendations = [
            {
                "cover": build_steam_header_image_url(item.get("id_game")),
                **{
                    format_column_label(RECOMMENDATION_COLUMN_LABELS.get(k, k)): ( # type: ignore
                        format_price_value(v)
                        if k == "price"
                        else format_playtime_value(v)
                        if k == "avg_playtime"
                        else v
                    )
                    for k, v in item.items()
                    if k != "id_game"
                },
            }
            for item in recommendations
        ]
        st.dataframe(
            display_recommendations,
                use_container_width=True,
                column_config={
                    "cover": st.column_config.ImageColumn(
                        "Cover",
                        help="Steam game cover image",
                        width="medium",
                    )
                },
            )
    else:
        st.info("No recommendations available.")
