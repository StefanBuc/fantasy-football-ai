import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class DefenseFeatures:
    def __init__(self, defense_df:pd.DataFrame):
        self.defense_df = defense_df.copy()
    
    def build_defence_features(self):
        seasons = "_".join(map(str,self.defense_df["season"].unique()))
        
        cache_file = BASE_DIR / "cache" / f"defense_features_{seasons}.parquet"
        
        if cache_file.exists():
            print("Loading cached defense features dataset...")
            return pd.read_parquet(cache_file)
        
        df = self.defense_df.copy()
        df = df.fillna(0)
        df = df.sort_values(["opponent_team", "position", "season", "week"]).reset_index(drop=True)
        
        feature_cols = [
            "passing_yards_allowed",
            "rushing_yards_allowed",
            "receiving_yards_allowed",
            "passing_tds_allowed",
            "rushing_tds_allowed",
            "receiving_tds_allowed",
            "fantasy_points_ppr_allowed",
            "targets_allowed",
            "receptions_allowed",
        ]
        
        for col in feature_cols:
            df[f"{col}_last1"] = (
                df.groupby(["opponent_team", "season", "position"])[col]
                .transform(lambda x: x.shift(1))
            )
            
            df[f"{col}_last3"] = (
                df.groupby(["opponent_team", "season", "position"])[col]
                .transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
            )
            
            df[f"{col}_last5"] = (
                df.groupby(["opponent_team", "season", "position"])[col]
                .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
            )
            
            df[f"{col}_season_avg"] = (
                df.groupby(["opponent_team", "season", "position"])[col]
                .transform(lambda x: x.shift(1).expanding().mean())
            )
            
        relative_cols = [
            "last3",
            "last5",
            "season_avg"
        ]

        for col in feature_cols:
            for window in relative_cols:

                feature = f"{col}_{window}"

                league_average = (
                    df.groupby(["season", "position"])[feature]
                    .transform("mean")
                )

                df[f"{feature}_relative"] = (
                    df[feature] / league_average
                )
        
        model_df = df.dropna()
        
        cache_dir = BASE_DIR / "cache"
        cache_dir.mkdir(exist_ok=True)
        model_df.to_parquet(cache_file, index=False)
        
        return model_df
        
        