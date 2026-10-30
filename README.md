# Fantasy Football AI

Fantasy Football AI is a full-stack application that produces weekly NFL fantasy-football projections and applies them to ESPN Fantasy leagues. It combines historical NFL data, position-specific PyTorch sequence models, a FastAPI backend, ESPN roster integration, and a React/Tailwind frontend.

The application currently supports projections for quarterbacks, running backs, wide receivers, tight ends, kickers, and D/ST.

## Current functionality

- Downloads NFL weekly statistics, snap counts, schedules, weekly rosters, depth charts, play-by-play data, and player identifiers.
- Builds five-game player histories and pregame opponent-defense features without using the target game's results.
- Uses separate PyTorch models and feature sets for QB, RB, WR, TE, K, and D/ST.
- Uses chronological train, validation, and test seasons, early stopping, and MAE-based evaluation.
- Compares model performance against last-game and rolling-mean baselines.
- Generates batched weekly projections through a FastAPI API.
- Connects public ESPN leagues and locally configured private ESPN leagues.
- Maps ESPN players to NFL/GSIS identifiers and projects complete fantasy rosters.
- Displays My Team, Matchup, and League views in a React frontend.
- Supports benches, IR slots, ESPN team logos, future-week selection, and dark mode.
- Applies live ESPN injury availability on top of cached base projections.
- Produces labelled cold-start fallbacks for players with fewer than five games.
- Builds time-safe unavailable-teammate opportunity features from injury reports.
- Batches and caches a complete league's weekly projections for faster repeated requests.
- Includes automated tests for temporal history, defensive features, projection construction, player matching, ESPN routes, and API contracts.

## Architecture

```text
NFL and play-by-play data
          |
          v
Feature engineering and five-game sequences
          |
          v
Position-specific PyTorch models
          |
          v
FastAPI projection and ESPN integration layer
          |
          v
React + TypeScript + Tailwind frontend
```

The player models use two inputs:

1. An LSTM processes the player's five most recent games using position-specific features.
2. A feed-forward encoder processes the upcoming opponent's pregame defensive profile.

The two representations are combined to predict fantasy points. Kicker and D/ST models use the same overall sequence architecture with special-teams-specific features.

## Repository structure

```text
.
|-- backend/
|   |-- main.py                       # FastAPI application
|   |-- requirements.txt              # Runtime dependencies
|   |-- requirements-dev.txt          # Test dependencies
|   |-- app/
|   |   |-- config/                   # Features, model versions, ESPN config
|   |   |-- integrations/             # ESPN connection and player matching
|   |   |-- routes/                   # FastAPI route modules
|   |   |-- schemas/                  # Pydantic API contracts
|   |   |-- scripts/                  # Training, evaluation, and projection CLIs
|   |   `-- services/                 # Data, models, inference, and caching
|   |-- models/pytorch/               # Local trained checkpoints (Git-ignored)
|   `-- tests/                         # Backend test suite
`-- frontend/
    |-- src/                           # React application
    |-- public/                        # Static assets
    `-- package.json                   # Frontend dependencies and scripts
```

## Requirements

- Python 3.10-3.11 (Python 3.11 is recommended)
- Node.js and npm
- Internet access for NFL and ESPN data
- Trained PyTorch checkpoints under `backend/models/pytorch/`

The models can run on CPU. PyTorch automatically uses CUDA when a compatible GPU and PyTorch installation are available.

## Backend setup

From the repository root:

```powershell
py -3.11 -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

The pinned NumPy and pandas versions have prebuilt Windows wheels through Python
3.11. Using Python 3.12 or newer can make `pip` try to compile pandas locally,
which requires a C/C++ build toolchain. If a previous virtual environment was created
with another Python version, deactivate it and recreate it before installing:

```powershell
deactivate
Remove-Item -Recurse -Force backend\.venv
```

Install the PyTorch build appropriate for the laptop after installing the other
requirements. Choose the CPU or CUDA command from the official
[PyTorch installation selector](https://pytorch.org/get-started/locally/).

Run backend commands from the `backend` directory so imports such as `app.services` resolve correctly:

```powershell
cd backend
python -m uvicorn main:app --reload
```

The API is available at `http://127.0.0.1:8000`.

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Health: `http://127.0.0.1:8000/api/health/`

The first data or projection request can take longer because NFL data and model checkpoints are loaded lazily and then reused by the backend process.

## Frontend setup

In another terminal, from the repository root:

```powershell
cd frontend
npm install
npm run dev
```

