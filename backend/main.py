from __future__ import annotations
import json

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse

from backend.config import FRONTEND_BASE_URL
from backend.steam_auth import (
    build_steam_login_url,
    verify_openid_response,
    extract_steam_id,
    get_owned_games,
    get_recently_played_games,
    get_player_summary,
    build_frontend_redirect_url,
)
from backend.recommender import SteamRecommender


app = FastAPI(title="Steam Personalized Recommender API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_BASE_URL,
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

recommender = None


@app.on_event("startup")
def startup_event() -> None:
    global recommender
    try:
        recommender = SteamRecommender()
    except Exception as e:
        print("Recommender not loaded on startup:", str(e))
        recommender = None


@app.get("/")
def root():
    return {"message": "backend working"}


@app.get("/login/steam")
def login_steam():
    return RedirectResponse(build_steam_login_url())


@app.get("/auth/steam/callback")
def auth_steam_callback(request: Request):
    query_params = dict(request.query_params)

    try:
        is_valid = verify_openid_response(query_params)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Steam verification failed: {str(e)}")

    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid Steam OpenID response")

    claimed_id = query_params.get("openid.claimed_id", "")
    steam_id = extract_steam_id(claimed_id)

    if not steam_id:
        raise HTTPException(status_code=400, detail="Could not extract SteamID")

    return RedirectResponse(build_frontend_redirect_url(steam_id))


@app.get("/api/user/library")
def user_library(steam_id: str = Query(...)):
    try:
        profile = get_player_summary(steam_id)
        owned_games = get_owned_games(steam_id)
        recent_games = get_recently_played_games(steam_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return JSONResponse(
        {
            "steam_id": steam_id,
            "profile": profile,
            "owned_games_count": len(owned_games),
            "recent_games_count": len(recent_games),
            "owned_games": owned_games,
            "recent_games": recent_games,
        }
    )


@app.get("/api/recommendations")
def recommendations(steam_id: str = Query(...), n: int = Query(10, ge=1, le=50)):
    global recommender

    if recommender is None:
        raise HTTPException(
            status_code=500,
            detail="Recommender artifacts not loaded. Run backend/train_model.py first.",
        )

    try:
        owned_games = get_owned_games(steam_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Private profile wala empty library -> fallback
    result = recommender.recommend_for_user(owned_games=owned_games, n=n)
    result["steam_id"] = steam_id
    result["owned_games_count"] = len(owned_games)

    return JSONResponse(result)