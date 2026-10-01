from pydantic import BaseModel, Field


class SummarizeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    max_words: int = Field(ge=10, le=200)


class SummarizeResponse(BaseModel):
    summary: str
    model: str
    latency_ms: int
    request_id: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: str
    mode: str
