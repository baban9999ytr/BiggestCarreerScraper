# Privacy Notice

**Effective date:** 25 August 2026

This notice explains how an operator of the Kariyer.net ATS Automation API (the "Service") may process information when running this software. The software is self-hosted and does not provide a central hosted service. The person or organization that deploys and operates it is responsible for determining the applicable controller, lawful basis, retention periods, notices, and user-rights process for its deployment.

This is operational documentation, not legal advice. Adapt it with qualified privacy counsel before using the Service in a regulated or customer-facing environment.

## Information Processed

Depending on configuration and use, the Service can process:

- Kariyer.net login email addresses and passwords submitted to `POST /login` or supplied through environment variables.
- Session tokens, session timestamps, login status, 2FA method, and 2FA codes submitted through the API.
- Job-listing and applicant information available to the authenticated Kariyer.net employer account, including candidate CV details and other personal data contained in ATS pages.
- Technical information used to operate and diagnose the browser session, such as page URLs, error messages, application logs, browser screenshots, and captured HTML.
- Exported JSON and CSV files created under the configured `EXPORT_DIR`.
- Data sent to a caller-selected `target_url` by `POST /handle-jobs/{token}`.

The Service is not designed to collect information from children and should not be used for that purpose.

## How Information Is Used

The operator may use this information to:

1. Authenticate an authorized employer account and complete CAPTCHA or 2FA steps.
2. Maintain an active browser automation session and report its status.
3. Extract job listings and candidate details requested by the operator.
4. Produce local JSON, CSV, screenshot, and diagnostic files.
5. Deliver extracted job data to an endpoint explicitly configured by the operator.
6. Diagnose failures, page-layout changes, and automation issues.

The Service does not add advertising, profiling, or data-sale functionality. A deployment operator may nevertheless connect it to other systems, so review all configured callback URLs, logs, monitoring, and hosting providers.

## Data Sources and Sharing

Information comes from the operator, the authenticated Kariyer.net ATS account, the browser session, and any callback destination configured by the operator.

The Service may transmit or expose information to:

- Kariyer.net and its authentication, ATS, CAPTCHA, and 2FA infrastructure as part of normal browser automation.
- CAPTCHA or OCR services configured by the operator, such as a CapSolver integration if enabled. Review the applicable provider's terms and privacy documentation before enabling one.
- The `target_url` supplied to `/handle-jobs/{token}`. This URL is caller-controlled and may receive extracted job and applicant data.
- The infrastructure, hosting provider, backups, log aggregation, and administrators used by the deployment operator.

The software itself does not intentionally sell personal information. It does not guarantee that external services or a deployment's infrastructure will handle data in the same way; their terms and privacy notices apply.

## Local Storage and Retention

- Active sessions are held in process memory and are normally configured to expire after six hours through `SESSION_TTL_SECONDS` (21,600 seconds). Restarting the process removes in-memory sessions.
- Job exports are written to `EXPORT_DIR` as JSON and CSV files. Candidate-detail exports are also written there.
- Diagnostic files and screenshots may be written to `DEBUG_DIR` and `SCREENSHOT_DIR`, including screenshots taken for up to 60 seconds after 2FA code submission and during auto-solver testing.
- The application does not automatically delete generated exports, screenshots, or debug files. The deployment operator must establish and enforce a retention and deletion schedule, including backups.
- Do not place `.env`, credentials, session tokens, exports, or diagnostic captures in source control or shared storage without access controls.

## Security Responsibilities and Limitations

The deployment operator is responsible for:

- Protecting credentials, 2FA codes, bearer session tokens, exports, and diagnostic artifacts.
- Restricting access to the API, WebSocket livestream, filesystem, logs, and generated files.
- Replacing the development CORS configuration with an allowlist and adding authentication, authorization, TLS, rate limiting, and request validation.
- Restricting or validating `target_url` to prevent unauthorized disclosure or server-side request forgery.
- Redacting secrets and personal data from logs, screenshots, error reports, and backups.
- Applying operating-system, Python, browser, and dependency security updates.

The default application stores session state in memory, permits broad CORS, and uses bearer tokens in request bodies and paths. These defaults are unsuitable for an internet-facing production deployment without additional controls.

## Privacy Rights and Requests

Where applicable law grants rights such as access, correction, deletion, restriction, objection, portability, or withdrawal of consent, requests should be directed to the organization operating the Service. The operator must verify the requester's identity, locate copies in exports, logs, screenshots, and backups, and respond within the legally required period.

Candidate information should be processed only for an appropriate employment-related purpose, with the required notices, permissions, access controls, and retention limits. For Turkish operations, assess obligations under KVKK; for European operations, assess GDPR and local employment-data requirements.

## Changes and Contact

The operator may update this notice when the Service, integrations, storage, or legal requirements change. Each deployment should publish a current contact address and identify its data controller or responsible organization. This repository does not define a central privacy contact; replace this paragraph with the operator's name, address, and contact method before distribution.
