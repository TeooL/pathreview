## Solution plan

**Issue:** [Add a safety event count to the health check endpoint #68](https://github.com/ascherj/pathreview/issues/68)

### Understand
**Expected:** `/api/health` should report how many safety events (PII detections, prompt-injection attempts, content filtering, bias detections, rate limiting) occurred recently, so operators can tell from the health endpoint whether the safety layer is actively catching problems.

**Actual:** The endpoint hardcodes `safety_events_last_hour` to `0`. The relevant block in `api/routes/health.py` (lines 75-79) is a literal placeholder — the comment says "this would be populated by actual safety event logging." Meanwhile, `safety/monitoring.py` already defines a working `SafetyMonitor` class with `log_event()` (increments a per-event-type Redis counter) and `get_event_count()` (reads it back) — but a repo-wide grep shows `SafetyMonitor` is never imported or instantiated anywhere outside its own file. So the counting infrastructure exists but is completely unwired: nothing calls `log_event()` when a safety trigger fires, and the health endpoint never calls `get_event_count()`.

**Secondary nuance:** even once wired up, `get_event_count`'s `window_hours` argument isn't enforced — the docstring says so directly. The Redis key is a flat `INCR` counter with a 24-hour TTL, not a real rolling window, so it can't currently express "last hour" accurately (it really means "since last reset, within a 24h TTL").

### Map
- `api/routes/health.py` — replace the hardcoded `0` with a real read from `SafetyMonitor`, and inject a Redis client via `Depends` (the endpoint already does ad-hoc `redis.Redis(...)` construction for its Redis dependency check at line 44, which is the closest existing precedent).
- `safety/monitoring.py` — `SafetyMonitor.log_event` / `get_event_count`. Needs: (a) an aggregate helper across all `VALID_EVENT_TYPES`, and (b) a real time-windowed storage scheme if "last hour" is to be accurate.
- `safety/rate_limiter.py` — reference implementation for a proper rolling window (uses a Redis sorted set + `zremrangebyscore`/`zcard`); the safety-event windowing fix should mirror this pattern instead of the current flat counter.
- `safety/bias_detector.py`, `safety/content_filter.py`, `safety/pii_scrubber.py`, `safety/prompt_defense.py`, `safety/rate_limiter.py` — the actual sources of safety events. None of them currently call `SafetyMonitor.log_event()`, so no real events are recorded today regardless of the health endpoint.
- `core/config.py` / `core/database.py` — pattern reference for a shared dependency provider (`get_db`-style); may want an equivalent `get_redis_client()` so `SafetyMonitor` isn't constructed ad hoc in multiple places.
- `tests/unit/` — has tests for each safety module already but none for `health.py` or `safety/monitoring.py`; need new test files for both.

### Plan
1. Add a shared Redis client dependency (e.g. `core/redis.py::get_redis_client()`, mirroring `core/database.py::get_db()`) and inject it into `health.py` via `Depends`, replacing the endpoint's separate inline `redis.Redis(...)` construction.
2. Fix time-windowing in `safety/monitoring.py`: replace the flat `INCR` + 24h-TTL counter with a rolling-window store (Redis sorted set keyed by timestamp, following `RateLimiter`'s pattern), so `get_event_count(event_type, window_hours=1)` genuinely reflects only the last hour. Add a `get_total_event_count(window_hours=1)` method that sums across `VALID_EVENT_TYPES`.
3. Wire `SafetyMonitor.log_event(...)` calls into each safety module at the point it actually triggers (bias_detector, content_filter, pii_scrubber, prompt_defense, rate_limiter) so events are recorded during real request handling, not just theoretically loggable.
4. Update `api/routes/health.py` to call the new aggregate method and return the real count instead of the hardcoded `0`; ensure a Redis outage degrades gracefully (see edge cases) rather than breaking the whole health check.
5. Add tests: unit tests for `SafetyMonitor`'s windowing/aggregation logic, and a test for `/api/health` asserting `safety_events_last_hour` reflects logged events (mocking Redis, since no `fakeredis` dependency currently exists in the project).

### Inputs & outputs
**Input:** Safety events raised during real request handling in `bias_detector`, `content_filter`, `pii_scrubber`, `prompt_defense`, and `rate_limiter`, each identified by an `event_type` (from `SafetyMonitor.VALID_EVENT_TYPES`) plus a details dict.

**Output:** The `/api/health` response's `safety_events_last_hour` field becomes a real integer — the count of safety events actually logged via `SafetyMonitor` within a genuine rolling one-hour window, instead of a hardcoded `0`.

### Risks & unknowns
- No `fakeredis` (or similar) dev dependency currently exists — tests will need either a hand-rolled fake Redis or a new dependency added to `pyproject.toml`.
- Switching to a sorted-set rolling window is a Redis data-shape change (not a DB migration, but still worth flagging) — old flat-counter keys can simply be left to expire naturally.
- Wiring `log_event()` into five separate safety modules is more surface area than a single-file fix. Still unclear whether issue #68 expects full wiring across all modules or just the counting infrastructure + health endpoint, with module wiring as a follow-up — need to confirm early in Week 9.
- Haven't verified any of this against the real app yet (no `docker` available in my current environment) — need to validate with `docker compose up -d` + `make run` before considering the fix complete.
- Adding a Redis call inside each safety check's hot path could add latency — likely negligible since `rate_limiter.py` already does exactly this, but worth a quick sanity check.

### Edge cases
- Redis unreachable when logging an event — must not crash the safety check that triggered it (already handled: `log_event`'s existing try/except swallows errors and logs via structlog).
- Redis unreachable when computing the health count — endpoint should still return a response (e.g. `0` or an explicit "unknown"/"unavailable" marker) rather than failing the whole health check over an optional metric, consistent with how `vector_db_url` absence is handled today.
- Zero events logged in the window — should cleanly return `0`, not error.
- `event_type` not in `VALID_EVENT_TYPES` — already handled (logs a warning, does not increment); behavior should stay unchanged.
- High event volume — the rolling-window sorted set needs periodic pruning (`zremrangebyscore`) so keys don't grow unbounded, matching what `RateLimiter` already does.