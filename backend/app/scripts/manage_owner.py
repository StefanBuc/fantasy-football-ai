"""Create/reset the sole owner from an interactive server terminal, never HTTP."""

import argparse
from getpass import getpass

from app.config.espn_config import BACKEND_DIR  # Loads backend/.env consistently with the API.
from app.services.account_store import accounts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Replace the owner login and revoke all sessions; keep leagues/history.")
    args = parser.parse_args()
    username = input("Owner username: ").strip()
    password = getpass("Password (at least 8 characters): ")
    if password != getpass("Confirm password: "):
        parser.error("Passwords do not match.")
    try:
        accounts.set_owner(username, password, reset=args.reset)
    except ValueError as error:
        parser.error(str(error))
    print("Owner login saved. Existing sessions revoked. Saved leagues and prediction history are unchanged.")


if __name__ == "__main__":
    main()
