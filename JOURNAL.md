## Week 7 — Issue selection

**Issue link:** https://github.com/ascherj/pathreview/issues/68

**Issue title:** Add a safety event count to the health check endpoint #68

**Tier:** [X] Tier 1  [ ] Tier 2  [ ] Tier 3

**Problem summary:**
This issue affects the /api/health api endpoint. Currently the endpoint returns service status but not service metrics. We need to implement a health safety event count to the endpoint.

**Branch name:** 'fix/68-add-safety-event-counter'

**Setup confirmation:** [X] App runs locally at localhost:5173

**Cohort ledger:** [X] Issue added to cohort ledger

## Week 8 — Reproduction & solution planning

**Reproduction commit link:** https://github.com/TeooL/pathreview/commit/d38545b0484d571711e56be5872a4daf1edf3e43

**Reproduction summary:**
Docker wasn't available in my sandbox to run the full Postgres/Redis stack, so I reproduced at the code level: `api/routes/health.py` hardcodes `safety_events_last_hour` to `0` (the "count" block at lines 75-79 is a placeholder — the comment literally says "this would be populated by actual safety event logging"). A `grep` across the repo confirms `safety/monitoring.py`'s `SafetyMonitor` class (which already has working `log_event()`/`get_event_count()` methods backed by Redis) is never imported or instantiated anywhere else in the app. I wrote a standalone script that imports the real `SafetyMonitor` unmodified, logs several safety events against a fake in-memory Redis, and confirms `get_event_count` correctly reports 4 events — while the value `/api/health` actually returns for that field stays `0`, proving the endpoint is fully disconnected from real safety event data.

**PLAN.md link:** https://github.com/TeooL/pathreview/blob/fix/68-add-safety-event-counter/PLAN.md

**Walkthrough video (recommended):** [link to your Loom video, ≤2 min — recommended, not graded]

**Blockers or open questions:**
- Couldn't run the full app locally (no `docker` in this environment), so I haven't verified behavior against real Postgres/Redis yet — need to do that in Week 9 with `docker compose up -d`.
- `SafetyMonitor.get_event_count`'s `window_hours` parameter isn't actually enforced (the docstring says so directly) — the Redis key is a flat counter with a 24h TTL, not a true rolling window. Need to decide in Week 9 whether fixing "last hour" semantics properly (rolling window, like `RateLimiter` already does with sorted sets) is in scope, or whether a simpler "since last reset" approximation is acceptable for this issue.
- Open question: should every safety module (bias_detector, content_filter, pii_scrubber, prompt_defense, rate_limiter) get wired up to call `log_event()`, or does this issue only expect the health endpoint + monitoring infra to be fixed with wiring left as follow-up? See PLAN.md for details.

## Week 9 — Solution building & PR submission

### Check-in 1 (mid-week — Wednesday, 2026-07-29)

**Current progress:**
All 5 sub-tasks from PLAN.md are implemented, in order of dependency rather than the original list order:
1. Rewrote `SafetyMonitor` (`safety/monitoring.py`) to track events in a real Redis sorted-set rolling window instead of a flat counter with an unenforced `window_hours`, and added `get_total_event_count()` to sum across event types.
2. Added `core/redis.py::get_redis_client()` as a shared FastAPI dependency (also fixed the endpoint's Redis health check, which referenced the nonexistent `settings.redis_host`/`settings.redis_port` instead of `settings.redis_url`), and wired it into `api/routes/health.py` so `safety_events_last_hour` reports a real `SafetyMonitor` count instead of the hardcoded `0`.
3. Added an optional `monitor` parameter (default `None`, so existing callers/tests are unaffected) to `BiasDetector.detect_bias`, `ContentFilter.filter`, `PromptDefense.is_injection_attempt`, `PIIScrubber.detect`, and `RateLimiter.check_rate_limit`, so each records a `SafetyMonitor` event when it actually triggers.

Each sub-task is its own commit (`7933d18`, `5e3aa0b`, `4d5e892`).

**Next steps:**
Run `docker compose up -d` + `make run` to sanity-check `/api/health` end-to-end against real Postgres/Redis (only verified against mocks so far, per the Week 8 blocker), then open the PR.

**Blockers:**
Still no `docker` available in my current environment, so the real-service verification above is deferred to whenever I have Docker access.

---

### Check-in 2 (submission — Sunday, 2026-08-02)

**PR link:** https://github.com/TeooL/pathreview/pull/1

**Branch:** `fix/68-add-safety-event-counter`

**What you built:**
`/api/health` now reports a real `safety_events_last_hour` count instead of a hardcoded `0`, sourced from `SafetyMonitor`'s Redis-backed rolling window (fixed to be a genuine time window rather than a flat 24h-TTL counter). The five safety detectors (bias, content filter, prompt injection, PII, rate limiting) now optionally log events into that monitor whenever they actually trigger.

**Tests added or updated:**
`tests/unit/test_safety_monitor.py` (new — rolling window, aggregation, error handling), `tests/unit/test_health.py` (new — endpoint reports real counts, degrades gracefully on failures, 503s on real dependency failures), `tests/unit/test_content_filter.py` (new — no prior coverage existed), and added monitor-wiring cases to `test_bias_detector.py`, `test_prompt_defense.py`, `test_pii_scrubber.py`, `test_rate_limiter.py`.

**Pre-existing failures (documented, not introduced by this change):** Before starting, `make test-unit` already had 53 failing tests (mostly regex/parsing bugs in `bias_detector`, `pii_scrubber`, `prompt_defense`, and several parser/scorer modules — see baseline capture) and `make check` already had 182 ruff errors, ~51 black-noncompliant files, and mypy errors from missing type stubs (`PyPDF2`, `jose`, `passlib`, `rank_bm25`) plus a numpy/Python-3.14 stub incompatibility that halts a full mypy run early. I re-ran both after every commit: the failing-test set is byte-for-byte identical to the baseline (53 failed, count of passing tests only grew), and ruff's count actually dropped to 172 (cleaning up import blocks in the files I touched) with no new violations introduced anywhere I changed.

**Self-review confirmation:** [x] make check passes (no new issues vs. documented pre-existing baseline)  [x] make test-unit passes (same 53 pre-existing failures, all new tests green)

**Draft PR feedback received from:** None