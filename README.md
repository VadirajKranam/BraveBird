# BraveBird Automation

Python Playwright runner for a 2FA login, session reuse, offline locator resolution, nested form entry, and document capture.

## What it does

- Logs into GitHub with username/password plus a TOTP code from a shared secret.
- Saves and reuses browser storage state on later runs.
- Falls back to a fresh login when the saved session is stale.
- Navigates through a small portal to a nested form inside an iframe.
- Resolves fields with multiple locator strategies and records which one won.
- Captures the generated receipt as a native download.
- Writes a JSON manifest with inputs, visited pages, timings, and captured files.
- On final failure, writes a screenshot, HTML, console log, and manifest evidence bundle with redaction.

## Setup

1. Create or activate the workspace virtual environment.
2. Install dependencies:

   ./.venv/bin/python -m pip install -r requirements.txt

3. Install the Playwright browser binary:

   ./.venv/bin/python -m playwright install chromium

4. Put your inputs in [inputs/example.json](inputs/example.json).

5. Run the automation:

   ./.venv/bin/python -m bravebird.cli --input inputs/example.json

   Or use the Makefile:

   make run

## Optional environment variables

- HEADLESS=true or false — controls browser headless mode. Default is true.

The Makefile `run` target sets `HEADLESS=true` by default.

The login secrets are read from the input JSON file so the runner can be driven by changing inputs only.

## Output

Each run writes a folder under runs/ containing:

- manifest.json
- downloads/
- evidence/ on failure

## TOTP behavior

The TOTP provider is implemented directly in code as a deterministic Base32-secret-based generator. The runner fills the GitHub 2FA field automatically, retries a wrong code once, and never logs the code. If GitHub rejects the first code, the runner generates the next code and tries again once before failing.

## Dead session detection

The saved storage state is loaded on startup. The runner probes a privileged GitHub page and checks whether the browser remains signed in instead of merely watching for a redirect. If the saved state is stale, the runner performs a full login again and overwrites the stored state.

## Locator strategy order

The offline resolver tries these strategies in order:

1. Role and accessible name
2. Label association
3. Nearby text
4. Structural context
5. Id or class fallback

This order prefers accessibility-first signals, then progressively weaker structural hints. The same resolver works against saved HTML, which is why the offline fixture command can resolve fields without a live browser.

## Portal quirks handled

- iframe: the form is embedded in a nested browsing context
- dependent field: city options depend on the selected region
- native download: the receipt is saved through Playwright download handling

## Retry policy

Retryable failures are bounded and use exponential backoff. The login flow retries once for a bad 2FA code. The runner treats transient page interaction failures as retryable, while final failures stop the run and write evidence.

## Failure evidence bundle

On a final failure the runner writes:

- screenshot
- page HTML
- console log
- stage key
- redacted manifest entry

Credentials, codes, and account identifiers are redacted from evidence files.

## Offline resolver check

You can test the resilient locator logic without a live portal:

    ./.venv/bin/python -m bravebird.resolve_cli --html fixtures/offline/request-form.html --spec fixtures/offline/spec.json
