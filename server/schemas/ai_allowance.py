"""Sanitized provider-reported USD allowances, separate from local token estimates."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Money = float | None


class ProviderAllowance(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    status: Literal["available", "partial", "permission_required", "unavailable"]
    balance_status: Literal["available", "permission_required", "unavailable"]
    key_status: Literal["available", "unavailable", "not_supported"]
    checked_at_utc: str
    balance_remaining_usd: Money = Field(default=None, ge=0)
    account_credits_usd: Money = Field(default=None, ge=0)
    account_usage_usd: Money = Field(default=None, ge=0)
    spending_scope: Literal["key", "effective"] = "key"
    spending_limit_usd: Money = Field(default=None, ge=0)
    spending_used_usd: Money = Field(default=None, ge=0)
    spending_remaining_usd: Money = Field(default=None, ge=0)
    spending_percent: Money = Field(default=None, ge=0)
    limit_reset: Literal["daily", "weekly", "monthly"] | None = None
    key_usage_daily_usd: Money = Field(default=None, ge=0)
