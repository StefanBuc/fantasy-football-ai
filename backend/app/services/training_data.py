import pandas as pd

class TrainingData:
    def __init__(self, df:pd.DataFrame):
        self.df = df.copy()
        
    def build_next_week_dataset(self):
        df = self.df.copy()
        
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
            df[f"{col}_last3"] = (
                df.groupby(["player_id", "season"])[col]
                .transform(lambda x: x.shift(1).rolling(3).mean())
            )
            
        df["next_week_points"] = (
            df.groupby(["player_id", "season"])["fantasy_points_ppr"]
            .shift(-1)
        )

        return df.dropna()