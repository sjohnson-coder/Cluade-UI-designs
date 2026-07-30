from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvaluateRequest(StrictModel):
    market: dict[str, Any] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=dict)
    broker: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, Any] = Field(default_factory=dict)
    burst: dict[str, Any] = Field(default_factory=dict)


class MissedRegisterRequest(StrictModel):
    signal_id: str | None = None
    side: Literal["BUY", "SELL"]
    entry: float
    sl: float
    tp: float
    gates: list[str] = Field(default_factory=list)
    timestamp: int | None = None

    @field_validator("entry", "sl", "tp")
    @classmethod
    def finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("price must be finite")
        return value

    @model_validator(mode="after")
    def valid_geometry(self):
        if self.side == "BUY" and not (self.sl < self.entry < self.tp):
            raise ValueError("BUY requires sl < entry < tp")
        if self.side == "SELL" and not (self.tp < self.entry < self.sl):
            raise ValueError("SELL requires tp < entry < sl")
        return self


class MissedResolveRequest(StrictModel):
    signal_id: str = Field(min_length=1)
    prices: list[float] = Field(min_length=1)
    timestamp: int | None = None

    @field_validator("prices")
    @classmethod
    def finite_prices(cls, values: list[float]) -> list[float]:
        if not all(math.isfinite(value) for value in values):
            raise ValueError("prices must be finite")
        return values


class GovernanceCandidateRequest(StrictModel):
    candidate_id: str | None = None
    change_type: str = "calibration"
    metrics: dict[str, Any]
    artifact_path: str
    feature_schema: list[str] = Field(min_length=1)


class GovernanceApproveRequest(StrictModel):
    candidate_id: str = Field(min_length=1)
