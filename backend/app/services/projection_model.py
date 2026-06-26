import pandas as pd
from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import joblib
from pathlib import Path


POSITION_BASE_COLS = {
    "QB": [
        "fantasy_points_ppr",
        "passing_yards",
        "passing_tds",
        "rushing_yards",
        "rushing_tds",
        "carries",
    ],
    "RB": [
        "fantasy_points_ppr",
        "carries",
        "rushing_yards",
        "rushing_tds",
        "targets",
        "receptions",
        "receiving_yards",
        "receiving_tds",
    ],
    "WR": [
        "fantasy_points_ppr",
        "targets",
        "receptions",
        "receiving_yards",
        "receiving_tds",
        "target_share",
        "wopr",
    ],
    "TE": [
        "fantasy_points_ppr",
        "targets",
        "receptions",
        "receiving_yards",
        "receiving_tds",
        "target_share",
        "wopr",
    ],
}

BASE_COLS = [
    "fantasy_points_ppr",
    "targets",
    "receptions",
    "carries",
    "passing_yards",
    "passing_tds",
    "rushing_yards",
    "rushing_tds",
    "receiving_yards",
    "receiving_tds",
    "target_share",
    "wopr",
]

WINDOWS = ["last1", "last3", "last5", "season_avg"]

class ProjectionModel:
    def __init__(self, position: str | None = None):
        self.position = position
        self.model = XGBRegressor(
            n_estimators=100,
            learning_rate=0.05,
            max_depth=4,
            random_state=42
        )
        
        if position is None:
            selected_base_cols = BASE_COLS
        else:
            selected_base_cols = POSITION_BASE_COLS.get(position, BASE_COLS)

        self.feature_cols = [
            f"{col}_{window}"
            for col in selected_base_cols
            for window in WINDOWS
        ]
            
    
    def train(self, df: pd.DataFrame, test_season: int | None = None):
        if test_season is not None:
            train_df = df[df["season"] < test_season]
            test_df = df[df["season"] == test_season]

            X_train = train_df[self.feature_cols]
            y_train = train_df["next_week_points"]

            X_test = test_df[self.feature_cols]
            y_test = test_df["next_week_points"]
        else:
            X = df[self.feature_cols]
            y = df["next_week_points"]

            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )

        self.model.fit(X_train, y_train)

        preds = self.model.predict(X_test)
        mae = mean_absolute_error(y_test, preds)

        return mae

    def predict(self, df: pd.DataFrame):
        X = df[self.feature_cols]
        df = df.copy()
        df["predicted_points"] = self.model.predict(X)
        return df
    
    def evaluate_by_position(self, df: pd.DataFrame):
        X = df[self.feature_cols]
        y = df["next_week_points"]

        df = df.copy()
        df["predicted_points"] = self.model.predict(X)
        df["absolute_error"] = (df["next_week_points"] - df["predicted_points"]).abs()

        results = (
            df.groupby("position")["absolute_error"]
            .mean()
            .sort_values()
        )

        return results
    
    def feature_importance(self):
        return pd.DataFrame({
            "feature": self.feature_cols,
            "importance": self.model.feature_importances_
        }).sort_values("importance", ascending=False)
        
    def save_model(self, file_name: str):
        model_dir = Path("models")
        model_dir.mkdir(exist_ok=True)

        file_path = model_dir / file_name
        joblib.dump(self.model, file_path)

    def load_model(self, file_name: str):
        file_path = Path("models") / file_name

        if not file_path.exists():
            return False

        self.model = joblib.load(file_path)
        return True