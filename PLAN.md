# Implementation Plan

## Goal

Build a local service that allows an agent to read key teaching-affairs data from the SYSU teaching affairs system for the currently authorized user.

## Constraints

- No authentication bypass, exploit research, or unauthorized data access.
- Target a single self-owned account in `v1`.
- Prefer real upstream API reuse after login; fall back to browser DOM extraction only when necessary.
- Allow manual login takeover when the `CAS/NetID` flow presents captcha, MFA, or unexpected page changes.

## Milestones

1. Baseline service
   - FastAPI app with health, login, refresh, import-state, and keepalive endpoints.
   - Typed config, session storage, cache storage, and normalized response models.
2. Browser-backed auth
   - Playwright browser launcher.
   - Session persistence via storage state.
   - Session validation, keepalive worker, and explicit login status reporting.
   - Student QR login via Enterprise WeCom scan, with automatic `storage_state.json` persistence after successful CAS->JWXT completion.
3. Data extraction
   - Discover authenticated request paths for timetable, exams, grades, empty classrooms, and CET scores.
   - Implement response normalization and strict query validation.
   - Keep high-cardinality endpoints constrained by required filters.
4. Timetable hardening
   - Implement timetable normalization and stale-cache fallback.
   - Surface parse and upstream contract failures as explicit errors.
5. Hardening
   - Add structured logs with sensitive-field redaction.
   - Add smoke tests for health and parser behavior.
   - Add integration notes for turning REST endpoints into MCP tools later.
6. MCP packaging
   - Expose the existing auth and query capabilities as a local `stdio` MCP server.
   - Reuse the same service layer as the REST API instead of self-calling HTTP.
   - Keep the first version focused on tools; defer streamable HTTP to a later iteration.

## v1 Deliverables

- A runnable local repository.
- Project docs for agent usage and implementation boundaries.
- A verified student QR login path that only requires the user to scan/confirm and does not require manual cookie export.
- A runnable local `stdio` MCP server for the same single-user JWXT workflow.
- Working service with agent-facing endpoints for:
  - timetable (`/timetable`)
  - exams (`/exams`)
  - grades (`/grades`)
  - empty classrooms (`/classrooms/empty`)
  - CET scores (`/cet-scores`)
- Basic tests around API health, parameter validation, and serialization behavior.

## Deferred

- Training plan, course selection, notices, and additional student-service pages.
- Multi-user session isolation.
- Direct MCP server exposure.
- Scheduled background sync.
- Alias normalization for human-friendly classroom campus inputs such as `东校 -> 东校园`.
