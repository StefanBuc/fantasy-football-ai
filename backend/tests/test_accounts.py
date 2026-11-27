from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from main import app
from app.config.security import cookie_name, public_origin
from app.services.account_store import accounts
from app.routes import account, espn
from app.services.accuracy_jobs import accuracy_jobs

ORIGIN = 'https://ffa.stefanb.me'
PASSWORD = 'An owner password for test only!'
TAILSCALE = 'http://100.94.147.92:8090'


def test_owner_password_minimum_is_eight_for_creation_and_reset():
    with pytest.raises(ValueError, match='8–256'):
        accounts.set_owner('owner', '1234567')
    assert accounts.owner() is None
    accounts.set_owner('owner', '12345678')
    assert accounts.attempt_login('owner', '12345678')[0] == 'ok'
    with pytest.raises(ValueError, match='8–256'):
        accounts.set_owner('owner', '1234567', reset=True)
    assert accounts.attempt_login('owner', '12345678')[0] == 'ok'
    accounts.set_owner('owner', 'newpass8', reset=True)
    assert accounts.attempt_login('owner', 'newpass8')[0] == 'ok'


@pytest.fixture
def secured(monkeypatch):
    monkeypatch.setenv('FANTASY_AUTH_ENABLED', 'true')
    monkeypatch.setenv('FANTASY_PUBLIC_URL', ORIGIN)
    monkeypatch.setenv('FANTASY_INSECURE_LOCAL_DEV', 'false')
    accounts.set_owner('owner', PASSWORD)
    client = TestClient(app, base_url=ORIGIN)
    return client


def login(client, remember=True):
    anonymous = client.get('/api/auth/session')
    assert anonymous.status_code == 200
    response = client.post('/api/auth/login', json={'username': 'owner', 'password': PASSWORD, 'remember': remember},
        headers={'Origin': ORIGIN, 'X-CSRF-Token': anonymous.json()['csrf_token']})
    assert response.status_code == 200, response.text
    client.headers.update({'Origin': ORIGIN, 'X-CSRF-Token': response.json()['csrf_token']})
    return response


@pytest.fixture
def fake_league(monkeypatch):
    league = SimpleNamespace(settings=SimpleNamespace(name='My private league'),
        teams=[SimpleNamespace(team_id=1, team_name='Team one', team_abbrev='ONE', logo_url=None,
                               standing=1, wins=0, losses=0, ties=0, points_for=0, points_against=0,
                               streak_type=None, streak_length=None, playoff_pct=None)], current_week=13)
    getter = Mock(return_value=league)
    monkeypatch.setattr(account, 'get_league', getter)
    monkeypatch.setattr(espn, 'get_league', getter)
    return league, getter


def save_private(client):
    response = client.post('/api/account/connections', json={'league_id': 123, 'season': 2026,
        'mode': 'private', 'swid': 'secret-swid-value', 'espn_s2': 'secret-s2-value'})
    assert response.status_code == 200, response.text
    return response.json()


def test_all_data_and_docs_require_auth_even_with_localhost_or_spoofed_headers(secured):
    for path, method in [('/api/accuracy/2026', 'get'), ('/openapi.json', 'get'), ('/docs', 'get'),
                         ('/api/espn/local/connect', 'post'), ('/api/espn/trade-rosters', 'post'),
                         ('/api/account/connections', 'get')]:
        response = getattr(secured, method)(path, headers={'X-Forwarded-For': '127.0.0.1', 'CF-Connecting-IP': '127.0.0.1'})
        assert response.status_code == 401, path
    assert secured.get('/api/health/').status_code == 200
    assert secured.get('/api/health/ready').status_code == 200
    assert secured.get('/api/auth/session').json()['authenticated'] is False


def test_session_cookie_is_secure_hashed_revocable_and_rotated_on_login(secured):
    secured.get('/api/auth/session')
    old_token = secured.cookies.get(cookie_name())
    response = login(secured)
    cookie = response.headers['set-cookie']
    assert all(value in cookie for value in ('__Host-fantasy_session=', 'HttpOnly', 'Secure', 'SameSite=strict', 'Path=/', 'Max-Age=2592000'))
    assert secured.cookies.get(cookie_name()) != old_token
    assert accounts.session(old_token) is None
    token = secured.cookies.get(cookie_name())
    with accounts.connect() as db:
        rows = db.execute('SELECT token_hash FROM sessions').fetchall()
        assert token not in str([tuple(row) for row in rows])
    assert secured.get('/api/auth/session').json()['authenticated'] is True
    assert secured.post('/api/auth/logout').status_code == 200
    assert accounts.session(token) is None
    assert secured.get('/api/account/connections').status_code == 401


