"""Fixed research profile: the client cannot supply prompts, tools or extra turns."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from schemas.groq_analysis import (
    GroqAnalysisRequest,
    GroqAnalysisResponse,
    GroqFindings,
)


class TradingAgentsRequest(GroqAnalysisRequest):
    model_config = ConfigDict(extra="forbid")


class AgentReview(BaseModel):
    role: Literal["bull", "bear", "research_manager"]
    findings: GroqFindings


class AgentRunStats(BaseModel):
    profile: Literal["snapshot_debate_v1"] = "snapshot_debate_v1"
    requests_used: int = Field(ge=0, le=3)
    tokens_used: int = Field(ge=0)
    elapsed_ms: float = Field(ge=0)
    reserved_tokens: int = Field(gt=0)
    upstream_revision: str


class TradingAgentsResponse(GroqAnalysisResponse):
    snapshot_id: str
    agents: list[AgentReview] = Field(min_length=3, max_length=3)
    run_stats: AgentRunStats
