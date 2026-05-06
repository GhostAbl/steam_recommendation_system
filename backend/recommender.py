from __future__ import annotations

import math
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
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

        required_cols = {"id_game", "name"}
        missing = required_cols - set(self.df.columns)
        if missing:
            raise ValueError(f"Missing required columns in dataframe: {missing}")

        self.df["id_game"] = self.df["id_game"].astype(int)
        self.id_to_index = {int(game_id): idx for idx, game_id in enumerate(self.df["id_game"].tolist())}

    @staticmethod
    def _weight_for_game(playtime_forever_minutes: int, playtime_2weeks_minutes: int) -> float:
        forever_hours = max(playtime_forever_minutes, 0) / 60.0
        recent_hours = max(playtime_2weeks_minutes, 0) / 60.0
        return 1.0 + math.log1p(forever_hours) + 0.5 * math.log1p(recent_hours)

    @staticmethod
    def _join_names(names: list[str], limit: int = 2) -> str:
        clean = [name.strip() for name in names if isinstance(name, str) and name.strip()]
        return ", ".join(clean[:limit])

    @staticmethod
    def _extract_tags(tags_text: object, max_tags: int = 6) -> list[str]:
        raw = str(tags_text or "").strip()
        if not raw:
            return []
        tags: list[str] = []
        seen: set[str] = set()
        for token in raw.split():
            t = token.strip()
            if not t:
                continue
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            tags.append(t)
            if len(tags) >= max_tags:
                break
        return tags

    def _build_fallback_reason(self, row: pd.Series, max_players: float, max_owners: float) -> str:
        review_rate = float(row.get("positive_review_rate", 0.0))
        review_pct = review_rate * 100.0
        player_norm = float(row.get("player_count", 0.0)) / max_players if max_players > 0 else 0.0
        owner_norm = float(row.get("estimated_owners", 0.0)) / max_owners if max_owners > 0 else 0.0

        weighted_components = {
            "review": 0.50 * review_rate,
            "players": 0.30 * player_norm,
            "owners": 0.20 * owner_norm,
        }
        primary = max(weighted_components, key=weighted_components.get)

        if primary == "review":
            return f"Very well reviewed ({review_pct:.0f}% positive)."
        if primary == "players":
            return f"Popular right now ({review_pct:.0f}% positive)."
        return f"Owned by many players ({review_pct:.0f}% positive)."

    def _build_personalized_reason(
        self,
        row: pd.Series,
        nearest_owned_names: list[str],
        max_players: float,
    ) -> str:
        parts = [f"Matches games you play (similarity {float(row.get('similarity', 0.0)):.2f})."]

        anchors = self._join_names(nearest_owned_names, limit=2)
        if anchors:
            parts.append(f"Similar to: {anchors}.")

        review_pct = float(row.get("positive_review_rate", 0.0)) * 100.0
        if review_pct >= 85:
            parts.append(f"Great reviews ({review_pct:.0f}% positive).")
        elif review_pct >= 75:
            parts.append(f"Good reviews ({review_pct:.0f}% positive).")

        player_norm = float(row.get("player_count", 0.0)) / max_players if max_players > 0 else 0.0
        if player_norm >= 0.7:
            parts.append("Lots of active players.")

        return " ".join(parts[:3])

    def _build_user_profile_vector(self, owned_games: Iterable[dict]) -> tuple[csr_matrix | None, set[int], list[int]]:
        """
        Build a weighted average vector from the user's owned games that match our dataset.
        Returns (profile_vector, matched_ids, matched_indices)
        """
        matched_indices: list[int] = []
        weights: list[float] = []
        matched_ids: set[int] = set()

        for game in owned_games:
            appid = int(game.get("appid", 0))
            if appid not in self.id_to_index:
                continue

            idx = self.id_to_index[appid]
            matched_indices.append(idx)
            matched_ids.add(appid)

            playtime_forever = int(game.get("playtime_forever", 0))
            playtime_2weeks = int(game.get("playtime_2weeks", 0))
            weights.append(self._weight_for_game(playtime_forever, playtime_2weeks))

        if not matched_indices:
            return None, set(), []

        rows = self.matrix[matched_indices]
        weight_array = np.array(weights, dtype=np.float64).reshape(-1, 1)
        weighted_rows = rows.multiply(weight_array)
        profile_vector = weighted_rows.sum(axis=0)
        profile_vector = csr_matrix(profile_vector / weight_array.sum())

        return profile_vector, matched_ids, matched_indices

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
                "description": str(row.get("description", "") or "").strip(),
                "tags": self._extract_tags(row.get("tags_text", "")),
                "score": round(float(row["fallback_score"]), 4),
                "discount": float(row["discount"]) if pd.notnull(row.get("discount")) else 0.0,
                "reason": self._build_fallback_reason(row, max_players=max_players, max_owners=max_owners),
            }
            for _, row in top.iterrows()
        ]

    def recommend_for_user(self, owned_games: list[dict], n: int = 10) -> dict:
        """
        Return personalized recommendations for a Steam user library.
        """
        profile_vector, owned_ids, matched_indices = self._build_user_profile_vector(owned_games)
        matched_count = len(matched_indices)

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

        candidate_df = candidate_df[~candidate_df["id_game"].isin(owned_ids)]
        top = candidate_df.sort_values("final_score", ascending=False).head(n)

        top_indices = top.index.tolist()
        nearest_owned_names_by_row: dict[int, list[str]] = {idx: [] for idx in top_indices}

        if matched_indices and top_indices:
            top_matrix = self.matrix[top_indices]
            matched_matrix = self.matrix[matched_indices]
            top_to_owned_sims = cosine_similarity(top_matrix, matched_matrix)

            for row_pos, row_idx in enumerate(top_indices):
                sim_row = top_to_owned_sims[row_pos]
                if sim_row.size == 0:
                    continue

                best_owned_positions = np.argsort(sim_row)[::-1][:2]
                names: list[str] = []
                for owned_pos in best_owned_positions:
                    if sim_row[owned_pos] <= 0:
                        continue
                    owned_idx = matched_indices[int(owned_pos)]
                    owned_name = str(self.df.iloc[owned_idx].get("name", "")).strip()
                    if owned_name and owned_name not in names:
                        names.append(owned_name)
                nearest_owned_names_by_row[row_idx] = names

        recommendations = []
        for row_idx, row in top.iterrows():
            recommendations.append(
                {
                    "id_game": int(row["id_game"]),
                    "name": row["name"],
                    "description": str(row.get("description", "") or "").strip(),
                    "tags": self._extract_tags(row.get("tags_text", "")),
                    "score": round(float(row["final_score"]), 4),
                    "similarity": round(float(row["similarity"]), 4),
                    "price": float(row["price"]) if pd.notnull(row.get("price")) else 0.0,
                    "discount": float(row["discount"]) if pd.notnull(row.get("discount")) else 0.0,
                    "positive_review_rate": round(float(row["positive_review_rate"]) * 100, 2),
                    "reason": self._build_personalized_reason(
                        row,
                        nearest_owned_names=nearest_owned_names_by_row.get(row_idx, []),
                        max_players=max_players,
                    ),
                }
            )

        return {
            "matched_games_count": matched_count,
            "used_fallback": False,
            "recommendations": recommendations,
        }
