import pandas as pd

from app.integrations.espn_player_matching import (
    ESPNPlayerMatch,
)
from app.integrations.espn_roster_projection import (
    ESPNRosterPlayer,
    build_espn_projection_request,
    build_espn_request_batches,
    project_espn_request_batches,
    project_espn_roster,
)
from app.services.projection_types import (
    PlayerProjection,
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


def test_live_unavailable_player_adds_team_context():
    class CapturingService:
        def __init__(self):
            self.calls = []
            self.player_df = pd.DataFrame(
                [
                    {
                        "player_id": "out-wr",
                        "season": 2024,
                        "season_type": "REG",
                        "week": 1,
                        "target_share": 0.25,
                        "carries": 1.0,
                        "offense_pct": 0.9,
                    }
                ]
            )

        def project_requests(self, position, requests):
            self.calls.extend(requests)
            return ProjectionSlateResult(
                projections=[
                    PlayerProjection(
                        request=request,
                        position=position,
                        predicted_points=10.0,
                        injury_context_used=True,
                        unavailable_teammates=int(
                            request.teammate_out_count
                        ),
                    )
                    for request in requests
                ],
                skipped=[],
            )

    service = CapturingService()
    roster_players = [
        ESPNRosterPlayer(
            espn_id=1,
            player_name="Out Receiver",
            position="WR",
            lineup_slot="WR",
            team="BUF",
            injury_status="OUT",
        ),
        ESPNRosterPlayer(
            espn_id=2,
            player_name="Healthy Receiver",
            position="WR",
            lineup_slot="WR",
            team="BUF",
            injury_status="ACTIVE",
        ),
    ]
    id_map = pd.DataFrame(
        [
            {"espn_id": 1, "player_id": "out-wr", "position": "WR"},
            {"espn_id": 2, "player_id": "healthy-wr", "position": "WR"},
        ]
    )
    roster_df = pd.DataFrame(
        [
            {
                "player_id": player_id,
                "player_name": player_id,
                "position": "WR",
                "team": "BUF",
            }
            for player_id in ["out-wr", "healthy-wr"]
        ]
    )

    project_espn_roster(
        weekly_service=service,
        roster_players=roster_players,
        id_map=id_map,
        roster_df=roster_df,
        opponents={"BUF": "MIA"},
        season=2024,
        week=2,
    )

    healthy_request = next(
        request
        for request in service.calls
        if request.player_id == "healthy-wr"
    )
    assert healthy_request.teammate_out_count == 1.0
    assert healthy_request.teammate_out_target_share == 0.25
    assert healthy_request.teammate_out_carries == 1.0
    assert healthy_request.teammate_out_offense_pct == 0.9


def test_nonstarting_qb_receives_zero_projection():
    class QBProjectionService:
        def __init__(self):
            self.player_df = pd.DataFrame()

        def project_requests(self, position, requests):
            return ProjectionSlateResult(
                projections=[
                    PlayerProjection(
                        request=request,
                        position=position,
                        predicted_points=20.0,
                    )
                    for request in requests
                ],
                skipped=[],
            )

    roster_players = [
        ESPNRosterPlayer(
            espn_id=1,
            player_name="Starting Quarterback",
            position="QB",
            lineup_slot="QB",
            team="BUF",
            injury_status="ACTIVE",
        ),
        ESPNRosterPlayer(
            espn_id=2,
            player_name="Backup Quarterback",
            position="QB",
            lineup_slot="BE",
            team="BUF",
            injury_status="ACTIVE",
        ),
    ]
    id_map = pd.DataFrame(
        [
            {
                "espn_id": 1,
                "player_id": "qb-1",
                "position": "QB",
            },
            {
                "espn_id": 2,
                "player_id": "qb-2",
                "position": "QB",
            },
        ]
    )
    roster_df = pd.DataFrame(
        [
            {
                "player_id": player_id,
                "player_name": player_id,
                "position": "QB",
                "team": "BUF",
                "season": 2024,
                "week": 1,
            }
            for player_id in ["qb-1", "qb-2"]
        ]
    )
    depth_chart_df = pd.DataFrame(
        [
            {
                "player_id": "qb-1",
                "team": "BUF",
                "position": "QB",
                "depth_position": "QB",
                "depth_team": 1,
            },
            {
                "player_id": "qb-2",
                "team": "BUF",
                "position": "QB",
                "depth_position": "QB",
                "depth_team": 2,
            },
        ]
    )

    projections = project_espn_roster(
        weekly_service=QBProjectionService(),
        roster_players=roster_players,
        id_map=id_map,
        roster_df=roster_df,
        opponents={"BUF": "MIA"},
        season=2024,
        week=1,
        depth_chart_df=depth_chart_df,
    )

    by_espn_id = {
        projection.espn_id: projection
        for projection in projections
    }
    assert by_espn_id[1].predicted_points == 20.0
    assert by_espn_id[1].status == "projected"
    assert by_espn_id[2].predicted_points == 0.0
    assert by_espn_id[2].status == "skipped"
    assert "not the active starting quarterback" in (
        by_espn_id[2].reason or ""
    )
