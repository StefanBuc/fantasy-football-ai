import pandas as pd


class FantasyEngine:
    
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
    
    def clean_data(self):
        df = self.df.copy()

        df = df[df["position"].isin(["QB", "RB", "WR", "TE"])]

        numeric_cols = [
            "fantasy_points_ppr",
            "targets",
            "receptions",
            "carries",
            "rushing_yards",
            "rushing_tds",
            "receiving_yards",
            "receiving_tds",
            "passing_yards",
            "passing_tds",
            "wopr",
            "target_share",
        ]

        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].fillna(0)

        return df
    
    def aggregate_player_stats(self):
        df = self.clean_data()
        
        agg_df = self.df.groupby(['player_id', 'player_name', 'position', 'recent_team']).agg({
            "fantasy_points_ppr": "mean",
            "targets": "mean",
            "receptions": "mean",
            "rushing_yards": "mean",
            "rushing_tds": "mean",
            "receiving_yards": "mean",
            "receiving_tds": "mean",
            "passing_yards": "mean",
            "passing_tds": "mean",
            "wopr": "mean",
            "target_share": "mean"
        }).reset_index()
        
        return agg_df
    
    def compute_fantasy_score(self, df:pd.DataFrame):
        
        df["projected_points"] = (
            df["fantasy_points_ppr"] * 0.6 +
            df["targets"] * 1.5 +
            df["receptions"] * 1.0 +
            df["receiving_yards"] * 0.02 +
            df["rushing_yards"] * 0.02 +
            df["receiving_tds"] * 6 +
            df["rushing_tds"] * 6 +
            df["passing_tds"] * 4 +
            df["wopr"] * 5 +
            df["target_share"] * 10
        )

        return df
    
    def rank_players(self):
        
        df = self.aggregate_player_stats()
        df = self.compute_fantasy_score(df)
        
        df = df.sort_values(by="projected_points", ascending=False)
        
        return df