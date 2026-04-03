# Live Discovery Notes

This file records concrete findings from live, unauthenticated probing of `https://jwxt.sysu.edu.cn/jwxt` on 2026-04-02.

## Confirmed Entry Points

- Base URL resolves and serves the SPA entry: `https://jwxt.sysu.edu.cn/jwxt/`
- The SPA login route is `https://jwxt.sysu.edu.cn/jwxt/#/login`
- CAS entrypoint redirects to:
  - `GET /jwxt/api/sso/cas/login`
  - `302 Location: https://cas.sysu.edu.cn/esc-sso/login?service=https%3A%2F%2Fjwxt.sysu.edu.cn%2Fjwxt%2Fapi%2Fsso%2Fcas%2Flogin`

## Confirmed Unauthenticated API Behavior

- `GET /jwxt/api/login/status` returns `{"code":200,"data":0}` in the unauthenticated state.
- `GET /jwxt/api/verificationCodes` returned `{"code":53000000,"message":"系统异常"}` when probed directly without the expected frontend flow.

## Frontend-Referenced APIs

Extracted from `assets/js/app.dae03.js`:

- `POST /api/login`
- `GET /api/login/status`
- `GET /api/verificationCodes`
- `GET /api/privilege`
- `GET /system-manage/info-delivery`
- `GET /base-info/acadyearterm/showNewAcadlist`
- `GET /timetable-search/classTableInfo/selectStudentClassTable`
- `GET /schedule/agg/classesStudyObj/list`
- `GET /achievement-manage/score-check/list`

## Login Payload Clues

The bundle contains a login submission flow with these fields:

- `userName`
- `password` from the form
- `timestamp`
- `token`
- `captchaVerification`
- `pattern`

Observed transformation logic in the bundle:

- `i = hash(password).toUpperCase() + timestamp`
- `token = hash(i).toLowerCase()`

The exact hash function symbol was minified, but it is almost certainly a deterministic frontend digest step, not plain-text password submission.

## Captcha / Verification Clues

The login page loads `Geetest` resources and a custom verification flow:

- `GET /VerificationCode/sysu-captcha/captcha/get`
- `POST /VerificationCode/sysu-captcha/captcha/check`

The verification component constructs a `captchaVerification` value and may AES-encrypt slider coordinates before verification.

## Immediate Implications

- We should not assume a plain username/password login without captcha.
- The most realistic next integration path is:
  1. import a valid authenticated browser session, or
  2. complete the CAS flow in a browser and persist the resulting session state.
- Once authenticated, the first endpoints to probe for student timetable data are:
  - `/base-info/acadyearterm/showNewAcadlist`
  - `/timetable-search/classTableInfo/selectStudentClassTable`
