from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import numpy as np
import pyodbc
import joblib

from scipy.sparse import hstack, csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler

try:
    from backend.config import SQL_CONNECTION_STRING, MODELS_DIR
except ModuleNotFoundError as e:
    if e.name != "backend":
        raise
    # Support direct execution: python backend/train_model.py
    root_dir = Path(__file__).resolve().parents[1]
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    from backend.config import SQL_CONNECTION_STRING, MODELS_DIR


TAG_VECTOR_WEIGHT = 0.55
OTHER_TEXT_VECTOR_WEIGHT = 0.30
NUMERIC_VECTOR_WEIGHT = 0.15

TAG_MAX_FEATURES = 3000
OTHER_TEXT_MAX_FEATURES = 5000


SQL_QUERY = """
WITH TagAgg AS (
    SELECT
        btg.id_game,
        STRING_AGG(t.tag_name, ' ') AS tags_text
    FROM bridge_tag_game btg
    JOIN tag t 
        ON t.id_tag = btg.id_tag
    GROUP BY btg.id_game
),
DevAgg AS (
    SELECT
        bdg.id_game,
        STRING_AGG(d.developer_name, ' ') AS dev_text
    FROM bridge_developer_game bdg
    JOIN developer d 
        ON d.id_developer = bdg.id_developer
    GROUP BY bdg.id_game
),
PubAgg AS (
    SELECT
        bpg.id_game,
        STRING_AGG(p.publisher_name, ' ') AS pub_text
    FROM bridge_publisher_game bpg
    JOIN publisher p 
        ON p.id_publisher = bpg.id_publisher
    GROUP BY bpg.id_game
)
SELECT
    g.id_game,
    g.name,
    g.description,
    g.is_free,
    g.supp_windows,
    g.supp_mac,
    g.supp_linux,
    COALESCE(ta.tags_text, '') AS tags_text,
    COALESCE(da.dev_text, '') AS dev_text,
    COALESCE(pa.pub_text, '') AS pub_text,
    gm.avg_playtime,
    gm.median_playtime,
    gm.player_count,
    gm.positive_reviews,
    gm.negative_reviews,
    gm.owners_min,
    gm.owners_max,
    gm.price,
    gm.discount
FROM game g
LEFT JOIN game_metrics gm 
    ON gm.id_game = g.id_game
LEFT JOIN TagAgg ta 
    ON ta.id_game = g.id_game
LEFT JOIN DevAgg da 
    ON da.id_game = g.id_game
LEFT JOIN PubAgg pa 
    ON pa.id_game = g.id_game;
"""


def main() -> None:
    if not SQL_CONNECTION_STRING:
        raise ValueError("SQL_CONNECTION_STRING is missing in .env")

    conn = pyodbc.connect(SQL_CONNECTION_STRING)
    df = pd.read_sql(SQL_QUERY, conn)
    conn.close()

    # Fill text columns
    for col in ["name", "description", "tags_text", "dev_text", "pub_text"]:
        df[col] = df[col].fillna("").astype(str)

    # Fill numeric columns
    numeric_cols = [
        "price",
        "discount",
        "avg_playtime",
        "median_playtime",
        "player_count",
        "positive_reviews",
        "negative_reviews",
        "owners_min",
        "owners_max",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Derived fields
    df["positive_review_rate"] = np.where(
        (df["positive_reviews"] + df["negative_reviews"]) > 0,
        df["positive_reviews"] / (df["positive_reviews"] + df["negative_reviews"]),
        0,
    )

    df["estimated_owners"] = (df["owners_min"] + df["owners_max"]) / 2.0

    # Normalize booleans to text-friendly / numeric-friendly values
    for col in ["is_free", "supp_windows", "supp_mac", "supp_linux"]:
        df[col] = df[col].fillna(False).astype(bool)

    # Split text channels so tags can be explicitly upweighted.
    df["tag_features"] = df["tags_text"]
    df["other_text_features"] = (
        df["name"] + " " +
        df["description"] + " " +
        df["dev_text"] + " " +
        df["pub_text"] + " " +
        df["is_free"].astype(str) + " " +
        df["supp_windows"].astype(str) + " " +
        df["supp_mac"].astype(str) + " " +
        df["supp_linux"].astype(str)
    )

    tag_tfidf = TfidfVectorizer(
        stop_words="english",
        max_features=TAG_MAX_FEATURES,
    )
    tags_matrix = tag_tfidf.fit_transform(df["tag_features"]) * TAG_VECTOR_WEIGHT

    other_text_tfidf = TfidfVectorizer(
        stop_words="english",
        max_features=OTHER_TEXT_MAX_FEATURES,
    )
    other_text_matrix = other_text_tfidf.fit_transform(df["other_text_features"]) * OTHER_TEXT_VECTOR_WEIGHT

    # Numeric features for hybrid model
    hybrid_numeric_cols = [
        "price",
        "discount",
        "player_count",
        "positive_review_rate",
        "estimated_owners",
    ]
    X_num = df[hybrid_numeric_cols].fillna(0)

    scaler = StandardScaler()
    num_matrix = scaler.fit_transform(X_num) * NUMERIC_VECTOR_WEIGHT

    combined_matrix = hstack([
        tags_matrix,
        other_text_matrix,
        csr_matrix(num_matrix),
    ]).tocsr()

    # Save artifacts
    df.to_pickle(MODELS_DIR / "games_dataframe.pkl")
    joblib.dump(combined_matrix, MODELS_DIR / "combined_matrix.joblib")
    joblib.dump(other_text_tfidf, MODELS_DIR / "tfidf_vectorizer.joblib")
    joblib.dump(tag_tfidf, MODELS_DIR / "tags_tfidf_vectorizer.joblib")
    joblib.dump(scaler, MODELS_DIR / "numeric_scaler.joblib")
    joblib.dump(
        {
            "tag_weight": TAG_VECTOR_WEIGHT,
            "other_text_weight": OTHER_TEXT_VECTOR_WEIGHT,
            "numeric_weight": NUMERIC_VECTOR_WEIGHT,
            "tag_max_features": TAG_MAX_FEATURES,
            "other_text_max_features": OTHER_TEXT_MAX_FEATURES,
            "numeric_cols": hybrid_numeric_cols,
        },
        MODELS_DIR / "model_config.joblib",
    )

    print("Training artifacts saved to:", MODELS_DIR)
    print("Rows:", len(df))


if __name__ == "__main__":
    main()
