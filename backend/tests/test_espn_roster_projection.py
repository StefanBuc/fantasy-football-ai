import pandas as pd

from app.integrations.espn_player_matching import (
    ESPNPlayerMatch,
)
from app.integrations.espn_roster_projection import (
    build_espn_projection_request,
    build_espn_request_batches,
    project_espn_request_batches,
)
from app.services.projection_types import (
    ProjectionSlateResult,
)

def make_player_match() -> ESPNPlayerMatch:
    return ESPNPlayerMatch(
        espn_id=123,
        espn_name="Test Player",
        position="RB",
        player_id="00-0012345",
        status="matched",
    )


def test_builds_projection_request():
    roster_df = pd.DataFrame(
        [
            {
                "player_id": "00-0012345",
                "player_name": "T.Player",
                "position": "RB",
                "team": "ATL",
            }
        ]
    )

    request, reason = build_espn_projection_request(
        player_match=make_player_match(),
        roster_df=roster_df,
        opponents={"ATL": "TB"},
        season=2024,
        week=1,
    )

    assert reason is None
    assert request is not None
    assert request.player_id == "00-0012345"
    assert request.player_name == "Test Player"
    assert request.team == "ATL"
    assert request.opponent_team == "TB"
    assert request.season == 2024
    assert request.upcoming_week == 1


def test_skips_player_not_on_active_roster():
    roster_df = pd.DataFrame(
        columns=[
            "player_id",
            "player_name",
            "position",
            "team",
        ]
    )

    request, reason = build_espn_projection_request(
        player_match=make_player_match(),
        roster_df=roster_df,
        opponents={"ATL": "TB"},
        season=2024,
        week=1,
    )

    assert request is None
    assert reason is not None
    assert "not on the active NFL roster" in reason


def test_skips_player_on_bye():
    roster_df = pd.DataFrame(
        [
            {
                "player_id": "00-0012345",
                "player_name": "T.Player",
                "position": "RB",
                "team": "ATL",
            }
        ]
    )

    request, reason = build_espn_projection_request(
        player_match=make_player_match(),
        roster_df=roster_df,
        opponents={},
        season=2024,
        week=1,
    )

    assert request is None
    assert reason == "ATL does not play during week 1."
    
def test_groups_requests_by_position_and_skips_inactive_player():
    player_matches = [
        ESPNPlayerMatch(
            espn_id=101,
            espn_name="Quarterback",
            position="QB",
            player_id="00-0000001",
            status="matched",
        ),
        ESPNPlayerMatch(
            espn_id=102,
            espn_name="Running Back",
            position="RB",
            player_id="00-0000002",
            status="matched",
        ),
        ESPNPlayerMatch(
            espn_id=103,
            espn_name="Inactive Receiver",
            position="WR",
            player_id="00-0000003",
            status="matched",
        ),
    ]

    roster_df = pd.DataFrame(
        [
            {
                "player_id": "00-0000001",
                "player_name": "Q.Back",
                "position": "QB",
                "team": "BUF",
            },
            {
                "player_id": "00-0000002",
                "player_name": "R.Back",
                "position": "RB",
                "team": "ATL",
            },
        ]
    )

    requests_by_position, skipped = (
        build_espn_request_batches(
            player_matches=player_matches,
            roster_df=roster_df,
            opponents={
                "BUF": "NYJ",
                "ATL": "TB",
            },
            season=2024,
            week=1,
        )
    )

    assert len(requests_by_position["QB"]) == 1
    assert len(requests_by_position["RB"]) == 1
    assert len(requests_by_position["WR"]) == 0
    assert len(requests_by_position["TE"]) == 0

    qb_request = requests_by_position["QB"][0]
    rb_request = requests_by_position["RB"][0]

    assert qb_request.player_id == "00-0000001"
    assert qb_request.opponent_team == "NYJ"

    assert rb_request.player_id == "00-0000002"
    assert rb_request.opponent_team == "TB"

    assert 103 in skipped
    assert "not on the active NFL roster" in skipped[103]


class FakeWeeklyProjectionService:
    def __init__(self):
        self.calls = []

    def project_requests(
        self,
        position,
        requests,
    ):
        self.calls.append((position, requests))

        return ProjectionSlateResult(
            projections=[],
            skipped=[],
        )


def test_projects_each_nonempty_position_batch_once():
    service = FakeWeeklyProjectionService()
    qb_request = build_espn_projection_request(
        player_match=ESPNPlayerMatch(
            espn_id=201,
            espn_name="Quarterback",
            position="QB",
            player_id="qb-1",
            status="matched",
        ),
        roster_df=pd.DataFrame(
            [
                {
                    "player_id": "qb-1",
                    "player_name": "Q.Back",
                    "position": "QB",
                    "team": "BUF",
                }
            ]
        ),
        opponents={"BUF": "NYJ"},
        season=2024,
        week=1,
    )[0]

    assert qb_request is not None

    results = project_espn_request_batches(
        weekly_service=service,
        requests_by_position={
            "QB": [qb_request],
            "RB": [],
            "WR": [],
            "TE": [],
        },
    )

    assert list(results) == ["QB"]
    assert len(service.calls) == 1
    assert service.calls[0][0] == "QB"
    assert service.calls[0][1] == [qb_request]
