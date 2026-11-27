from datetime import datetime, timezone
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from main import app
from app.routes import public
from app.services.prediction_history import prediction_history
from app.services.account_store import accounts
from app.config.security import account_path


@pytest.fixture
def visitor(monkeypatch):
    monkeypatch.setenv('FANTASY_AUTH_ENABLED', 'true')
    monkeypatch.setenv('FANTASY_PUBLIC_URL', 'https://ffa.stefanb.me')
    monkeypatch.setattr(public, 'utc_now', lambda: datetime(2026, 11, 26, tzinfo=timezone.utc))
    public.summary_cache.clear()
    return TestClient(app, base_url='https://ffa.stefanb.me')


def record(id, *, scope='weekly', predicted=10, actual=None, method='model', week=12, season=2026):
    with prediction_history.connect() as db:
        db.execute("""INSERT INTO predictions(scope,season,week,player_id,player_name,position,team,opponent_team,
            predicted_points,actual_points,projection_method,model_version,model_revision,generated_at,recorded_at,
            kickoff,actual_updated_at) VALUES(?,?,?,?,?,'QB','BUF','MIA',?,?,?,'v1','hash','x','x','x',?)""",
            (scope, season, week, id, 'Private name must never appear', predicted, actual, method,
             '2026-11-25T15:00:00+00:00' if actual is not None else None))


def test_public_summary_is_anonymous_readonly_and_never_loads_models(visitor, monkeypatch):
    from app.services.projection_registry import projection_services
    load = Mock(side_effect=AssertionError('Public summary must never run inference'))
    monkeypatch.setattr(projection_services, 'get', load)
    assert not prediction_history.path.exists()
    assert not account_path().exists()
    response = visitor.get('/api/public/performance')
    assert response.status_code == 200
    assert response.json()['state'] == 'collecting'
    assert response.json()['season'] == 2026
    assert response.json()['compared'] == 0
    assert response.json()['mae'] is None
    assert response.json()['within_five_pct'] is None
    assert not prediction_history.path.exists()
    assert not account_path().exists()
    load.assert_not_called()


def test_public_metrics_only_include_nfl_wide_results_and_show_sample_size(visitor):
    record('first', predicted=10, actual=14, week=11)
    record('second', predicted=20, actual=10, week=12, method='recent_average')
    record('pending', predicted=15)
    record('private', scope='espn:123', predicted=99999, actual=0)
    record('old', season=2025, predicted=1000, actual=0)
    response = visitor.get('/api/public/performance?league_id=123')
    assert response.status_code == 200
    data = response.json()
    assert (data['saved'], data['compared'], data['pending']) == (3, 2, 1)
    assert data['mae'] == 7
    assert data['within_five_pct'] == 50
    assert (data['model_compared'], data['fallback_compared']) == (1, 1)
    assert (data['latest_week'], data['latest_week_compared'], data['latest_week_mae']) == (12, 1, 10)
    assert data['last_result_update'] == '2026-11-25T15:00:00+00:00'
    assert 'Private name' not in response.text
    assert 'espn:123' not in response.text
    assert 'records' not in data and 'player_id' not in data


def test_private_only_history_cannot_be_inferred_from_public_counts(visitor):
    record('private', scope='espn:123', predicted=20, actual=20)
    response = visitor.get('/api/public/performance')
    assert response.json()['saved'] == 0
    assert response.json()['compared'] == 0
    assert response.json()['state'] == 'collecting'


def test_public_summary_caches_reads_and_does_not_change_saved_records(visitor, monkeypatch):
    record('first', predicted=10, actual=10)
    reader = Mock(wraps=public.read_public_performance)
    monkeypatch.setattr(public, 'read_public_performance', reader)
    with prediction_history.connect() as db:
        previous = [tuple(row) for row in db.execute('SELECT * FROM predictions')]
    assert visitor.get('/api/public/performance').status_code == 200
    assert visitor.get('/api/public/performance').status_code == 200
    reader.assert_called_once_with(2026)
    with prediction_history.connect() as db:
        assert [tuple(row) for row in db.execute('SELECT * FROM predictions')] == previous


def test_unavailable_history_is_an_error_not_a_fabricated_zero(visitor, monkeypatch):
    prediction_history.path.parent.mkdir(parents=True, exist_ok=True)
    prediction_history.path.write_text('not a database')
    response = visitor.get('/api/public/performance')
    assert response.status_code == 503
    assert 'temporarily unavailable' in response.json()['detail']
    assert str(prediction_history.path) not in response.text


def test_public_preview_does_not_enable_registration_or_private_apis(visitor):
    for path in ('/api/account/connections', '/api/accuracy/2026', '/api/espn/local/connect',
                 '/api/auth/signup', '/api/public/private', '/api/public/performance/private'):
        method = visitor.post if path in {'/api/espn/local/connect', '/api/auth/signup'} else visitor.get
        assert method(path).status_code == 401
    assert accounts.owner() is None
