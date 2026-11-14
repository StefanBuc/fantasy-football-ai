"""Live ESPN fantasy totals and NFL game states, independent of model inference."""

from hashlib import sha256
import json
from math import isfinite
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import requests
from espn_api.football.constant import PRO_TEAM_MAP

from app.services.prediction_history import prediction_history, normalize_team, utc_now
from app.services.result_cache import ResultCache

game_cache = ResultCache(ttl_seconds=20, max_entries=8, name="live_games")
score_cache = ResultCache(ttl_seconds=20, max_entries=16, name="live_scores")
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
LIVE_NOTE = "Live/final points use ESPN league scoring. AI predictions and ranges use full PPR and app K/DST scoring."


class LiveLeagueClient:
    """The verified player-card query, with bounded I/O and no full league load."""
    finalScoringPeriod = 18

    def __init__(self, league_id, season, espn_s2=None, swid=None):
        self.endpoint = ("https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
                         f"/seasons/{season}/segments/0/leagues/{league_id}")
        self.season = season
        self.cookies = {"espn_s2": espn_s2, "SWID": swid} if espn_s2 and swid else {}
        self.espn_request = self

    def get_player_card(self, ids, max_period):
        filters = {"players": {"filterIds": {"value": ids},
            "filterStatsForTopScoringPeriodIds": {"value": max_period,
                "additionalValue": [f"00{self.season}", f"10{self.season}"]}}}
        response = requests.get(self.endpoint, params={"view": "kona_playercard"},
            headers={"x-fantasy-filter": json.dumps(filters)}, cookies=self.cookies, timeout=(3, 8))
        response.raise_for_status()
        payload = response.json()
        return payload[0] if isinstance(payload, list) and payload else payload


def parse_games(payload, season, week):
    if (payload.get("season", {}).get("year") != season or payload.get("season", {}).get("type") != 2
            or payload.get("week", {}).get("number") != week):
        raise ValueError("ESPN returned a different season/week")
    games = {}
    for event in payload.get("events", []):
        status = event.get("status", {})
        kind = status.get("type", {})
        name = str(kind.get("name", ""))
        if any(word in name for word in ("POSTPONED", "CANCELED", "SUSPENDED")):
            state = "postponed"
        elif kind.get("completed") is True:
            state = "final"
        else:
            state = {"pre": "pregame", "in": "live"}.get(kind.get("state"), "unknown")
        for competitor in event.get("competitions", [{}])[0].get("competitors", []):
            team = normalize_team(competitor.get("team", {}).get("abbreviation"))
            games[team] = {"game_state": state, "kickoff_at": event.get("date"),
                           "game_detail": kind.get("shortDetail") or kind.get("detail")}
    for team in payload.get("week", {}).get("teamsOnBye", []):
        games[normalize_team(team.get("abbreviation"))] = {"game_state": "bye", "kickoff_at": None,
                                                          "game_detail": "Bye week"}
    return games


def fetch_games(season, week):
    response = requests.get(SCOREBOARD_URL,
        params={"dates": season, "week": week, "seasontype": 2, "limit": 1000}, timeout=(3, 8))
    response.raise_for_status()
    return parse_games(response.json(), season, week)


def parse_fantasy_players(payload, season, week):
    players = {}
    for row in payload.get("players", []):
        player = row.get("playerPoolEntry", {}).get("player", row.get("player", row))
        player_id = player.get("id", row.get("id"))
        if not isinstance(player_id, int):
            continue
        actual = [entry for entry in player.get("stats", [])
                  if entry.get("seasonId") == season and entry.get("scoringPeriodId") == week
                  and entry.get("statSourceId") == 0 and entry.get("statSplitTypeId") != 2]
        points = None
        team_id = player.get("proTeamId")
        if len(actual) == 1:
            team_id = actual[0].get("proTeamId") or team_id
            try:
                value = float(actual[0]["appliedTotal"])
                if isfinite(value):
                    points = value
            except (KeyError, ValueError, TypeError):
                pass
        team = normalize_team(PRO_TEAM_MAP.get(team_id))
        players[player_id] = {"points": points, "team": "" if team in {"NONE", "FA", "0"} else team}
    return players


def fetch_fantasy_scores(league, season, week, ids):
    if not ids:
        return {}
    batches = [list(ids[start:start + 200]) for start in range(0, len(ids), 200)]
    def fetch(batch):
        payload = league.espn_request.get_player_card(batch, max(week, int(league.finalScoringPeriod)))
        return parse_fantasy_players(payload, season, week)
    with ThreadPoolExecutor(max_workers=min(3, len(batches))) as executor:
        players = {}
        for result in executor.map(fetch, batches):
            players.update(result)
        return players


def live_response(league, season, week, descriptors, scope, credentials=None):
    ids = tuple(sorted({player.espn_id for player in descriptors}))
    credential_hash = sha256(repr(credentials).encode()).hexdigest()
    identity = (scope, season, week, credential_hash, ids)

    def build():
        games, fantasy = {}, {}
        notes = [LIVE_NOTE]
        try:
            games = game_cache.get_or_create((season, week), lambda: fetch_games(season, week))
        except Exception:
            notes.append("NFL game status is unavailable; live/final labels cannot be confirmed.")
        active_ids = tuple(sorted({player.espn_id for player in descriptors
            if games.get(normalize_team(player.team), {}).get("game_state") in {"live", "final"}}))
        if active_ids:
            try:
                source = league() if callable(league) else league
                fantasy = fetch_fantasy_scores(source, season, week, active_ids)
            except Exception:
                notes.append("Live fantasy scores are unavailable. No missing score is treated as zero.")
        return {"games": games, "fantasy": fantasy, "checked_at": utc_now(), "note": " ".join(notes)}

    data = score_cache.get_or_create(identity, build)
    # Read frozen predictions on every response, even when live data is cached.
    try:
        frozen_rows = prediction_history.week_records(season, week, scope)
    except (OSError, sqlite3.Error):
        frozen_rows = {}
    results = []
    for descriptor in descriptors:
        fantasy = data["fantasy"].get(descriptor.espn_id, {})
        team = fantasy.get("team") or normalize_team(descriptor.team)
        game = data["games"].get(team, {"game_state": "unknown", "kickoff_at": None, "game_detail": None})
        position = descriptor.position.replace("D/ST", "DST")
        player_id = normalize_team(descriptor.player_id) if position == "DST" else str(descriptor.player_id)
        frozen = frozen_rows.get((position, player_id))
        if frozen and frozen["team"] != team:
            frozen = None
        results.append({"espn_id": descriptor.espn_id, **game,
            "kickoff_at": game.get("kickoff_at") or (frozen["kickoff"] if frozen else None),
            "live_points": fantasy.get("points") if game["game_state"] in {"live", "final"} else None,
            "prediction_saved": frozen is not None,
            "pregame_predicted_points": frozen["predicted_points"] if frozen else None,
            "floor_points": frozen.get("floor_points") if frozen else None,
            "ceiling_points": frozen.get("ceiling_points") if frozen else None,
            "range_note": frozen.get("range_note") if frozen else None,
            "range_revision": frozen.get("range_revision") if frozen else None,
        })
    return {"season": season, "week": week, "checked_at": data["checked_at"],
            "note": data["note"], "players": results}
