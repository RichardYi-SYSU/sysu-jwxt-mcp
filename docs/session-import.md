# Session Import Workflow

Use this path when the remote machine cannot open a visible browser window.

## Goal

Log in on your local computer, export the relevant browser session, copy it to the remote machine, and import it into `data/state/storage_state.json`.

## Recommended Workflow

1. On your local computer, open `https://jwxt.sysu.edu.cn/jwxt/`.
2. Complete the normal login flow until you can access the student side of the system.
3. Export cookies for:
   - `jwxt.sysu.edu.cn`
   - `cas.sysu.edu.cn`
4. Save the export as JSON.

The importer accepts either:

- a Playwright `storageState` JSON object with `cookies` and `origins`, or
- a plain cookie list JSON array where each item contains:
  - `name`
  - `value`
  - `domain`
  - `path`
  - `expires`
  - `httpOnly`
  - `secure`
  - `sameSite`

## Copy to Remote

From your local machine:

```bash
scp jwxt-session.json <user>@<server>:/home/yichw/sysu-jwxt-agent/
```

## Import on Remote

On the remote machine:

```bash
cd /home/yichw/sysu-jwxt-agent
.venv/bin/python scripts/import_session.py --input jwxt-session.json
```

Or via the local API:

```bash
curl -X POST http://127.0.0.1:8000/auth/import-state \
  -H 'Content-Type: application/json' \
  --data @jwxt-session.json
```

If your file is a cookie list array, wrap it as:

```json
{
  "cookies": [
    {
      "name": "SESSION",
      "value": "...",
      "domain": "jwxt.sysu.edu.cn",
      "path": "/",
      "expires": -1,
      "httpOnly": true,
      "secure": true,
      "sameSite": "None"
    }
  ]
}
```

## Verify

After import:

```bash
curl -X POST http://127.0.0.1:8000/auth/refresh
```

If the imported session is valid, the response should report `authenticated: true`.

## Notes

- Importing cookies is safer than trying to reimplement the live captcha flow immediately.
- Session imports may expire quickly if CAS or JWXT rotates cookies aggressively.
- If `authenticated` stays `false`, the export likely missed a required cookie or was taken before login fully completed.