Vite prints the local frontend URL when it starts. During development, the Vite proxy forwards API requests to the backend. For a separately hosted backend, copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_BASE_URL`.

Useful frontend checks:

```powershell
npm run lint
npm run build
```

## ESPN configuration

The project uses the community-maintained `espn-api` package. Public leagues can be connected using their league ID and season. Private leagues require ESPN session-cookie credentials.

For local private-league development, copy `backend/.env.example` to `backend/.env` and provide:

```dotenv
ESPN_LEAGUE_ID=your_league_id
ESPN_SEASON=2026
ESPN_SWID=your_swid_cookie
ESPN_S2=your_espn_s2_cookie
ESPN_ENABLE_LOCAL_API=true
```

The credential-backed `/api/espn/local/*` endpoints are hidden from the generated API schema and restricted to loopback clients. Never commit `.env`, `ESPN_SWID`, or `ESPN_S2`; these cookies should be treated like passwords.

## API overview

All routers are registered in `backend/main.py`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health/` | Basic process health |
| `GET` | `/api/health/ready` | Basic readiness response |
| `GET` | `/api/metadata/` | Application metadata |
| `GET` | `/api/players/` | Latest record for each NFL player |
| `GET` | `/api/players/{player_id}` | Player summary |
| `GET` | `/api/players/{player_id}/stats` | Player weekly history |
| `GET` | `/api/players/{season}/{position}` | Players filtered by season and position |
| `GET` | `/api/weeks/{season}` | Available regular-season weeks |
| `GET` | `/api/weeks/{season}/{week}` | Weekly NFL schedule |
| `GET` | `/api/predictions/week/{season}/{week}` | Weekly QB/RB/WR/TE projections |
| `POST` | `/api/espn/connect` | Connect a public ESPN league |
| `POST` | `/api/espn/projections` | Project a public league team |
| `POST` | `/api/espn/matchup` | Project both sides of a matchup |

Local private-league equivalents are available under `/api/espn/local/*` when explicitly enabled.

## Training models

Training uses the requested seasons chronologically:

- All seasons except the last two are training seasons.
- The penultimate season is validation data used for early stopping.
- The final season is the held-out test set.

With the default 2020-2024 data, that produces training seasons 2020-2022, validation season 2023, and test season 2024.

Train an offensive-position model from `backend/`:

```powershell
python -m app.scripts.train_pytorch `
    --position QB `
    --season 2020 2021 2022 2023 2024 `
    --num_epochs 30 `
    --patience 7 `
    --version 4
```

Supported values are `QB`, `RB`, `WR`, `TE`, and `ALL`.

Train kicker and D/ST models separately:

```powershell
python -m app.scripts.train_special_teams `
    --position ALL `
    --season 2020 2021 2022 2023 2024 `
    --version 1
```

The selected deployed checkpoint versions are configured in `backend/app/config/model_config.py`.

## Evaluation and inference checks

The training scripts report:

- Training MAE
- Validation MAE
- Held-out test MAE
- Last-game baseline MAE
- Five-game rolling-mean baseline MAE

The inference checker verifies that direct checkpoint inference, raw-feature inference, and the optimized service return matching predictions:

```powershell
python -m app.scripts.check_pytorch_inference `
    --position QB `
    --split test `
    --version 4 `
    --benchmark-size 100
```

## Weekly projections

Generate a ranked QB/RB/WR/TE slate from `backend/`:

```powershell
python -m app.scripts.project_week `
    --season 2024 `
    --week 10 `
    --position ALL `
    --top 20
```

The full offensive-player model requires five previous games, and history can cross season boundaries. Players with one to four games receive a clearly labelled average of their available games. Players with no history receive a lower-confidence historical position average. If no prior position data exists, the player is skipped instead of fabricating a projection.

## Projection performance and caching

- Models and prepared NFL data are cached and reused per backend process.
- Inference is batched by position instead of running players individually.
- ESPN projections are generated for the whole fantasy league and cached for six hours.
- The cache key includes a roster fingerprint, so trades, waivers, and lineup changes produce a new entry.
- Injury status is applied after the base projection is loaded from cache. Confirmed unavailable players receive an adjusted projection of zero, while questionable and doubtful players retain their base projection with a warning.

The current league cache is process-local, limited to 32 entries, and cleared on restart. A shared persistent cache is still required before horizontally scaling the API.

## Tests

From `backend/`:

```powershell
python -m pytest tests -v
```

The test suite covers time-aware player histories, pregame defense construction, roster and depth-chart selection, ESPN player matching, league projection caching, injury adjustment, and API response contracts.

## Current limitations and roadmap

The next planned work is:

1. Train and evaluate injury-context checkpoints before promoting them to production.
2. Replace the process-local projection cache with Redis or persistent database storage.
3. Add an automated weekly data refresh, evaluation, projection, and optional retraining pipeline.
4. Add production deployment configuration, meaningful readiness checks, restricted CORS, HTTPS, logging, and monitoring.

Additional modeling improvements include rolling-origin evaluation, formal PyTorch feature-importance analysis, uncertainty intervals, and monitoring prediction quality by position and week.

## Security notes

- Never commit `.env` files, ESPN cookies, or other credentials.
- Never log `ESPN_SWID` or `ESPN_S2`.
- The current wildcard CORS configuration is intended for development and must be restricted before deployment.
- The local credential-backed ESPN API is not intended to expose one developer's cookies to public users.
- External NFL and ESPN data sources are network-dependent and can change independently of this project.

## Disclaimer

This project is for educational and personal fantasy-football analysis. It is not affiliated with or endorsed by the NFL or ESPN. ESPN integration relies on an unofficial API and may change without notice.
