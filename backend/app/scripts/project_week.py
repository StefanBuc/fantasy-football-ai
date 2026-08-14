import argparse

from app.services.pytorch_inference import (
    PyTorchProjectionService,
)
from app.services.NFL_data import NFLData
from app.services.projection_slate import (
    build_projection_requests,
    project_position_slate,
)

POSITIONS = ("QB", "RB", "WR", "TE")


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--season",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--week",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--position",
        type=str.upper,
        choices=[*POSITIONS, "ALL"],
        default="ALL",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=20,
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if args.week < 1 or args.week > 18:
        raise ValueError(
            "Week must be between 1 and 18."
        )

    if args.top < 1:
        raise ValueError(
            "--top must be at least 1."
        )

    context_seasons = [
        args.season - 1,
        args.season,
    ]

    data = NFLData(context_seasons)
    data.load_data()
    data.load_schedule()
    data.load_weekly_rosters()

    player_df = data.get_player_stats()
    defense_df = data.get_defense_stats()

    roster_df = data.get_week_roster(
        season=args.season,
        week=args.week,
    )

    opponents = data.get_week_opponents(
        season=args.season,
        week=args.week,
    )

    positions = (
        POSITIONS
        if args.position == "ALL"
        else (args.position,)
    )

    for position in positions:
        requests = build_projection_requests(
            roster_df=roster_df,
            opponents=opponents,
            position=position,
        )

        service = PyTorchProjectionService(
            position=position,
            player_df=player_df,
            defense_df=defense_df,
        )

        result = project_position_slate(
            service=service,
            requests=requests,
        )

        print()
        print(
            f"{position} projections | "
            f"{args.season} week {args.week}"
        )

        print(
            f"Projected: {len(result.projections)} | "
            f"Skipped: {len(result.skipped)}"
        )

        for rank, projection in enumerate(
            result.projections[:args.top],
            start=1,
        ):
            request = projection.request

            print(
                f"{rank:>2}. "
                f"{request.player_name} "
                f"({request.team} vs "
                f"{request.opponent_team}): "
                f"{projection.predicted_points:.2f}"
            )


if __name__ == "__main__":
    main()