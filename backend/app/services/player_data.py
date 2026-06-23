import nfl_data_py as nfl
import pandas as pd

class PlayerData:
    def __init__(self, season: int = 2024):
        self.season = season
        self.weekly = None

    def load_data(self):
        print("Loading NFL data...")
        
        self.weekly = nfl.import_weekly_data([self.season])
        
        print("Data loaded:")
        print(self.weekly.head())
        
        
    def get_player_pool(self):
        if self.weekly is None:
            raise ValueError("Weekly data has not been loaded. Call load_data() first.")

        df = self.weekly.copy()
        
        cols = [
            "player_id",
            "player_name",
            "position",
            "recent_team",
            "week",
            "fantasy_points",
            "fantasy_points_ppr",
            "targets",
            "carries",
            "receptions",
            "passing_yards",
            "passing_tds",
            "rushing_yards",
            "rushing_tds",
            "receiving_yards",
            "receiving_tds",
            "target_share",
            "wopr",
        ]
        
        df = df[cols]
        
        return df
        
        