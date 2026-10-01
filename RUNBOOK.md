# Runbook

Triage guide for the AI summarize API. Every error response has the shape
`{"error": {"code", "message", "request_id"}}`; **start with `error.code` and the
`request_id`**, then search server logs for that ID (upstream detail is logged there, never returned to clients).

"Escalate to" uses roles, since this is a single-owner project: *API owner* = whoever runs the service,
*Provider* = the LLM vendor's status page / support.

| Symptom | `error.code` | Likely cause | How to confirm | Fix | Escalate to |
|---|---|---|---|---|---|
| **401** on every call | `missing_api_key` | Client not sending `X-API-Key`; header stripped by a proxy; monitor env var empty | `curl -i -H "X-API-Key: <key>" .../v1/summarize`; check the client/monitor sends the header; `echo $MONITOR_API_KEY` | Set the header / secret (`MONITOR_API_KEY` in GitHub secrets for the monitor) | Client team if it's their integration; otherwise API owner |
| **403** on every call | `invalid_api_key` | Key rotated or removed from `API_KEYS`; typo or stray whitespace in the secret; many 403s from one IP also trip the throttle (then 429) | Compare the key in the caller's config with the server's `API_KEYS`; a valid key works with `curl` | Update the caller's key or add it to `API_KEYS` and restart; fix the monitor secret | API owner (key management). If 403s come from unknown callers in volume, treat as key guessing and block the source |
| **429** | `rate_limited` | Caller exceeded `RATE_LIMIT_PER_MIN` for its key (or 403 attempts from one IP); retry storm | Response has `Retry-After` (seconds); count requests per key in logs | Client: back off and honor `Retry-After`. Server: raise `RATE_LIMIT_PER_MIN` if legitimate. Note the limiter is in-memory and per instance | API owner if limits are too low for a legitimate use |
| **504** | `upstream_timeout` | LLM slower than `REQUEST_TIMEOUT_SECONDS` (default 10s); provider degraded; very long input | Provider status page; compare `latency_ms` of recent successes; reproduce with `X-Fault: slow` in a test env to rule out the API itself | Retry (idempotent); raise `REQUEST_TIMEOUT_SECONDS` if the provider is just slow; shorten inputs | Provider if their status shows degradation; otherwise API owner |
| **502** | `upstream_error` | Provider returned an error (5xx, auth failure, quota exhausted, network) | Server log line `upstream error (request <id>)` has the real provider message; check `ANTHROPIC_API_KEY` validity and billing/quota | Fix the credential or quota; wait out a provider incident; retry later | Provider (incident/quota); API owner (credentials) |
| **502** | `bad_upstream_response` | Provider reply could not be parsed (truncated/non-JSON), e.g. cut off by token limit | Log line for the request ID; reproduce with `X-Fault: bad_json` to confirm the API handles it | Retry; if persistent, review `max_tokens` and the parsing code in `llm_client.py` | API owner; Provider if replies are malformed |
| **502** | `empty_upstream_output` | Model returned nothing (filtered, refused, or whitespace-only input) | Log line `empty upstream output (request <id>)`; try the same input manually | Retry; check input isn't blank/whitespace; review prompt if it refuses valid inputs | API owner |
| **Slow but 200** | none (`latency_ms` high, monitor says `too slow`) | Provider latency, large `max_words`, cold start, host resource pressure | `latency_ms` in responses; `monitor/failures.jsonl` for the trend; Newman/monitor timing | Lower `max_words`, check host CPU/memory, check provider status; adjust `MAX_LATENCY_MS` if the threshold is unrealistic | Provider for sustained latency; API owner for host issues |
| **Monitor alert, API unreachable** | n/a (connection error in `failures.jsonl`) | Service down, wrong `BASE_URL`, network | `curl $BASE_URL/health`; check the process/host | Restart the service; correct `BASE_URL` | API owner |

## Alerts
The monitor posts one message per failing check, then stays quiet for 30 minutes
(`monitor/alert_state.json`). Every failure is still written to `monitor/failures.jsonl`, so
check that file, not just Slack, to see how long something has been failing. A check that passes
resets its alert state.

## Reproducing failures safely
Run the API with `ENABLE_FAULTS=true` and send `X-Fault: timeout | slow | upstream_500 | bad_json | empty_output`
(see `docs/faults.md`). Never enable this in production.
