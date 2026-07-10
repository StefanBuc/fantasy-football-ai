import nfl_data_py as nfl

class NFLData:
    def __init__(self, season: list = [2020, 2021, 2022, 2023, 2024]):
        self.season = season
        self.weekly = None

    def load_data(self):
        print("Loading NFL data...")
        
        self.weekly = nfl.import_weekly_data(self.season)
        
        print("Data loaded!")
        
        
    def get_player_pool(self):
        if self.weekly is None:
            raise ValueError("Weekly data has not been loaded. Call load_data() first.")

        df = self.weekly.copy()
        
        cols = [
            "player_id",
            "player_name",
            "position",
            "recent_team",
            "season",
            "season_type",
            "week",
            "opponent_team",
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
        
    def get_defense_stats(self):
        if self.weekly is None:
            raise ValueError("Weekly data has not been loaded. Call load_data() first.")
        
        df = self.weekly[
            (self.weekly["season_type"] == "REG") &
            (self.weekly["position"].isin(["QB", "RB", "WR", "TE"]))
        ]
        
        defense = (
            df
            .groupby(
                [
                    "opponent_team",
                    "season",
                    "week",
                    "position"
                ]
            )
            [
                [
                    "passing_yards",
                    "rushing_yards",
                    "receiving_yards",
                    "passing_tds",
                    "rushing_tds",
                    "receiving_tds",
                    "fantasy_points_ppr"
                ]
            ]
            .sum()
            .reset_index()
        )
        
        return defense