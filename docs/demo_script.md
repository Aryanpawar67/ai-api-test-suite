# 2-minute demo

Prep (before the call): `make install`; have a Slack/Discord webhook URL ready; two terminals.

**1. Tests green (~40s)**
- Terminal A: `make run` (API in mock mode).
- Terminal B: `make test`. Point out: offline, deterministic, and the coverage table (state the number it prints).
- Optional: `make newman` to show the Postman contract run.

**2. Break the key, get one alert (~50s)**
- `export ALERT_WEBHOOK_URL=<your webhook>`
- `MONITOR_API_KEY=wrong make monitor` → `FAIL summarize ... HTTP 403 invalid_api_key`; show the message in Slack/Discord.
- Run it again → "alert suppressed"; show `monitor/failures.jsonl` still logs both failures.

**3. Runbook (~30s)**
- Open `RUNBOOK.md`, find the **403** row: likely cause, how to confirm, fix.
- Fix the key (`make monitor`) → both checks `OK`.

Talking point if asked about LLM testing: assert structure and constraints (length, language, schema), not exact text; mock for deterministic CI, small `-m live` suite for real integration.
