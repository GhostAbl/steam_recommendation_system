from __future__ import annotations

import math
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, vstack
from sklearn.metrics.pairwise import cosine_similarity

from backend.config import MODELS_DIR


DF_PATH = MODELS_DIR / "games_dataframe.pkl"
MATRIX_PATH = MODELS_DIR / "combined_matrix.joblib"


class SteamRecommender:
    def __init__(self) -> None:
        if not DF_PATH.exists():
            raise FileNotFoundError(f"Missing dataframe file: {DF_PATH}")
        if not MATRIX_PATH.exists():
            raise FileNotFoundError(f"Missing matrix file: {MATRIX_PATH}")

        self.df: pd.DataFrame = pd.read_pickle(DF_PATH)
        self.matrix: csr_matrix = joblib.load(MATRIX_PATH)

        # Ensure required columns exist
        required_cols = {"id_game", "name"}
        missing = required_cols - set(self.df.columns)
        if missing:
            raise ValueError(f"Missing required columns in dataframe: {missing}")

        self.df["id_game"] = self.df["id_game"].astype(int)

    def get_popular_fallback(self, n: int = 10) -> list[dict]:
        """
        Fallback recommendations when user library is unavailable/private.
        """
        df = self.df.copy()

        if "positive_review_rate" not in df.columns:
            pos = df.get("positive_reviews", pd.Series(0, index=df.index)).fillna(0)
            neg = df.get("negative_reviews", pd.Series(0, index=df.index)).fillna(0)
            total = pos + neg
            df["positive_review_rate"] = np.where(total > 0, pos / total, 0)

        for col in ["player_count", "estimated_owners"]:
            if col not in df.columns:
                df[col] = 0
            df[col] = df[col].fillna(0)

        max_players = max(float(df["player_count"].max()), 1.0)
        max_owners = max(float(df["estimated_owners"].max()), 1.0)

        df["fallback_score"] = (
            0.50 * df["positive_review_rate"] +
            0.30 * (df["player_count"] / max_players) +
            0.20 * (df["estimated_owners"] / max_owners)
        )

        top = df.sort_values("fallback_score", ascending=False).head(n)

        return [
            {
                "id_game": int(row["id_game"]),
                "name": row["name"],
                "score": round(float(row["fallback_score"]), 4),
                "reason": "Popular fallback recommendation",
            }
            for _, row in top.iterrows()
        ]

    @staticmethod
    def _weight_for_game(playtime_forever_minutes: int, playtime_2weeks_minutes: int) -> float:
        """
        Simple weighting:
        - base ownership gives 1.0
        - more playtime gives higher weight
        - recent play gives a bonus
        """
        forever_hours = max(playtime_forever_minutes, 0) / 60.0
        recent_hours = max(playtime_2weeks_minutes, 0) / 60.0

        return 1.0 + math.log1p(forever_hours) + 0.5 * math.log1p(recent_hours)

    def _build_user_profile_vector(self, owned_games: Iterable[dict]) -> tuple[csr_matrix | None, set[int], int]:
        """
        Build a weighted average vector from the user's owned games that match our dataset.
        Returns (profile_vector, matched_ids, match_count)
        """
        id_to_index = {int(game_id): idx for idx, game_id in enumerate(self.df["id_game"].tolist())}

        matched_indices: list[int] = []
        weights: list[float] = []
        matched_ids: set[int] = set()

        for game in owned_games:
            appid = int(game.get("appid", 0))
            if appid not in id_to_index:
                continue

            idx = id_to_index[appid]
            matched_indices.append(idx)
            matched_ids.add(appid)

            playtime_forever = int(game.get("playtime_forever", 0))
            playtime_2weeks = int(game.get("playtime_2weeks", 0))
            weights.append(self._weight_for_game(playtime_forever, playtime_2weeks))

        if not matched_indices:
            return None, set(), 0

        rows = self.matrix[matched_indices]
        weight_array = np.array(weights, dtype=np.float64).reshape(-1, 1)

        # Weighted sum then normalize by total weight
        weighted_rows = rows.multiply(weight_array)
        profile_vector = weighted_rows.sum(axis=0)
        profile_vector = csr_matrix(profile_vector / weight_array.sum())

        return profile_vector, matched_ids, len(matched_indices)

    def recommend_for_user(self, owned_games: list[dict], n: int = 10) -> dict:
        """
        Return personalized recommendations for a Steam user library.
        """
        profile_vector, owned_ids, matched_count = self._build_user_profile_vector(owned_games)

        if profile_vector is None:
            return {
                "matched_games_count": 0,
                "used_fallback": True,
                "recommendations": self.get_popular_fallback(n=n),
            }

        sims = cosine_similarity(profile_vector, self.matrix).flatten()

        candidate_df = self.df.copy()
        candidate_df["similarity"] = sims

        if "positive_review_rate" not in candidate_df.columns:
            pos = candidate_df.get("positive_reviews", pd.Series(0, index=candidate_df.index)).fillna(0)
            neg = candidate_df.get("negative_reviews", pd.Series(0, index=candidate_df.index)).fillna(0)
            total = pos + neg
            candidate_df["positive_review_rate"] = np.where(total > 0, pos / total, 0)

        for col in ["player_count", "estimated_owners"]:
            if col not in candidate_df.columns:
                candidate_df[col] = 0
            candidate_df[col] = candidate_df[col].fillna(0)

        max_players = max(float(candidate_df["player_count"].max()), 1.0)
        max_owners = max(float(candidate_df["estimated_owners"].max()), 1.0)

        candidate_df["final_score"] = (
            0.70 * candidate_df["similarity"] +
            0.20 * candidate_df["positive_review_rate"] +
            0.07 * (candidate_df["player_count"] / max_players) +
            0.03 * (candidate_df["estimated_owners"] / max_owners)
        )

        # Exclude already owned games
        candidate_df = candidate_df[~candidate_df["id_game"].isin(owned_ids)]

        top = candidate_df.sort_values("final_score", ascending=False).head(n)

        recommendations = []
        for _, row in top.iterrows():
            recommendations.append(
                {
                    "id_game": int(row["id_game"]),
                    "name": row["name"],
                    "score": round(float(row["final_score"]), 4),
                    "similarity": round(float(row["similarity"]), 4),
                    "price": float(row["price"]) if pd.notnull(row.get("price")) else 0.0,
                    "avg_playtime": float(row["avg_playtime"]) if pd.notnull(row.get("avg_playtime")) else 0.0,
                    "positive_review_rate": round(float(row["positive_review_rate"]) * 100, 2),
                    "reason": "Similar to games in your Steam library",
                }
            )

        return {
            "matched_games_count": matched_count,
            "used_fallback": False,
            "recommendations": recommendations,
        }
