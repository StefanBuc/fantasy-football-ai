"""Maximum-projection legal slot assignment; recommendations never mutate ESPN."""

from datetime import datetime, timezone
from math import isfinite

import numpy as np
from scipy.optimize import linear_sum_assignment

from app.schemas.espn import OptimizerPlayer, OptimizedSlot, LineupChange

BENCH_SLOTS = {"BE", "IR", "ER", "Rookie", ""}
SLOT_ORDER = ("QB", "RB", "WR", "TE", "RB/WR", "WR/TE", "RB/WR/TE", "OP", "D/ST", "K")
DEFAULT_ELIGIBILITY = {
    "QB": {"QB", "OP"}, "RB": {"RB", "RB/WR", "RB/WR/TE", "OP"},
    "WR": {"WR", "RB/WR", "WR/TE", "RB/WR/TE", "OP"},
    "TE": {"TE", "WR/TE", "RB/WR/TE", "OP"}, "K": {"K"}, "D/ST": {"D/ST"},
}


def normalize_slot(slot):
    return {"FLEX": "RB/WR/TE", "SUPERFLEX": "OP", "DST": "D/ST"}.get(slot, slot)


def points(player):
    value = player.predicted_points
    return value if value is not None and isfinite(value) else None


def started(player, now):
    if player.is_on_bye:
        return False
    return player.kickoff_at is None or player.kickoff_at <= now


def is_starter(player):
    return normalize_slot(player.current_slot or "") not in BENCH_SLOTS


def optimize_lineup(players: list[OptimizerPlayer], slot_counts: dict[str, int], now=None):
    now = now or datetime.now(timezone.utc)
    counts = {normalize_slot(slot): int(count) for slot, count in slot_counts.items() if int(count) > 0}
    unsupported = set(counts) - set(SLOT_ORDER) - BENCH_SLOTS
    if unsupported:
        raise ValueError("Unsupported starting slots: " + ", ".join(sorted(unsupported)))
    slots = [slot for slot in SLOT_ORDER for _ in range(counts.get(slot, 0))]
    if not slots:
        raise ValueError("ESPN did not provide any supported starting lineup slots.")
    own = [player for player in players if not player.is_free_agent]
    if len({player.espn_id for player in players}) != len(players):
        raise ValueError("A player appears more than once in the candidate pool.")
    lineup: list[OptimizedSlot | None] = [None] * len(slots)
    locked_ids = set()
    notes = ["Uses full-PPR AI projections and app K/DST scoring; custom ESPN scoring may differ."]
    unknown_locked = False

    for player in own:
        if is_starter(player) and started(player, now):
            slot = normalize_slot(player.current_slot)
            index = next((i for i, label in enumerate(slots) if label == slot and lineup[i] is None), None)
            if index is None:
                raise ValueError("Current starters do not match ESPN's lineup slots. Refresh the league and try again.")
            locked = player.model_copy(update={"predicted_points": player.pregame_predicted_points
                                               if player.prediction_saved else None})
            unknown_locked |= points(locked) is None
            lineup[index] = OptimizedSlot(slot=slot, player=locked, locked=True, action="locked")
            locked_ids.add(player.espn_id)
    remaining = [index for index, item in enumerate(lineup) if item is None]
    eligible = []
    for player in sorted(players, key=lambda item: (item.is_free_agent, item.espn_id)):
        if (player.espn_id in locked_ids or normalize_slot(player.current_slot or "") in {"IR", "ER"}
                or player.is_on_bye or player.availability == "unavailable" or started(player, now)
                or player.status != "projected" or points(player) is None):
            continue
        eligible.append(player)
    if remaining:
        weights = np.full((len(remaining), len(eligible) + len(remaining)), -1e9)
        weights[:, len(eligible):] = 0  # An empty slot scores zero; never invent a replacement score.
        for row, index in enumerate(remaining):
            slot = slots[index]
            for column, player in enumerate(eligible):
                allowed = {normalize_slot(value) for value in player.eligible_slots} if player.eligible_slots else DEFAULT_ELIGIBILITY.get(player.position, set())
                if slot in allowed:
                    preference = -1 if player.is_free_agent else 3 if normalize_slot(player.current_slot or "") == slot else 2
                    weights[row, column] = round(points(player), 6) + preference * 1e-9
        rows, columns = linear_sum_assignment(weights, maximize=True)
        for row, column in zip(rows, columns):
            index = remaining[row]
            player = eligible[column] if column < len(eligible) and weights[row, column] > -1e8 else None
            action = ("empty" if player is None else "add" if player.is_free_agent else
                      "keep" if normalize_slot(player.current_slot or "") == slots[index] else
                      "move" if is_starter(player) else "start")
            lineup[index] = OptimizedSlot(slot=slots[index], player=player, action=action)
    selected = {item.player.espn_id for item in lineup if item.player is not None}
    bench = [player for player in own if player.espn_id not in selected and normalize_slot(player.current_slot or "") not in {"IR", "ER"}]
    changes = [LineupChange(action="bench", player=player,
                           reason=("No usable projection is available for this starter."
                                   if points(player) is None or player.status != "projected" else
                                   "This player is unavailable or on bye."
                                   if player.is_on_bye or player.availability == "unavailable" else
                                   "Leaving this slot empty projects more points than this player's negative projection."
                                   if points(player) < 0 else
                                   "A different eligible player improves the projected starting lineup."))
               for player in bench if is_starter(player) and not started(player, now)]
    for item in lineup:
        if item.action in {"add", "start", "move"}:
            changes.append(LineupChange(action=item.action, player=item.player, slot=item.slot,
                reason=("Add this available player, then start them in this slot; a waiver claim may be required."
                        if item.action == "add" else "Use this eligible player in the recommended starting slot.")))

    def total(values):
        values = list(values)
        return sum(value for value in values) if all(value is not None for value in values) else None

    current_values = []
    for player in own:
        if is_starter(player):
            current_values.append((player.pregame_predicted_points if player.prediction_saved else None)
                                  if player.espn_id in locked_ids else points(player))
    current = total(current_values)
    optimized = total(points(item.player) if item.player else 0 for item in lineup)
    movable_current = total(points(player) for player in own if is_starter(player) and player.espn_id not in locked_ids)
    movable_optimized = total(points(item.player) if item.player else 0 for item in lineup if not item.locked)
    improvement = movable_optimized - movable_current if movable_current is not None and movable_optimized is not None else None
    adds = sum(item.action == "add" for item in lineup)
    if unknown_locked:
        notes.append("Some locked starters have no saved pregame projection. Full totals are unavailable; improvement only measures movable slots.")
    if any(item.player is None for item in lineup):
        notes.append("Some slots remain empty: no eligible, available player with a nonnegative usable projection was found.")
    if any(normalize_slot(player.current_slot or "") in {"IR", "ER"} for player in own):
        notes.append("IR players need activation in ESPN before they can be recommended as starters.")
    if any(points(player) is None or player.status != "projected" for player in players):
        notes.append("Players without usable projections are excluded from new assignments; comparisons involving missing projections are incomplete.")
    if any(player.kickoff_at is None and not player.is_on_bye for player in players):
        notes.append("Players with unknown kickoff times are not moved or added; current starters in that state are kept in place.")
    if adds:
        notes.append("Free-agent upgrades are suggested regardless of roster space; managers choose any drops. Some additions require waiver claims.")
    if not any(player.eligible_slots for player in players):
        notes.append("ESPN eligibility was unavailable; standard football position eligibility was used.")
    return {"lineup": lineup, "bench": bench, "changes": changes, "current_points": current,
            "optimized_points": optimized, "improvement": improvement,
            "notes": notes}
