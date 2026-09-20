import argparse

from app.config.espn_config import (
    get_local_espn_config,
)
from app.integrations.espn_fantasy import (
    get_league,
)


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--team-id",
        type=int,
        required=True,
    )

    return parser.parse_args()


def main():
    args = parse_args()
    config = get_local_espn_config()

    league = get_league(
        league_id=config.league_id,
        year=config.season,
        espn_s2=config.espn_s2,
        swid=config.swid,
    )

    team = next(
        (
            team
            for team in league.teams
            if team.team_id == args.team_id
        ),
        None,
    )

    if team is None:
        raise ValueError(
            f"Team {args.team_id} was not found."
        )

    print(f"Team: {team.team_name}")
    print(f"Roster size: {len(team.roster)}")

    for player in team.roster:
        print(
            f"{player.playerId} | "
            f"{player.name} | "
            f"{player.position} | "
            f"{player.proTeam} | "
            f"{player.lineupSlot} | "
            f"{player.injuryStatus}"
        )


if __name__ == "__main__":
    main()