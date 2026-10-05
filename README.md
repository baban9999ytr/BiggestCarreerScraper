# Kariyer.net ATS Automation API

[![Python Support](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![CI Status](https://github.com/baban9999ytr/pythongeneraljobscraper/actions/workflows/ci.yml/badge.svg)](https://github.com/baban9999ytr/PictureFormatter/actions/workflows/ci.yml)

Kariyer.net ATS Automation API is a Python/FastAPI service that uses Playwright to sign in to the Kariyer.net employer ATS, handle CAPTCHA and two-factor authentication (2FA), inspect job listings, and export job and candidate data.

A browser UI is served at `/index`. The service can also be used directly through REST endpoints, Server-Sent Events (SSE), and WebSocket endpoints.

> This project is an automation tool for authenticated Kariyer.net employer accounts. It is **not** an official Kariyer.net API client.

## Features

- Token-based asynchronous login sessions
- Playwright/Chromium browser automation for Kariyer.net ATS
- CAPTCHA automation with configurable provider (CapSolver, NoCaptcha AI)
- Email or SMS 2FA selection, code submission, and resend support
- Extraction of active, passive, draft, and archived job listings
- Candidate-detail extraction and JSON/CSV exports
- Applicant filtering through ATS UI controls
- Webhook support for posting extracted job data to external services
- Live browser-session streaming over WebSocket (JPEG frames, pointer control)
- FastAPI OpenAPI documentation at `/docs` and `/redoc`
- Optional auto-solver validation mode (`--autosolvetester`) with periodic debug screenshots
- On-demand outbound proxy support (`OUTBOUND_PROXY` env var)
- Structured logging with automatic credential/token masking

## Scope and limitations

Use this service only with accounts and data that you are authorized to access. You are responsible for complying with:

- Kariyer.net terms and policies
- Applicable privacy and data-protection law, including KVKK where applicable
- CAPTCHA and anti-bot restrictions
- The repository's `PRIVACY.MD` notice

The current implementation should be treated as a development or internal-service baseline.

- Sessions are stored in process memory plus a local SQLite metadata store. Memory state is lost when the service restarts; the metadata store survives restarts.
- Supabase ingestion is optional and has no migration system.
- Session tokens are bearer credentials. Do not expose them in logs, URLs, screenshots, browser storage, or client-side analytics.
- Export files are served exclusively through `/download-export/{token}/{filename}` — `exports/` is not mounted as a public static route.
- `/process-jobs` uses the validated `ExportRequest` model from `app/models/schemas.py`. The `filters` field supports candidate filters, but live ATS selectors may need maintenance when Kariyer.net changes its UI.
- The caller-provided webhook functionality is protected against SSRF via `app/core/url_validation.py`. Restrict `ALLOWED_ORIGINS` before public deployment.
- The WebSocket livestream exposes the active browser screen and pointer controls. It must be authenticated and authorized in production.

## Tech stack

| Area               | Technology                                                                             |
| ------------------ | -------------------------------------------------------------------------------------- |
| Language           | Python 3.10+                                                                           |
| API                | FastAPI, Uvicorn, Pydantic 2                                                           |
| Browser automation | Playwright with Chromium                                                               |
| HTTP clients       | `aiohttp`, `requests`, `curl_cffi`                                                     |
| CAPTCHA/OCR        | GeekedTest, OpenCV, NumPy, `ddddocr`                                                   |
| Configuration      | `pydantic-settings`, environment variables, `.env` file                                |
| Persistence        | Local JSON/CSV files, SQLite metadata store (`aiosqlite`), optional Supabase ingestion |
| Frontend           | Static HTML/JS dashboard served at `/index` from `public/index.html`                   |

## Prerequisites

- Python 3.10 or newer (3.11+ recommended for Playwright compatibility)
- `pip` and a virtual environment
- Chromium installed through Playwright (`playwright install chromium`)
- Network access to `ats.kariyer.net`, GeeTest assets, and configured webhook URLs
- A Kariyer.net employer account authorized to access the relevant ATS data

## Installation

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
playwright install chromium
```

Or install from `requirements.txt` directly:

```powershell
pip install -r requirements.txt
playwright install chromium
```

## Environment variables

Copy `.env.example` to `.env` and fill in your values. Never commit real credentials or keys.

```dotenv
# Application environment
APP_ENV=development

# CORS — comma-separated list of allowed origins (no wildcards)
ALLOWED_ORIGINS=http://localhost:8000,http://localhost:3000

# Kariyer.net account credentials
KARIYER_EMAIL=company@example.com
KARIYER_PASSWORD=replace-with-a-secret

# Session TTL in seconds (default: 6 hours)
SESSION_TTL_SECONDS=21600

# Storage directories (defaults are ./exports, ./screenshots, ./debug)
# EXPORT_DIR=/absolute/path/to/exports
# SCREENSHOT_DIR=/absolute/path/to/screenshots
# DEBUG_DIR=/absolute/path/to/debug

# CAPTCHA solver (optional)
# CAPTCHA_PROVIDER=capsolver          # or: nocaptcha
# CAPTCHA_API_KEY=your-api-key

# Outbound proxy for browser contexts and HTTP clients (optional)
# OUTBOUND_PROXY=http://proxy.example.com:8080

# Supabase ingestion (optional)
# SUPABASE_URL=https://your-project.supabase.co
# SUPABASE_KEY=your-service-role-key
# ENABLE_TELEMETRY=true

# CV scrape delay between candidate page requests (default: 30 seconds)
# CV_SCRAPE_DELAY_SECONDS=30
```

## Starting the server

```powershell
python main.py
```

Or with `uvicorn` directly:

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/index` for the browser UI, or `http://localhost:8000/docs` for the Swagger interactive docs.

## Running the auto-solver tester

The `--autosolvetester` flag runs a headless login loop against `KARIYER_EMAIL`/`KARIYER_PASSWORD` and writes periodic debug screenshots:

```powershell
python main.py --autosolvetester
```

Use this only with a dedicated test account. The server does not start in this mode; it exits after the login flow completes.

## Outbound proxy

Set `OUTBOUND_PROXY` in `.env` to route all browser traffic and outbound HTTP calls through a proxy:

```dotenv
OUTBOUND_PROXY=http://proxy.example.com:8080
# or with credentials:
# OUTBOUND_PROXY=http://user:pass@proxy.example.com:8080
```

Leave it unset (the default) to connect directly. The proxy setting is applied automatically via `app/core/proxy.py` — no code changes are needed to toggle it.

## Security

The following security controls are implemented:

- Strict CORS allowlist — wildcards are rejected at startup
- WebSocket sessions authenticated before `accept()` is called
- SSRF protection for caller-provided webhook URLs
- Path-traversal protection on all export downloads
- Credential and token masking in structured logs
- CAPTCHA API keys stored as `SecretStr`, never logged or serialized

Do not expose the default CORS policy, unauthenticated WebSocket controls, or caller-defined webhook endpoints to the public internet without a reverse proxy that adds TLS termination, rate limiting, and access control.

## API

All REST request bodies use JSON. Authenticated operations use a generated session `token` in the request body or URL path.

### Health and documentation

| Method | Route           | Description                           |
| ------ | --------------- | ------------------------------------- |
| GET    | `/`             | Returns `{"status":"online"}`         |
| GET    | `/health`       | Returns `{"status":"healthy"}`        |
| GET    | `/index`        | Serves `public/index.html` browser UI |
| GET    | `/docs`         | Swagger UI                            |
| GET    | `/redoc`        | ReDoc API documentation               |
| GET    | `/openapi.json` | OpenAPI schema                        |

### Authentication and sessions

| Method | Route                     | Description                                      |
| ------ | ------------------------- | ------------------------------------------------ |
| POST   | `/login`                  | Starts a background Kariyer.net login session    |
| GET    | `/session-status/{token}` | Retrieves the current session and login state    |
| GET    | `/stream-status/{token}`  | Streams public session-state updates through SSE |
| POST   | `/submit-2fa-choice`      | Selects `email` or `sms` as the 2FA method       |
| POST   | `/submit-2fa-code`        | Submits a received 2FA code                      |
| POST   | `/resend-2fa-code`        | Requests a new 2FA code                          |
| POST   | `/close-session`          | Terminates the browser session                   |

#### Start login

```http
POST /login
Content-Type: application/json
```

```json
{
  "email": "company@example.com",
  "password": "your-password"
}
```

Example response:

```json
{
  "status": "initiating",
  "token": "<uuid>",
  "status_url": "/session-status/<uuid>",
  "livestream_url": "/ws/livestream/<uuid>",
  "verification_url": "/?token=<uuid>"
}
```

Open `/?token=<uuid>` in a browser to use the interactive UI, or poll `/session-status/<uuid>` directly.

#### Select 2FA method

```http
POST /submit-2fa-choice
Content-Type: application/json
```

```json
{
  "token": "<uuid>",
  "method": "email"
}
```

Supported methods: `email`, `sms`

#### Submit 2FA code

```http
POST /submit-2fa-code
Content-Type: application/json
```

```json
{
  "token": "<uuid>",
  "code": "123456"
}
```

#### Resend 2FA code

```http
POST /resend-2fa-code
Content-Type: application/json
```

```json
{
  "token": "<uuid>"
}
```

#### Close session

```http
POST /close-session
Content-Type: application/json
```

```json
{
  "token": "<uuid>"
}
```

### Extraction and exports

| Method | Route                                 | Description                                                  |
| ------ | ------------------------------------- | ------------------------------------------------------------ |
| POST   | `/process-jobs`                       | Starts background job extraction                             |
| GET    | `/export-status/{token}`              | Returns job-export progress and result metadata              |
| POST   | `/process-candidate-details`          | Starts candidate-detail extraction from the current ATS page |
| GET    | `/candidate-details-status/{token}`   | Returns candidate extraction progress and metadata           |
| POST   | `/handle-jobs/{token}`                | Extracts jobs and posts the payload to a webhook URL         |
| GET    | `/download-export/{token}/{filename}` | Securely serves a generated export file                      |

#### Process jobs

```http
POST /process-jobs
Content-Type: application/json
```

```json
{
  "token": "<uuid>",
  "limit": 10
}
```

`limit` is optional (default: `100`, max: `5000`).

Poll the result:

```http
GET /export-status/<uuid>
```

When `is_processing` becomes `false` and `result.status` is `"completed"`, the response includes `result.exports`:

```json
{
  "result": {
    "status": "completed",
    "count": 10,
    "exports": {
      "json": "/download-export/<uuid>/kariyer_jobs_<uuid>_<id>.json",
      "csv": "/download-export/<uuid>/kariyer_jobs_<uuid>_<id>.csv"
    }
  }
}
```

The browser UI renders these as clickable download buttons automatically.

#### Process candidate details

```http
POST /process-candidate-details
Content-Type: application/json
```

```json
{
  "token": "<uuid>"
}
```

Poll result:

```http
GET /candidate-details-status/<uuid>
```

#### Send extracted jobs to a webhook

```http
POST /handle-jobs/<uuid>
Content-Type: application/json
```

```json
{
  "target_url": "https://example.com/api/webhook",
  "limit": 10
}
```

The `target_url` is validated against SSRF rules before the request is made.

## Filtering

`/process-jobs` accepts a `filters` object. Example:

```json
{
  "token": "<uuid>",
  "limit": 50,
  "filters": {
    "personal": {
      "gender": { "male": true, "female": false },
      "age_range": { "min_age": 22, "max_age": 35 },
      "military_status": ["Yapıldı", "Muaf"],
      "languages": [{ "language": "İngilizce", "min_level": "İleri" }]
    },
    "education": {
      "levels": ["Lisans", "Yüksek Lisans"]
    },
    "experience": {
      "experience_type": "experienced",
      "position_scope": "all_jobs"
    }
  }
}
```

Full filter schema is defined in `app/models/schemas.py`.

## Livestream WebSocket

```text
ws://localhost:8000/ws/livestream/{token}
```

The server streams JPEG screenshot bytes from the active Playwright browser session. The client can send pointer control events as JSON:

```json
{ "action": "click", "x": 500, "y": 320 }
```

Supported actions: `click`, `mousedown`, `mousemove`, `mouseup`

Do not expose this endpoint without strong authentication and authorization.

## Browser UI

Navigate to `http://localhost:8000/index` (or `/?token=<uuid>` after login) to use the browser UI.

**Login flow:**

1. Enter your Kariyer.net employer email and password
2. The UI polls `/stream-status/{token}` via SSE and transitions automatically through CAPTCHA, 2FA choice, and 2FA code states
3. Once authenticated, a "Process Jobs?" button appears with a configurable limit field
4. After extraction completes, JSON and CSV download buttons appear automatically

The UI calls the same REST endpoints as the API and requires no separate configuration.

## Example PowerShell workflow

```powershell
$login = @{
    email = "company@example.com"
    password = "your-password"
} | ConvertTo-Json

$session = Invoke-RestMethod `
    http://localhost:8000/login `
    -Method Post `
    -ContentType "application/json" `
    -Body $login

$token = $session.token

# Poll until login succeeds or a 2FA state is returned.
Invoke-RestMethod "http://localhost:8000/session-status/$token"

$choice = @{ token = $token; method = "email" } | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/submit-2fa-choice `
    -Method Post -ContentType "application/json" -Body $choice

$code = @{ token = $token; code = "123456" } | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/submit-2fa-code `
    -Method Post -ContentType "application/json" -Body $code

$jobs = @{ token = $token; limit = 1 } | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/process-jobs `
    -Method Post -ContentType "application/json" -Body $jobs

Invoke-RestMethod "http://localhost:8000/export-status/$token"
```

## Project structure

```text
main.py                                  FastAPI app entry point
openapi.json                             Generated OpenAPI schema (updated on startup)
config.py                                Compatibility shim — re-exports from app/core/config.py
models.py                                Compatibility shim — re-exports from app/models/
schemas.py                               Compatibility shim — re-exports from app/models/schemas.py
supabaser.py                             Compatibility shim — re-exports from app/services/supabase_service.py
automation.py                            Kariyer.net login, CAPTCHA, and 2FA automation
automation_process_jobs.py               Job-list and candidate extraction pipeline
automation_extract_candidate_details.py  Candidate-detail extraction
pyproject.toml                           Project configuration, dependencies, test and lint settings
requirements.txt                         pip-compatible dependency list
.env.example                             Environment variable template

app/
  core/
    config.py                            AppSettings (pydantic-settings) — single source of truth
    proxy.py                             Outbound proxy helpers for Playwright and HTTP clients
    browser_manager.py                   Playwright lifecycle manager (startup/shutdown)
    metadata_store.py                    SQLite metadata persistence (aiosqlite)
    logger.py                            Structured logging with secret masking
    export_security.py                   Path-traversal and extension validation for exports
    cors.py                              CORS origin resolver
    url_validation.py                    SSRF validation for webhook target URLs
    ws_auth.py                           WebSocket pre-accept authentication
    openapi.py                           OpenAPI schema export helper
  api/
    routers/
      auth.py                            Login, 2FA, session-status, SSE, WebSocket routes
      jobs.py                            Job extraction, candidate details, export, webhook routes
      system.py                          Health, index, and export download routes
      api_router.py                      Aggregates all routers
    dependencies.py                      require_session FastAPI dependency
  models/
    schemas.py                           Pydantic request/response models
    session.py                           Session dict builders
  services/
    job_filter_service.py                Pure candidate filtering functions
    supabase_service.py                  Supabase ingestion logic

tests/
  conftest.py
  test_config.py
  test_auth_routes.py
  test_filtering.py
  test_export_security.py
  test_phase2.py

scripts/
  cleanup_legacy.py                      Legacy file removal helper
  cleanup_root.py                        Root directory audit helper
  export_openapi.py                      CLI schema exporter

public/
  index.html                             Browser UI dashboard

html_stuff/                              Reference/captured Kariyer HTML pages
kariyer_ats/                             JS extraction workspace (not imported by Python)
GeekedTest/                              GeeTest/CAPTCHA helper package and model assets
exports/                                 Generated JSON/CSV files (git-ignored)
debug/                                   Debug screenshots and artifacts (git-ignored)
screenshots/                             Screenshot output directory (git-ignored)
```

## Testing

Run the full test suite:

```powershell
pytest tests/ -v
```

Expected output: **21 tests passing** across config, auth routes, filtering, export security, and Phase 2 features.

Run basic import checks:

```powershell
python -c "import main; print('main OK')"
python -m compileall main.py config.py automation.py automation_process_jobs.py automation_extract_candidate_details.py
```

Validate `pyproject.toml`:

```powershell
python -c "import tomllib; tomllib.loads(open('pyproject.toml').read()); print('TOML OK')"
```

For safer live validation:

1. Start with `GET /health`.
2. Test login with a non-production account where possible.
3. Use a low extraction `limit`, such as `1`.
4. Avoid placing credentials, candidate data, session tokens, or CAPTCHA artifacts in screenshots and logs.
5. Verify that generated exports are excluded from Git.

## Contributing

1. Create a focused branch for each change.
2. Do not commit credentials, API keys, session tokens, exports, screenshots, or debug captures.
3. Update this README when routes, request models, environment variables, or launch behavior change.
4. Add automated tests for parsing, session state, and export behavior where practical.
5. Run smoke checks and document external-service limitations in pull requests.
6. Confirm that contributions comply with Kariyer.net terms and applicable privacy requirements.

See `PRIVACY.MD` for the deployment privacy notice.

## License

This project is distributed under the MIT License.

The current copyright holder is identified as `MUSTAFA GÖKSAL`. Update the license notice if the legal owner differs.
