import pandas as pd

class OffenseFeatures:
    
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        
    def clean(self):
        
        df = self.df.copy()
        
        df = df[df["position"].isin(["QB", "RB", "WR", "TE"])]
        
        df = df.fillna(0)
        
        return df
    
    def create_features(self):
        df = self.clean()
        
        df ["total_yards"] = df["rushing_yards"] + df["receiving_yards"] + df["passing_yards"]
        
        df["total_tds"] = df["rushing_tds"] + df["receiving_tds"] + df["passing_tds"]
        
        df["yards_per_touch"] = df["total_yards"] / (df["carries"] + df["receptions"])
        
        df["opportunity_score"] = df["targets"] + df["carries"]
        
        df ["efficiency_score"] = df["total_yards"] / (df["opportunity_score"] + 1)
        
        return df
    
    def position_score(self, df):
        df["score"] = 0
        
        #QB Scoring
        qb = df["position"] == "QB"
        df.loc[qb, "score"] = (
            df["passing_yards"] * 0.04 +
            df["passing_tds"] * 4 +
            df["rushing_yards"] * 0.1 +
            df["fantasy_points_ppr"] * 0.5
        )
        
        #RB Scoring
        rb = df["position"] == "RB"
        df.loc[rb, "score"] = (
            df["rushing_yards"] * 0.1 +
            df["rushing_tds"] * 6 +
            df["receptions"] * 1.0 +
            df["receiving_yards"] * 0.1 +
            df["receiving_tds"] * 6 +
            df["fantasy_points_ppr"] * 0.5
        )
        
        #WR/TE Scoring
        wr_te = df["position"].isin(["WR", "TE"])
        df.loc[wr_te, "score"] = (
            df["receiving_yards"] * 0.1 +
            df["receptions"] * 1.0 +
            df["receiving_tds"] * 6 +
            df["fantasy_points_ppr"] * 0.5
        )

        return df

    def build(self):
        df = self.create_features()
        df = self.position_score(df)
        
        df = df.sort_values(by="score", ascending=False)
        
        return df