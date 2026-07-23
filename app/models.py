"""Validated local API models."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    postal_code: str = Field(pattern=r"^[0-9]{5}$")
    radius: Decimal = Field(ge=Decimal("0.5"))
    distance_unit: str
    fuel: str
    currency: str
    open_only: bool = False
    sort: str
    refresh: bool = False

    @field_validator("distance_unit")
    @classmethod
    def valid_unit(cls, value: str) -> str:
        if value not in {"km", "mi"}:
            raise ValueError("Unsupported distance unit")
        return value

    @field_validator("fuel")
    @classmethod
    def valid_fuel(cls, value: str) -> str:
        if value not in {"e5", "e10", "diesel", "all"}:
            raise ValueError("Unsupported fuel")
        return value

    @field_validator("sort")
    @classmethod
    def valid_sort(cls, value: str) -> str:
        if value not in {"price", "distance", "name"}:
            raise ValueError("Unsupported sorting method")
        return value

    @field_validator("currency")
    @classmethod
    def normalized_currency(cls, value: str) -> str:
        value = value.upper()
        if not (3 <= len(value) <= 8 and value.isascii() and value.isalnum()):
            raise ValueError("Unsupported currency")
        return value


class SafeError(BaseModel):
    error: str
    message: str
    retry_after_seconds: int | None = None