def test_browser_session_cookie_has_no_persistent_max_age(secured):
    response = login(secured, remember=False)
    assert 'Max-Age=' not in response.headers['set-cookie']


def test_login_and_authenticated_writes_require_both_origin_and_bound_csrf(secured):
    status = secured.get('/api/auth/session').json()
    body = {'username': 'owner', 'password': PASSWORD}
    for headers in ({}, {'Origin': ORIGIN}, {'Origin': 'https://evil.example', 'X-CSRF-Token': status['csrf_token']},
                    {'Origin': ORIGIN, 'X-CSRF-Token': 'wrong'}):
        assert secured.post('/api/auth/login', json=body, headers=headers).status_code == 403
    login(secured)
    assert secured.patch('/api/account/preferences', json={'theme': 'dark'}, headers={'X-CSRF-Token': 'wrong'}).status_code == 403
    assert secured.patch('/api/account/preferences', json={'theme': 'dark'}, headers={'Origin': 'https://evil.example'}).status_code == 403


def test_login_throttle_persists_between_clients_and_wrong_password_is_generic(secured):
    status = secured.get('/api/auth/session').json()
    headers = {'Origin': ORIGIN, 'X-CSRF-Token': status['csrf_token']}
    for _ in range(20):
        response = secured.post('/api/auth/login', json={'username': 'unknown', 'password': 'wrong'}, headers=headers)
        assert response.status_code == 401
        assert response.json()['detail'] == 'Incorrect username or password.'
    another = TestClient(app, base_url=ORIGIN)
    csrf = another.get('/api/auth/session').json()['csrf_token']
    response = another.post('/api/auth/login', json={'username': 'owner', 'password': PASSWORD},
        headers={'Origin': ORIGIN, 'X-CSRF-Token': csrf})
    assert response.status_code == 429
    assert response.headers['retry-after'] == '900'


def test_encrypted_league_saved_without_returning_cookies_and_preferences_survive_new_login(secured, fake_league, monkeypatch):
    login(secured)
    row = save_private(secured)
    assert 'secret-' not in str(row)
    assert 'credentials' not in row
    with accounts.connect() as db:
        ciphertext = db.execute('SELECT credentials FROM connections').fetchone()[0]
        owner_hash = db.execute('SELECT password_hash FROM owner').fetchone()[0]
    assert 'secret-' not in ciphertext
    assert owner_hash.startswith('$argon2id$')
    assert accounts.private_config(row['id']).espn_s2 == 'secret-s2-value'
    assert secured.patch(f"/api/account/connections/{row['id']}/preferences", json={
        'preferred_team_id': 1, 'default_view': 'optimized'}).status_code == 200
    assert secured.patch('/api/account/preferences', json={'theme': 'dark', 'active_connection': row['id']}).status_code == 200
    other = TestClient(app, base_url=ORIGIN)
    login(other)
    data = other.get('/api/account/connections').json()
    assert data['preferences']['theme'] == 'dark'
    assert data['preferences']['active_connection'] == row['id']
    assert data['connections'][0]['preferred_team_id'] == 1
    assert data['connections'][0]['default_view'] == 'optimized'
    assert 'secret-' not in str(data)
    assert 'password_hash' not in str(data)


def test_private_routes_require_explicit_saved_connection_and_never_fall_back_to_environment(secured, fake_league, monkeypatch):
    login(secured)
    row = save_private(secured)
    monkeypatch.setattr(espn, 'get_local_espn_config', Mock(side_effect=AssertionError('Do not use shared environment credentials')))
    assert secured.post('/api/espn/local/connect').status_code == 400
    response = secured.post('/api/espn/local/connect', headers={'X-League-Connection': row['id']})
    assert response.status_code == 200, response.text
    assert response.json()['league_id'] == 123
    assert accuracy_jobs.targets()[0]['mode'] == 'saved'
    # Image requests cannot attach custom JS headers; they may select the same
    # saved connection by non-secret ID, still requiring the login cookie.
    assert secured.post(f"/api/espn/local/connect?connection_id={row['id']}").status_code == 200


