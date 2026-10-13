"""Bounded, manual scanner; callers cannot supply symbols, prompts, or model IDs."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class SignalScannerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interval: Literal["15m", "1h"] = "15m"
    pairs: int = Field(default=2, ge=1, le=3)
