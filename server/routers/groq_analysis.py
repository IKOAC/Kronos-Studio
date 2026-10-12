"""Local-only read-only Groq research endpoints."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request

from schemas.groq_analysis import GroqAnalysisRequest, GroqAnalysisResponse, GroqQuota
from services.groq_analysis import GroqAnalysisError, GroqAnalysisService
from services.ai_providers import ProviderAnalysisService

router = APIRouter()


def require_local_client(request: Request) -> None:
    """Prevent remote clients and arbitrary browser origins using the local key."""
    address = request.client.host if request.client else ""
    try:
        if not ipaddress.ip_address(address).is_loopback:
            raise ValueError("remote")
    except ValueError as exc:
        raise HTTPException(
            status_code=403, detail="Groq endpoints are only available locally."
        ) from exc

    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.port != 3000
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise HTTPException(status_code=403, detail="Untrusted browser origin.")


def _service() -> GroqAnalysisService:
    return ProviderAnalysisService()


@router.get(
    "/analysis/groq/usage",
    response_model=GroqQuota,
    dependencies=[Depends(require_local_client)],
)
def groq_usage(service: GroqAnalysisService = Depends(_service)) -> GroqQuota:
    try:
        return service.get_quota()
    except GroqAnalysisError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.post(
    "/analysis/groq",
    response_model=GroqAnalysisResponse,
    dependencies=[Depends(require_local_client)],
)
def analyze_with_groq(
    request: GroqAnalysisRequest,
    service: GroqAnalysisService = Depends(_service),
) -> GroqAnalysisResponse:
    try:
        return GroqAnalysisResponse.model_validate(service.analyze(request))
    except GroqAnalysisError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
