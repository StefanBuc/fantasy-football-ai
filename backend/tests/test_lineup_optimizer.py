from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from main import app
from app.routes import espn
from app.schemas.espn import OptimizerPlayer, ESPNRosterProjectionResponse, ESPNLeaguePlayerResponse
from app.services.lineup_optimizer import optimize_lineup

NOW = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
FUTURE = datetime(2026, 12, 1, 18, tzinfo=timezone.utc)


def player(id, value, position='QB', slot='BE', **updates):
    return OptimizerPlayer(espn_id=id, player_name=f'Player {id}', player_id=f'nfl-{id}',
        position=position, current_slot=slot, team='BUF', opponent_team='MIA', predicted_points=value,
        status='projected', availability='healthy', kickoff_at=FUTURE,
        eligible_slots={'QB': ['QB', 'OP'], 'RB': ['RB', 'RB/WR/TE', 'OP'],
                        'WR': ['WR', 'RB/WR/TE', 'OP']}.get(position, [position]), **updates)


@pytest.fixture(autouse=True)
def settings_cache_isolated():
    espn.optimizer_settings_cache.clear()
    yield
    espn.optimizer_settings_cache.clear()


def test_flex_assignment_maximizes_total_without_using_a_player_twice():
    first = player(1, 20, 'RB', 'RB')
    second = player(2, 19, 'RB')
    second.eligible_slots = ['RB']
    third = player(3, 18, 'WR', 'RB/WR/TE')
    result = optimize_lineup([first, second, third], {'RB': 1, 'RB/WR/TE': 1, 'BE': 1}, NOW)
    assert [(entry.slot, entry.player.espn_id) for entry in result['lineup']] == [('RB', 2), ('RB/WR/TE', 1)]
    assert result['current_points'] == 38
    assert result['optimized_points'] == 39
    assert result['improvement'] == 1
    assert {change.action for change in result['changes']} == {'bench', 'start', 'move'}


def test_free_agent_upgrade_is_suggested_even_when_roster_is_full():
    owned = player(1, 8, slot='QB')
    reserve = player(2, 5)
    free = player(3, 15, is_free_agent=True)
    result = optimize_lineup([owned, reserve, free], {'QB': 1, 'BE': 1}, NOW)
    assert result['lineup'][0].player.is_free_agent
    assert result['improvement'] == 7
    assert any('regardless of roster space' in note for note in result['notes'])
    assert [(change.action, change.player.espn_id) for change in result['changes']] == [('bench', 1), ('add', 3)]
    assert {p.espn_id for p in result['bench']} == {1, 2}


def test_equal_score_keeps_owned_current_starter_over_unnecessary_pickup():
    result = optimize_lineup([player(1, 15, slot='QB'), player(2, 15), player(3, 15, is_free_agent=True)], {'QB': 1, 'BE': 1}, NOW)
    assert result['lineup'][0].player.espn_id == 1
    assert result['changes'] == []
    assert result['improvement'] == 0


def test_ir_byes_unavailable_and_started_bench_players_are_not_promoted():
    injured = player(2, 50)
    injured.availability = 'unavailable'
    bye = player(3, 40)
    bye.is_on_bye = True
    ir = player(4, 100, slot='IR')
    started = player(5, 90)
    started.kickoff_at = NOW - timedelta(hours=1)
    free = player(6, 80, is_free_agent=True)
    free.kickoff_at = NOW - timedelta(hours=1)
    result = optimize_lineup([player(1, 10, slot='QB'), injured, bye, ir, started, free, player(7, 14)],
                             {'QB': 1, 'BE': 5, 'IR': 1}, NOW)
    assert result['lineup'][0].player.espn_id == 7
    assert result['lineup'][0].action == 'start'


def test_started_starter_is_kept_in_slot_and_uses_saved_pregame_projection():
    locked = player(1, 1, 'RB', 'RB')
    locked.kickoff_at = NOW - timedelta(hours=1)
    locked.prediction_saved = True
    locked.pregame_predicted_points = 18
    result = optimize_lineup([locked, player(2, 100, 'RB', is_free_agent=True)], {'RB': 1}, NOW)
    assert result['lineup'][0].locked
    assert result['lineup'][0].player.espn_id == 1
    assert result['optimized_points'] == 18
    assert result['current_points'] == 18
    assert result['changes'] == []


def test_unknown_locked_score_does_not_fabricate_totals_but_movable_gain_is_known():
    locked = player(1, 99, 'RB', 'RB')
    locked.kickoff_at = NOW - timedelta(hours=1)
    result = optimize_lineup([locked, player(2, 10, slot='QB'), player(3, 14)], {'QB': 1, 'RB': 1, 'BE': 1}, NOW)
    assert result['current_points'] is None
    assert result['optimized_points'] is None
    assert result['improvement'] == 4


def test_unknown_kickoff_is_not_assumed_to_be_unlocked():
    unknown = player(1, 10, slot='QB')
    unknown.kickoff_at = None
    result = optimize_lineup([unknown, player(2, 100)], {'QB': 1, 'BE': 1}, NOW)
    assert result['lineup'][0].locked
    assert result['lineup'][0].player.espn_id == 1


