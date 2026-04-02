# Agent Guide

## Purpose

This repository exists to give an agent a safe, local way to read timetable data from `jwxt.sysu.edu.cn` for one authorized user.

## Guardrails

- Do not implement authentication bypasses or attempt to access data outside the signed-in user's scope.
- Treat cookies, storage state, and local cache as sensitive.
- When upstream pages or APIs change, fail explicitly instead of guessing.
- Prefer browser-observed authenticated APIs over brittle scraping when both are available.

## Operator Workflow

1. Start the local API service.
2. Trigger `POST /auth/login`.
3. If the service reports `manual_login_required`, complete login in the opened browser window and retry.
4. Call `GET /timetable?term=current`.
5. If real-time fetch fails, inspect whether the response was served from stale cache before trusting it.

## Expected Next Steps

- Replace placeholder login logic with the recorded `CAS/NetID` flow.
- Capture the timetable request path from browser traces.
- Add parser coverage once real payload samples are available.
