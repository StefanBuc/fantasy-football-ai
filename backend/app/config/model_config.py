FEATURE_COLS = [
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
    "offense_pct",
    "passing_yards_allowed",
    "rushing_yards_allowed",
    "receiving_yards_allowed",
    "passing_tds_allowed",
    "rushing_tds_allowed",
    "receiving_tds_allowed",
    "fantasy_points_ppr_allowed",
    "targets_allowed",
    "receptions_allowed",
    "week"
]

QB_FEATURE_COLS = [
    "fantasy_points_ppr",
    "passing_yards",
    "passing_tds",
    "carries",
    "rushing_yards",
    "rushing_tds",
    "offense_pct",
    "passing_yards_allowed",
    "passing_tds_allowed",
    "fantasy_points_ppr_allowed",
    "week",
]

RB_FEATURE_COLS = [
    "fantasy_points_ppr",
    "carries",
    "targets",
    "receptions",
    "rushing_yards",
    "rushing_tds",
    "receiving_yards",
    "receiving_tds",
    "target_share",
    "offense_pct",
    "rushing_yards_allowed",
    "rushing_tds_allowed",
    "targets_allowed",
    "week",
]

WR_TE_FEATURE_COLS = [
    "fantasy_points_ppr",
    "targets",
    "receptions",
    "receiving_yards",
    "receiving_tds",
    "target_share",
    "wopr",
    "offense_pct",
    "receiving_yards_allowed",
    "receiving_tds_allowed",
    "targets_allowed",
    "receptions_allowed",
    "week",
]

K_FEATURE_COLS = [
    "fantasy_points",
    "field_goals_attempted",
    "field_goals_made",
    "field_goals_missed",
    "field_goals_0_39",
    "field_goals_40_49",
    "field_goals_50_59",
    "field_goals_60_plus",
    "extra_points_attempted",
    "extra_points_made",
    "week",
]

DST_FEATURE_COLS = [
    "fantasy_points",
    "sacks",
    "interceptions",
    "fumble_recoveries",
    "blocked_kicks",
    "safeties",
    "return_touchdowns",
    "points_allowed",
    "yards_allowed",
    "week",
]

SPECIAL_TEAMS_MATCHUP_SOURCES = {
    "K": {
        "kicker_points_allowed": "fantasy_points",
        "field_goal_attempts_allowed": "field_goals_attempted",
        "extra_point_attempts_allowed": "extra_points_attempted",
    },
    "DST": {
        "dst_points_allowed": "fantasy_points",
        "sacks_allowed": "sacks",
        "interceptions_allowed": "interceptions",
        "fumble_recoveries_allowed": "fumble_recoveries",
        "offensive_points": "points_allowed",
        "offensive_yards": "yards_allowed",
    },
}

DEFENSE_STAT_COLS = [
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

POSITION_CONFIGS = {
    "QB": {"hidden_size": 32, "num_layers": 1, "dropout": 0.0},
    "RB": {"hidden_size": 64, "num_layers": 2, "dropout": 0.2},
    "WR": {"hidden_size": 64, "num_layers": 2, "dropout": 0.2},
    "TE": {"hidden_size": 32, "num_layers": 1, "dropout": 0.0},
    "K": {"hidden_size": 32, "num_layers": 1, "dropout": 0.0},
    "DST": {"hidden_size": 32, "num_layers": 1, "dropout": 0.0},
}

SELECTED_PYTORCH_MODEL_VERSIONS = {
    "QB": 4,
    "RB": 4,
    "WR": 4,
    "TE": 4,
    "K": 1,
    "DST": 1,
}
