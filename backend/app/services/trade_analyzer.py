"""Evaluate hypothetical roster exchanges without changing ESPN or saved predictions."""

from datetime import datetime, timezone
from math import isfinite
from statistics import mean
from typing import Callable

from app.schemas.espn import OptimizerPlayer
from app.schemas.trade import LocalTradeRequest, TradeAnalysis
from app.services.lineup_optimizer import (
    BENCH_SLOTS, DEFAULT_ELIGIBILITY, is_starter, normalize_slot, optimize_lineup, points, started,
)


def week_points(player, now):
    if player.is_on_bye or player.availability == "unavailable":
        return 0.0
    if started(player, now):
        value = player.pregame_predicted_points if player.prediction_saved else None
        return value if value is not None and isfinite(value) else None
    return points(player) if player.status == "projected" else None


def assess(roster, slots, now):
    result = optimize_lineup(roster, slots, now)
    # A missing bench projection can hide the best starter. Do not report a
    # confidently complete comparison just because that player was excluded.
    incomplete = any(
        normalize_slot(p.current_slot or "") not in {"IR", "ER"}
        and not p.is_on_bye and p.availability != "unavailable"
        and (is_starter(p) or not started(p, now))
        and week_points(p, now) is None for p in roster
    )
    value = None if incomplete else result["optimized_points"]
    return {**result, "value": value}


def average(values):
    values = list(values)
    return mean(values) if values and all(value is not None for value in values) else None


def difference(after, before):
    return after - before if after is not None and before is not None else None


def slot_points(result, slot):
    if result["value"] is None:
        return None
    return sum(points(entry.player) if entry.player else 0
               for entry in result["lineup"] if entry.slot == slot)


def backups(result, slot, now):
    return sum(
        not p.is_on_bye and p.availability != "unavailable" and not started(p, now)
        and p.status == "projected" and points(p) is not None
        and slot in ({normalize_slot(s) for s in p.eligible_slots} if p.eligible_slots
                     else DEFAULT_ELIGIBILITY.get(p.position, set()))
        for p in result["bench"]
    )


