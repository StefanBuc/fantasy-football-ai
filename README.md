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
- Protects the public deployment with a single owner account, secure server-side sessions, and encrypted saved private-league connections.
- Welcomes visitors with a public homepage, interactive sample previews, and aggregate model-performance tiles; signup stays closed.
- Maps ESPN players to NFL/GSIS identifiers and projects complete fantasy rosters.
- Displays My Team, Optimized lineup, Trade analyzer, Matchup, Players, League, and Accuracy views in a React frontend.
- Recommends the highest projected eligible lineup, with optional free-agent additions and explicit start/bench changes.
- Evaluates trades using before/after optimized lineups, weekly and remaining-season projections, team needs, backup depth, and projected league power ranks.
- Supports benches, IR slots, ESPN team logos, future-week selection, and dark mode.
- Applies live ESPN injury availability on top of cached base projections.
- Produces labelled cold-start fallbacks for players with fewer than five games.
- Builds time-safe unavailable-teammate opportunity features from injury reports.
- Batches and caches a complete league's weekly projections for faster repeated requests.
- Saves pregame projections permanently and compares them with published results in the Accuracy tab.
- Automatically captures pregame projections and syncs next-day results while the backend runs, with persistent job status.
- Shows tested floor/ceiling estimates before kickoff and ESPN live/final fantasy points above the saved pregame prediction during/after games.
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

