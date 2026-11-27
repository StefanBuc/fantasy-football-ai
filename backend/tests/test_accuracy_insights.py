from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import sqlite3

from fastapi.testclient import TestClient
import pandas as pd
import pytest

from main import app
from app.services.accuracy_insights import insights, range_result
from app.services.espn_benchmark import espn_benchmark, ESPN_SCORING
from app.services import prediction_history as history

PREGAME = datetime(2026, 11, 8, 15, tzinfo=timezone.utc)
KICKOFF = datetime(2026, 11, 8, 18, tzinfo=timezone.utc)


def row(**values):
    return {"position": "QB", "predicted_points": 10, "actual_points": 14,
        "floor_points": None, "ceiling_points": None,
        "espn_predicted_points": 13, "espn_scoring": ESPN_SCORING,
        "espn_recorded_at": PREGAME.isoformat(), "kickoff": KICKOFF.isoformat(), **values}


def test_espn_projection_uses_week_specific_raw_stats_and_full_ppr_not_league_points():
    player = SimpleNamespace(position='QB', projected_points=999, stats={10:{
        'projected_points':999, 'projected_breakdown':{
            'passingYards':250, 'passingTouchdowns':2, 'passingInterceptions':1,
            'rushingYards':20, 'receivingReceptions':2, 'receivingYards':10,
            'lostFumbles':.25, 'passing2PtConversions':.1, 'puntReturnTouchdowns':.05,
            '2PtConversions':999, 'passing300To399YardGame':999,
        }}})
    result = espn_benchmark(player,10)
    assert result['espn_predicted_points'] == pytest.approx(21)
    assert result['espn_scoring'] == ESPN_SCORING
    assert espn_benchmark(player,11) == {}
    player.stats={10:{'projected_breakdown':{'rushingYards':0}}}
    assert espn_benchmark(player,10)['espn_predicted_points'] == 0


@pytest.mark.parametrize('stats', [{}, {10:{'points':20,'breakdown':{'passingYards':250}}},
    {0:{'projected_breakdown':{'passingYards':250}}},
    {10:{'projected_breakdown':{'passingYards':float('nan')}}},
    {10:{'projected_breakdown':{'passingYards':'invalid'}}},
    {10:{'projected_breakdown':{'passingYards':250,'lostFumbles':None}}}])
def test_unusable_or_actual_stats_do_not_invent_an_espn_forecast(stats):
    assert espn_benchmark(SimpleNamespace(position='QB',stats=stats,projected_points=20),10) == {}


def test_espn_benchmark_excludes_special_teams_and_supports_string_week_keys():
    player=SimpleNamespace(position='DST',stats={'10':{'projected_breakdown':{'rushingYards':10}}})
    assert espn_benchmark(player,10) == {}
    player.position='RB'
    assert espn_benchmark(player,10)['espn_predicted_points'] == 1
    assert espn_benchmark(None,10) == {}


def test_range_coverage_includes_boundaries_and_excludes_missing_invalid_and_pending():
    rows=[row(actual_points=value,floor_points=10,ceiling_points=20) for value in [10,20,9,21]]
    rows += [row(),row(actual_points=None,floor_points=10,ceiling_points=20),row(floor_points=20,ceiling_points=10)]
    result=insights(rows)['range_coverage']
    assert (result['count'],result['inside'],result['below'],result['above'],result['missing']) == (4,2,1,1,2)
    assert result['coverage_pct'] == 50 and result['average_width'] == 10
    assert result['by_position'][0]['count'] == 4
    assert range_result(row(actual_points=-2,floor_points=-5,ceiling_points=0)) == 'inside'
    assert insights([row()])['range_coverage']['coverage_pct'] is None


def test_error_buckets_are_symmetric_disjoint_and_thresholds_are_cumulative():
    result=insights([row(predicted_points=20+error,actual_points=20) for error in [-11,-10,-5,-2,0,2,5,10,11]])['error_distribution']
    assert [bucket['count'] for bucket in result['buckets']] == [1,1,1,3,1,1,1]
    assert sum(bucket['pct'] for bucket in result['buckets']) == pytest.approx(100)
    assert result['within_two_pct'] == pytest.approx(100*3/9)
    assert result['within_five_pct'] == pytest.approx(100*5/9)
    assert result['within_ten_pct'] == pytest.approx(100*7/9)
    assert result['median_absolute_error'] == 5
    assert result['p90_absolute_error'] == 11
    assert result['rmse'] == pytest.approx((500/9)**.5)


def test_espn_uses_identical_paired_cohort_and_rejects_postgame_mismatched_scoring():
    paired=[row(),row(predicted_points=20,actual_points=10,espn_predicted_points=10),
            row(predicted_points=12,actual_points=10,espn_predicted_points=20),
            row(predicted_points=9,actual_points=10,espn_predicted_points=11)]
    other=[row(predicted_points=999,actual_points=0,espn_predicted_points=None),
           row(espn_recorded_at=KICKOFF.isoformat()), row(espn_scoring='custom'),
           row(espn_recorded_at='invalid'),row(espn_recorded_at=PREGAME.replace(tzinfo=None).isoformat()),
           row(position='DST'),row(actual_points=None)]
    result=insights(paired+other)['espn_comparison']
    assert (result['count'],result['pending'],result['ai_closer'],result['espn_closer'],result['ties']) == (4,1,1,2,1)
    assert result['ai_mae'] == 4.25 and result['espn_mae'] == 3
    assert result['mae_improvement'] == -1.25
    assert result['by_position'][0]['count'] == 4


