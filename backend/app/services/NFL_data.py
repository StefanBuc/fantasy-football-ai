import nfl_data_py as nfl

class NFLData:
    def __init__(self, season: list = [2020, 2021, 2022, 2023, 2024]):
        self.season = season
        self.weekly = None
        self.snap_counts = None
        self.ids = None

    def load_data(self):
        print("Loading NFL data...")
        
        self.weekly = nfl.import_weekly_data(self.season)
        self.snap_counts = nfl.import_snap_counts(self.season)
        self.ids = nfl.import_ids()
        
        print("Data loaded!")
        
        
    def get_player_stats(self):
        if self.weekly is None:
            raise ValueError("Weekly data has not been loaded. Call load_data() first.")
        if self.snap_counts is None:
            raise ValueError("Snap counts data has not been loaded. Call load_data() first.")
        if self.ids is None:
            raise ValueError("IDs data has not been loaded. Call load_data() first.")

        player_stats_df = self.weekly.copy()
        player_snap_df = self.snap_counts.copy()
        
        ids = self.ids[
            [
                "gsis_id",
                "pfr_id"
            ]
        ]

        player_snap_df = player_snap_df.merge(
            ids,
            left_on="pfr_player_id",
            right_on="pfr_id",
            how="left"
        )
        
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
        
        player_stats_df = player_stats_df[cols]
        player_snap_df = player_snap_df.rename(columns={"player": "player_name", "team": "recent_team"})
        player_snap_df = player_snap_df[["gsis_id", "season", "week", "offense_snaps", "offense_pct"]]
        
        player_stats_df = player_stats_df.merge(
            player_snap_df,
            left_on=[
                "player_id",
                "season",
                "week"
            ],
            right_on=[
                "gsis_id",
                "season",
                "week"
            ],
            how="left"
        )        
        return player_stats_df[[col for col in cols] + ["offense_snaps", "offense_pct"]]
        
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
                    "fantasy_points_ppr",
                    "targets",
                    "receptions",
                ]
            ]
            .sum()
            .reset_index()
        )
        
        defense = defense.rename(
            columns={
                "passing_yards": "passing_yards_allowed",
                "rushing_yards": "rushing_yards_allowed",
                "receiving_yards": "receiving_yards_allowed",
                "passing_tds": "passing_tds_allowed",
                "rushing_tds": "rushing_tds_allowed",
                "receiving_tds": "receiving_tds_allowed",
                "fantasy_points_ppr": "fantasy_points_ppr_allowed",
                "targets": "targets_allowed",
                "receptions": "receptions_allowed",
            }
        )
        
        return defense