"""Contracts for the read-only Groq analysis backend."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas.financial_analysis import (
    FinancialAnalysisRequest,
    FinancialAnalysisResponse,
)

GROQ_MODEL = "openai/gpt-oss-120b"


class GroqAnalysisRequest(FinancialAnalysisRequest):
    """A finite numerical snapshot, never raw instructions for the language model."""

    symbol: str = Field(
        default="UNKNOWN", pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,31}$"
    )
    interval: str = Field(default="1h", pattern=r"^[0-9]{1,3}[A-Za-z]{1,3}$")

    @field_validator("forecasts")
    @classmethod
    def validate_model_ids(cls, values):
        # Prevent untrusted model identifiers becoming natural-language instructions.
        import re

        if any(
            not re.fullmatch(r"[A-Za-z0-9_./:-]{1,120}", value.model_name)
            for value in values
        ):
            raise ValueError(
                "Forecast model identifiers may only contain letters, digits, _ . / : -"
            )
        return values


class GroqFindings(BaseModel):
    """An LLM's bounded qualitative interpretation, never trade arithmetic."""

    model_config = ConfigDict(extra="forbid")

    setup_verdict: Literal["supports", "rejects", "unclear"] | None = None
    summary: str = Field(min_length=1, max_length=380)
    supporting_evidence_ids: list[str] = Field(max_length=5)
    conflicting_evidence_ids: list[str] = Field(max_length=5)
    limitations: list[str] = Field(max_length=3)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str):
        if not value.strip() or any(char.isdigit() for char in value):
            raise ValueError(
                "The model summary must not quote unverified numeric claims."
            )
        return value.strip()

    @field_validator("supporting_evidence_ids", "conflicting_evidence_ids")
    @classmethod
    def validate_evidence_ids(cls, value: list[str]):
        if len(set(value)) != len(value):
            raise ValueError("Evidence identifiers must be unique.")
        return value

    @field_validator("limitations")
    @classmethod
    def validate_limitations(cls, value: list[str]):
        if any(
            len(v) > 170 or not v.strip() or any(c.isdigit() for c in v) for v in value
        ):
            raise ValueError(
                "Limitations must be nonempty, bounded, and contain no numerical claims."
            )
        return value


class GroqQuota(BaseModel):
    day_utc: str
    token_limit_assumed: int | None
    tokens_observed: int
    token_percent_observed: float | None
    requests_limit: int | None
    requests_used: int
    requests_percent_used: float | None
    usage_percent: float | None
    cap_percent: float
    pending_5pct_alerts: list[int]
    token_tracking_scope: Literal["locally_recorded"] = "locally_recorded"


class GroqAnalysisResponse(BaseModel):
    symbol: str
    interval: str
    provider: Literal["groq"] = "groq"
    model: Literal["openai/gpt-oss-120b"] = GROQ_MODEL
    metrics: FinancialAnalysisResponse
    findings: GroqFindings
    forecast_consensus: Literal["up", "down", "flat", "mixed", "insufficient"]
    quota: GroqQuota
    providers_used: list[Literal["groq"]] = Field(default_factory=list)
    provider_attempts: list[dict] = Field(default_factory=list)
    market_data: dict | None = None