For container setup instead of local Python/Node environments, see [Docker setup](#docker-setup).

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

## Public site and sign-in

With authentication enabled (the default), `/` is the public homepage. Visitors can explore features, labelled fictional player/lineup/trade examples, and model-performance tiles without connecting a league. `/login` opens owner sign-in, `/app` opens the protected league dashboard, and `/signup` explains that registration is closed. The disabled signup buttons do not create accounts. The existing owner account and saved leagues continue to work; signed-in visitors can return home and reopen their dashboard.

The anonymous `GET /api/public/performance` endpoint reads aggregate results for the current NFL season from saved NFL-wide predictions (`scope='weekly'`). It excludes all ESPN league records, player names, account details, and credentials. Tiles show mean absolute error, the percentage of graded forecasts within five points, the number graded, and the last result update. They disclose sample size, scoring, and model/fallback coverage. These are full-PPR projections with the app's kicker/D/ST scoring, rather than a particular league's scoring settings. If there are no graded NFL-wide results, the page shows a collecting state instead of invented accuracy figures.

The endpoint reads existing history without loading models, running predictions, or creating a database. Summaries are cached for 60 seconds on the server; the homepage refreshes them every five minutes and when its tab becomes visible. The existing background prediction/result jobs supply this history while the backend runs. Private league accuracy remains in the authenticated Accuracy tab. Public pages do not fetch private league connections or projections.

## Docker setup

Docker Desktop must be running with Linux containers. Use Compose 2.24 or newer for optional environment files. This runs a built React frontend through Nginx and a FastAPI backend, with PyTorch 2.14.1 and CUDA 12.6 to support Pascal GPUs such as the Quadro P1000. The single `compose.yaml` requests your NVIDIA GPU by default. Windows GPU access requires Docker Desktop's WSL 2 backend and compatible NVIDIA drivers; see [Docker's GPU setup](https://docs.docker.com/desktop/features/gpu/).

From the repository root:

```powershell
docker compose up -d
```

Host ports default to 8090 for the frontend and loopback-only 8091 for the API; container-internal ports remain 8080 and 8000. Owner login works at **https://ffa.stefanb.me**, **http://100.94.147.92:8090** through Tailscale, and **http://localhost:8090** on the Docker host. `http://127.0.0.1:8090` and IPv6 loopback work too. Native Vite development works at **http://localhost:5173**, including its loopback aliases and alternate local ports. Other HTTP addresses point you to a configured address. To change the public/Tailscale entry points, set `FANTASY_PUBLIC_URL` or `FANTASY_TAILSCALE_URL` in a `.env` file beside `compose.yaml`. Set `FANTASY_TAILSCALE_URL=` to disable the Tailscale HTTP exception. Compose builds missing images automatically; the first build downloads Python, Node, and PyTorch's CUDA libraries. Models and data still load on their first uncached request.

Backend builds keep pip downloads in a BuildKit cache mount outside the final image. This lets dependency rebuilds reuse PyTorch and CUDA downloads even when Docker cannot reuse the entire installation layer. The first build with this cache still downloads the packages: older `--no-cache-dir` builds did not retain their installers. The cache belongs to the Docker builder on each machine and may be removed by builder-cache pruning. Continue using `docker compose up -d --build` for normal updates; application-code changes alone reuse the installed dependency layers.

The model directory `backend/models/pytorch/` must exist and contain the selected checkpoints. It is mounted read-only rather than copied into an image. Optional configuration is read from `backend/.env`; `.env` files, model files, databases, and caches are excluded from image builds. Add private leagues in the authenticated UI. An existing environment-configured league can be imported there without retyping its credentials.

Trained checkpoints are Git-ignored, so `git pull` does not transfer them to a new server. Copy the selected files from the machine where they were trained into the server's `backend/models/pytorch/`: `QB_model_v4.pth`, `RB_model_v4.pth`, `WR_model_v4.pth`, `TE_model_v4.pth`, `K_model_v1.pth`, and `DST_model_v1.pth`. The container user must be able to read them. Check model loading without downloading NFL data with `docker compose exec backend python -c "from app.services.pytorch_projection_model import load_selected_projection_checkpoint; load_selected_projection_checkpoint('QB')"`.

Inference checks the installed PyTorch wheel's CUDA architectures before automatically selecting a GPU. An unsupported GPU falls back to CPU with an explanation in the logs; each loaded checkpoint reports its actual device. The default CUDA 12.6 build retains P1000 support; PyTorch 2.15/CUDA 13 builds dropped that generation. Build versions are configurable with `TORCH_VERSION` and `TORCH_INDEX_URL` in the root Compose `.env` (for example, `TORCH_VERSION=2.15.0` and `TORCH_INDEX_URL=https://download.pytorch.org/whl/cu134` for newer GPUs). Switching versions downloads the matching wheels once; subsequent builds reuse the persistent pip cache. If an earlier workaround set `CUDA_VISIBLE_DEVICES=-1` in `backend/.env`, remove that line before recreating the containers to enable the GPU. For an intentional CPU-only runtime, keep that setting and recreate both services with `docker compose up -d --no-build --force-recreate backend frontend`.

The frontend shares the backend's network namespace and proxies API calls through `127.0.0.1`. **Loopback is not authentication:** private data routes, including `/api/espn/local/*`, require an owner session in the default configuration. Minimal health checks, session/login entry points, and the aggregate `/api/public/performance` summary are anonymous. The API port remains bound to loopback. Restrict access to frontend port 8090 to your tunnel/reverse proxy using the server firewall where appropriate; an externally reachable HTTP port is not a substitute for HTTPS.

On your server, after updating the source:

```bash
docker compose up -d --build
docker compose exec backend python -m app.scripts.manage_owner
```

The second command interactively asks for an owner username and a password of at least 8 characters; the password is hidden and never passed on the command line. There is no public signup or first-visitor account claim. Open **https://ffa.stefanb.me**, sign in, and add a public/private league or choose **Import server-configured league**. Setup is required once per account database. Reset a forgotten login or revoke all sessions from the trusted server terminal with:

```bash
docker compose exec backend python -m app.scripts.manage_owner --reset
```

Resetting the login preserves saved leagues, preferences, and prediction history. The normal `/api/health/` probe is available before setup so containers can start; `/api/health/ready` returns 503 until the owner and public origin are configured.

Cloudflare must **bypass caching for `/api/*` and the HTML entry page**, including any Cache Everything or Edge TTL overrides. The app sends `Cache-Control: no-store, private` for API responses and `no-cache` for HTML; hashed `/assets/*` files can be cached. Do not add a rule that strips `Set-Cookie` or caches authenticated responses. HTTPS terminates at Cloudflare; the app checks the configured browser Origin and session-bound CSRF token instead of trusting forwarded IP headers. Nginx includes a Content Security Policy, anti-framing policy, and HTTPS/security headers. Existing Cloudflare Access, if used, can remain an additional outer gate.

Docker cache data lives in the `projection-cache` named volume, separate from `backend/cache/`, and survives container rebuilds and `docker compose down`. Avoid `down --volumes` unless you want to delete that cache. The cache fingerprints use a consistent file order on Windows and Linux.

Prediction history uses a separate `prediction-history` volume at `/app/data/predictions.sqlite3`. It survives cache expiry, refreshes, rebuilds, and normal `docker compose down`. `down --volumes` deletes this history as well as the cache; back up the history before removing volumes.

Owner credentials, session hashes, saved connections, and preferences live in `/app/data/accounts.sqlite3` in the same persistent data volume, separate from prediction history. ESPN cookies are encrypted using a Fernet key in the separate `account-secrets` volume at `/app/secrets/credentials.key`. **Back up the account database and encryption key separately and protect both.** Losing the key makes existing saved ESPN cookies unreadable. Restore the key, or remove/re-add all affected private connections; the app never silently replaces a missing key while encrypted credentials remain. Never use `down --volumes` to update this deployment.

Useful commands:

```powershell
docker compose logs -f backend
docker compose ps
docker compose down
```

To override the host ports, set `FRONTEND_PORT` and `BACKEND_PORT` in a `.env` file beside `compose.yaml` (not `backend/.env`), or use environment variables. Existing overrides take precedence over the defaults. For example, on Linux:

```bash
FRONTEND_PORT=8092 BACKEND_PORT=8093 docker compose up -d
```

On PowerShell, set `$env:FRONTEND_PORT = '8092'` and `$env:BACKEND_PORT = '8093'` before starting Compose. After changing port mappings, run `docker compose up -d` to recreate the affected containers; no image rebuild is needed. For source changes, run `docker compose up --build -d --wait` again; this setup uses built images rather than development hot reload.

The backend image is named `fantasy-football-ai-backend:gpu`. Models load lazily and select CUDA when available, otherwise CPU. To verify GPU access and run a CUDA operation:

```powershell
docker compose exec backend python -c "import torch; assert torch.cuda.is_available(), 'CUDA unavailable'; print(torch.cuda.get_device_name(0)); print(torch.ones(1, device='cuda').sum().item())"
```

This Compose setup requires an NVIDIA GPU; local Python development can still use CPU when CUDA is unavailable. GPU acceleration applies to model inference; ESPN downloads, Parquet restoration, and pandas feature preparation still run on CPU.

## Owner sessions and saved preferences

Docker enforces owner authentication. Passwords are hashed with Argon2id. Session cookies contain random opaque identifiers; only their SHA-256 hashes are stored server-side. The public HTTPS site's cookies use `Secure`, `HttpOnly`, `SameSite=Strict`, and the `__Host-` prefix. State-changing requests require the exact origin for the selected entry point plus a session-bound CSRF token, including login. CORS allows only configured origins. Sign-in is limited to 20 attempts per 15 minutes across workers using the account database.

The explicitly configured Tailscale HTTP address uses a separate host-only `HttpOnly`, `SameSite=Strict` session cookie without `Secure`, because browsers do not send Secure cookies over HTTP. Tailscale supplies transport encryption between tailnet devices; the app still requires owner login and does not treat a Host header or an IP address as authentication. Only a configured IPv4 origin in `100.64.0.0/10` can use this exception; general public HTTP and arbitrary LAN addresses cannot. Nginx preserves the incoming Host and port so the API can select the correct entry point. Keep Tailscale access restricted to your devices/users. If you later use Tailscale HTTPS/MagicDNS, prefer HTTPS there as well.

Sessions are bound to their issuing origin, and public/Tailscale cookies cannot be replayed between entry points. Sign in separately on each address using the **same owner account**; saved leagues, team/tab preferences, and theme are shared. Signing out on one address leaves the other signed in; **Sign out all devices** revokes both. Existing pre-origin-binding sessions require one new sign-in after upgrading; the database migration preserves the owner, saved connections, encryption key, and prediction history.

HTTP loopback access is supported automatically for exact `localhost`, `127.0.0.1`, and `[::1]` hosts. It uses a separate host-only `HttpOnly`, `SameSite=Strict` cookie per port, with server-side origin binding and the same login/CSRF requirements. An app on another local port cannot read authenticated responses using a different Origin. This does not allow arbitrary LAN hosts or hostnames containing the word localhost. Public HTTPS cookies remain Secure. Vite and Nginx preserve the browser's Host/port through the same-origin API proxy.

Without **Remember me**, the cookie lasts for the browser session, with a maximum server lifetime of 12 hours and two hours of inactivity. Remembered sessions last up to 30 days with a seven-day inactivity limit. Login rotates the session identifier. Sign out revokes this session; **Sign out all devices** and a terminal password reset revoke all sessions. Expired sessions return the frontend to login, and logout clears cached league views and in-memory credentials. No authentication tokens or ESPN credentials are stored in browser local/session storage.

The owner can save up to 10 league/season connections. Private credentials are validated with ESPN before saving, never returned by connection APIs, and can be renewed through **Update**. The **Your leagues** screen supports selecting and removing connections. Removal deletes saved cookies and stops enrollment for that league's automatic captures while retaining existing accuracy history. Saved private leagues participate in the existing scheduler without an open browser. Credentials that expire need to be renewed; the app does not automatically log into ESPN using an ESPN password.

Opening a league remembers it as the next automatic connection. Use the **My team** selector in the dashboard header to save your own team for that league. **Go to my team** and the **My team** tab return to it; new visits open that team even if you previously browsed another roster, matchup, or trade. Browsing selections are saved separately and never overwrite your own-team choice. The server validates that your chosen team belongs to the league, and existing account databases gain this preference automatically without replacing saved credentials. Your team, dashboard tab, and theme are restored on other signed-in devices. A new visit starts at the league's current week rather than retaining a stale past-week filter. Historical predictions and existing cache/history formats are preserved. This is intentionally a **single-owner app**, not a multi-user registration/permissions system.

For native localhost development, run `python -m app.scripts.manage_owner` once from `backend/`, start the API on port 8000, and run `npm run dev` from `frontend/`. Use Vite's normal same-origin `/api` proxy. No insecure-development flag or public-domain redirect is needed for loopback login. `FANTASY_PUBLIC_URL` defaults to `https://ffa.stefanb.me` if unset. The legacy `FANTASY_INSECURE_LOCAL_DEV=true` option is accepted only with a loopback public URL; it is unnecessary for ordinary localhost access. `FANTASY_AUTH_ENABLED=false` remains an explicit native-development/testing escape hatch; never expose it publicly, and Docker forces authentication on with insecure development off.

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

With authentication enabled, private API calls select an authenticated saved connection using `X-League-Connection`; protected logo images can use its non-secret ID in a query parameter while still requiring the session cookie. Environment credentials are available only through the authenticated import action. In explicit authentication-disabled native development, the legacy private routes still require `ESPN_ENABLE_LOCAL_API=true` and a loopback client. Never commit `.env`, `ESPN_SWID`, or `ESPN_S2`; these cookies should be treated like passwords.

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
| `POST` | `/api/espn/optimized-lineup` | Optimize a team's lineup, optionally including free agents |
| `POST` | `/api/espn/trade-rosters` | Load current team rosters for trade selection without model inference |
| `POST` | `/api/espn/trade-analysis` | Compare a hypothetical trade's lineup and remaining-season impact |

Local private-league equivalents are available under `/api/espn/local/*` when explicitly enabled.

## Optimized lineup

Open **Optimized lineup** after connecting your league, then choose a team and week. By default it uses only that team's players. Turn on **Include free agents** to consider ESPN's available-player pool as well. The page shows the recommended starters and bench, who to start or bench, and projected point improvement. Suggested additions show **(Free agent)** beside the player's name; some require a waiver claim rather than an immediate pickup. Better free agents are recommended even if the roster is full, including one-week upgrades. The optimizer does not check open roster space or select drops; managers choose whom to drop.

Assignments use ESPN's starting slot counts and player eligibility, including FLEX and Superflex, and maximize total projected points without using anyone twice. Players whose games have started stay in their current slots; started bench players cannot be promoted. Players with unknown kickoff times are also kept in place. Bye-week players, unavailable players, and IR players awaiting activation are excluded from new starter assignments. Questionable players remain eligible and show their injury status. Missing projections remain unavailable, and empty slots are shown explicitly. Unsupported starting positions such as IDP produce an explanatory error.

This recommends changes for you to make in ESPN. It does not submit lineup changes, pickups, drops, or waiver claims. Projections use full-PPR offense and the app's K/DST scoring, so custom ESPN scoring can differ. Future-week suggestions use current rosters and injury statuses. Free-agent searches consider up to 1,000 available players; waiver priority, budgets, acquisition limits, and positional roster caps must still be checked in ESPN.

The public endpoint accepts `league_id`, `season`, `team_id`, `week`, and optional `include_free_agents` (default `false`) and `refresh` (default `false`). The guarded local equivalent uses the configured league and accepts only the team, week, and options. Optimization reuses existing model/data caches, checks current ESPN rosters, and does not retain a browser session copy of recommendations. The open page rechecks when a recommended player's kickoff passes. Locked slots use saved pregame projections; without one, full totals stay unavailable while improvement can still be calculated for movable slots.

## Trade analyzer

Open **Trade analyzer**, choose two teams, and select the players each team sends. Choose an **Effective week** and **Last week to include** (for example, Week 17 if that is your fantasy championship). Select **Analyze trade** to compare:

- Individual traded players' projected points for the effective week and the full selected horizon.
- Each team's optimized starting-lineup points before/after the exchange, for the effective week, each later week, and the horizon total.
- Position needs relative to the league's average starting-slot points, the incoming players who would start, and changes in eligible bench backups for the effective week.
- Projected league power ranks before/after, based on average optimized starting-lineup points across the selected weeks. These measure roster strength rather than standings or playoff probability.

The verdict compares **marginal starting-lineup improvement**, not the sum of the players exchanged. Trading a strong bench player for a needed starter can benefit both teams. Differences of no more than 0.5 points per week between the teams' gains are labelled fairly even. Byes, NFL opponents, ESPN slot counts, FLEX/Superflex eligibility, kickoff locks, and current injury/IR statuses are considered. If a traded player has already kicked off or has an unknown kickoff, choose a later effective week. Unequal packages and full rosters are allowed; no drops are chosen, no open roster space is checked, and no free-agent replacements are assumed.

This uses the existing projection models, with currently available player histories for each upcoming opponent; it does not recursively invent future game results or need another model. Future health, returns from IR, NFL role changes, and injuries are unknown, so **remaining-season totals are scenarios using current health and roles**, not a validated season-long forecast. Review the per-week breakdown and choose a sensible horizon. AI points still use full-PPR offense and the app's K/DST rules, not custom ESPN scoring. Missing forecasts are shown as unavailable; full-horizon totals/verdicts remain incomplete rather than silently summing partial weeks. Power ranks are withheld when any team's full horizon is incomplete. Backup counts overlap when a player is eligible for multiple slot types.

Roster selection is lightweight. Analysis builds each league/week once through the existing model projection cache, so the first multi-week analysis can take longer and subsequent proposals reuse those forecasts. Hypothetical rosters never change ESPN or write hypothetical values to prediction history. ESPN ownership is rechecked on submission. Trade processing delays, league vetoes, keeper/dynasty value, waiver pickups, and playoff simulations are outside this analysis.

`POST /api/espn/trade-analysis` accepts `league_id`, `season`, `team_a_id`, `team_b_id`, `team_a_player_ids`, `team_b_player_ids`, `week`, and `end_week`. Each side sends 1–10 unique ESPN IDs, including negative D/ST IDs where applicable. The private equivalent uses the authenticated saved connection and accepts the trade fields without connection fields. Both routes require owner authentication in production.

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

- My Team, Matchup, and Players keep up to 12 recently loaded views in browser session storage for 15 minutes. Returning to a view shows saved results immediately while checking the API for updates. Background failures keep the saved view visible with an error. Connection mode, API URL, league, season, week, and team separate entries; changing leagues or successfully forcing a data refresh clears saved views. Browser storage is optional and stores no ESPN credentials.
- Identical frontend requests share an in-flight HTTP call. Completed calls are not reused by this mechanism, so background checks still contact the backend. Responses from a previous team/week request cannot replace the currently selected view.
- The backend console logs request duration, response status, weekly and ESPN cache hits/misses, data loading, feature preparation, position service setup, and batched projections. Stage timings include `duration_ms` and report failures as `outcome=error`.
- API responses include `X-Response-Time-ms` (time until response headers are ready), also accessible from the frontend. Request logs exclude query strings and bodies.
- Models and prepared NFL data are cached and shared by the weekly and ESPN projection routes per backend process (up to two seasons).
- Regular weekly projections are cached for 15 minutes per season, week, and position (up to 128 entries per season service). Concurrent requests share the computation. Unexpired projections now survive backend restarts; expiry recomputes predictions using the service's loaded data.
- My Team and Matchup display when projections were last generated, in your local timezone. Refresh reloads the season's NFL data, rebuilds model features, and regenerates projections without restarting the backend. Previous results stay visible during refresh and on failure, with a retry option.
- API clients can send `"refresh": true` in public/local team-projection and matchup POST bodies, or `refresh=true` on the weekly prediction GET route. Normal requests reuse cached results and preserve their original generation timestamps. Refresh can take as long as a first load; upstream sources may still have no new data.
- Each model prints its actual CPU or CUDA device when loaded, including the GPU name when CUDA is used. Models load on the first request for their position.
- Inference is batched by position instead of running players individually.
- ESPN projections are generated for the whole fantasy league and cached for six hours.
- The cache key includes a roster fingerprint and the loaded data's generation, so roster changes and successful data refreshes produce new entries. Requests already running against older data cannot overwrite refreshed results. A failed data reload keeps the previous season service.
- Injury status is applied after the base projection is loaded from cache. Confirmed unavailable players receive an adjusted projection of zero, while questionable and doubtful players retain their base projection with a warning.

Prepared NFL data, special-teams weekly tables, and projection results are also saved locally in `backend/cache/runtime.sqlite3` (Git-ignored). NFL and special-teams snapshots expire after six hours; league projections expire six hours after generation, and regular weekly projections after 15 minutes. Cache reads do not extend expiry. On restart, valid snapshots open without decoding every table: cached team projections need no NFL tables, and other tables load individually on demand. Valid projections skip inference. The first uncached load still takes time. Normal requests keep using the previous service while a forced data refresh runs.

Cache keys include source-code fingerprints, the selected checkpoint contents, the NFL data generation, and the relevant request/roster inputs. Refresh bypasses saved NFL data and creates a new generation. Expired entries are pruned; disk storage is limited to four NFL snapshots, four special-teams snapshots, 32 league projections, 128 weekly projections per generation, and 256 entries overall. Unreadable or invalid entries fall back to normal computation. This is a local single-host cache; shared hosting still needs shared storage.

Set the `FANTASY_CACHE_PATH` environment variable before starting the backend to choose another cache file. To reset all saved entries, stop the backend and delete only `backend/cache/runtime.sqlite3`. ESPN credentials are not stored in this disk cache. ESPN league connections are reused in memory for up to 15 seconds to avoid downloading the league twice during Connect followed by projections. Different credentials have separate entries; Refresh bypasses this short cache to fetch current roster/availability.

## Matchup win chance

Matchup shows an estimated pregame win percentage for each team. It sums projected starter points and approximates their combined variability using up to 16 prior scoring games per offensive player, with position defaults for limited history, kickers, and D/ST. Short histories are shrunk toward the defaults. Bench and IR players are excluded; bye and confirmed unavailable players contribute zero. Missing starter projections produce an unavailable message instead of a misleading percentage.

The calculation assumes independent player scores and a normal distribution of the scoring difference. It is a rough estimate, has not been validated against actual matchup outcomes, and does not incorporate live ESPN scores or game progress. Player-point accuracy tracking and floor/ceiling estimates are available below; matchup-probability calibration remains future work.

## Prediction accuracy tracking

Open **Accuracy** in the connected league dashboard. Normal projection requests save the points you viewed on My team, Matchup, and Players, including live injury adjustments. League history is separated by ESPN league ID. The regular weekly projection API, projection CLI, and automatic NFL captures save a separate weekly history. The scheduler also saves league projections without needing to visit each team's page. Browser-only cached views need their normal background API request to complete before a manual page view can save a prediction.

The latest saved projection for each player, position, season, and week is updated only before that player's scheduled kickoff, then frozen. Kickoffs use the schedule's Eastern time, including daylight-saving changes. Both generation time and recording time must precede kickoff. Postgame projections, byes, skipped/unmatched players, and games with unknown kickoff times are excluded. A cached pregame result can be saved while the game is still in the future. Tracking starts when this feature is installed; it does not manufacture a historical prediction record.

Results sync automatically as described below, or click **Sync results** to fetch published NFL stats yourself. Syncing does not load models or rebuild feature tables. Games must have published game scores and be at least 12 hours past kickoff. Offense uses `fantasy_points_ppr`, matching the model targets; K/DST use the same play-by-play scoring functions as training. These are the app's scoring rules, **not custom ESPN league scoring**. Missing or ambiguous player stats remain pending, including players with no stat row; missing data is never treated as a zero-point game. Subsequent syncs apply stat corrections. K/DST syncs may take longer because they download play-by-play data. A failed sync preserves saved history.

### Automatic capture and sync

Automatic tracking is enabled by default with the normal API startup, including Docker. Keep the backend running: a sleeping or stopped laptop cannot capture predictions, and past games are never backfilled with hindsight. Saving a private league, or connecting a public league, registers it for future automatic captures. Job records contain only the league ID, season, and connection mode; saved private credentials are decrypted from the separate account store at execution time. Removing a saved connection stops its enrollment, and connections marked as requiring new cookies are skipped until updated. In authentication-disabled native development only, an enabled local environment configuration can still be enrolled automatically. On upgrade, import the old server-configured private league once through the owner UI to resume its league captures. Registration and status survive restarts in the history database.

A background worker checks once per minute, with network work starting after API startup. During the six hours before a regular-season kickoff, it captures every 15 minutes. Weekly NFL captures cover QB/RB/WR/TE/K/DST for the approaching games, using the latest available roster if that week's roster is not published. League captures use the same roster/free-agent matching, QB starter signals, and live injury adjustments as the Players page. Existing kickoff locks still apply at write time. The current NFL season includes the previous calendar year during January and February. Models and prepared NFL data are shared with normal requests. When a capture needs a season service that has been loaded for over six hours, the scheduler refreshes it through the existing registry, which keeps its previous service usable during a refresh.

Automatic results syncing starts from 8 a.m. Eastern the following day, and never earlier than 12 hours after kickoff. It repeats every six hours for games in the last 14 days, allowing late publications and stat corrections. Older results remain available through manual **Sync results**. There are no results downloads when no saved recent games qualify. Schedule planning reuses its download for 30 minutes. Failed captures, syncs, and schedule downloads retry after 15 minutes. Capture and sync work is serialized through a process-shared file lock beside the history database; another API worker, reloader, or manual sync cannot duplicate an active job. An interrupted job is retried once that lock is released, preserving any predictions already saved. This coordinates workers using the same local history file; it is not a distributed scheduler across separate machines or separate native/Docker databases.

The **Automatic tracking** panel shows the last scheduler check, last successful capture and sync, counts, failures, and retry times. The Accuracy page refreshes its status and history every minute while open. Status reads never download NFL or ESPN data. The scheduler stops scheduling new jobs on shutdown; a running network/inference operation cannot always be interrupted immediately. Set `FANTASY_AUTOMATION_ENABLED=false` before starting the backend to disable automation while retaining manual capture and sync.

The view includes projected versus actual points, mean absolute error (MAE), mean signed error (projected minus actual), per-position metrics, a weekly trend, and model/fallback groups. Only scored records enter error averages. Positive signed error means overprediction. Model labels and a checkpoint-set content fingerprint are saved with each prediction, alongside method, kickoff, generation, recording, and actual-update timestamps. The revision identifies the selected set of checkpoint files; fallbacks are labelled separately from model predictions. Small samples and pending results can make early averages unrepresentative.

### Range coverage, error patterns, and ESPN comparison

The Accuracy page also shows cumulative percentages within 2, 5, and 10 points; median and 90th-percentile absolute misses; RMSE (which gives large misses more weight); and seven non-overlapping under/overprediction buckets. A forecast exactly two points away is in the central bucket, five points away is in the 2–5 bucket, and ten points away is in the 5–10 bucket. All figures use the entire selected season/week/position/history cohort, before table pagination.

Floor/ceiling coverage uses only graded forecasts with usable bounds saved before kickoff. It shows scores below the floor, inside the range (including its boundaries), or above the ceiling, plus average range width and per-position coverage. Missing historical ranges stay missing instead of being regenerated from today's calibration. The current calibration targets 80% coverage; observed coverage and sample sizes are shown separately.

New league captures and My team/Matchup/Players projection requests archive ESPN's **week-specific projected offensive stat breakdown**, converted to standard full-PPR scoring: passing yards/25, passing TDs ×4, interceptions ×−2, rushing/receiving yards/10, rushing/receiving and kick/punt return TDs ×6, receptions ×1, passing/rushing/receiving two-point conversions ×2, and lost fumbles ×−2. This follows the offensive scoring used by the app's NFL results; it deliberately ignores custom league bonuses and ESPN's league-applied projected points. See the source definitions in [nflfastR](https://github.com/nflverse/nflfastR/blob/master/R/calculate_stats.R) and the [ESPN API player documentation](https://github.com/cwendt94/espn-api/wiki/Player-Class).

The comparison is limited to QB/RB/WR/TE. K/DST require a separate scoring conversion and are excluded. Missing, invalid, wrong-week, and season-average ESPN data never become zero forecasts. Genuine zero projections remain valid. ESPN observations are timestamped independently from the AI's generation time, updated only before kickoff, and frozen with the prediction. A fresh ESPN observation can be saved even when the displayed cached AI generation is older than the archived AI; the newer archived AI stays intact. Old records gain nullable ESPN fields without changing their scores or ranges; past ESPN forecasts are never backfilled. If a newer pregame request has no ESPN breakdown, the most recent valid ESPN observation for the same game is retained.

AI and ESPN errors are calculated on **exactly the same paired players and published NFL outcomes**. The page shows each source's MAE, closer-prediction counts/ties, and error reduction (ESPN MAE minus AI MAE; positive favors AI), including a per-position breakdown. Forecasts without a saved ESPN counterpart remain part of normal AI accuracy but are excluded from this head-to-head comparison. Pending pairs and sample counts are explicit; a small early sample does not establish a consistent winner. No additional cron jobs, models, or external downloads are needed to read these statistics.

## Floor/ceiling estimates and live scores

My team, Matchup, and Players share the same score display. Before kickoff it shows **Ceiling**, the main **AI prediction**, then **Floor** vertically. Once a game starts it shows the **ESPN live score** above the **saved AI pregame prediction**, and retains this comparison with a Final label after the game. The matchup headline also switches to the displayed starters' live totals with AI projections underneath. Missing live points stay unavailable rather than becoming zero. A first visit after kickoff with no saved pregame forecast shows **Not saved before kickoff**; it never relabels a newly generated postgame forecast as the original. Old records without saved bounds remain unchanged. Existing history databases add nullable range columns automatically without replacing stored predictions.

Ranges are estimated low/high outcomes, not minimum/maximum guarantees. The included `backend/app/config/projection_ranges.json` was calibrated on 2025 regular-season weeks 1–12 and evaluated separately on weeks 13–18. Every selected checkpoint was trained on 2020–2022, selected using 2023, and previously tested on 2024, so this range evaluation uses a later season. It fits the 10th/90th percentiles of actual-minus-predicted errors separately by position and projection method, widening bounds to include the main projection if needed. The six main-model ranges covered approximately 81–85% of the later 2025 validation outcomes for an 80% target. The tooltip reports the applicable sample count and observed coverage. Negative floors are allowed. Methods without at least 100 calibration and 50 validation samples show Range unavailable. Bounds are tied to each checkpoint's SHA-256 hash, so replacing a model disables its old calibration until regenerated. The main model predictions are unchanged.

To regenerate the artifact after changing checkpoints, use an evaluation season later than every training/validation/test season saved in the checkpoint:

```powershell
cd backend
python -m app.scripts.calibrate_ranges --season 2025 --split-week 12
```

The script reuses completed-season NFL/special-teams cache tables when available, including expired snapshots for this offline evaluation, and otherwise downloads the required public data. It does not write retrospective forecasts into prediction history or retrain models. Range generation is separate from normal page requests. Automated and manually viewed pregame forecasts save their current ranges alongside the point prediction, under the same kickoff lock.

Live/final points use **your ESPN league's scoring rules**, while AI projections/ranges and historical accuracy use **full PPR offense and the app's K/DST rules**. They can differ in custom-scoring leagues. The game-state feed uses ESPN's NFL scoreboard status, not a fixed elapsed-game timer. Points come from actual stat entries for the selected season/week through ESPN's player-card API; projected stat entries are never used as live points. The requested scoreboard season/week and regular-season type are checked before applying a status. Unavailable/postponed game states are labelled explicitly.

Visible pages check the separate `/api/espn/live` or guarded `/api/espn/local/live` POST route every 30 seconds and resume on returning to the tab. Requests contain the displayed players' ESPN IDs plus their NFL IDs, position, and team for frozen-prediction lookup; negative ESPN defense IDs are supported. Game and score responses have short 20-second memory caches; private score cache keys include a credential hash. Pregame-only requests do not download league/player cards. Active/final player cards are batched, with up to three concurrent provider requests. Polling never runs models, rebuilds feature data, or changes saved pregame predictions. Feed failures show an unavailable/stale notice with the last successful check time. The original pregame win-chance estimate remains labelled as such; it is not a live win-probability model.

History is stored in `backend/data/predictions.sqlite3` locally, or the separate Docker volume above, with no TTL or cache pruning. Set `FANTASY_HISTORY_PATH` before starting the backend to choose another file. The directory is Git-ignored and excluded from Docker image builds. Back up the database while the backend is stopped. It contains NFL player projections and league-ID scopes, not ESPN credentials or fantasy-team names.

API endpoints (season 2020 through the current year):

- `GET /api/accuracy/{season}` reads history without NFL downloads. Optional `league_id` selects league history; omit it for weekly API history. Filters: `week`, `position` (`QB/RB/WR/TE/K/DST`), `limit` (1–200), `offset`. The weekly trend spans all weeks for the chosen position; other summary metrics honor the week filter.
- `POST /api/accuracy/{season}/sync` fetches results for that season and optional `league_id` scope. It does not refresh projections or alter frozen forecasts. No history means no download.
- `GET /api/accuracy/{season}/automation` returns persisted capture/sync status for the optional `league_id` scope. Manual syncs update the same status and respect the scheduler's lock.
- `POST /api/espn/live` accepts `league_id`, `season`, `week`, and a `players` array (`espn_id`, optional `player_id`, `position`, `team`). `/api/espn/local/live` takes only `week` and `players`, uses configured server credentials, and retains the existing local-access guard. These routes return live/final points, game status, and frozen-prediction metadata without model inference.

## Tests

From `backend/`:

```powershell
python -m pytest tests -v
```

The test suite covers time-aware player histories, pregame defense construction, roster and depth-chart selection, ESPN player matching, league projection caching, injury adjustment, prediction-history persistence and kickoff locks, result reconciliation, automatic job cadence/recovery/locking, and API response contracts. Tests isolate history/cache files and disable the live scheduler unless explicitly testing it.

`backend/pytest.ini` limits default discovery to `tests/`, keeping the interactive legacy `xgb_test.py` training script out of collection.

Frontend cache and request-deduplication tests run from `frontend/` with `npm.cmd test` (verified with Node 26, using built-in TypeScript stripping). Run `npm.cmd run build` and `npm.cmd run lint` for frontend checks.

## Current limitations and roadmap

The next planned work is:

1. Train and evaluate injury-context checkpoints before promoting them to production.
2. Move the local SQLite cache to shared storage if deploying multiple API hosts.
3. Extend automatic capture/sync with scheduled evaluation and optional retraining.
4. Add production deployment configuration, meaningful readiness checks, restricted CORS, HTTPS, logging, and monitoring.

Additional modeling improvements include rolling-origin evaluation, formal PyTorch feature-importance analysis, player-specific range models, and matchup-probability calibration.

## Security notes

- Never commit `.env` files, ESPN cookies, or other credentials.
- Never log `ESPN_SWID` or `ESPN_S2`.
- The current wildcard CORS configuration is intended for development and must be restricted before deployment.
- The local credential-backed ESPN API is not intended to expose one developer's cookies to public users.
- External NFL and ESPN data sources are network-dependent and can change independently of this project.

## Disclaimer

This project is for educational and personal fantasy-football analysis. It is not affiliated with or endorsed by the NFL or ESPN. ESPN integration relies on an unofficial API and may change without notice.
