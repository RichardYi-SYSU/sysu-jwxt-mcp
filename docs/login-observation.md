# Login Observation Workflow

Use this workflow before implementing the real login and timetable fetchers.

## Goal

Capture the normal browser-authenticated path into `jwxt.sysu.edu.cn`, persist session state, and identify the request(s) used to load timetable data after login.

## Steps

1. Install Playwright browser binaries:

   ```bash
   .venv/bin/playwright install chromium
   ```

2. Run the observation script in SSH-friendly headless mode:

   ```bash
   .venv/bin/python scripts/observe_login.py
   ```

3. Review the terminal output and generated artifacts:
   - The script prints the current URL as redirects settle.
   - It writes a screenshot and HTML snapshot of the final page state.
   - It records request and response metadata for later inspection.

4. Review generated artifacts under `data/observation/`:
   - `requests-*.json`
   - `responses-*.json`
   - `login-page-*.png`
   - `login-page-*.html`

5. Inspect the request list for likely timetable sources:
   - `XHR` or `fetch` requests made after timetable navigation.
   - page URLs or endpoints containing semester, course, or schedule hints.
   - HTML page loads that may embed timetable data server-side.

## Headless Mode Limitation

Pure SSH headless mode can observe the redirect chain and login entry pages, but it does not allow you to manually operate the remote browser window. That means:

- It is useful for mapping the `CAS/NetID` path and capturing page structure.
- It is not sufficient by itself for a human-only login flow with captcha or MFA.
- To complete real authentication later, we will likely need one of:
  - a local-browser-to-remote-session import workflow, or
  - a scriptable form-based login path if the upstream flow allows it.

If you do have GUI access, you can still run a visible browser with:

```bash
.venv/bin/python scripts/observe_login.py --headed
```

## What to Implement Next

- Add real Playwright login logic in `AuthService` and `BrowserSessionManager`.
- Replace the placeholder in `JwxtClient._fetch_live_timetable`.
- Store a redacted sample payload for parser development once you know the real source.

## Notes

- The script persists browser storage state to `data/state/storage_state.json`.
- Treat all artifacts as sensitive; they may reveal authenticated URLs or session behavior.
- The current script logs metadata only, not full response bodies, to reduce accidental leakage.
