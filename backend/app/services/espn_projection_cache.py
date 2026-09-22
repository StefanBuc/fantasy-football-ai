from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from threading import Lock
from typing import Callable

from app.integrations.espn_roster_projection import (
    ESPNRosterPlayer,
    ESPNRosterProjection,
    project_espn_roster,
)
from app.services.weekly_projection_service import (
    WeeklyProjectionService,
)


@dataclass(frozen=True)
class ESPNLeagueWeekProjection:
    generated_at: datetime
    roster_week: int
    team_projections: dict[
        int,
        tuple[ESPNRosterProjection, ...],
    ]


class ESPNProjectionCache:
    """Small process-local cache for expensive model results."""

    def __init__(
        self,
        ttl: timedelta = timedelta(hours=6),
        max_entries: int = 32,
    ) -> None:
        self.ttl = ttl
        self.max_entries = max_entries
        self._entries: OrderedDict[
            tuple[int, int, int, str],
            ESPNLeagueWeekProjection,
        ] = OrderedDict()
        self._lock = Lock()

    def get_or_create(
        self,
        key: tuple[int, int, int, str],
        builder: Callable[[], ESPNLeagueWeekProjection],
    ) -> tuple[ESPNLeagueWeekProjection, bool]:
        now = datetime.now(timezone.utc)

        with self._lock:
            entry = self._entries.get(key)
            if (
                entry is not None
                and now - entry.generated_at < self.ttl
            ):
                self._entries.move_to_end(key)
                return entry, True

            if entry is not None:
                del self._entries[key]

            entry = builder()
            self._entries[key] = entry
            self._entries.move_to_end(key)

            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

            return entry, False

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def roster_fingerprint(league) -> str:
    roster_rows: list[str] = []

    for team in sorted(
        league.teams,
        key=lambda item: int(item.team_id),
    ):
        for player in team.roster:
            roster_rows.append(
                "|".join(
                    (
                        str(int(team.team_id)),
                        str(int(player.playerId)),
                        str(player.name),
                        str(player.position).upper(),
                        str(player.lineupSlot),
                        str(
                            getattr(player, "proTeam", "")
                            or ""
                        ).upper(),
                    )
                )
            )

    payload = "\n".join(sorted(roster_rows))
    return sha256(payload.encode("utf-8")).hexdigest()


def make_roster_player(
    player,
    normalize_team: Callable[[str], str],
) -> ESPNRosterPlayer:
    pro_team = getattr(player, "proTeam", None)
    return ESPNRosterPlayer(
        espn_id=int(player.playerId),
        player_name=str(player.name),
        position=str(player.position).upper(),
        lineup_slot=str(player.lineupSlot),
        team=(
            normalize_team(str(pro_team))
            if pro_team
            else None
        ),
    )


def build_league_week_projection(
    league,
    service: WeeklyProjectionService,
    season: int,
    week: int,
    normalize_team: Callable[[str], str],
) -> ESPNLeagueWeekProjection:
    roster_df, roster_week = (
        service.data.get_projection_roster(
            season=season,
            week=week,
        )
    )
    opponents = service.data.get_week_opponents(
        season=season,
        week=week,
    )
    id_map = service.data.get_player_id_map()

    roster_by_team = {
        int(team.team_id): [
            make_roster_player(player, normalize_team)
            for player in team.roster
        ]
        for team in league.teams
    }
    all_players = [
        player
        for players in roster_by_team.values()
        for player in players
    ]

    all_projections = project_espn_roster(
        weekly_service=service,
        roster_players=all_players,
        id_map=id_map,
        roster_df=roster_df,
        opponents=opponents,
        season=season,
        week=week,
    )

    team_projections: dict[
        int,
        tuple[ESPNRosterProjection, ...],
    ] = {}
    offset = 0

    for team_id, players in roster_by_team.items():
        next_offset = offset + len(players)
        team_projections[team_id] = tuple(
            all_projections[offset:next_offset]
        )
        offset = next_offset

    return ESPNLeagueWeekProjection(
        generated_at=datetime.now(timezone.utc),
        roster_week=roster_week,
        team_projections=team_projections,
    )
