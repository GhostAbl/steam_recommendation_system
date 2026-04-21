from __future__ import annotations

import requests
import streamlit as st

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


st.set_page_config(page_title="Steam Personalized Recommender", layout="wide")
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
    st.write("Or paste a SteamID manually:")
    manual_id = st.text_input("SteamID64", value=st.session_state.steam_id)
    if st.button("Use this SteamID"):
        st.session_state.steam_id = manual_id.strip()
        set_query_param("steam_id", st.session_state.steam_id)

steam_id = st.session_state.steam_id.strip()

if not steam_id:
    st.info("Sign in with Steam or paste a SteamID64 to continue.")
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