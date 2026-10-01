# PLAN: AI API Test & Monitoring Suite

Repo name: `ai-api-test-suite`

## Instructions for Claude Code (read first)
- Work one phase at a time. At the end of each phase: run the checks listed, commit with a clear message, then stop and summarize before starting the next.
- Use synthetic data only. Never commit secrets; read keys from environment variables and provide `.env.example`.
- Do not invent metrics. Report only what the tests and monitor actually produced.
- The suite must run fully offline in `MOCK_LLM=true` mode so tests are deterministic and free; a live mode is optional.
- Keep it simple enough that the owner can explain every file.

## Goal
Show how a team catches failures in AI-backed APIs before customers do: a small LLM-backed service, an automated test suite covering real failure modes, a scheduled monitor with alerts, and a runbook that maps each failure to a fix.

## Tech stack
- Python 3.11+, FastAPI (system under test), pytest + httpx (tests)
- Postman collection + Newman CLI (API contract tests)
- GitHub Actions (CI and scheduled monitor)
- Slack or Discord incoming webhook (alerts)
- Anthropic API (live mode only)
- n8n (optional; only keep on resume if an exported workflow is included)

## Target repo structure
```
ai-api-test-suite/
  README.md
  PLAN.md
  RUNBOOK.md
  .env.example
  target_api/
    main.py                  # FastAPI app
    llm_client.py            # real client + mock client
    faults.py                # fault injection
    schemas.py               # pydantic request/response models
  tests/
    conftest.py
    test_auth.py
    test_schema.py
    test_rate_limit.py
    test_timeouts.py
    test_malformed_input.py
    test_llm_output_contract.py
  postman/
    ai_api.postman_collection.json
    local.postman_environment.json
  monitor/
    run_checks.py            # smoke checks + failure log + alert
    alert.py                 # webhook sender
    failures.jsonl           # generated, git-ignored
  .github/workflows/
    ci.yml
    monitor.yml
  docs/architecture.md
```

## Phase 0: Setup
- [ ] Repo, `.gitignore`, `requirements.txt`, `.env.example` (`API_KEYS`, `ANTHROPIC_API_KEY`, `MOCK_LLM`, `ALERT_WEBHOOK_URL`, `RATE_LIMIT_PER_MIN`).
- [ ] Makefile or npm-free scripts: `make run`, `make test`, `make newman`, `make monitor`.

## Phase 1: Target API (system under test)
- [ ] `POST /v1/summarize`: body `{ "text": str (1-5000 chars), "max_words": int (10-200) }`, returns `{ "summary": str, "model": str, "latency_ms": int, "request_id": str }`.
- [ ] `GET /health` returns status and mode (mock/live).
- [ ] API key auth via `X-API-Key` header; 401 on missing, 403 on invalid.
- [ ] Simple in-memory rate limiter returning 429 with `Retry-After`.
- [ ] Request timeout (configurable, default 10s) returning 504 with a clear error body.
- [ ] Consistent error schema: `{ "error": { "code": str, "message": str, "request_id": str } }`.
- [ ] `llm_client.py`: mock client (deterministic output based on input) and live Anthropic client selected by `MOCK_LLM`.
- Check: manual curl for success, 401, 403, 422, 429.

## Phase 2: Fault injection
- [ ] `faults.py`: header `X-Fault: timeout | upstream_500 | slow | bad_json | empty_output` (honored only when `ENABLE_FAULTS=true`).
- [ ] Each fault triggers the matching upstream failure inside the mock client.
- [ ] Document each fault and the expected API response in `docs/faults.md`.
- Check: each fault returns the documented status and error body.

## Phase 3: pytest suite
- [ ] `test_auth.py`: missing key, wrong key, valid key.
- [ ] `test_schema.py`: valid payload; missing field; wrong types; text too long; `max_words` out of range; response matches the pydantic schema.
- [ ] `test_rate_limit.py`: burst above limit returns 429 with `Retry-After`; recovers after the window.
- [ ] `test_timeouts.py`: `X-Fault: slow` yields 504 within the configured limit.
- [ ] `test_malformed_input.py`: invalid JSON, empty body, unicode and very long strings, null bytes.
- [ ] `test_llm_output_contract.py`: non-deterministic-style checks: summary is non-empty, within `max_words`, language matches input, no leaked system prompt; use structure and constraints, not exact text. Also test `bad_json` and `empty_output` faults produce a handled error, not a 500 crash.
- [ ] Use fixtures, parametrization, and markers (`@pytest.mark.live` for optional live tests).
- Check: `pytest -q` passes in mock mode; coverage report shows what is covered (report the real number).

## Phase 4: Postman / Newman collection
- [ ] Build a collection mirroring the key scenarios (auth, validation, rate limit, health) with test scripts asserting status, schema and headers.
- [ ] Environment file with `base_url` and `api_key` variables (no real secrets).
- [ ] Run via Newman in CI and export an HTML report.
- Check: `make newman` passes against the local server.

## Phase 5: Monitor and alerts
- [ ] `monitor/run_checks.py`: hits `/health` and one real `/v1/summarize` request against a configurable base URL, measures latency, validates response contract.
- [ ] On failure: append a JSON line (timestamp, check name, status, latency, error) to `failures.jsonl` and call `alert.py` to post a concise message to the webhook.
- [ ] Alert de-duplication: do not re-alert for the same failing check within 30 minutes (state in a small JSON file).
- [ ] `monitor.yml`: GitHub Actions cron (e.g., hourly) plus manual dispatch; webhook URL from repository secret.
- [ ] Optional: export an n8n workflow JSON that does the same check on a schedule and add it under `n8n/`. Only mention n8n on the resume if this exists.
- Check: break the API key in the monitor env; the alert arrives once, not repeatedly.

## Phase 6: CI
- [ ] `ci.yml`: on push and PR: install, start the API in mock mode, run pytest and Newman, upload reports as artifacts.
- [ ] Badge in README.
- Check: CI green on main; a deliberately broken test makes CI red.

## Phase 7: Runbook and docs
- [ ] `RUNBOOK.md`: table of failure symptom, likely cause, how to confirm, fix, and who to escalate to, covering: 401/403, 429, 504, 502/upstream 500, malformed LLM output, empty output, slow responses.
- [ ] README: problem statement, architecture diagram (Mermaid), run in under 5 commands, how to add a test, how alerts work, Limitations (in-memory rate limiter, mock-only determinism, single-instance).
- [ ] `docs/demo_script.md`: 2-minute demo.

## Demo script (2 minutes)
1. Start API, run `make test` (all green).
2. Invalid API key in the monitor environment, run `make monitor`, show the alert in Slack/Discord.
3. Open `RUNBOOK.md` at that failure and show the fix.

## Definition of done
- Mock-mode tests pass offline; CI green; monitor alert demonstrated at least once.
- README claims match what is in the repo.

## Resume bullets (use only after the above is true)
- Built automated tests (pytest, Postman/Newman) for an LLM-backed REST API covering authentication, schema validation, rate limits, timeouts and malformed input, with [X]% code coverage.
- Added a scheduled monitor with webhook alerts and a failure runbook for triage.
- Label this entry "Personal Project".

## Interview prep
- How do you test non-deterministic output? Assert structure and constraints (length, language, schema), not exact text.
- Why mock the LLM? Deterministic, free, fast tests; a small live suite covers real integration.
- What would you add next? Contract tests against the provider, load tests, distributed rate limiting.
