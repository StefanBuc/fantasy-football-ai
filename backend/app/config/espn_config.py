import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class ESPNLocalConfig:
    league_id: int
    season: int
    swid: str
    espn_s2: str


def required_environment_value(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"Missing environment variable: {name}"
        )

    return value


def get_local_espn_config() -> ESPNLocalConfig:
    league_id_value = required_environment_value(
        "ESPN_LEAGUE_ID"
    )
    swid = required_environment_value("ESPN_SWID")
    espn_s2 = required_environment_value("ESPN_S2")

    season_value = os.getenv(
        "ESPN_SEASON",
        str(date.today().year),
    )

    try:
        league_id = int(league_id_value)
        season = int(season_value)
    except ValueError as error:
        raise RuntimeError(
            "ESPN_LEAGUE_ID and ESPN_SEASON "
            "must be integers."
        ) from error

    return ESPNLocalConfig(
        league_id=league_id,
        season=season,
        swid=swid,
        espn_s2=espn_s2,
    )