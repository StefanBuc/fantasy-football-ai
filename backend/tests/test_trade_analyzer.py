from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from main import app
from app.routes import espn
from app.schemas.espn import OptimizerPlayer
from app.schemas.trade import LocalTradeRequest
from app.services.trade_analyzer import analyze_trade

NOW = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
FUTURE = datetime(2099, 12, 1, 18, tzinfo=timezone.utc)
NAMES = {1: 'Team A', 2: 'Team B', 3: 'Team C'}
SLOTS = {'QB': 1, 'WR': 1, 'BE': 2}


def player(id, score, position, slot='BE', **updates):
    return OptimizerPlayer(**{
        'espn_id': id, 'player_id': f'nfl-{id}', 'player_name': f'Player {id}',
        'position': position, 'current_slot': slot, 'predicted_points': score,
        'eligible_slots': [position, 'OP'] + (['RB/WR/TE'] if position in {'RB', 'WR', 'TE'} else []),
        'status': 'projected', 'availability': 'healthy', 'team': 'BUF', 'opponent_team': 'MIA',
        'kickoff_at': FUTURE, **updates,
    })


def rosters():
    return {
        1: [player(1, 30, 'QB', 'QB'), player(2, 20, 'QB'), player(3, 5, 'WR', 'WR')],
        2: [player(4, 10, 'QB', 'QB'), player(5, 16, 'WR', 'WR'), player(6, 15, 'WR')],
        3: [player(7, 28, 'QB', 'QB'), player(8, 16, 'WR', 'WR')],
    }


def request(**updates):
    return LocalTradeRequest(**{
        'team_a_id': 1, 'team_b_id': 2, 'team_a_player_ids': [2], 'team_b_player_ids': [5],
        'week': 13, 'end_week': 14, **updates,
    })


def analyze(profiles=None, **updates):
    profiles = profiles or {13: rosters(), 14: rosters()}
    return analyze_trade(season=2026, request=request(**updates), team_names=NAMES,
                         slot_counts=SLOTS, load_week=profiles.__getitem__, now=NOW)


def test_verdict_uses_marginal_starter_value_and_reoptimizes_both_teams():
    result = analyze()
    a, b = result.teams
    # A gives 20 to receive 16 but gains more because their spare QB was benched.
    assert (a.weekly_before, a.weekly_after, a.weekly_change) == (35, 46, 11)
    assert (b.weekly_before, b.weekly_after, b.weekly_change) == (26, 35, 9)
    assert (a.rest_change, b.rest_change) == (22, 18)
    assert result.favors_team_id == 1
    assert 'Both teams improve' in result.summary
    assert any('Incoming Player 5' in note for note in a.explanations)
    assert any('Biggest starting-slot need: WR' in note for note in a.explanations)
    assert any('QB eligible backups this week: 1 before, 0 after' in note for note in a.explanations)
    assert a.weeks_covered == 2
    assert [(row.team_id, row.rank_before, row.rank_after) for row in result.power_rankings] == [(1, 2, 1), (3, 1, 2), (2, 3, 3)]
    assert len({slot.player.espn_id for slot in a.lineup_after}) == 2


def test_nearly_equal_gains_have_a_neutral_verdict_and_ties_share_power_rank():
    profiles = {13: rosters(), 14: rosters()}
    for roster in profiles.values():
        roster[2][0].predicted_points = 8
        roster[3][0].predicted_points = 19
    result = analyze(profiles)
    assert result.favors_team_id is None
    assert 'Fairly even' in result.verdict
    assert result.teams[0].power_rank_before == 1
    assert next(row for row in result.power_rankings if row.team_id == 3).rank_before == 1


def test_each_week_uses_its_own_projection_and_bye_instead_of_multiplying_one_week():
    profiles = {13: rosters(), 14: rosters()}
    profiles[14][2][1].is_on_bye = True
    profiles[14][2][1].predicted_points = 0
    result = analyze(profiles)
    incoming = next(p for p in result.players if p.espn_id == 5)
    assert incoming.weekly_points == 16
    assert incoming.rest_of_season_points == 16
    assert incoming.projected_games == 1
    assert result.teams[0].weeks[0].change == 11
    assert result.teams[0].weeks[1].change == 0
    assert result.teams[0].rest_change == 11