def analyze_trade(*, season: int, request: LocalTradeRequest, team_names: dict[int, str],
                  slot_counts: dict[str, int],
                  load_week: Callable[[int], dict[int, list[OptimizerPlayer]]], now=None) -> TradeAnalysis:
    now = now or datetime.now(timezone.utc)
    a, b = request.team_a_id, request.team_b_id
    if a not in team_names or b not in team_names:
        raise ValueError("One of the selected teams is no longer in this league.")
    sent = {a: set(request.team_a_player_ids), b: set(request.team_b_player_ids)}
    weeks = list(range(request.week, request.end_week + 1))
    first = load_week(request.week)
    for team_id in (a, b):
        owned = {p.espn_id: p for p in first.get(team_id, [])}
        if not sent[team_id].issubset(owned):
            raise ValueError("A selected player is no longer on the sending team. Reload rosters and select the trade again.")
        if any(started(owned[id], now) and not owned[id].is_on_bye for id in sent[team_id]):
            raise ValueError("A traded player's game has started or their kickoff is unknown. Choose a later effective week.")

    profiles = {request.week: first, **{week: load_week(week) for week in weeks[1:]}}

    before, after = {}, {}
    for week in weeks:
        rosters = profiles[week]
        if set(team_names) - set(rosters):
            raise ValueError(f"League roster projections are incomplete for Week {week}.")
        before[week] = {id: assess(rosters.get(id, []), slot_counts, now) for id in team_names}
        after[week] = dict(before[week])
        for receiving, giving in ((a, b), (b, a)):
            kept = [p for p in rosters.get(receiving, []) if p.espn_id not in sent[receiving]]
            incoming = [p.model_copy(update={"current_slot": "IR" if normalize_slot(p.current_slot or "") in {"IR", "ER"} else "BE"})
                        for p in rosters.get(giving, []) if p.espn_id in sent[giving]]
            after[week][receiving] = assess(kept + incoming, slot_counts, now)

    means_before = {id: average(before[w][id]["value"] for w in weeks) for id in team_names}
    means_after = {id: average(after[w][id]["value"] for w in weeks) for id in team_names}

    def ranks(values):
        if any(v is None for v in values.values()):
            return {id: None for id in values}
        # Competition ranking gives tied teams the same rank.
        return {id: 1 + sum(round(v, 6) > round(value, 6) for v in values.values())
                for id, value in values.items()}

    ranks_before, ranks_after = ranks(means_before), ranks(means_after)
    starting_slots = [normalize_slot(s) for s, count in slot_counts.items()
                      if count > 0 and normalize_slot(s) not in BENCH_SLOTS]
    impacts = []
    for id in (a, b):
        positions = [{
            "slot": slot,
            "before_points": average(slot_points(before[w][id], slot) for w in weeks),
            "after_points": average(slot_points(after[w][id], slot) for w in weeks),
            "league_average": average(slot_points(before[w][other], slot) for w in weeks for other in team_names),
            "backups_before": backups(before[request.week][id], slot, now),
            "backups_after": backups(after[request.week][id], slot, now),
        } for slot in starting_slots]
        explanations = []
        needs = [p for p in positions if p["before_points"] is not None and p["league_average"] is not None]
        if needs:
            need = min(needs, key=lambda p: p["before_points"] - p["league_average"])
            gap = need["before_points"] - need["league_average"]
            if gap < -0.5:
                explanations.append(f"Biggest starting-slot need: {need['slot']} averages {abs(gap):.1f} points per week below the league average before the trade.")
        for position in positions:
            delta = difference(position["after_points"], position["before_points"])
            if delta is not None and abs(delta) >= 0.1:
                explanations.append(f"{position['slot']} starters {'gain' if delta > 0 else 'lose'} {abs(delta):.1f} projected points per week on average.")
            if position["backups_after"] < position["backups_before"]:
                explanations.append(f"{position['slot']} eligible backups this week: {position['backups_before']} before, {position['backups_after']} after.")
        first_before, first_after = before[request.week][id], after[request.week][id]
        for entry in first_after["lineup"]:
            if entry.player and entry.player.espn_id in sent[b if id == a else a]:
                explanations.append(f"Incoming {entry.player.player_name} enters the optimized lineup at {entry.slot} this week.")
        empty = sum(entry.player is None for entry in first_after["lineup"])
        if empty:
            explanations.append(f"The post-trade lineup has {empty} unfilled slot(s) this week; no free-agent replacements are assumed.")
        if means_before[id] is None or means_after[id] is None:
            explanations.append("Missing projections or kickoff information make the full remaining-season comparison incomplete.")
        rest_before = means_before[id] * len(weeks) if means_before[id] is not None else None
        rest_after = means_after[id] * len(weeks) if means_after[id] is not None else None
        impacts.append({
            "team_id": id, "team_name": team_names[id], "weekly_before": first_before["value"],
            "weekly_after": first_after["value"], "weekly_change": difference(first_after["value"], first_before["value"]),
            "rest_before": rest_before, "rest_after": rest_after, "rest_change": difference(rest_after, rest_before),
            "weeks_covered": sum(before[w][id]["value"] is not None and after[w][id]["value"] is not None for w in weeks),
            "power_rank_before": ranks_before[id], "power_rank_after": ranks_after[id],
            "lineup_before": first_before["lineup"], "lineup_after": first_after["lineup"],
            "positions": positions, "explanations": explanations,
            "weeks": [{"week": w, "before_points": before[w][id]["value"], "after_points": after[w][id]["value"],
                       "change": difference(after[w][id]["value"], before[w][id]["value"])} for w in weeks],
        })

    values = []
    for id in (a, b):
        for player in first[id]:
            if player.espn_id not in sent[id]:
                continue
            weekly = [next((p for p in profiles[w].get(id, []) if p.espn_id == player.espn_id), None) for w in weeks]
            scores = [week_points(p, now) if p else None for p in weekly]
            values.append({**player.model_dump(), "from_team_id": id, "weekly_points": scores[0],
                "rest_of_season_points": sum(scores) if all(v is not None for v in scores) else None,
                "projected_games": sum(p is not None and not p.is_on_bye and score is not None for p, score in zip(weekly, scores)),
                "missing_weeks": sum(v is None for v in scores)})

    deltas = [impact["rest_change"] for impact in impacts]
    favors = None
    if any(delta is None for delta in deltas):
        verdict = "Not enough projection coverage for a verdict"
        summary = "Review the available weeks below. Missing values are not treated as zero."
    elif abs(deltas[0] - deltas[1]) <= 0.5 * len(weeks):
        verdict = "Fairly even on projected starter value"
        summary = "The teams' projected improvements differ by no more than 0.5 points per week. Position fit and depth may still matter."
    else:
        favors = a if deltas[0] > deltas[1] else b
        verdict = f"Favors {team_names[favors]} on projected starter value"
        summary = (f"{team_names[a]}: {deltas[0]:+.1f} starting-lineup points; "
                   f"{team_names[b]}: {deltas[1]:+.1f} across Weeks {request.week}–{request.end_week}. "
                   + ("Both teams improve. " if all(delta > 0 for delta in deltas) else "")
                   + "This compares optimized lineups, including the players each roster can already start.")
    return TradeAnalysis(season=season, week=request.week, end_week=request.end_week, generated_at=now,
        verdict=verdict, favors_team_id=favors, summary=summary, teams=impacts, players=values,
        power_rankings=sorted([{"team_id": id, "team_name": team_names[id],
            "before_points": means_before[id], "after_points": means_after[id],
            "rank_before": ranks_before[id], "rank_after": ranks_after[id]} for id in team_names],
            key=lambda row: (row["after_points"] is None, -(row["after_points"] or 0), row["team_name"])),
        notes=[
            "Uses the existing full-PPR AI projections and app K/DST scoring; custom ESPN scoring may differ.",
            "Rest-of-season totals include the selected effective week through the last week shown. Byes and NFL opponents are accounted for week by week.",
            "Future forecasts reuse currently available histories and current injury/IR statuses. They do not predict recoveries, future roles, injuries, or future game results; long-range estimates are less certain.",
            "Power rank uses average optimized starting-lineup points over the selected weeks, not standings or playoff odds. All teams are re-ranked after the exchange; ranks are unavailable when any team's full horizon is incomplete.",
            "Players who have kicked off stay locked. Select a later effective week if a traded player has already played. Missing projections are shown as unavailable, not zero.",
            "No free agents, drops, roster-space limits, trade processing delays, or waiver moves are assumed. Managers choose any needed drops. IR players still require activation.",
            "These are hypothetical recommendations. No ESPN roster changes or hypothetical prediction-history records are submitted.",
        ])
