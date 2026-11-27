from datetime import timedelta

from fastapi.testclient import TestClient
import pytest

from main import app
from app.services.prediction_history import prediction_history, PredictionHistory
from app.services.roster_tracking import roster_category
from app.services.espn_benchmark import ESPN_SCORING
from test_prediction_history import record, sample, schedule, PREGAME, KICKOFF


@pytest.mark.parametrize("slot,expected", [
    ("QB", "starter"), ("RB/WR/TE", "starter"), ("SUPERFLEX", "starter"),
    ("D/ST", "starter"), ("K", "starter"), ("BE", "bench"), ("IR", "bench"),
    ("ER", "bench"), ("Rookie", "bench"), (None, None), ("", None), ("unrecognized", None),
])
def test_roles_only_classify_known_slots(slot, expected):
    assert roster_category(slot) == expected
    assert roster_category(slot, free_agent=True) == "free_agent"


def test_new_roster_observation_updates_older_cached_ai_then_freezes_and_reloads(monkeypatch):
    record(monkeypatch, samples=[sample(roster_category="bench")])
    record(monkeypatch, now=PREGAME + timedelta(minutes=10),
           samples=[sample(predicted_points=25, roster_category="starter")])
    record(monkeypatch, now=PREGAME + timedelta(minutes=20), generated_at=PREGAME,
           samples=[sample(predicted_points=10, roster_category="free_agent")])
    saved = prediction_history.rows(2026, "espn:123")[0]
    assert saved["predicted_points"] == 25
    assert saved["generated_at"] == (PREGAME + timedelta(minutes=10)).isoformat()
    assert saved["roster_category"] == "free_agent"
    assert saved["roster_recorded_at"] == (PREGAME + timedelta(minutes=20)).isoformat()
    record(monkeypatch, now=KICKOFF, generated_at=PREGAME,
           samples=[sample(roster_category="starter"), sample(player_id="late", roster_category="bench")])
    reloaded = PredictionHistory(prediction_history.path).rows(2026, "espn:123")
    assert reloaded == [saved]


def test_missing_role_does_not_erase_observation_and_old_clock_does_not_rewind_it(monkeypatch):
    record(monkeypatch, samples=[sample(roster_category="starter")])
    record(monkeypatch, now=PREGAME + timedelta(minutes=10), samples=[sample(roster_category="bench")])
    record(monkeypatch, now=PREGAME + timedelta(minutes=5), samples=[sample(roster_category="starter")])
    record(monkeypatch, now=PREGAME + timedelta(minutes=20), samples=[sample()])
    saved = prediction_history.rows(2026, "espn:123")[0]
    assert saved["roster_category"] == "bench"
    assert saved["roster_recorded_at"] == (PREGAME + timedelta(minutes=10)).isoformat()


def test_role_is_league_specific_and_changed_game_does_not_inherit_old_observation(monkeypatch):
    record(monkeypatch, samples=[sample(roster_category="starter")])
    record(monkeypatch, scope="weekly", samples=[sample(roster_category="starter")])
    record(monkeypatch, scope="espn:456", samples=[sample(roster_category="free_agent")])
    record(monkeypatch, now=PREGAME + timedelta(minutes=10), games=schedule(gameday="2026-11-09"))
    assert prediction_history.rows(2026, "espn:123")[0]["roster_category"] is None
    assert prediction_history.rows(2026, "weekly")[0]["roster_category"] is None
    assert prediction_history.rows(2026, "espn:456")[0]["roster_category"] == "free_agent"


def test_migration_preserves_forecasts_and_results_without_inventing_past_roles(monkeypatch):
    record(monkeypatch, samples=[sample(roster_category="starter")])
    with prediction_history.connect() as db:
        db.execute("UPDATE predictions SET actual_points=14,floor_points=5,ceiling_points=15")
        for column in ("roster_category", "roster_recorded_at"):
            db.execute(f"ALTER TABLE predictions DROP COLUMN {column}")
        before = dict(db.execute("SELECT * FROM predictions").fetchone())
    after = PredictionHistory(prediction_history.path).rows(2026, "espn:123")[0]
    assert {key: after[key] for key in before} == before
    assert after["roster_category"] is after["roster_recorded_at"] is None


def test_roster_filter_applies_to_every_metric_before_pagination_and_preserves_unknowns(monkeypatch):
    samples = [sample(player_id=key, roster_category=category,
                      espn_predicted_points=espn, espn_scoring=ESPN_SCORING)
               for key, category, espn in [("s1", "starter", 19), ("s2", "starter", 12),
                                           ("b1", "bench", 20), ("f1", "free_agent", 0),
                                           ("u1", None, 20)]]
    record(monkeypatch, samples=samples)
    record(monkeypatch, samples=[sample(roster_category="starter")], week=11,
           games=schedule(week=11, gameday="2026-11-15"))
    record(monkeypatch, samples=[sample(roster_category="starter")], scope="espn:456")
    with prediction_history.connect() as db:
        for key, actual in [("s1", 19), ("s2", 11), ("b1", 20), ("f1", 0)]:
            db.execute("UPDATE predictions SET actual_points=?,floor_points=19,ceiling_points=21 WHERE player_id=?",
                       (actual, key))
    client = TestClient(app)
    response = client.get("/api/accuracy/2026?league_id=123&week=10&position=QB&roster_category=starter&limit=1&offset=1")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {"saved": 2, "scored": 2, "pending": 0, "mae": 5, "bias": 5}
    assert len(body["records"]) == 1 and body["records"][0]["roster_category"] == "starter"
    assert body["roster_coverage"] == {"total": 5, "recorded": 4, "unknown": 1}
    assert body["by_position"][0]["scored"] == body["by_model"][0]["scored"] == 2
    assert [row["week"] for row in body["weekly_trend"]] == [10, 11]
    assert body["range_coverage"]["count"] == 2 and body["range_coverage"]["coverage_pct"] == 50
    assert body["error_distribution"]["within_five_pct"] == 50
    assert body["espn_comparison"]["count"] == 2 and body["espn_comparison"]["ai_mae"] == 5
    assert body["espn_comparison"]["espn_mae"] == .5
    for category, key in [("bench", "b1"), ("free_agent", "f1"), ("unknown", "u1")]:
        filtered = client.get(f"/api/accuracy/2026?league_id=123&roster_category={category}").json()
        assert filtered["summary"]["saved"] == 1
        assert filtered["records"][0]["player_id"] == key
    assert client.get("/api/accuracy/2026?league_id=123").json()["summary"]["saved"] == 6
    assert client.get("/api/accuracy/2026?roster_category=rostered").status_code == 422