def test_missing_projection_cannot_become_a_zero_or_a_confident_verdict():
    profiles = {13: rosters(), 14: rosters()}
    profiles[14][2][1].predicted_points = None
    profiles[14][2][1].status = 'skipped'
    result = analyze(profiles)
    assert result.favors_team_id is None
    assert 'Not enough' in result.verdict
    assert result.teams[0].rest_after is None
    assert result.teams[0].weeks_covered == 1
    assert result.teams[0].weeks[0].change == 11
    assert result.teams[0].weeks[1].change is None
    assert next(p for p in result.players if p.espn_id == 5).rest_of_season_points is None
    assert next(p for p in result.players if p.espn_id == 5).missing_weeks == 1
    assert all(p.rank_after is None for p in result.power_rankings)


def test_started_trade_players_are_rejected_before_loading_remaining_weeks():
    initial = rosters()
    initial[1][1].kickoff_at = NOW - timedelta(minutes=1)
    load = Mock(return_value=initial)
    with pytest.raises(ValueError, match='Choose a later effective week'):
        analyze_trade(season=2026, request=request(), team_names=NAMES,
                      slot_counts=SLOTS, load_week=load, now=NOW)
    load.assert_called_once_with(13)


def test_unknown_kickoff_and_wrong_ownership_are_not_assumed_tradeable():
    profiles = {13: rosters(), 14: rosters()}
    profiles[13][1][1].kickoff_at = None
    with pytest.raises(ValueError, match='kickoff is unknown'):
        analyze(profiles)
    with pytest.raises(ValueError, match='sending team'):
        analyze(team_a_player_ids=[6])


def test_nontraded_started_starters_remain_locked_with_frozen_pregame_points():
    profiles = {13: rosters(), 14: rosters()}
    profiles[13][1][0] = player(1, 999, 'QB', 'QB', kickoff_at=NOW - timedelta(hours=1),
                               prediction_saved=True, pregame_predicted_points=30)
    # A started bench player without saved points cannot be used and does not
    # invalidate an otherwise fully known starting-lineup comparison.
    profiles[13][1].append(player(9, 999, 'WR', kickoff_at=NOW - timedelta(hours=1)))
    result = analyze(profiles)
    assert result.teams[0].weekly_after == 46
    assert result.teams[0].lineup_after[0].locked
    assert result.teams[0].lineup_after[0].player.espn_id == 1


def test_full_rosters_and_unequal_packages_do_not_trigger_drops_or_reject_analysis():
    profiles = {13: rosters(), 14: rosters()}
    result = analyze(profiles, team_a_player_ids=[2, 3])
    assert result.teams[0].weekly_after == 46
    assert result.teams[1].weekly_after == 35
    # Input roster objects are never mutated by an analysis.
    assert profiles[13][2][1].current_slot == 'WR'
    assert profiles[13][1][1].current_slot == 'BE'
    assert len(profiles[13][1]) == 3
    assert len(profiles[13][2]) == 3


def test_ir_incoming_players_are_not_silently_activated():
    profiles = {13: rosters(), 14: rosters()}
    for roster in profiles.values():
        roster[2][1].current_slot = 'IR'
    result = analyze(profiles)
    assert result.teams[0].weekly_change == 0
    assert all(entry.player.espn_id != 5 for entry in result.teams[0].lineup_after)


def test_validation_rejects_duplicate_players_same_teams_and_reversed_horizon():
    for updates in ({'team_b_id': 1}, {'team_a_player_ids': [2, 2]},
                    {'team_b_player_ids': [2]}, {'end_week': 12}, {'team_a_player_ids': []}):
        with pytest.raises(ValidationError):
            request(**updates)
    assert request(team_a_player_ids=[-16002]).team_a_player_ids == [-16002]


