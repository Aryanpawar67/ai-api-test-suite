"""Fault injection for testing failure handling.

Send `X-Fault: <name>` to make the mock LLM client fail in a specific way.
Honored only when ENABLE_FAULTS=true; otherwise the header is ignored.
"""
import os

FAULTS = {"timeout", "upstream_500", "slow", "bad_json", "empty_output"}


def faults_enabled() -> bool:
    return os.getenv("ENABLE_FAULTS", "false").lower() == "true"


def slow_fault_seconds() -> float:
    return float(os.getenv("SLOW_FAULT_SECONDS", "15"))


def parse_fault(header_value: str | None) -> str | None:
    """Return the fault name to inject, None for no fault, ValueError if unknown."""
    if not header_value or not faults_enabled():
        return None
    if header_value not in FAULTS:
        raise ValueError(f"Unknown fault '{header_value}'. Valid: {', '.join(sorted(FAULTS))}")
    return header_value
