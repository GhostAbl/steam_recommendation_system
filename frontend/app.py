from __future__ import annotations

import json
from html import escape
from pathlib import Path
from urllib.parse import quote_plus
import requests
import streamlit as st

st.set_page_config(page_title="Steam Personalized Recommender", layout="wide")

FRONTEND_DIR = Path(__file__).resolve().parent
CSS_PATH = FRONTEND_DIR / "styles.css"


def inject_stylesheet() -> None:
    if not CSS_PATH.exists():
        return
    css = CSS_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


inject_stylesheet()


BACKEND_BASE_URL = "http://127.0.0.1:8000"
RECS_N_QUERY_PARAM = "recs_n"
DEFAULT_RECS_COUNT = 10
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
    "price": "price (USD)",
}
COVER_PLACEHOLDER_BASE = "https://placehold.co/460x215/0d2338/8fd8ff?text="


def render_hero() -> None:
    st.markdown(
        """
        <section class="hero-shell">
          <p class="hero-kicker">PERSONALIZED DISCOVERY</p>
          <h1>Steam Recommender</h1>
          <p class="hero-sub">
            Connect your Steam profile and get high-confidence game picks based on what you actually play.
          </p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_stat_strip(items: list[tuple[str, str]]) -> None:
    blocks = []
    for label, value in items:
        safe_label = escape(str(label))
        safe_value = escape(str(value))
        blocks.append(
            f'<div class="stat-tile"><p>{safe_label}</p><h4>{safe_value}</h4></div>'
        )
    joined = "".join(blocks)
    st.markdown(f'<div class="stat-strip">{joined}</div>', unsafe_allow_html=True)


def get_query_param(name: str, default: str = "") -> str:
    value = st.query_params.get(name, default)

    if isinstance(value, list):
        return value[0] if value else default

    return value


def set_query_param(name: str, value: str) -> None:
    st.query_params[name] = value


def clear_query_param(name: str) -> None:
    try:
        if name in st.query_params:
            del st.query_params[name]
    except Exception:
        # Fallback for older Streamlit query param behavior.
        st.query_params[name] = ""


def clear_steam_session() -> None:
    st.session_state.steam_id = ""
    st.session_state.steam_input = ""
    st.session_state.steam_authenticated = False
    st.session_state.last_steam_id_from_url = ""
    st.session_state.last_steam_auth_loaded_id = ""
    st.session_state.auto_loaded_library_id = ""
    st.session_state.auto_loaded_recs_key = ""
    st.session_state.pop("library", None)
    st.session_state.pop("recs", None)
    clear_query_param("steam_id")
    clear_query_param("auth")
    clear_query_param(RECS_N_QUERY_PARAM)


def parse_int_in_range(raw_value: str, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default

    if parsed < min_value:
        return min_value
    if parsed > max_value:
        return max_value
    return parsed


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
        if price <= 0:
            return "Free"
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


def clamp_text(value: object, max_chars: int = 220) -> str:
    text = str(value or "").strip()
    if not text:
        return "No description available."
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0].strip()
    return f"{cut}..." if cut else f"{text[:max_chars]}..."


def render_recommendation_cards(recommendations: list[dict]) -> None:
    cards: list[str] = []
    for item in recommendations:
        name = escape(str(item.get("name", "Unknown game")))
        price_text = escape(str(format_price_value(item.get("price", 0))))
        review_text = escape(f"{float(item.get('positive_review_rate', 0.0)):.1f}% positive")
        similarity_text = escape(f"Similarity {float(item.get('similarity', 0.0)):.2f}")
        score_text = escape(f"Score {float(item.get('score', 0.0)):.3f}")

        raw_description = str(item.get("description", "") or "").strip()
        description_text = escape(clamp_text(raw_description, max_chars=170))
        full_description = escape(raw_description) if raw_description else "No description available."
        has_long_description = len(raw_description) > 170
        reason_text = escape(clamp_text(item.get("reason", ""), max_chars=170))
        raw_tags = item.get("tags", [])
        tags_list = raw_tags if isinstance(raw_tags, list) else []
        tag_chips = "".join(
            f'<span class="rec-tag">{escape(str(tag).strip())}</span>'
            for tag in tags_list
            if str(tag).strip()
        )
        tags_block = f'<div class="rec-tags">{tag_chips}</div>' if tag_chips else ""

        cover_url = build_steam_header_image_url(item.get("id_game")) or f"{COVER_PLACEHOLDER_BASE}No+Cover"
        safe_cover_url = escape(cover_url)
        store_url = build_steam_store_url(item.get("id_game"))
        safe_store_url = escape(store_url) if store_url else ""
        more_description_html = (
            f'<details class="rec-more"><summary>View more</summary><p>{full_description}</p></details>'
            if has_long_description
            else ""
        )

        card_html = (
            f'<article class="rec-card">'
            f'<img class="rec-cover" src="{safe_cover_url}" alt="{name} cover" loading="lazy" />'
            f'<div class="rec-body">'
            f"<h4>{name}</h4>"
            f'<div class="rec-meta">'
            f'<span class="rec-pill rec-pill-price">{price_text}</span>'
            f'<span class="rec-pill">{review_text}</span>'
            f'<span class="rec-pill">{similarity_text}</span>'
            f'<span class="rec-pill">{score_text}</span>'
            f"</div>"
            f'<p class="rec-desc">{description_text}</p>'
            f"{more_description_html}"
            f'<p class="rec-reason">{reason_text}</p>'
            f"{tags_block}"
            f"</div>"
            f"</article>"
        )

        if safe_store_url:
            cards.append(
                f'<a class="rec-link" href="{safe_store_url}" target="_blank" rel="noopener noreferrer">{card_html}</a>'
            )
        else:
            cards.append(card_html)

    st.markdown(f'<section class="rec-grid">{"".join(cards)}</section>', unsafe_allow_html=True)


def _cover_placeholder_url(app_id_int: int) -> str:
    text = quote_plus(f"No Cover - App {app_id_int}")
    return f"{COVER_PLACEHOLDER_BASE}{text}"


def build_steam_store_url(app_id) -> str | None:
    try:
        app_id_int = int(app_id)
    except (TypeError, ValueError):
        return None
    return f"https://store.steampowered.com/app/{app_id_int}/"


@st.cache_data(ttl=21600, show_spinner=False)
def _resolve_cover_url(app_id_int: int) -> str:
    candidates = [
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id_int}/header.jpg",
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id_int}/capsule_616x353.jpg",
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id_int}/capsule_467x181.jpg",
    ]

    for url in candidates:
        try:
            response = requests.head(url, timeout=4, allow_redirects=True)
            if response.ok:
                content_type = (response.headers.get("Content-Type") or "").lower()
                if "image" in content_type:
                    return url
        except requests.RequestException:
            continue

    return _cover_placeholder_url(app_id_int)


def build_steam_header_image_url(app_id) -> str | None:
    try:
        app_id_int = int(app_id)
    except (TypeError, ValueError):
        return None
    return _resolve_cover_url(app_id_int)


def to_user_friendly_error(message: str) -> str:
    msg = (message or "").strip()
    low = msg.lower()

    if "steam profile not found" in low:
        return "We couldn't find that Steam profile. Cause: wrong ID/link or the profile does not exist."
    if "could not resolve vanity profile url" in low:
        return "That custom Steam profile link is invalid. Cause: the vanity name was not found."
    if "invalid steam input" in low:
        return "Invalid input format. Use a Steam profile link or a 17-digit SteamID."
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


render_hero()

steam_id_from_url = get_query_param("steam_id", "")
auth_from_url = get_query_param("auth", "")

if "steam_id" not in st.session_state:
    st.session_state.steam_id = ""
if "steam_input" not in st.session_state:
    st.session_state.steam_input = ""
if "steam_authenticated" not in st.session_state:
    st.session_state.steam_authenticated = False
if "last_steam_id_from_url" not in st.session_state:
    st.session_state.last_steam_id_from_url = ""
if "last_steam_auth_loaded_id" not in st.session_state:
    st.session_state.last_steam_auth_loaded_id = ""
if "auto_loaded_library_id" not in st.session_state:
    st.session_state.auto_loaded_library_id = ""
if "auto_loaded_recs_key" not in st.session_state:
    st.session_state.auto_loaded_recs_key = ""

# Sync SteamID from URL only when SteamID actually changes (fresh callback),
# so reruns don't overwrite current local state.
if steam_id_from_url and steam_id_from_url != st.session_state.last_steam_id_from_url:
    previous_steam_id = st.session_state.steam_id.strip()
    profile_switched = bool(previous_steam_id) and previous_steam_id != steam_id_from_url

    st.session_state.steam_id = steam_id_from_url
    st.session_state.steam_input = steam_id_from_url
    st.session_state.last_steam_id_from_url = steam_id_from_url

    # Only clear cached profile/recommendations when user really switches profile
    # inside the same active session. On hard reload we keep query-backed restore.
    if profile_switched:
        st.session_state.last_steam_auth_loaded_id = ""
        st.session_state.auto_loaded_library_id = ""
        st.session_state.auto_loaded_recs_key = ""
        st.session_state.pop("library", None)
        st.session_state.pop("recs", None)
        clear_query_param(RECS_N_QUERY_PARAM)

# Mark Steam-authenticated only when callback explicitly provides auth=steam.
if auth_from_url == "steam" and steam_id_from_url:
    st.session_state.steam_authenticated = True
    if st.session_state.last_steam_auth_loaded_id != steam_id_from_url:
        library = load_library(steam_id_from_url)
        if library:
            st.session_state.library = library
            st.session_state.pop("recs", None)
            st.session_state.auto_loaded_recs_key = ""
            clear_query_param(RECS_N_QUERY_PARAM)
        st.session_state.last_steam_auth_loaded_id = steam_id_from_url
    clear_query_param("auth")

with st.sidebar:
    st.markdown(
        """
        <p class="sidebar-eyebrow">ACCOUNT</p>
        <h2 class="sidebar-title">Login</h2>
        <p class="sidebar-sub">Connect Steam or use any public profile link.</p>
        """,
        unsafe_allow_html=True,
    )

    is_steam_authenticated = bool(st.session_state.steam_authenticated)
    if is_steam_authenticated:
        if st.button("Sign out", use_container_width=True):
            clear_steam_session()
            st.rerun()
    else:
        st.markdown(
            f'<a class="steam-login-btn" href="{BACKEND_BASE_URL}/login/steam" target="_self">'
            f"Sign in with Steam"
            f"</a>",
            unsafe_allow_html=True,
        )

    st.markdown('<p class="sidebar-section-title">Use a Profile URL or SteamID</p>', unsafe_allow_html=True)
    st.text_input(
        "Steam profile URL or SteamID",
        key="steam_input",
        placeholder="Profile URL / SteamID",
    )
    if st.button("Use this profile", use_container_width=True):
        candidate = st.session_state.steam_input.strip()
        if not candidate:
            st.error("Please enter a Steam profile link or SteamID.")
        else:
            try:
                resolved = resolve_steam_input(candidate)
                if resolved:
                    st.session_state.steam_id = resolved
                    st.session_state.steam_authenticated = False
                    st.session_state.last_steam_auth_loaded_id = ""
                    st.session_state.auto_loaded_library_id = ""
                    st.session_state.auto_loaded_recs_key = ""
                    set_query_param("steam_id", resolved)
                    clear_query_param("auth")
                    clear_query_param(RECS_N_QUERY_PARAM)
                    st.session_state.last_steam_id_from_url = resolved
                    library = load_library(resolved)
                    if library:
                        st.session_state.library = library
                        st.session_state.pop("recs", None)
            except requests.RequestException:
                st.error("Cannot connect right now. Cause: network/backend request failed.")
            except Exception:
                st.error("Could not load this profile. Cause: unexpected app error.")
    st.markdown(
        '<p class="sidebar-footnote">Tip: Use your custom profile link or a 17-digit SteamID.</p>',
        unsafe_allow_html=True,
    )

steam_id = st.session_state.steam_id.strip()

if not steam_id:
    st.markdown(
        '<div class="info-banner">Sign in with Steam or paste a Steam profile link to continue.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

st.success(f"Using SteamID: {steam_id}")

# Auto-restore profile details after page reload using the SteamID in URL/session.
if "library" not in st.session_state and st.session_state.auto_loaded_library_id != steam_id:
    library = load_library(steam_id)
    if library:
        st.session_state.library = library
    st.session_state.auto_loaded_library_id = steam_id

saved_recs_n = parse_int_in_range(
    get_query_param(RECS_N_QUERY_PARAM, str(DEFAULT_RECS_COUNT)),
    default=DEFAULT_RECS_COUNT,
    min_value=1,
    max_value=20,
)

# Auto-restore recommendations after page reload when recs_n is present in URL.
recs_restore_key = f"{steam_id}:{saved_recs_n}"
if get_query_param(RECS_N_QUERY_PARAM, "") and "recs" not in st.session_state and st.session_state.auto_loaded_recs_key != recs_restore_key:
    restored_recs = load_recommendations(steam_id, saved_recs_n)
    if restored_recs:
        st.session_state.recs = restored_recs
    st.session_state.auto_loaded_recs_key = recs_restore_key

num_recs = st.number_input("Number of recommendations", min_value=1, max_value=20, value=saved_recs_n, step=1)
left_col, center_col, right_col = st.columns([2, 1, 2])
with center_col:
    get_recs_clicked = st.button("Get Personalized Recommendations", use_container_width=False)

if get_recs_clicked:
    recs = load_recommendations(steam_id, int(num_recs))
    if recs:
        st.session_state.recs = recs
        set_query_param(RECS_N_QUERY_PARAM, str(int(num_recs)))
        st.session_state.auto_loaded_recs_key = f"{steam_id}:{int(num_recs)}"

if "library" in st.session_state:
    library = st.session_state.library
    profile = library.get("profile", {})

    st.markdown("### Steam Profile")
    left, right = st.columns([1, 3])

    with left:
        avatar = profile.get("avatarfull")
        if avatar:
            st.image(avatar, width=120)

    with right:
        st.write("**Profile Name:**", profile.get("personaname", "Unknown"))
        render_stat_strip(
            [
                ("Owned Games", str(library.get("owned_games_count", 0))),
                ("Recently Played", str(library.get("recent_games_count", 0))),
                ("Steam ID", steam_id),
            ]
        )

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

    st.markdown("### Recommendations")

    if recs.get("used_fallback"):
        st.warning("Could not build a personalized profile from your library. Showing fallback recommendations instead.")

    render_stat_strip(
        [
            ("Matched in Dataset", str(recs.get("matched_games_count", 0))),
            ("Owned on Steam", str(recs.get("owned_games_count", 0))),
            ("Recommendation Count", str(len(recs.get("recommendations", [])))),
        ]
    )

    recommendations = recs.get("recommendations", [])
    if recommendations:
        view_mode = st.radio(
            "Recommendation view",
            options=["Card View", "Table View"],
            horizontal=True,
            key="recommendation_view_mode",
        )

        if view_mode == "Card View":
            render_recommendation_cards(recommendations)
        else:
            display_recommendations = [
                {
                    "cover": build_steam_header_image_url(item.get("id_game")),
                    **{
                        format_column_label(RECOMMENDATION_COLUMN_LABELS.get(k, k)): ( # type: ignore
                            format_price_value(v)
                            if k == "price"
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
                        ),
                        "Description": st.column_config.TextColumn(
                            "Description",
                            width="large",
                        ),
                        "Reason": st.column_config.TextColumn(
                            "Reason",
                            width="large",
                        ),
                    },
                )
    else:
        st.info("No recommendations available.")
