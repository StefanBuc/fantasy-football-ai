from types import SimpleNamespace

import pandas as pd

from app.services.matchup_probability import estimate_win_chance


def player(player_id, points, **overrides):
    return SimpleNamespace(**{
        "player_id": player_id, "predicted_points": points,
        "position": "RB", "lineup_slot": "RB", "is_on_bye": False,
        "availability": "healthy", "status": "projected", **overrides,
    })


def team(*players):
    return SimpleNamespace(players=list(players), season=2024, week=17)


def test_equal_lineups_have_equal_chances_and_bench_is_ignored():
    home = team(player("a", 20), player("bench", 100, lineup_slot="BE"))
    away = team(player("b", 20), player("ir", None, lineup_slot="IR", status="skipped"))
    result = estimate_win_chance(home, away, pd.DataFrame())
    assert result["home_win_pct"] == result["away_win_pct"] == 50


def test_stronger_projection_is_favored_and_swapping_teams_reverses_chances():
    home, away = team(player("a", 30)), team(player("b", 20))
    result = estimate_win_chance(home, away, pd.DataFrame())
    reverse = estimate_win_chance(away, home, pd.DataFrame())
    assert 50 < result["home_win_pct"] < 100
    assert result["home_win_pct"] + result["away_win_pct"] == 100
    assert reverse["home_win_pct"] == result["away_win_pct"]


def test_missing_starter_projection_or_empty_lineup_has_no_percentage():
    for home in (team(), team(player("a", None, status="skipped"))):
        result = estimate_win_chance(home, team(player("b", 20)), pd.DataFrame())
        assert result["home_win_pct"] is None and result["away_win_pct"] is None


def test_unavailable_and_bye_players_are_zero_without_uncertainty():
    home = team(player("a", 100, availability="unavailable"))
    away = team(player("b", None, status="skipped", is_on_bye=True))
    result = estimate_win_chance(home, away, pd.DataFrame())
    assert result["home_win_pct"] == 50


def test_more_variable_history_produces_less_extreme_chances():
    home, away = team(player("a", 30)), team(player("b", 20))
    quiet = pd.DataFrame([
        {"player_id": identifier, "season": 2024, "week": week, "fantasy_points_ppr": 10.0}
        for identifier in ("a", "b") for week in range(1, 17)
    ])
    noisy = quiet.copy()
    noisy["fantasy_points_ppr"] = [0, 100] * 16
    stable_result = estimate_win_chance(home, away, quiet)
    noisy_result = estimate_win_chance(home, away, noisy)
    assert 50 < noisy_result["home_win_pct"] < stable_result["home_win_pct"]


def test_current_and_future_games_cannot_change_pregame_estimate():
    home, away = team(player("a", 30)), team(player("b", 20))
    prior = pd.DataFrame([
        {"player_id": "a", "season": 2024, "week": week, "fantasy_points_ppr": float(week)}
        for week in range(1, 17)
    ])
    future = pd.DataFrame([
        {"player_id": "a", "season": 2024, "week": week, "fantasy_points_ppr": 10000.0}
        for week in (17, 18)
    ])
    assert estimate_win_chance(home, away, prior) == estimate_win_chance(
        home, away, pd.concat([prior, future]),
    )
