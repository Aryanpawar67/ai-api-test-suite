import asyncio
import hmac
import logging
import os
import time
import uuid
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .faults import parse_fault
from .llm_client import EmptyUpstreamOutput, UpstreamError, get_client
from .schemas import HealthResponse, SummarizeRequest, SummarizeResponse

logger = logging.getLogger("target_api")
app = FastAPI(title="AI Summarize API")
llm = get_client()


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict | None = None):
        self.status, self.code, self.message, self.headers = status, code, message, headers


def error_response(request: Request, status: int, code: str, message: str, headers=None):
    return JSONResponse(
        status_code=status,
        headers=headers,
        content={"error": {"code": code, "message": message, "request_id": request.state.request_id}},
    )


# --- config (read per request so tests can change env vars) ---
def api_keys() -> set[str]:
    return {k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()}


def rate_limit() -> int:
    return int(os.getenv("RATE_LIMIT_PER_MIN", "30"))


def request_timeout() -> float:
    return float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))


# --- in-memory sliding-window rate limiter (single instance only) ---
RATE_WINDOW_SECONDS = 60
_hits: dict[str, deque] = defaultdict(deque)


def reset_rate_limiter() -> None:
    _hits.clear()


def check_rate_limit(key: str) -> None:
    now = time.monotonic()
    hits = _hits[key]
    while hits and now - hits[0] >= RATE_WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= rate_limit():
        retry_after = max(1, int(RATE_WINDOW_SECONDS - (now - hits[0])) + 1)
        raise APIError(429, "rate_limited", "Too many requests.", {"Retry-After": str(retry_after)})
    hits.append(now)


def key_is_valid(candidate: str) -> bool:
    # Constant-time comparison against every configured key (no early exit).
    matched = False
    for key in api_keys():
        matched |= hmac.compare_digest(candidate.encode(), key.encode())
    return matched


def authenticate(request: Request, x_api_key: str | None = Header(default=None)) -> str:
    if not x_api_key:
        raise APIError(401, "missing_api_key", "X-API-Key header is required.")
    if not key_is_valid(x_api_key):
        # Throttle key guessing: failed attempts count against the client IP.
        check_rate_limit(f"invalid:{request.client.host if request.client else 'unknown'}")
        raise APIError(403, "invalid_api_key", "API key is not valid.")
    check_rate_limit(x_api_key)
    return x_api_key


# --- middleware and error handlers ---
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    return error_response(request, exc.status, exc.code, exc.message, exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0]
    where = ".".join(str(p) for p in first["loc"])
    return error_response(request, 422, "validation_error", f"{where}: {first['msg']}")


# --- routes ---
@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", mode=llm.mode)


@app.post("/v1/summarize", response_model=SummarizeResponse)
async def summarize(
    body: SummarizeRequest,
    request: Request,
    _key: str = Depends(authenticate),
    x_fault: str | None = Header(default=None),
):
    try:
        fault = parse_fault(x_fault)
    except ValueError as exc:
        raise APIError(400, "invalid_fault", str(exc))
    start = time.perf_counter()
    try:
        summary, model = await asyncio.wait_for(
            llm.summarize(body.text, body.max_words, fault), timeout=request_timeout()
        )
    except asyncio.TimeoutError:
        raise APIError(504, "upstream_timeout", "The LLM did not respond in time.")
    except UpstreamError as exc:
        logger.error("upstream error (request %s): %s", request.state.request_id, exc)
        raise APIError(502, exc.code, "The LLM provider returned an error.")
    if not summary.strip():
        logger.error("empty upstream output (request %s)", request.state.request_id)
        raise APIError(502, EmptyUpstreamOutput.code, "The LLM provider returned an empty summary.")
    return SummarizeResponse(
        summary=summary,
        model=model,
        latency_ms=int((time.perf_counter() - start) * 1000),
        request_id=request.state.request_id,
    )
