import pandas as pd

from app.integrations.espn_player_matching import (
    match_espn_player,
)


def test_match_espn_player_by_id():
    id_map = pd.DataFrame(
        [
            {
                "espn_id": 12345,
                "player_id": "00-0012345",
                "position": "QB",
            }
        ]
    )

    result = match_espn_player(
        id_map=id_map,
        espn_id=12345,
        espn_name="Test Quarterback",
        position="QB",
    )

    assert result.status == "matched"
    assert result.player_id == "00-0012345"
    assert result.reason is None


def test_match_espn_player_reports_missing_id():
    id_map = pd.DataFrame(
        columns=[
            "espn_id",
            "player_id",
            "position",
        ]
    )

    result = match_espn_player(
        id_map=id_map,
        espn_id=99999,
        espn_name="Unknown Player",
        position="WR",
    )

    assert result.status == "missing"
    assert result.player_id is None


def test_match_espn_player_reports_ambiguous_id():
    id_map = pd.DataFrame(
        [
            {
                "espn_id": 12345,
                "player_id": "00-player-one",
                "position": "RB",
            },
            {
                "espn_id": 12345,
                "player_id": "00-player-two",
                "position": "RB",
            },
        ]
    )

    result = match_espn_player(
        id_map=id_map,
        espn_id=12345,
        espn_name="Ambiguous Player",
        position="RB",
    )

    assert result.status == "ambiguous"
    assert result.player_id is None