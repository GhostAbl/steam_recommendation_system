import streamlit as st
import pandas as pd
import joblib
from scipy.sparse import hstack, csr_matrix

# Load saved objects
nn = joblib.load("models/steam_recommender_model.joblib")
tfidf = joblib.load("models/tfidf_vectorizer.joblib")
scaler = joblib.load("models/numeric_scaler.joblib")
df = pd.read_pickle("models/games_dataframe.pkl")

# Rebuild features if needed
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

text_matrix = tfidf.transform(df["text_features"])
num_matrix = scaler.transform(df[numeric_cols].fillna(0))
combined_matrix = hstack([text_matrix, csr_matrix(num_matrix)])

def recommend_games(game_name, n=5):
    matches = df[df["name"].str.lower() == game_name.lower()]
    if matches.empty:
        return None

    idx = matches.index[0]
    distances, indices = nn.kneighbors(combined_matrix[idx], n_neighbors=n+1)

    recs = []
    for dist, i in zip(distances[0][1:], indices[0][1:]):
        recs.append({
            "Game": df.iloc[i]["name"],
            "Similarity": round(1 - float(dist), 4),
            "Price": df.iloc[i]["price"],
            "Avg Playtime": df.iloc[i]["avg_playtime"],
            "Positive Review Rate": round(df.iloc[i]["positive_review_rate"] * 100, 2)
        })
    return pd.DataFrame(recs)

st.title("Steam Game Recommender")

game_name = st.selectbox("Choose a game", sorted(df["name"].dropna().unique()))

if st.button("Recommend"):
    result = recommend_games(game_name, n=5)
    st.dataframe(result)