@pytest.fixture
def endpoint(monkeypatch):
    profiles = rosters()
    teams = [SimpleNamespace(team_id=id, team_name=NAMES[id], roster=[
        SimpleNamespace(playerId=p.espn_id, name=p.player_name, position=p.position,
                        proTeam=p.team, injuryStatus='ACTIVE') for p in players])
        for id, players in profiles.items()]
    league = SimpleNamespace(teams=teams)
    monkeypatch.setattr(espn, 'get_public_league', lambda **_: league)
    monkeypatch.setattr(espn, 'optimizer_slot_counts', lambda *_: SLOTS)
    monkeypatch.setattr(espn, 'get_espn_projection_service', lambda *_: SimpleNamespace(data=SimpleNamespace(
        schedule=pd.DataFrame({'season': [2026, 2026], 'week': [13, 14], 'game_type': ['REG', 'REG']}))))
    week_loader = Mock(side_effect=lambda *args: rosters())
    monkeypatch.setattr(espn, 'trade_week_profiles', week_loader)
    return TestClient(app), league, week_loader


def test_public_analysis_endpoint_and_coverage_validation(endpoint):
    client, _, loader = endpoint
    body = {'league_id': 123, 'season': 2026, **request().model_dump()}
    response = client.post('/api/espn/trade-analysis', json=body)
    assert response.status_code == 200
    assert response.json()['teams'][0]['rest_change'] == 22
    assert [call.args[3] for call in loader.call_args_list] == [13, 14]
    assert client.post('/api/espn/trade-analysis', json={**body, 'end_week': 18}).status_code == 400


def test_stale_ownership_is_rejected_before_inference(endpoint, monkeypatch):
    client, _, loader = endpoint
    service = Mock(side_effect=AssertionError('Must validate ownership before models'))
    monkeypatch.setattr(espn, 'get_espn_projection_service', service)
    response = client.post('/api/espn/trade-analysis', json={
        'league_id': 123, 'season': 2026, **request(team_a_player_ids=[6]).model_dump()})
    assert response.status_code == 400
    assert 'sending team' in response.json()['detail']
    service.assert_not_called()
    loader.assert_not_called()


def test_trade_rosters_are_lightweight_and_do_not_run_models(endpoint, monkeypatch):
    client, _, _ = endpoint
    service = Mock(side_effect=AssertionError('Roster selection should not run models'))
    monkeypatch.setattr(espn, 'get_espn_projection_service', service)
    response = client.post('/api/espn/trade-rosters', json={'league_id': 123, 'season': 2026})
    assert response.status_code == 200
    assert response.json()['teams'][0]['players'][0]['espn_id'] == 1
    service.assert_not_called()


def test_local_trade_endpoints_retain_existing_access_guard(monkeypatch):
    monkeypatch.setattr(espn, 'local_espn_api_enabled', lambda: False)
    client = TestClient(app)
    assert client.post('/api/espn/local/trade-rosters', json={}).status_code == 404
    assert client.post('/api/espn/local/trade-analysis', json=request().model_dump()).status_code == 404


def test_trade_week_adapter_reuses_model_cache_without_writing_hypothetical_history(monkeypatch):
    raw = SimpleNamespace(playerId=1, eligibleSlots=['QB'], lineupSlot='QB', injuryStatus='ACTIVE')
    league = SimpleNamespace(teams=[SimpleNamespace(team_id=1, roster=[raw])])
    item = SimpleNamespace(espn_id=1, player_id='nfl-1', player_name='Player 1', position='QB', team='BUF',
        opponent_team='MIA', lineup_slot='QB', predicted_points=20, status='projected', projection_method='model', is_on_bye=False)
    cached = SimpleNamespace(team_projections={1: [item]})
    monkeypatch.setattr(espn, 'roster_fingerprint', lambda *_: 'fingerprint')
    cache = Mock(return_value=(cached, True))
    monkeypatch.setattr(espn.projection_cache, 'get_or_create', cache)
    writer = Mock(side_effect=AssertionError('Never save hypothetical values'))
    monkeypatch.setattr(espn, 'record_predictions', writer)
    monkeypatch.setattr(espn, 'prediction_display', lambda *args: [
        {**p, 'kickoff_at': FUTURE} for p in args[4]])
    profiles = espn.trade_week_profiles(league, 123, 2026, 13, SimpleNamespace(generation='v1'))
    assert profiles[1][0].predicted_points == 20
    assert profiles[1][0].eligible_slots == ['QB']
    cache.assert_called_once()
    writer.assert_not_called()
