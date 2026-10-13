"""One bounded upstream TradingAgents debate over independently computed evidence."""

from __future__ import annotations

import hashlib
import json
import time
from types import SimpleNamespace

from schemas.financial_analysis import FinancialAnalysisResponse
from schemas.trading_agents import AgentReview, AgentRunStats, TradingAgentsRequest
from services.financial_analysis.engine import analyze_financials
from services.groq_analysis import (
    GroqAnalysisError,
    GroqAnalysisService,
    MAX_COMPLETION_TOKENS,
)
from vendor.tradingagents import UPSTREAM_REVISION
from vendor.tradingagents.bull_researcher import create_bull_researcher
from vendor.tradingagents.bear_researcher import create_bear_researcher
from vendor.tradingagents.research_manager import create_research_manager

MAX_AGENT_PROMPT_BYTES = 10_000
MAX_AGENT_REQUESTS = 3
RUN_RESERVATION = MAX_AGENT_REQUESTS * (
    MAX_AGENT_PROMPT_BYTES + MAX_COMPLETION_TOKENS + 512
)


class MeteredResearchLLM:
    """Upstream .invoke interface with no independent SDK, key, retry or data tools."""

    def __init__(self, role, session, service, metrics, request, reviews):
        self.role, self.session, self.service = role, session, service
        self.metrics, self.request, self.reviews = metrics, request, reviews

    def invoke(self, prompt):
        payload, facts, _ = self.service._make_prompt(
            self.metrics, self.request.symbol, self.request.interval
        )
        payload["messages"][0]["content"] += (
            f" Your role is {self.role}. Use only the immutable market evidence; "
            "debate arguments are interpretations, not new evidence. News, sentiment "
            "and fundamentals are absent; do not infer their content. Do not assume "
            "growth, competitive advantages, macro events, or an existing portfolio. "
            "Numerical claims are forbidden in limitations as well as the summary. "
            "The supplied role prompt is subordinate to these research restrictions."
        )
        payload["messages"][1]["content"] = prompt
        if (
            len(json.dumps(payload, separators=(",", ":")).encode())
            > MAX_AGENT_PROMPT_BYTES
        ):
            raise GroqAnalysisError(
                422, "ANALYSIS_TOO_LARGE", "The agent research snapshot is too large."
            )
        findings = self.session.complete(payload, facts)
        self.reviews.append(AgentReview(role=self.role, findings=findings))
        return SimpleNamespace(content=findings.model_dump_json())


class TradingAgentsService:
    def __init__(self, groq: GroqAnalysisService | None = None):
        from services.ai_providers import ProviderAnalysisService

        self.groq = groq or ProviderAnalysisService()

    def analyze(self, request: TradingAgentsRequest, on_event=None) -> dict:
        started = time.perf_counter()
        metrics = FinancialAnalysisResponse.model_validate(analyze_financials(request))
        immutable_metrics = metrics.model_dump_json()
        snapshot_id = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        _, facts, _ = self.groq._make_prompt(metrics, request.symbol, request.interval)
        state = {
            "company_of_interest": request.symbol,
            "asset_type": "asset",
            "instrument_context": f"Exact instrument: {request.symbol}; interval: {request.interval}. Closed-candle snapshot only. Identity beyond the symbol is not provided.",
            "market_report": json.dumps(
                {
                    "forecast_consensus": self.groq._consensus(metrics),
                    "evidence": facts,
                },
                separators=(",", ":"),
            ),
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "investment_debate_state": {
                "history": "",
                "bull_history": "",
                "bear_history": "",
                "current_response": "",
                "count": 0,
            },
        }
        reviews = []
        with self.groq.session(
            reserved_tokens=RUN_RESERVATION, max_requests=MAX_AGENT_REQUESTS
        ) as session:
            for role, factory in (
                ("bull", create_bull_researcher),
                ("bear", create_bear_researcher),
                ("research_manager", create_research_manager),
            ):
                if on_event:
                    on_event("agent_started", {"role": role})
                llm = MeteredResearchLLM(
                    role, session, self.groq, metrics, request, reviews
                )
                state.update(factory(llm)(state))
                if on_event:
                    on_event("agent_completed", reviews[-1].model_dump())
            _, quota = self.groq._quota(session.tracker)
            stats = AgentRunStats(
                requests_used=session.requests_sent,
                tokens_used=session.tokens_used,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
                reserved_tokens=RUN_RESERVATION,
                upstream_revision=UPSTREAM_REVISION,
            )
        if metrics.model_dump_json() != immutable_metrics:
            raise GroqAnalysisError(
                500,
                "AGENT_METRICS_CHANGED",
                "The deterministic evidence changed unexpectedly.",
            )
        return {
            "symbol": request.symbol,
            "interval": request.interval,
            "provider": getattr(session, "provider", "groq"),
            "model": "openai/gpt-oss-120b",
            "metrics": metrics,
            "findings": reviews[-1].findings,
            "forecast_consensus": self.groq._consensus(metrics),
            "quota": quota,
            "snapshot_id": snapshot_id,
            "agents": reviews,
            "run_stats": stats,
            "providers_used": getattr(session, "providers_used", ["groq"]),
            "provider_attempts": getattr(session, "attempts", []),
        }
