from urllib.error import HTTPError

import numpy as np
import pandas as pd

from app.services import NFL_data as nfl_data_module
from app.services.NFL_data import (
    NFLData,
    WEEKLY_PLAYER_STATS_URL,
)


def test_weekly_data_uses_new_nflverse_release_after_404(
    monkeypatch,
):
    def fail_legacy_download(seasons):
        raise HTTPError(
            url="legacy-url",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    loaded_urls = []

    def load_current_release(url):
        loaded_urls.append(url)
        return pd.DataFrame(
            {
                "season": [2025],
                "team": ["BUF"],
                "fantasy_points": np.array(
                    [20.0],
                    dtype=np.float64,
                ),
            }
        )

    monkeypatch.setattr(
        nfl_data_module.nfl,
        "import_weekly_data",
        fail_legacy_download,
    )
    monkeypatch.setattr(
        nfl_data_module.pd,
        "read_parquet",
        load_current_release,
    )

    result = NFLData([2025])._load_weekly_player_data()

    assert loaded_urls == [
        WEEKLY_PLAYER_STATS_URL.format(season=2025)
    ]
    assert "recent_team" in result.columns
    assert "team" not in result.columns
    assert result.loc[0, "recent_team"] == "BUF"
    assert result["fantasy_points"].dtype == np.float32


def test_projection_roster_uses_latest_available_week():
    data = NFLData([2026])
    data.weekly_rosters = pd.DataFrame(
        [
            {
                "player_id": "player-1",
                "player_name": "Future Player",
                "position": "RB",
                "team": "BUF",
                "season": 2026,
                "week": 2,
                "status": "ACT",
            }
        ]
    )

    roster, roster_week = data.get_projection_roster(
        season=2026,
        week=3,
    )

    assert roster_week == 2
    assert roster["player_id"].tolist() == [
        "player-1"
    ]


def test_empty_depth_chart_returns_standard_columns():
    data = NFLData([2026])
    data.depth_charts = pd.DataFrame()

    depth_chart = data.get_week_depth_chart(
        season=2026,
        week=1,
    )

    assert depth_chart.empty
    assert depth_chart.columns.tolist() == [
        "player_id",
        "team",
        "position",
        "depth_position",
        "depth_team",
    ]


def test_current_depth_chart_schema_maps_qb_ranks():
    data = NFLData([2025])
    data.schedule = pd.DataFrame(
        [
            {
                "season": 2025,
                "week": 1,
                "game_type": "REG",
                "home_team": "BUF",
                "away_team": "BAL",
                "gameday": "2025-09-07",
            }
        ]
    )
    data.depth_charts = pd.DataFrame(
        [
            {
                "dt": "2025-09-05T12:00:00Z",
                "team": "BUF",
                "gsis_id": "qb-1",
                "pos_grp": "3WR 1TE",
                "pos_abb": "QB",
                "pos_slot": 9,
                "pos_rank": 1,
            },
            {
                "dt": "2025-09-05T12:00:00Z",
                "team": "BUF",
                "gsis_id": "qb-2",
                "pos_grp": "3WR 1TE",
                "pos_abb": "QB",
                "pos_slot": 9,
                "pos_rank": 2,
            },
        ]
    )

    depth_chart = data.get_week_depth_chart(
        season=2025,
        week=1,
    )

    assert depth_chart["player_id"].tolist() == [
        "qb-1",
        "qb-2",
    ]
    assert depth_chart["position"].tolist() == [
        "QB",
        "QB",
    ]
    assert depth_chart["depth_team"].tolist() == [
        1,
        2,
    ]
