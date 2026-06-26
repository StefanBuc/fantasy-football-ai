import pandas as pd
from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

class ProjectionModel:
    def __init__(self):
        self.model = XGBRegressor(
            n_estimators=100,
            learning_rate=0.05,
            max_depth=4,
            random_state=42
        )
        
        self.feature_cols = [
            "fantasy_points_ppr_last3",
            "targets_last3",
            "receptions_last3",
            "carries_last3",
            "passing_yards_last3",
            "passing_tds_last3",
            "rushing_yards_last3",
            "rushing_tds_last3",
            "receiving_yards_last3",
            "receiving_tds_last3",
            "target_share_last3",
            "wopr_last3",
        ]
    
    def train(self, df: pd.DataFrame):
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