def test_expired_espn_connection_has_safe_error_and_can_be_updated(secured, fake_league, monkeypatch):
    login(secured)
    row = save_private(secured)
    monkeypatch.setattr(account, 'validated_league', Mock(side_effect=account.HTTPException(403, 'Update saved cookies.')))
    assert secured.post(f"/api/account/connections/{row['id']}/connect").status_code == 403
    assert accounts.connection(row['id'])['status'] == 'reauth_required'
    monkeypatch.setattr(account, 'validated_league', lambda *_: fake_league[0])
    response = secured.put(f"/api/account/connections/{row['id']}", json={
        'league_id': 123, 'season': 2026, 'mode': 'private', 'swid': 'new-secret', 'espn_s2': 'new-s2'})
    assert response.status_code == 200
    assert response.json()['status'] == 'connected'
    assert accounts.private_config(row['id']).espn_s2 == 'new-s2'


def test_delete_removes_credentials_and_capture_target_but_preserves_history(secured, fake_league):
    login(secured)
    row = save_private(secured)
    with accuracy_jobs.connect() as db:
        db.execute("INSERT INTO predictions(scope,season,week,player_id,position,team,opponent_team,predicted_points,projection_method,model_version,model_revision,generated_at,recorded_at,kickoff) VALUES('espn:123',2026,13,'p','QB','BUF','MIA',20,'model','v1','hash','x','x','x')")
    assert secured.delete(f"/api/account/connections/{row['id']}").status_code == 200
    assert accounts.connection(row['id']) is None
    assert accuracy_jobs.targets() == []
    with accuracy_jobs.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0] == 1


def test_missing_key_is_not_silently_replaced_and_cannot_expose_credentials(secured, fake_league, monkeypatch):
    from app.config.security import key_path
    login(secured)
    row = save_private(secured)
    # Simulate restoring the account DB without its separately backed-up key.
    monkeypatch.setenv('FANTASY_ENCRYPTION_KEY_PATH', str(key_path().parent / 'missing.key'))
    response = secured.post(f"/api/account/connections/{row['id']}/connect")
    assert response.status_code == 503
    assert 'secret-' not in response.text
    assert not key_path().exists()


def test_expiration_logout_all_and_password_reset_revoke_sessions(secured):
    login(secured)
    first_token = secured.cookies.get(cookie_name())
    other = TestClient(app, base_url=ORIGIN)
    login(other)
    assert other.post('/api/auth/logout?everywhere=true').status_code == 200
    assert accounts.session(first_token) is None
    login(secured)
    with accounts.connect() as db:
        db.execute('UPDATE sessions SET last_seen=0')
    assert secured.get('/api/account/connections').status_code == 401
    login(secured)
    accounts.set_owner('owner', 'A changed password for testing!', reset=True)
    assert secured.get('/api/account/connections').status_code == 401


def test_validation_never_echoes_secret_input_and_responses_are_not_cached(secured):
    login(secured)
    response = secured.post('/api/account/connections', json={'league_id': 1, 'season': 2026,
        'mode': 'private', 'swid': 'secret-' * 40, 'espn_s2': 'secret-s2'})
    assert response.status_code == 422
    assert 'secret-' not in response.text
    assert response.headers['cache-control'] == 'no-store, private'
    assert secured.get('/api/auth/session').headers['cache-control'] == 'no-store, private'


def test_https_required_and_owner_cannot_be_claimed_over_http(secured, monkeypatch):
    monkeypatch.setenv('FANTASY_PUBLIC_URL', 'http://public.example')
    with pytest.raises(RuntimeError, match='HTTPS'):
        public_origin()
    assert secured.get('/api/account/connections').status_code == 503
    assert secured.post('/api/auth/signup', json={}).status_code in {401, 503}


def test_background_capture_can_use_saved_private_credentials_without_a_browser(secured, fake_league, monkeypatch):
    from app.services.accuracy_scheduler import capture_league, current_local_config
    from app.integrations import espn_fantasy
    login(secured)
    save_private(secured)
    getter = Mock(return_value=fake_league[0])
    monkeypatch.setattr(espn_fantasy, 'get_league', getter)
    projector = Mock(return_value=(None, 7))
    monkeypatch.setattr(espn, 'project_league_players', projector)
    assert current_local_config() is None
    result = capture_league(SimpleNamespace(), {'scope': 'espn:123', 'season': 2026, 'mode': 'saved'}, 13, None, None)
    assert result['saved_count'] == 7
    getter.assert_called_once_with(league_id=123, year=2026, swid='secret-swid-value', espn_s2='secret-s2-value')
    assert projector.call_args.kwargs['strict_history'] is True