def test_empty_statistics_stay_unavailable_instead_of_claiming_zero_error():
    result=insights([])
    assert result['error_distribution']['median_absolute_error'] is None
    assert result['error_distribution']['within_five_pct'] is None
    assert result['range_coverage']['coverage_pct'] is None
    assert result['espn_comparison']['ai_mae'] is None


def save(monkeypatch,*,now=PREGAME,espn=13,player_id='qb',scope='espn:123',week=10,generated_at=None):
    monkeypatch.setattr(history,'utc_now',lambda:now)
    games=pd.DataFrame([{'season':2026,'week':week,'home_team':'BUF','away_team':'MIA',
        'game_type':'REG','gameday':'2026-11-08','gametime':'13:00'}])
    sample={'player_id':player_id,'player_name':'Test QB','position':'QB','team':'BUF',
            'opponent_team':'MIA','predicted_points':10,'espn_predicted_points':espn,'espn_scoring':ESPN_SCORING}
    return history.prediction_history.record(season=2026,week=week,samples=[sample],schedule=games,
        generated_at=generated_at or now,scope=scope,model_revision='test')


def test_espn_forecasts_freeze_at_kickoff_and_cannot_be_added_retrospectively(monkeypatch):
    save(monkeypatch)
    save(monkeypatch,now=PREGAME+timedelta(minutes=15),espn=14)
    save(monkeypatch,now=PREGAME+timedelta(minutes=20),espn=None)
    save(monkeypatch,now=KICKOFF,espn=999)
    saved=history.prediction_history.rows(2026,'espn:123')[0]
    assert saved['espn_predicted_points'] == 14
    assert saved['espn_recorded_at'] == (PREGAME+timedelta(minutes=15)).isoformat()
    save(monkeypatch,espn=None,player_id='late')
    save(monkeypatch,now=KICKOFF+timedelta(days=1),player_id='late',espn=999)
    assert history.prediction_history.week_records(2026,10,'espn:123')[('QB','late')]['espn_predicted_points'] is None


def test_fresh_espn_observation_updates_without_replacing_a_newer_archived_ai(monkeypatch):
    generated=PREGAME+timedelta(minutes=15)
    save(monkeypatch,now=generated,espn=None)
    observed=PREGAME+timedelta(minutes=30)
    save(monkeypatch,now=observed,generated_at=PREGAME,espn=16)
    saved=history.prediction_history.rows(2026,'espn:123')[0]
    assert saved['generated_at'] == generated.isoformat()
    assert saved['recorded_at'] == generated.isoformat()
    assert saved['espn_predicted_points'] == 16
    assert saved['espn_recorded_at'] == observed.isoformat()
    # A clock rollback must not replace the more recently observed ESPN forecast.
    save(monkeypatch,now=generated,espn=99)
    assert history.prediction_history.rows(2026,'espn:123')[0]['espn_predicted_points'] == 16


def test_report_insights_follow_scope_week_position_and_ignore_pagination(monkeypatch):
    for ident in ['a','b','c']: save(monkeypatch,player_id=ident)
    save(monkeypatch,player_id='other-week',week=11)
    save(monkeypatch,player_id='other-league',scope='espn:456')
    store=history.prediction_history
    with store.connect() as db:
        db.execute('UPDATE predictions SET actual_points=14,floor_points=5,ceiling_points=15')
    response=TestClient(app).get('/api/accuracy/2026?league_id=123&week=10&position=QB&limit=1&offset=1')
    assert response.status_code == 200, response.text
    result=response.json()
    assert len(result['records']) == 1
    assert result['error_distribution']['count'] == result['range_coverage']['count'] == result['espn_comparison']['count'] == 3
    assert result['records'][0]['range_result'] == 'inside'
    assert result['records'][0]['espn_error'] == -1
    assert TestClient(app).get('/api/accuracy/2026?league_id=123&position=WR').json()['espn_comparison']['count'] == 0


def test_migration_keeps_existing_scores_ranges_and_nulls_for_missing_old_forecasts(monkeypatch):
    save(monkeypatch,espn=None)
    with history.prediction_history.connect() as db:
        db.execute('UPDATE predictions SET actual_points=14,floor_points=5,ceiling_points=15')
        for column in ['espn_predicted_points','espn_scoring','espn_recorded_at']:
            db.execute(f'ALTER TABLE predictions DROP COLUMN {column}')
    saved=history.prediction_history.rows(2026,'espn:123')[0]
    assert saved['actual_points']==14 and saved['floor_points']==5 and saved['ceiling_points']==15
    assert saved['espn_predicted_points'] is None and saved['espn_recorded_at'] is None
