import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler
from scipy.sparse import hstack, csr_matrix
from sklearn.neighbors import NearestNeighbors
import joblib
import pyodbc

conn = pyodbc.connect(
    "DRIVER={SQL Server};"
    "SERVER=DESKTOP-DF2O428\\SQLEXPRESS;"
    "DATABASE=test_steam;"
    "Trusted_Connection=yes;"
)

query = """
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
    gm.initial_price,
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

df = pd.read_sql(query, conn)

df["description"] = df["description"].fillna("")
df["tags_text"] = df["tags_text"].fillna("")
df["dev_text"] = df["dev_text"].fillna("")
df["pub_text"] = df["pub_text"].fillna("")

df["positive_review_rate"] = np.where((df["positive_reviews"].fillna(0) + df["negative_reviews"].fillna(0)) > 0,df["positive_reviews"].fillna(0) / (df["positive_reviews"].fillna(0) + df["negative_reviews"].fillna(0)),0)

df["estimated_owners"] = (df["owners_min"].fillna(0) + df["owners_max"].fillna(0)) / 2

df["text_features"] = (
    df["name"].fillna("") + " " +
    df["description"].fillna("") + " " +
    df["tags_text"].fillna("") + " " +
    df["dev_text"].fillna("") + " " +
    df["pub_text"].fillna("") + " " +
    df["is_free"].astype(str) + " " +
    df["supp_windows"].astype(str) + " " +
    df["supp_mac"].astype(str) + " " +
    df["supp_linux"].astype(str)
)

tfidf = TfidfVectorizer(
    stop_words="english",
    max_features=5000
)

text_matrix = tfidf.fit_transform(df["text_features"])

numeric_cols = [
    "price",
    "initial_price",
    "discount",
    "avg_playtime",
    "median_playtime",
    "player_count",
    "positive_review_rate",
    "estimated_owners"
]

X_num = df[numeric_cols].fillna(0)

scaler = StandardScaler()
num_matrix = scaler.fit_transform(X_num)


combined_matrix = hstack([
    text_matrix,
    csr_matrix(num_matrix)
])


def recommend_games(game_name, df, model, feature_matrix, n=5):
    matches = df[df["name"].str.lower() == game_name.lower()]
    if matches.empty:
        return None

    idx = matches.index[0]
    distances, indices = model.kneighbors(feature_matrix[idx], n_neighbors=n+1)

    recs = []
    for dist, i in zip(distances[0][1:], indices[0][1:]):
        recs.append({
            "id_game": int(df.iloc[i]["id_game"]),
            "name": df.iloc[i]["name"],
            "similarity_score": 1 - float(dist),
            "price": float(df.iloc[i]["price"]) if pd.notnull(df.iloc[i]["price"]) else 0,
            "positive_review_rate": float(df.iloc[i]["positive_review_rate"]),
            "avg_playtime": float(df.iloc[i]["avg_playtime"]) if pd.notnull(df.iloc[i]["avg_playtime"]) else 0
        })

    return pd.DataFrame(recs)

nn = NearestNeighbors(metric="cosine", algorithm="brute")
nn.fit(combined_matrix) # type: ignore

joblib.dump(nn, "models/steam_recommender_model.joblib")
joblib.dump(tfidf, "models/tfidf_vectorizer.joblib")
joblib.dump(scaler, "models/numeric_scaler.joblib")
df.to_pickle("models/games_dataframe.pkl")