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