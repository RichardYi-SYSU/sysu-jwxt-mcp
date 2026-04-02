# Implementation Plan

## Goal

Build a local service that allows an agent to read timetable data from the SYSU teaching affairs system for the currently authorized user.

## Constraints

- No authentication bypass, exploit research, or unauthorized data access.
- Target a single self-owned account in `v1`.
- Prefer real upstream API reuse after login; fall back to browser DOM extraction only when necessary.
- Allow manual login takeover when the `CAS/NetID` flow presents captcha, MFA, or unexpected page changes.

## Milestones

1. Baseline service
   - FastAPI app with health, login, refresh, and timetable endpoints.
   - Typed config, session storage, cache storage, and normalized response models.
2. Browser-backed auth
   - Playwright browser launcher.
   - Session persistence via storage state.
   - Session validation and explicit login status reporting.
3. Timetable extraction
   - Discover authenticated request path or page data source.
   - Implement timetable normalization and stale-cache fallback.
   - Surface parse and upstream contract failures as explicit errors.
4. Hardening
   - Add structured logs with sensitive-field redaction.
   - Add smoke tests for health and parser behavior.
   - Add integration notes for turning REST endpoints into MCP tools later.

## v1 Deliverables

- A runnable local repository.
- Project docs for agent usage and implementation boundaries.
- Working service skeleton with clear extension points for live login and timetable fetch.
- Basic tests around API health and serialization behavior.

## Deferred

- Grades, exams, training plan, and course selection data.
- Multi-user session isolation.
- Direct MCP server exposure.
- Scheduled background sync.
