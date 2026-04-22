from __future__ import annotations

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
    background-color: #66c0f4;
    color: #1b2838;
    border: none;
    border-radius: 8px;
    font-weight: bold;
}

.stButton > button:hover {
    background-color: #8fd3ff;
    color: #171a21;
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

</style>
""", unsafe_allow_html=True)



BACKEND_BASE_URL = "http://127.0.0.1:8000"


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
    st.error(response.text)
    return None


def load_recommendations(steam_id: str, n: int) -> dict | None:
    response = requests.get(
        f"{BACKEND_BASE_URL}/api/recommendations",
        params={"steam_id": steam_id, "n": n},
        timeout=60,
    )
    if response.ok:
        return response.json()
    st.error(response.text)
    return None


def resolve_steam_input(steam_input: str) -> str | None:
    response = requests.get(
        f"{BACKEND_BASE_URL}/api/resolve-steam-id",
        params={"steam_input": steam_input},
        timeout=20,
    )
    if response.ok:
        return response.json().get("steam_id")
    st.error(response.text)
    return None


st.title("Steam Personalized Recommender")

steam_id_from_url = get_query_param("steam_id", "")

if "steam_id" not in st.session_state:
    st.session_state.steam_id = ""

# If user came back from Steam login, store it in session_state
if steam_id_from_url:
    st.session_state.steam_id = steam_id_from_url

with st.sidebar:
    st.header("Login")
    st.markdown(
        f'<a href="{BACKEND_BASE_URL}/login/steam" target="_self">'
        f'<button style="padding:0.5rem 1rem; cursor:pointer;">Sign in with Steam</button>'
        f"</a>",
        unsafe_allow_html=True,
    )

    st.divider()
    st.write("Or paste a Steam profile link:")
    manual_input = st.text_input(
        "Steam profile URL or SteamID64",
        value=st.session_state.steam_id,
        placeholder="https://steamcommunity.com/id/yourname",
    )
    if st.button("Use this profile"):
        resolved = resolve_steam_input(manual_input.strip())
        if resolved:
            st.session_state.steam_id = resolved
            set_query_param("steam_id", resolved)

steam_id = st.session_state.steam_id.strip()

if not steam_id:
    st.info("Sign in with Steam or paste a Steam profile link to continue.")
    st.stop()

st.success(f"Using SteamID: {steam_id}")

col1, col2 = st.columns([1, 1])

with col1:
    if st.button("Load Steam Library", use_container_width=True):
        library = load_library(steam_id)
        if library:
            st.session_state.library = library

with col2:
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
        st.write("**Persona Name:**", profile.get("personaname", "Unknown"))
        st.write("**Owned Games Count:**", library.get("owned_games_count", 0))
        st.write("**Recently Played Count:**", library.get("recent_games_count", 0))

    with st.expander("Show recently played games"):
        recent = library.get("recent_games", [])
        if recent:
            st.dataframe(recent, use_container_width=True)
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
        st.dataframe(recommendations, use_container_width=True)
    else:
        st.info("No recommendations available.")
