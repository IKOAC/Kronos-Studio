"""Read-only deterministic analysis of supplied OHLCV and forecasts."""

from fastapi import APIRouter

from schemas.financial_analysis import (
    FinancialAnalysisRequest,
    FinancialAnalysisResponse,
)
from services.financial_analysis.engine import analyze_financials

router = APIRouter()


@router.post("/analysis/metrics", response_model=FinancialAnalysisResponse)
def calculate_financial_metrics(
    request: FinancialAnalysisRequest,
) -> FinancialAnalysisResponse:
    return FinancialAnalysisResponse.model_validate(analyze_financials(request))