def test_password_reset_during_login_cannot_issue_a_session_for_the_old_password(secured, monkeypatch):
    attempt = accounts.attempt_login
    def reset_during_verification(username, password):
        result = attempt(username, password)
        accounts.set_owner('owner', 'The new password after a concurrent reset!', reset=True)
        return result
    monkeypatch.setattr(accounts, 'attempt_login', reset_during_verification)
    csrf = secured.get('/api/auth/session').json()['csrf_token']
    response = secured.post('/api/auth/login', json={'username': 'owner', 'password': PASSWORD},
        headers={'Origin': ORIGIN, 'X-CSRF-Token': csrf})
    assert response.status_code == 401
    assert secured.get('/api/account/connections').status_code == 401


def tailnet_login(client):
    anonymous = client.get('/api/auth/session')
    assert anonymous.status_code == 200
    assert anonymous.json()['login_origin'] == TAILSCALE
    response = client.post('/api/auth/login', json={'username': 'owner', 'password': PASSWORD, 'remember': True},
        headers={'Origin': TAILSCALE, 'X-CSRF-Token': anonymous.json()['csrf_token']})
    assert response.status_code == 200, response.text
    client.headers.update({'Origin': TAILSCALE, 'X-CSRF-Token': response.json()['csrf_token']})
    return response


def test_tailnet_http_login_and_public_https_login_share_account_preferences_but_not_cookies(secured, monkeypatch):
    monkeypatch.setenv('FANTASY_TAILSCALE_URL', TAILSCALE)
    private = TestClient(app, base_url=TAILSCALE)
    response = tailnet_login(private)
    cookie = response.headers['set-cookie']
    assert 'fantasy_session_tailnet=' in cookie
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie
    assert 'Secure' not in cookie
    assert private.patch('/api/account/preferences', json={'theme': 'dark', 'active_connection': None}).status_code == 200
    public_login = login(secured)
    assert '__Host-fantasy_session=' in public_login.headers['set-cookie']
    assert 'Secure' in public_login.headers['set-cookie']
    assert secured.get('/api/account/connections').json()['preferences']['theme'] == 'dark'
    assert private.post('/api/auth/logout').status_code == 200
    assert private.get('/api/account/connections').status_code == 401
    assert secured.get('/api/account/connections').status_code == 200


def test_tailnet_csrf_requires_its_exact_origin_not_just_any_allowed_site(secured, monkeypatch):
    monkeypatch.setenv('FANTASY_TAILSCALE_URL', TAILSCALE)
    private = TestClient(app, base_url=TAILSCALE)
    tailnet_login(private)
    assert private.patch('/api/account/preferences', json={'theme': 'dark'}, headers={'Origin': ORIGIN}).status_code == 403
    login(secured)
    assert secured.patch('/api/account/preferences', json={'theme': 'dark'}, headers={'Origin': TAILSCALE}).status_code == 403


def test_tokens_cannot_be_replayed_between_tailnet_and_public_cookie_names(secured, monkeypatch):
    monkeypatch.setenv('FANTASY_TAILSCALE_URL', TAILSCALE)
    private = TestClient(app, base_url=TAILSCALE)
    tailnet_login(private)
    tail_token = private.cookies.get('fantasy_session_tailnet')
    login(secured)
    public_token = secured.cookies.get('__Host-fantasy_session')
    assert secured.get('/api/account/connections', headers={'Cookie': '__Host-fantasy_session=' + tail_token}).status_code == 401
    assert private.get('/api/account/connections', headers={'Cookie': 'fantasy_session_tailnet=' + public_token}).status_code == 401


