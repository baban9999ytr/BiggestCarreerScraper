# Kariyer.net ATS Automation API


[![Python Support](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![CI Status](https://github.com/baban9999ytr/pythongeneraljobscraper/actions/workflows/ci.yml/badge.svg)](https://github.com/baban9999ytr/PictureFormatter/actions/workflows/ci.yml)


Kariyer.net ATS Automation API is a Python/FastAPI service that uses Playwright to sign in to the Kariyer.net employer ATS, handle CAPTCHA and two-factor authentication (2FA), inspect job listings, and export job and candidate data.

A small browser UI is available through `index.html`. The service can also be used directly through REST endpoints, Server-Sent Events (SSE), and WebSocket endpoints.

> This project is an automation tool for authenticated Kariyer.net employer accounts. It is **not** an official Kariyer.net API client.

## Features

- Token-based asynchronous login sessions
- Playwright/Chromium browser automation for Kariyer.net ATS
- CAPTCHA automation with a manual browser-stream fallback
- Email or SMS 2FA selection, code submission, and resend support
- Extraction of active, passive, draft, and archived job listings
- Candidate-detail extraction and JSON/CSV exports
- Applicant filtering through ATS UI controls
- Webhook support for posting extracted job data to external services
- Live browser-session streaming over WebSocket
- FastAPI OpenAPI documentation at `/docs` and `/redoc`
- Optional auto-solver validation mode with periodic debug screenshots

## Scope and limitations

Use this service only with accounts and data that you are authorized to access. You are responsible for complying with:

- Kariyer.net terms and policies
- Applicable privacy and data-protection law, including KVKK where applicable
- CAPTCHA and anti-bot restrictions
- The repository's `PRIVACY.MD` notice

The current implementation should be treated as a development or internal-service baseline.

- Sessions are stored in process memory and are lost when the service restarts.
- Supabase ingestion is optional and has no migration system; application sessions remain in memory.
- No automated test suite is currently implemented; `tests/` contains only a placeholder.
- CORS currently uses `allow_origins=["*"]` with credentials enabled. Restrict this before deployment.
- Session tokens are bearer credentials. Do not expose them in logs, URLs, screenshots, browser storage, or client-side analytics.
- Export paths may be returned by the API, but `main.py` does not currently mount `exports/` as a static route. Read generated files locally or add a protected download route.
- `/process-jobs` uses the validated `ExportRequest` model from `schemas.py`. Its `filters` field supports candidate filters, but the live ATS selectors can still require maintenance when Kariyer.net changes its UI.
- The caller-provided webhook functionality should be protected against SSRF before public deployment.
- The WebSocket livestream exposes the active browser screen and pointer controls. It must be authenticated and authorized in production.

## Tech stack

| Area | Technology |
| --- | --- |
| Language | Python 3.10+ |
| API | FastAPI, Uvicorn, Pydantic 2 |
| Browser automation | Playwright with Chromium |
| HTTP clients | `aiohttp`, `requests`, `curl_cffi` |
| CAPTCHA/OCR | GeekedTest, OpenCV, NumPy, `ddddocr` |
| Configuration | `python-dotenv`, environment variables |
| Persistence | Local JSON/CSV files, optional Supabase ingestion, and in-memory sessions |
| Frontend | Static HTML and browser JavaScript in `index.html` |

The root `requirements.txt` is the primary dependency manifest. `GeekedTest/requirements.txt` contains overlapping dependencies for the CAPTCHA helper package. `pyproject.toml` is currently empty.

## Prerequisites

- Python 3.10 or newer
- Python 3.11 or 3.12 is recommended for current Playwright compatibility
- `pip` and a virtual environment
- Chromium installed through Playwright
- Network access to `ats.kariyer.net`, GeeTest assets, and configured webhook URLs
- A Kariyer.net employer account authorized to access the relevant ATS data

For the optional Linux VNC launch path, also install:

- Xvfb
- Fluxbox
- x11vnc
- websockify
- noVNC

`start_all.sh` is Linux-oriented and is not a native PowerShell launcher.

## Environment variables

Create a local `.env` file and never commit real credentials, session tokens, CAPTCHA keys, exports, screenshots, or debug artifacts.

```dotenv
# Required only for --autosolvetester.
# Interactive /login accepts credentials in its JSON request body.
KARIYER_EMAIL=company@example.com
KARIYER_PASSWORD=replace-with-a-secret

# Optional service settings
KARIYER_LOGIN_URL=https://ats.kariyer.net
SESSION_TTL_SECONDS=21600
EXPORT_DIR=./exports
SCREENSHOT_DIR=./screenshots
DEBUG_DIR=./debug

# Optional CAPTCHA integrations.
# Configure the integration that your active flow actually uses.
CAPSOLVER_API_KEY=
NO_CAPTCHA_AI_KEY=

# Optional browser executable override.
# Normally not needed for a local Playwright Chromium installation.
PLAYWRIGHT_CHROME=

# Supabase ingestion
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=sb_publishable_replace-with-your-key
```

`CAPSOLVER_API_KEY` appears in some setup notes, while the current Python source explicitly reads `NO_CAPTCHA_AI_KEY`. Configure only the provider enabled in your automation flow.

## Database and ingestion setup

The optional ingestion worker in `supabaser.py` scans `exports/` for JSON files named `kariyer_jobs_*.json` and `kariyer_candidate_details_*.json`. It keeps only fields in the strict `TARGET_KEYS` allowlist, enriches each record with `executed_by` (the local device hostname) and `is_logged`, and inserts the cleaned records into the custom `scraping.job_postings` PostgreSQL table.

Configure `SUPABASE_URL` and the public Supabase publishable key (`sb_publishable_...`) in `.env`. The client selects the `scraping` schema and never requires a service-role key. RLS must be enabled on `scraping.job_postings` with an insert policy for `anon` and `authenticated` roles (`FOR INSERT TO anon, authenticated`), and without public `SELECT`, `UPDATE`, or `DELETE` policies. This makes the public key suitable for one-way record delivery: it can submit a JSON record, but cannot read, query, change, or erase records already stored.

After a file is processed, its filename is recorded in `extracted_jsons.json`, preventing it from being uploaded again. When job exports finish, `main.py` can run `process_and_upload` in a background thread with `asyncio.to_thread`, so ingestion does not block API request handling.

## Telemetry and opt-out configuration

Supabase uploading and the associated telemetry are opt-in. Before running ingestion, create a local `logging_optout.txt` file containing exactly:

```text
LET_LOG=TRUE
```

The value is case-insensitive. If the file is missing, contains `LET_LOG=FALSE`, or contains any other value, the worker logs a warning and aborts all Supabase uploads and telemetry enrichment. To disable external transmission immediately, set the value to `FALSE` or delete the `LET_LOG` line:

```text
LET_LOG=FALSE
```

When logging is active, the first three runs print a prominent warning explaining that telemetry and Supabase logging are enabled and how to opt out. The run count is stored locally in `.logging_warning_count.json`.

## Environment variables and files checklist

- Required for Supabase ingestion in `.env`: `SUPABASE_URL` and `SUPABASE_KEY`.
- Required opt-in file for upload: `logging_optout.txt` containing `LET_LOG=TRUE`.
- Keep local tracking and sensitive data out of source control: `extracted_jsons.json`, `.logging_warning_count.json`, `exports/`, and `.env` should be listed in `.gitignore`.
- Treat exports, screenshots, debug captures, credentials, and publishable-key configuration as local deployment data.

## Installation

### Windows PowerShell

```powershell
git clone <repository-url>
Set-Location .\LastRodeo

py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

If the repository includes `.env.example`, create your local environment file:

```powershell
Copy-Item .env.example .env
```

If it does not exist, create `.env` manually using the template above.

### Linux or macOS

```bash
git clone <repository-url>
cd LastRodeo

python3 -m venv .venv
. .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

If you add an `.env.example` file:

```bash
cp .env.example .env
```

If the Git-based `ddddocr` dependency fails to install, verify that Git is installed and available on `PATH`, then rerun the installation command.

## Running the service

### Development mode

From the repository root with the virtual environment enabled:

```powershell
python .\main.py
```

The service listens on:

```text
http://{ip}:8000
```

Useful endpoints:

- UI: `http://{ip}:8000/`
- Swagger UI: `http://{ip}:8000/docs`
- ReDoc: `http://{ip}:8000/redoc`
- OpenAPI schema: `http://{ip}:8000/openapi.json`
- Health check: `http://{ip}:8000/health`

### Auto-solver test mode

To test the configured login flow using `KARIYER_EMAIL` and `KARIYER_PASSWORD`:

```powershell
python .\main.py --autosolvetester
```

`config.py` defines a `--test` alias, but `main.py` documents and exposes `--autosolvetester`. Use `--autosolvetester` as the supported command.

### Production-oriented command

The application does not include a production process manager, persistent storage, migrations, or hardened authentication.

After addressing the security and persistence limitations, start it with:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Before exposing it outside a controlled environment, add:

- TLS termination
- Authentication and authorization
- Restricted CORS origins
- Rate limiting
- Secret management
- Log redaction
- Persistent session/state storage
- Process supervision
- Protected export downloads
- Webhook URL validation and SSRF protection

Do not expose the default CORS policy, unauthenticated WebSocket controls, or caller-defined webhook endpoint directly to the public internet.

### Optional Linux VNC mode

`start_all.sh` starts Xvfb, Fluxbox, x11vnc, noVNC/websockify, and then runs:

```bash
~/myenv/bin/python3 main.py
```

The script assumes those binaries are available and that the Python path exists exactly as written. VNC is bound locally without a password, so use it only in a controlled development environment.

## API

All REST request bodies use JSON.

There is no separate `Authorization` header in the current design. Authenticated operations use a generated session `token` in the request body or URL path.

### Health and documentation

| Method | Route | Description | Auth |
| --- | --- | --- | --- |
| GET | `/` | Returns `{"status":"online"}` | None |
| GET | `/health` | Returns `{"status":"healthy"}` | None |
| GET | `/index` | Serves `index.html` | None |
| GET | `/docs` | Swagger UI | None |
| GET | `/redoc` | ReDoc API documentation | None |
| GET | `/openapi.json` | OpenAPI schema | None |

### Authentication and sessions

| Method | Route | Description |
| --- | --- | --- |
| POST | `/login` | Starts a background Kariyer.net login session |
| GET | `/session-status/{token}` | Retrieves the current session and login state |
| GET | `/stream-status/{token}` | Streams public session-state updates through SSE |
| POST | `/submit-2fa-choice` | Selects `email` or `sms` as the 2FA method |
| POST | `/submit-2fa-code` | Submits a received 2FA code |
| POST | `/resend-2fa-code` | Requests a new 2FA code |
| POST | `/close-session` | Terminates the browser session and removes it from memory |

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
  "verification_url": "/stream-status/<uuid>"
}
```

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

Supported methods:

- `email`
- `sms`

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

| Method | Route | Description |
| --- | --- | --- |
| POST | `/process-jobs` | Starts background job extraction |
| GET | `/export-status/{token}` | Returns job-export progress and result metadata |
| POST | `/process-candidate-details` | Starts candidate-detail extraction from the current ATS page |
| GET | `/candidate-details-status/{token}` | Returns candidate extraction progress and metadata |
| POST | `/handle-jobs/{token}` | Extracts jobs and posts the payload to a webhook URL |

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

`limit` is optional, defaults to `100`, and must be between `1` and `5000`.

Example response:

```json
{
  "status": "processing",
  "token": "<uuid>"
}
```

Poll the result:

```http
GET /export-status/<uuid>
```

Generated files are written under `EXPORT_DIR`, typically as:

```text
kariyer_jobs_<token>_<id>.json
kariyer_jobs_<token>_<id>.csv
```

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

Poll result status:

```http
GET /candidate-details-status/<uuid>
```

Candidate data is typically written as:

```text
kariyer_candidate_details_<token>.json
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

The destination receives a wrapped payload containing fields such as:

```json
{
  "status": "success",
  "total_jobs": 10,
  "timestamp": "2026-01-01T12:00:00Z",
  "jobs": []
}
```

Validate, allowlist, and protect `target_url` values before deploying this endpoint.

## Filtering

`/process-jobs` accepts a validated `filters` object that maps JSON fields to Kariyer ATS UI interactions, including Vue multiselects, sliders, checkboxes, and radio buttons. The request model is defined in `schemas.py` and is imported by `models.py`.

Example intended filter request:

```json
{
  "token": "your-session-token",
  "limit": 50,
  "filters": {
    "personal": {
      "first_name": "Ahmet",
      "last_name": "Yılmaz",
      "gender": {
        "male": true,
        "female": false
      },
      "age_range": {
        "min_age": 22,
        "max_age": 35
      },
      "nationality": ["T.C."],
      "military_status": ["Yapıldı", "Muaf"],
      "driver_licences": ["B - Otomobil"],
      "languages": [
        {
          "language": "İngilizce",
          "min_level": "İleri"
        }
      ],
      "is_disabled_candidate": false,
      "is_disaster_affected": true
    },
    "education": {
      "levels": ["Lisans", "Yüksek Lisans"],
      "universities": ["Orta Doğu Teknik Üniversitesi"],
      "departments": ["Bilgisayar Mühendisliği"]
    },
    "experience": {
      "experience_type": "experienced",
      "position_scope": "all_jobs",
      "positions": ["Yazılım Geliştirme Uzmanı"],
      "position_levels": ["Uzman", "Kıdemli Uzman"],
      "sector_scope": "last_job",
      "sectors": ["Bilişim"],
      "is_currently_working": false,
      "is_retired": false
    },
    "location": {
      "current_locations": ["İstanbul(Asya)", "Ankara"],
      "preferred_cities": ["İzmir"]
    },
    "application": {
      "statuses": ["Yeni Başvuru", "Özgeçmiş İncelendi"],
      "questions": [
        {
          "question": "Vardiyalı çalışabilir misiniz?",
          "answer": "Evet"
        }
      ]
    },
    "kvkk": {
      "clarification_text_shown": true,
      "explicit_consent_approved": true
    },
    "review_status": {
      "review_status": "hide_reviewed",
      "response_status": "unanswered_custom"
    }
  }
}
```

### Enumerated filter values

#### `experience.experience_type`

- `experienced`
- `inexperienced`

#### `experience.position_scope`

- `all_jobs`
- `last_job`
- `last_3_jobs`

#### `experience.sector_scope`

- `all_jobs`
- `last_job`
- `last_3_jobs`

#### `review_status.review_status`

- `show_reviewed`
- `hide_reviewed`

#### `review_status.response_status`

- `unanswered_custom`
- `auto_replied`
- `answered_custom`

Values passed to Vue multiselect fields, such as universities, departments, sectors, locations, and position names, must exactly match the wording displayed by the Kariyer ATS UI.

## Livestream WebSocket

Connect to:

```text
ws://localhost:8000/ws/livestream/{token}
```

The server streams JPEG screenshot bytes from the active Playwright browser session.

The client can send pointer control events as JSON:

```json
{
  "action": "click",
  "x": 500,
  "y": 320
}
```

Supported actions:

- `click`
- `mousedown`
- `mousemove`
- `mouseup`
- `close`

Coordinates refer to the browser viewport. Do not expose this endpoint without strong authentication and authorization.

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

$choice = @{
    token = $token
    method = "email"
} | ConvertTo-Json

Invoke-RestMethod `
    http://localhost:8000/submit-2fa-choice `
    -Method Post `
    -ContentType "application/json" `
    -Body $choice

$code = @{
    token = $token
    code = "123456"
} | ConvertTo-Json

Invoke-RestMethod `
    http://localhost:8000/submit-2fa-code `
    -Method Post `
    -ContentType "application/json" `
    -Body $code

$jobs = @{
    token = $token
    limit = 1
} | ConvertTo-Json

Invoke-RestMethod `
    http://localhost:8000/process-jobs `
    -Method Post `
    -ContentType "application/json" `
    -Body $jobs

Invoke-RestMethod "http://localhost:8000/export-status/$token"
```

For browser clients, use `EventSource` with:

```text
/stream-status/{token}
```

Then poll the appropriate status endpoint until `is_processing` becomes `false`.

## Project structure

```text
main.py                                  FastAPI app, routes, sessions, exports, CLI
supabaser.py                              Opt-in JSON export ingestion into Supabase
models.py                                Pydantic request models and session helpers
config.py                                Environment configuration and shared state
automation.py                            Kariyer login, CAPTCHA, and 2FA automation
automation_process_jobs.py               Job-list and candidate extraction pipeline
automation_extract_candidate_details.py  Candidate-detail extraction
index.html                               Browser UI for the API workflow
GeekedTest/                              GeeTest/CAPTCHA helper package and model assets
extractor/                               Extraction-related workspace files
html_stuff/                              Captured/reference Kariyer HTML pages
exports/                                 Generated JSON/CSV files
debug/                                   Login and post-2FA diagnostic artifacts
screenshots/                             Screenshot output directory
tests/                                   Test workspace; currently a placeholder
```

The following files are legacy or generated variants and are not the documented application entry point:

```text
api.pyold
main_pyside.py.old
extractor_api.py
extractor_automation.py
```

Use `main.py` as the supported application entry point.

## Testing and validation

There is currently no configured pytest command or populated automated test suite.

Run basic syntax checks after installation:

```powershell
python -m compileall `
    .\main.py `
    .\models.py `
    .\config.py `
    .\automation.py `
    .\automation_process_jobs.py `
    .\automation_extract_candidate_details.py
```

Run the live auto-solver validation only with an authorized test account:

```powershell
python .\main.py --autosolvetester
```

For safer validation:

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