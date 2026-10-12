"""Manual, local-only TradingAgents review. No order/execution endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from routers.groq_analysis import require_local_client
from schemas.trading_agents import TradingAgentsRequest, TradingAgentsResponse
from services.groq_analysis import GroqAnalysisError
from services.trading_agents import TradingAgentsService

router = APIRouter()


def _service() -> TradingAgentsService:
    return TradingAgentsService()


@router.post(
    "/analysis/trading-agents",
    response_model=TradingAgentsResponse,
    dependencies=[Depends(require_local_client)],
)
def analyze_with_trading_agents(
    request: TradingAgentsRequest, service: TradingAgentsService = Depends(_service)
):
    try:
        return TradingAgentsResponse.model_validate(service.analyze(request))
    except GroqAnalysisError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
