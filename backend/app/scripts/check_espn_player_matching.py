import argparse

from app.config.espn_config import (
    get_local_espn_config,
)
from app.integrations.espn_fantasy import (
    get_league,
)
from app.integrations.espn_player_matching import (
    match_espn_player,
)
from app.services.NFL_data import NFLData


SUPPORTED_POSITIONS = {
    "QB",
    "RB",
    "WR",
    "TE",
}


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

    nfl_data = NFLData([config.season])
    nfl_data.load_player_ids()

    id_map = nfl_data.get_player_id_map()

    results = []

    for player in team.roster:
        position = str(player.position).upper()

        if position not in SUPPORTED_POSITIONS:
            continue

        result = match_espn_player(
            id_map=id_map,
            espn_id=int(player.playerId),
            espn_name=str(player.name),
            position=position,
        )

        results.append(result)

        print(
            f"{result.status.upper():<9} | "
            f"{result.espn_name:<25} | "
            f"{result.position:<2} | "
            f"{result.player_id or '-'}"
        )

    matched_count = sum(
        result.status == "matched"
        for result in results
    )

    print()
    print(f"Fantasy players checked: {len(results)}")
    print(f"Matched: {matched_count}")
    print(
        f"Unmatched or ambiguous: "
        f"{len(results) - matched_count}"
    )


if __name__ == "__main__":
    main()