def test_other_http_addresses_do_not_gain_the_tailnet_cookie_exception(secured, monkeypatch):
    monkeypatch.setenv('FANTASY_TAILSCALE_URL', TAILSCALE)
    other = TestClient(app, base_url='http://100.94.147.93:8090')
    response = other.get('/api/auth/session')
    assert response.json()['login_origin'] == ORIGIN
    assert '__Host-fantasy_session=' in response.headers['set-cookie']
    assert 'Secure' in response.headers['set-cookie']
    assert other.get('/api/account/connections').status_code == 401
    monkeypatch.setenv('FANTASY_TAILSCALE_URL', 'http://192.168.1.5:8090')
    assert secured.get('/api/auth/session').status_code == 503


def test_pre_origin_binding_sessions_require_relogin_without_resetting_owner(secured):
    import sqlite3
    from app.config.security import account_path
    # Simulate the first deployed account schema, which had no origin column.
    with sqlite3.connect(account_path()) as db:
        db.execute('DROP TABLE sessions')
        db.execute('CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, authenticated INTEGER NOT NULL, expires REAL NOT NULL, last_seen REAL NOT NULL, idle_seconds INTEGER NOT NULL)')
    response = secured.get('/api/auth/session')
    assert response.status_code == 200
    assert response.json()['configured'] is True
    assert response.json()['authenticated'] is False
    login(secured)
    assert secured.get('/api/account/connections').status_code == 200


def local_login(client, origin):
    anonymous = client.get('/api/auth/session')
    assert anonymous.status_code == 200, anonymous.text
    assert anonymous.json()['login_origin'] == origin
    response = client.post('/api/auth/login', json={'username': 'owner', 'password': PASSWORD, 'remember': True},
        headers={'Origin': origin, 'X-CSRF-Token': anonymous.json()['csrf_token']})
    assert response.status_code == 200, response.text
    client.headers.update({'Origin': origin, 'X-CSRF-Token': response.json()['csrf_token']})
    return response


@pytest.mark.parametrize('origin', [
    'http://localhost:8090', 'http://127.0.0.1:8090', 'http://[::1]:8090',
    'http://localhost:5173', 'http://127.0.0.1:5173', 'http://[::1]:5173',
    'http://localhost:5174',
])
def test_localhost_login_works_with_production_security_flags(secured, origin):
    # This installed TestClient splits IPv6 URL ports incorrectly. Exercise the
    # actual IPv6 Host/Origin headers using its working IPv4 transport instead.
    client = TestClient(app, base_url=origin.replace('[::1]', '127.0.0.1'),
                        headers={'Host': origin.removeprefix('http://')})
    response = local_login(client, origin)
    cookie = response.headers['set-cookie']
    assert cookie_name(origin) + '=' in cookie
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie
    assert 'Secure' not in cookie
    assert client.get('/api/account/connections').status_code == 200
    assert client.patch('/api/account/preferences', json={'theme': 'dark'}).status_code == 200
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/account/connections').status_code == 401


def test_localhost_ports_have_distinct_sessions_and_cross_origin_reads_are_denied(secured):
    first = TestClient(app, base_url='http://localhost:8090')
    second = TestClient(app, base_url='http://localhost:5173')
    local_login(first, 'http://localhost:8090')
    token = first.cookies.get('fantasy_session_local_8090')
    local_login(second, 'http://localhost:5173')
    assert second.cookies.get('fantasy_session_local_5173')
    assert first.get('/api/account/connections', headers={'Origin': 'http://localhost:5173'}).status_code == 403
    assert second.get('/api/account/connections', headers={'Cookie': 'fantasy_session_local_5173=' + token}).status_code == 401
    assert first.get('/api/account/connections').status_code == 200
    login(secured)
    assert 'Secure' in secured.get('/api/auth/session').headers.get('set-cookie', 'Secure')
    assert secured.get('/api/account/connections', headers={'Origin': 'http://localhost:8090'}).status_code == 403


def test_localhost_uses_safe_default_configuration_and_similar_names_are_not_loopback(secured, monkeypatch):
    monkeypatch.delenv('FANTASY_PUBLIC_URL')
    client = TestClient(app, base_url='http://localhost:8090')
    local_login(client, 'http://localhost:8090')
    for origin in ('http://localhost.evil.example:8090', 'http://127.0.0.1.evil.example:8090', 'http://192.168.1.5:8090'):
        other = TestClient(app, base_url=origin)
        response = other.get('/api/auth/session')
        assert response.json()['login_origin'] == ORIGIN
        assert 'Secure' in response.headers['set-cookie']
        assert other.get('/api/account/connections').status_code == 401
