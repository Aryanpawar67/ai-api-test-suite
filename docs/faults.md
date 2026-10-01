# Fault injection

Send `X-Fault: <name>` on `POST /v1/summarize` to make the **mock** LLM fail in a
specific way. The header is honored only when `ENABLE_FAULTS=true`; otherwise it is
ignored and the request succeeds normally. Faults have no effect in live mode.
An unknown fault name (with faults enabled) returns `400 invalid_fault`.

All errors use `{"error": {"code", "message", "request_id"}}`.

| Fault | What the mock LLM does | Status | `error.code` |
|---|---|---|---|
| `timeout` | Never responds; the API gives up after `REQUEST_TIMEOUT_SECONDS` | 504 | `upstream_timeout` |
| `slow` | Responds after `SLOW_FAULT_SECONDS` (default 15s). Returns 504 whenever that exceeds the timeout; succeeds if the timeout is raised above it | 504 | `upstream_timeout` |
| `upstream_500` | Raises as if the provider returned HTTP 500 | 502 | `upstream_error` |
| `bad_json` | Returns a truncated, unparseable reply | 502 | `bad_upstream_response` |
| `empty_output` | Returns a valid reply with an empty summary | 502 | `empty_upstream_output` |

Notes
- Provider error details are logged server-side (with the request ID), never returned to the client.
- The empty-summary check applies to the live client too, not just the mock.