def test_empty_slots_and_missing_projections_are_explicit():
    result = optimize_lineup([player(1, None)], {'QB': 1}, NOW)
    assert result['lineup'][0].player is None
    assert any('without usable projections' in note for note in result['notes'])
    negative = optimize_lineup([player(1, -2, slot='QB')], {'QB': 1}, NOW)
    assert negative['optimized_points'] == 0
    assert negative['improvement'] == 2


def test_unsupported_leagues_and_duplicate_player_ids_are_rejected():
    with pytest.raises(ValueError, match='Unsupported starting slots'):
        optimize_lineup([], {'LB': 1}, NOW)
    with pytest.raises(ValueError, match='more than once'):
        optimize_lineup([player(1, 10), player(1, 12)], {'QB': 1}, NOW)


def test_superflex_uses_espn_eligibility_and_preserves_unique_players():
    result = optimize_lineup([player(1, 20, slot='QB'), player(2, 19), player(3, 17, 'RB', 'OP')], {'QB': 1, 'OP': 1, 'BE': 1}, NOW)
    assert result['optimized_points'] == 39
    assert {entry.player.espn_id for entry in result['lineup']} == {1, 2}


def roster_projection(candidate):
    return ESPNRosterProjectionResponse(**{**candidate.model_dump(), 'lineup_slot': candidate.current_slot,
        'base_predicted_points': candidate.predicted_points, 'history_games': 5, 'injury_context_used': False,
        'unavailable_teammates': 0, 'adjustment_reason': None, 'reason': None})


def pool_projection(candidate, owner=None):
    return ESPNLeaguePlayerResponse(**{**candidate.model_dump(),
        'lineup_slot': candidate.current_slot, 'roster_status': 'available' if owner is None else 'rostered',
        'fantasy_team_id': owner, 'fantasy_team_name': None, 'percent_owned': None, 'percent_started': None,
        'season_average': None, 'base_predicted_points': candidate.predicted_points,
        'projection_status': 'projected', 'history_games': 5, 'projection_reason': None})


def test_roster_only_endpoint_never_fetches_free_agents(monkeypatch):
    own = [player(1, 10, slot='QB'), player(2, 14)]
    team = SimpleNamespace(team_id=1, team_name='My team', roster=[SimpleNamespace(playerId=p.espn_id, eligibleSlots=p.eligible_slots) for p in own])
    league = SimpleNamespace(teams=[team])
    monkeypatch.setattr(espn, 'get_public_league', lambda **_: league)
    monkeypatch.setattr(espn, 'optimizer_slot_counts', lambda *_: {'QB': 1, 'BE': 1})
    monkeypatch.setattr(espn, 'get_espn_projection_service', lambda *_: SimpleNamespace())
    monkeypatch.setattr(espn, 'build_team_projection_response', lambda *_: SimpleNamespace(players=[roster_projection(p) for p in own]))
    pool = Mock(side_effect=AssertionError('Free agents should be optional'))
    monkeypatch.setattr(espn, 'build_league_players_response', pool)
    response = TestClient(app).post('/api/espn/optimized-lineup', json={'league_id':123,'season':2026,'week':13,'team_id':1})
    assert response.status_code == 200
    assert response.json()['lineup'][0]['player']['espn_id'] == 2
    assert response.json()['improvement'] == 4
    pool.assert_not_called()


def test_free_agent_mode_excludes_other_teams_and_labels_available_players(monkeypatch):
    team = SimpleNamespace(team_id=1, team_name='My team', roster=[])
    league = SimpleNamespace(teams=[team])
    monkeypatch.setattr(espn, 'get_public_league', lambda **_: league)
    monkeypatch.setattr(espn, 'optimizer_slot_counts', lambda *_: {'QB':1, 'BE':1})
    monkeypatch.setattr(espn, 'get_espn_projection_service', lambda *_: SimpleNamespace())
    candidates = [pool_projection(player(1,10,slot='QB'),1), pool_projection(player(2,90),2),
                  pool_projection(player(3,15,is_free_agent=True))]
    monkeypatch.setattr(espn, 'build_league_players_response', lambda *_: SimpleNamespace(players=candidates))
    response = TestClient(app).post('/api/espn/optimized-lineup', json={'league_id':123,'season':2026,'week':13,'team_id':1,'include_free_agents':True})
    assert response.status_code == 200
    recommended = response.json()['lineup'][0]['player']
    assert recommended['espn_id'] == 3
    assert recommended['is_free_agent'] is True


def test_exact_roster_settings_are_used_instead_of_inferred_slot_counts():
    getter = Mock(return_value={'settings':{'rosterSettings':{'lineupSlotCounts':{'0':1,'2':2,'23':1,'20':5,'21':1}}}})
    league = SimpleNamespace(espn_request=SimpleNamespace(cookies=None, league_get=getter))
    assert espn.optimizer_slot_counts(league,123,2026) == {'QB':1,'RB':2,'RB/WR/TE':1,'BE':5,'IR':1}
    espn.optimizer_slot_counts(league,123,2026)
    getter.assert_called_once_with(params={'view':'mSettings'})


def test_local_optimizer_keeps_local_access_guard(monkeypatch):
    monkeypatch.setattr(espn, 'local_espn_api_enabled', lambda: False)
    assert TestClient(app).post('/api/espn/local/optimized-lineup', json={'team_id':1,'week':13}).status_code == 404
