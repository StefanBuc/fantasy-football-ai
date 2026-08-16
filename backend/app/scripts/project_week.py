import argparse

from app.services.weekly_projection_service import (
    WeeklyProjectionService,
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

    weekly_service = WeeklyProjectionService(
        season=args.season,
    )
    
    positions = (
        POSITIONS
        if args.position == "ALL"
        else (args.position,)
    )

    for position in positions:
        
        result = weekly_service.project_week(
            week=args.week,
            position=position,
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