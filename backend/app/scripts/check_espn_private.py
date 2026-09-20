from espn_api.requests.espn_requests import (
    ESPNAccessDenied,
    ESPNInvalidLeague,
)

from app.config.espn_config import (
    get_local_espn_config,
)
from app.integrations.espn_fantasy import (
    get_league,
)


def main():
    config = get_local_espn_config()

    try:
        league = get_league(
            league_id=config.league_id,
            year=config.season,
            espn_s2=config.espn_s2,
            swid=config.swid,
        )

    except ESPNAccessDenied as error:
        raise RuntimeError(
            "ESPN denied access. Check the private "
            "league credentials in .env."
        ) from error

    except ESPNInvalidLeague as error:
        raise RuntimeError(
            "The configured ESPN league or season "
            "does not exist."
        ) from error

    print(f"Connected to: {league.settings.name}")
    print(f"Season: {config.season}")
    print(f"Teams: {len(league.teams)}")

    for team in league.teams:
        print(
            f"{team.team_id}: "
            f"{team.team_name} "
            f"({team.team_abbrev})"
        )


if __name__ == "__main__":
    main()