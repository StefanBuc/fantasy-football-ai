import pandas as pd


class FantasyEngine:
    
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
    
    def compute_fantasy_score(self):
        df = self.df.copy()
        
        df["ranking"] = (
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
        df = self.compute_fantasy_score()
        df = df.sort_values(by="ranking", ascending=False)
        
        return df