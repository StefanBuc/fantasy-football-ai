import nfl_data_py as nfl
import pandas as pd

class NFLData:
    def __init__(self, season: list = [2020, 2021, 2022, 2023, 2024]):
        self.season = season
        self.weekly = None
        self.snap_counts = None
        self.ids = None
        self.schedule = None
        self.weekly_rosters = None
        self.depth_charts = None

    def load_data(self):
        print("Loading NFL data...")
        
        self.weekly = nfl.import_weekly_data(self.season)
        self.snap_counts = nfl.import_snap_counts(self.season)
        self.ids = nfl.import_ids()
        
        print("Data loaded!")
    
    def load_schedule(self):
        print("Loading NFL schedule...")

        self.schedule = nfl.import_schedules(
            self.season
        )

        print("NFL schedule loaded!")
    
    def load_weekly_rosters(self):
        print("Loading weekly NFL rosters...")

        self.weekly_rosters = (
            nfl.import_weekly_rosters(self.season)
        )

        print("Weekly NFL rosters loaded!")
    
    def load_depth_charts(self):
        print("Loading NFL depth charts...")

        self.depth_charts = nfl.import_depth_charts(
            self.season
        )

        print("NFL depth charts loaded!")
    
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
    
    def get_week_schedule(
        self,
        season: int,
        week: int,
    ):
        if self.schedule is None:
            raise ValueError(
                "Schedule has not been loaded. "
                "Call load_schedule() first."
            )

        required_columns = {
            "season",
            "week",
            "home_team",
            "away_team",
        }

        missing_columns = (
            required_columns
            - set(self.schedule.columns)
        )

        if missing_columns:
            raise ValueError(
                f"Schedule is missing columns: "
                f"{sorted(missing_columns)}"
            )

        games = self.schedule[
            (self.schedule["season"] == season)
            & (self.schedule["week"] == week)
        ].copy()

        if "game_type" in games.columns:
            games = games[
                games["game_type"] == "REG"
            ].copy()

        return games
    
    def get_week_roster(
        self,
        season: int,
        week: int,
    ):
        if self.weekly_rosters is None:
            raise ValueError(
                "Weekly rosters have not been loaded. "
                "Call load_weekly_rosters() first."
            )

        required_columns = {
            "player_id",
            "player_name",
            "position",
            "team",
            "season",
            "week",
            "status",
        }

        missing_columns = (
            required_columns
            - set(self.weekly_rosters.columns)
        )

        if missing_columns:
            raise ValueError(
                f"Roster is missing columns: "
                f"{sorted(missing_columns)}"
            )

        roster = self.weekly_rosters[
            (self.weekly_rosters["season"] == season)
            & (self.weekly_rosters["week"] == week)
            & (
                self.weekly_rosters["position"].isin(
                    ["QB", "RB", "WR", "TE"]
                )
            )
            & (self.weekly_rosters["status"] == "ACT")
            & self.weekly_rosters["player_id"].notna()
        ].copy()

        if "game_type" in roster.columns:
            roster = roster[
                roster["game_type"] == "REG"
            ].copy()

        duplicate_players = roster[
            roster["player_id"].duplicated(
                keep=False
            )
        ]

        if not duplicate_players.empty:
            raise ValueError(
                "A player appears more than once in "
                f"the {season} week {week} active roster."
            )

        return roster[
            [
                "player_id",
                "player_name",
                "position",
                "team",
                "season",
                "week",
                "status",
            ]
        ].reset_index(drop=True)
    
    def get_week_opponents(
        self,
        season: int,
        week: int,
    ) -> dict[str, str]:
        games = self.get_week_schedule(
            season=season,
            week=week,
        )

        opponents: dict[str, str] = {}

        for game in games.itertuples(index=False):
            home_team = str(game.home_team).upper()
            away_team = str(game.away_team).upper()

            if (
                home_team in opponents
                or away_team in opponents
            ):
                raise ValueError(
                    f"A team appears more than once in "
                    f"{season} week {week}."
                )

            opponents[home_team] = away_team
            opponents[away_team] = home_team

        return opponents

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

    def get_week_depth_chart(
        self,
        season: int,
        week: int,
    ):
        if self.depth_charts is None:
            raise ValueError(
                "Depth charts have not been loaded. "
                "Call load_depth_charts() first."
            )

        required_columns = {
            "season",
            "week",
            "game_type",
            "club_code",
            "formation",
            "gsis_id",
            "position",
            "depth_position",
            "depth_team",
        }

        missing_columns = (
            required_columns
            - set(self.depth_charts.columns)
        )

        if missing_columns:
            raise ValueError(
                f"Depth chart is missing columns: "
                f"{sorted(missing_columns)}"
            )

        depth_chart = self.depth_charts[
            (self.depth_charts["season"] == season)
            & (self.depth_charts["week"] == week)
            & (
                self.depth_charts["game_type"]
                == "REG"
            )
            & (
                self.depth_charts["formation"]
                == "Offense"
            )
            & (
                self.depth_charts["position"].isin(
                    ["QB", "RB", "WR", "TE"]
                )
            )
            & self.depth_charts["gsis_id"].notna()
        ].copy()

        depth_chart["depth_team"] = pd.to_numeric(
            depth_chart["depth_team"],
            errors="coerce",
        )

        depth_chart = depth_chart.dropna(
            subset=["depth_team"]
        )

        depth_chart = depth_chart.rename(
            columns={
                "gsis_id": "player_id",
                "club_code": "team",
            }
        )

        # If a player appears at multiple offensive spots,
        # retain their highest depth-chart placement.
        depth_chart = (
            depth_chart
            .sort_values("depth_team")
            .drop_duplicates(
                subset=["player_id"],
                keep="first",
            )
        )

        return depth_chart[
            [
                "player_id",
                "team",
                "position",
                "depth_position",
                "depth_team",
            ]
        ].reset_index(drop=True)