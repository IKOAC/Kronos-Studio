"""Independent AI dashboard API; all analysis is manually triggered."""

from fastapi import APIRouter, Depends, HTTPException
from errors.errors import PredictionAPIError
from routers.groq_analysis import require_local_client
from schemas.ai_market import MarketAnalysisRequest
from schemas.groq_analysis import GroqAnalysisResponse
from schemas.trading_agents import TradingAgentsResponse
from services.ai_market import MarketAnalysisService
from services.ai_providers import ProviderAnalysisService
from services.groq_analysis import GroqAnalysisError

router = APIRouter(dependencies=[Depends(require_local_client)])


def _service():
    return MarketAnalysisService()


def _providers():
    return ProviderAnalysisService()


@router.get("/analysis/providers")
def providers(service=Depends(_providers)):
    try:
        return service.statuses()
    except GroqAnalysisError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.post(
    "/analysis/market", response_model=GroqAnalysisResponse | TradingAgentsResponse
)
def analyze_market(request: MarketAnalysisRequest, service=Depends(_service)):
    try:
        return service.analyze(request)
    except GroqAnalysisError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except PredictionAPIError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": "MARKET_DATA_UNAVAILABLE",
                "message": "Completed market data could not be loaded. Check the source, symbol and history period.",
            },
        ) from exc
