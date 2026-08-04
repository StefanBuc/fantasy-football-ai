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
}