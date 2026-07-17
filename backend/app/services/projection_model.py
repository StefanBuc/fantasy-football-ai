import pandas as pd
from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import joblib
from pathlib import Path
import json


POSITION_BASE_COLS = {
    "QB": [
        "fantasy_points_ppr",
        "passing_yards",
        "passing_tds",
        "rushing_yards",
        "rushing_tds",
        "carries",
        "passing_yards_allowed",
        "passing_tds_allowed",
        "fantasy_points_ppr_allowed",
        "rushing_yards_allowed",
        "rushing_tds_allowed",
        "targets_allowed",
        "receptions_allowed",
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
        "rushing_yards_allowed",
        "rushing_tds_allowed",
        "receiving_yards_allowed",
        "receiving_tds_allowed",
        "fantasy_points_ppr_allowed",
        "offense_pct",
    ],
    "WR": [
        "fantasy_points_ppr",
        "targets",
        "receptions",
        "receiving_yards",
        "receiving_tds",
        "target_share",
        "wopr",
        "receiving_yards_allowed",
        "receiving_tds_allowed",
        "fantasy_points_ppr_allowed",
        "targets_allowed",
        "receptions_allowed",
        "offense_pct",
    ],
    "TE": [
        "fantasy_points_ppr",
        "targets",
        "receptions",
        "receiving_yards",
        "receiving_tds",
        "target_share",
        "wopr",
        "receiving_yards_allowed",
        "receiving_tds_allowed",
        "fantasy_points_ppr_allowed",
        "targets_allowed",
        "receptions_allowed",
        "offense_pct",
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
    "offense_pct",
    "offense_pct_trend",
]

WINDOWS = ["last1", "last3", "last5", "season_avg"]

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class ProjectionModel:
    def __init__(self, position: str | None = None):
        self.position = position
        self.model = XGBRegressor(
            n_estimators=300,
            learning_rate=0.03,
            max_depth=4,
            subsample=0.8,
            colsample_bytree=0.8,
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
        
        if position in ["RB", "WR", "TE"]:
            self.feature_cols.append("offense_pct_trend")

        relative_cols = [
            f"{col}_relative"
            for col in self.feature_cols
            if "_allowed" in col and not "last1" in col
        ]

        self.feature_cols.extend(relative_cols)
            
    
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
        
    def save_model(self, file_name: str, metadata: dict | None = None):
        model_dir = BASE_DIR / "models" / "xgb_models"
        model_dir.mkdir(exist_ok=True)

        model_path = model_dir / file_name
        metadata_path = model_dir / f"{file_name.replace('.joblib', '_metadata.json')}"
        joblib.dump(self.model, model_path)
        
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=4)

    def load_model(self, file_name: str):
        file_path = BASE_DIR / "models" / "xgb_models" / file_name

        if not file_path.exists():
            return False

        self.model = joblib.load(file_path)
        return True