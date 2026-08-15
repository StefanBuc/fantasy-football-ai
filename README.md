# Fantasy Football AI

Fantasy Football AI is a work-in-progress application for producing weekly NFL fantasy-football projections and eventually comparing those projections with a user's ESPN fantasy team. The backend combines historical NFL data, feature engineering, position-specific machine-learning models, a FastAPI API, and an early ESPN Fantasy integration.

## Project status

The model-training and command-line projection workflows are the most developed parts of the project. The FastAPI application and ESPN integration are under active development, and the frontend has not been implemented yet.

Currently available:

- NFL weekly statistics, snap counts, schedules, and rosters through `nfl_data_py`
- Fantasy-point and defensive-matchup feature engineering
- Position-specific PyTorch projection models for QB, RB, WR, and TE
- XGBoost model experiments
- Batch projections for a selected NFL week
- FastAPI route structure for health, metadata, players, weeks, and predictions
- Initial ESPN Fantasy helpers for rosters, schedules, standings, transactions, and free agents

Several API responses are still placeholders. See [Current API](#current-api) for details.

## Repository structure

```text
.
|-- backend/
|   |-- main.py                       # FastAPI application
|   |-- requirements.txt              # Python dependencies
|   |-- app/
|   |   |-- config/                   # Model features and selected versions
|   |   |-- integrations/
|   |   |   `-- espn_fantasy.py       # ESPN Fantasy integration helpers
|   |   |-- routes/                   # FastAPI routers
|   |   |-- scripts/                  # Training, evaluation, and projection CLIs
|   |   `-- services/                 # Data, features, models, and inference
|   `-- models/                       # Local trained artifacts (Git-ignored)
`-- frontend/                         # Reserved for the future frontend
```

## Requirements

- Python 3.10 or newer
- Internet access when downloading NFL or ESPN data
- A virtual environment is recommended
- Trained PyTorch checkpoints are required for weekly inference

The project can run on CPU. PyTorch will use CUDA when a compatible GPU and installation are available.

## Backend setup

From the repository root, create and activate a virtual environment:

### Windows PowerShell

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

Then run backend commands from the `backend` directory so imports such as `app.services` resolve correctly:

```powershell
cd backend
```

## Run the API

From `backend/`:

```powershell
python -m uvicorn main:app --reload
```

The API is available at `http://127.0.0.1:8000`. FastAPI's interactive documentation is available at:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

Some route modules currently download NFL data when imported, so API startup may require network access and can take time.

## Current API

The following routers are registered in `backend/main.py`:

| Method | Path | Status |
| --- | --- | --- |
| `GET` | `/api/health/` | Basic process health response |
| `GET` | `/api/health/ready` | Placeholder readiness response |
| `GET` | `/api/metadata/` | Basic application metadata |
| `GET` | `/api/players/` | Returns loaded weekly player records |
| `GET` | `/api/players/{player_id}` | In progress |
| `GET` | `/api/players/{player_id}/stats` | In progress |
| `GET` | `/api/players/{season}/{position}` | Filters weekly records by season and position |
| `GET` | `/api/weeks/...` | Placeholder week responses |
| `GET` | `/api/predictions/...` | Placeholder prediction responses |

An ESPN router also exists under `backend/app/routes/espn.py`, but it is not currently registered in `main.py` and still returns placeholder data.

## Train PyTorch models

Training downloads the requested NFL seasons, builds position-specific sequences and matchup features, and saves checkpoints under `backend/models/pytorch/`.

From `backend/`, train one position:

```powershell
python -m app.scripts.train_pytorch --position QB --season 2020 2021 2022 2023 2024 --version 4
```

Train every supported position:

```powershell
python -m app.scripts.train_pytorch --position ALL --season 2020 2021 2022 2023 2024 --version 4
```

Useful options include:

```text
--batch_size
--seed
--learning_rate
--num_epochs
--patience
--version
```

Model artifacts and generated caches are intentionally ignored by Git.

## Generate weekly projections

The projection command loads historical player and defense data, the active weekly roster, the schedule, and the selected position checkpoints. Players without enough prior games are skipped.

From `backend/`:

```powershell
python -m app.scripts.project_week --season 2024 --week 10 --position ALL --top 20
```

Project a single position:

```powershell
python -m app.scripts.project_week --season 2024 --week 10 --position WR --top 10
```

Supported positions are `QB`, `RB`, `WR`, and `TE`. The week must be between 1 and 18.

## Check inference

The inference check compares the checkpoint, raw-feature, and optimized service prediction paths and can optionally benchmark batch inference:

```powershell
python -m app.scripts.check_pytorch_inference --position QB --split validation --version 4
```

Optional benchmark example:

```powershell
python -m app.scripts.check_pytorch_inference --position QB --split test --version 4 --benchmark-size 100
```

## ESPN Fantasy integration

The project uses the community-maintained `espn-api` package. ESPN Fantasy does not provide a conventional supported OAuth flow for this use case, so private leagues require ESPN session-cookie values.

Typical local environment variables are:

```dotenv
ESPN_LEAGUE_ID=your_league_id
ESPN_YEAR=2026
ESPN_TEAM_ID=your_team_id
ESPN_SWID=your_swid_cookie
ESPN_S2=your_espn_s2_cookie
```

Do not commit these values. `.env` files are ignored by the repository.

The integration currently provides helpers to:

- Connect to an ESPN league
- Find a fantasy team by ESPN team ID
- Read its roster and schedule
- Retrieve weekly matchups
- Retrieve league standings, transactions, and free agents

Environment loading, serialization of ESPN objects, persistent synchronization, and player-ID mapping are still to be implemented. ESPN player IDs will eventually need to be mapped to the GSIS IDs used by the NFL dataset.

## Data and modeling overview

`NFLData` downloads and combines:

- Weekly player statistics
- Offensive snap counts
- Player identifier mappings
- NFL schedules
- Weekly rosters

The feature pipeline builds recent player histories and opponent defensive features. PyTorch inference selects a position-specific checkpoint, scales the input using checkpoint metadata, and produces projected PPR fantasy points. Weekly slate generation ranks eligible players by predicted points.

Because external datasets and ESPN endpoints can change, data-loading and synchronization code should be treated as network-dependent.

## Security notes

- Never commit `.env` files, ESPN cookies, or other credentials.
- Never log `ESPN_SWID` or `ESPN_S2`.
- Treat ESPN cookies like passwords because they can grant access to a private league.
- The current CORS configuration allows every origin and is intended only for development.
- Restrict CORS and encrypt stored credentials before deploying the application.

## Roadmap

- Complete and validate the player, week, and prediction API routes
- Load NFL data once during application startup instead of in route-module imports
- Register and implement the ESPN router
- Normalize ESPN responses into Pydantic schemas
- Map ESPN player IDs to NFL/GSIS player IDs
- Sync a user's roster and compare ESPN projections with model projections
- Add automated tests and persistent storage
- Build the frontend

## Disclaimer

This project is for educational and personal fantasy-football analysis. It is not affiliated with or endorsed by the NFL or ESPN. ESPN integration relies on an unofficial API and may change without notice.
