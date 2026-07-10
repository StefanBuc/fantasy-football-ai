import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class PlayerFeatures:
    def __init__(self, player_df:pd.DataFrame):
        self.player_df = player_df.copy()

    def build_offence_features(self):
        seasons = "_".join(map(str,self.player_df["season"].unique()))

        cache_file = BASE_DIR / "cache" / f"player_features_{seasons}.parquet"

        if cache_file.exists():
            print("Loading cached player features dataset...")
            return pd.read_parquet(cache_file)
        
        df = self.player_df.copy()
        df = df[df["position"].isin(["QB", "RB", "WR", "TE"])]
        df = df[df["season_type"] == "REG"]
        df = df.fillna(0)
        df = df.sort_values(["player_id", "season", "week"]).reset_index(drop=True)
        
        feature_cols = [
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
        
        for col in feature_cols:
            df[f"{col}_last1"] = (
                df.groupby(["player_id", "season"])[col]
                .transform(lambda x: x.shift(1))
            )
            
            df[f"{col}_last3"] = (
                df.groupby(["player_id", "season"])[col]
                .transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
            )
            
            df[f"{col}_last5"] = (
                df.groupby(["player_id", "season"])[col]
                .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
            )
            
            df[f"{col}_season_avg"] = (
                df.groupby(["player_id", "season"])[col]
                .transform(lambda x: x.shift(1).expanding().mean())
            )
            
        df["next_week_points"] = (
            df.groupby(["player_id", "season"])["fantasy_points_ppr"]
            .shift(-1)
        )

        model_df = df.dropna()
        
        cache_dir = BASE_DIR / "cache"
        cache_dir.mkdir(exist_ok=True)
        model_df.to_parquet(cache_file, index=False)

        return model_df