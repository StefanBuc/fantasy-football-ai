"""Run the scheduled trainer, check once, or roll back a promoted position."""
import argparse
from app.services.retraining_worker import RetrainingWorker, POSITIONS
from app.services.model_registry import rollback


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--once", action="store_true", help="Check the schedule once, then exit")
    group.add_argument("--run-now", action="store_true", help="Train/evaluate now, outside the normal schedule")
    group.add_argument("--rollback", choices=POSITIONS)
    args = parser.parse_args()
    if args.rollback:
        rollback(args.rollback)
        print(f"Restored the previous {args.rollback} model selection.")
    elif args.once or args.run_now:
        RetrainingWorker().run_once(force=args.run_now)
    else:
        RetrainingWorker().loop()


if __name__ == "__main__":
    main()
