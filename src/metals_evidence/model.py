"""Validated canonical envelopes. All fixture and live paths use these same types."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

QUALITY = frozenset({"OK", "PRELIMINARY", "REVISED", "SUSPECT", "MISSING"})
UNITS = frozenset({"tonne", "CNY/tonne", "USD/tonne", "USD/lb"})
METALS = frozenset({"COPPER", "ALUMINUM"})


def timestamp(value: str) -> datetime:
    """Reject ambiguous naive times, then normalize to UTC."""
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamps must include an explicit timezone")
    return result.astimezone(UTC)


def utc(value: str) -> str:
    return timestamp(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def number(value: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("numeric values must be decimal strings, not binary floats")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid decimal value") from exc
    if not result.is_finite():
        raise ValueError("numeric values must be finite")
    return result


def decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


@dataclass(frozen=True)
class Contract:
    """Metadata travels with the versioned observation, never a current-only lookup."""

    code: str
    exchange: str
    delivery_month: str
    last_trade_time: str

    def __post_init__(self) -> None:
        if not self.code or not self.exchange:
            raise ValueError("contract code and exchange are required")
        datetime.strptime(self.delivery_month + "-01", "%Y-%m-%d")
        object.__setattr__(self, "last_trade_time", utc(self.last_trade_time))

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(frozen=True)
class Observation:
    source: str
    series: str
    metal: str
    geography: str
    event_time: str
    published_time: str
    ingested_time: str
    revision: int
    value: str | None
    unit: str
    definition: str
    quality: str
    raw_payload: str
    contract: Contract | None = None

    def __post_init__(self) -> None:
        for field in ("source", "series", "geography", "definition", "raw_payload"):
            if not isinstance(getattr(self, field), str) or not getattr(self, field).strip():
                raise ValueError(f"{field} must be nonempty text")
        for field in ("event_time", "published_time", "ingested_time"):
            object.__setattr__(self, field, utc(getattr(self, field)))
        if self.event_time > self.published_time:
            raise ValueError("realized observations cannot precede their event time")
        if self.published_time > self.ingested_time:
            raise ValueError("ingestion cannot precede source publication")
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("revision must be a nonnegative integer")
        if self.metal not in METALS or self.unit not in UNITS or self.quality not in QUALITY:
            raise ValueError("unsupported metal, unit, or quality")
        if self.value is None:
            if self.quality != "MISSING":
                raise ValueError("null values must be marked MISSING")
        elif self.quality == "MISSING":
            raise ValueError("MISSING observations must have null values")
        elif number(self.value) < 0:
            raise ValueError("this v1 accepts nonnegative price, stock, and flow levels only")

    def to_dict(self) -> dict:
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        data["contract"] = self.contract.to_dict() if self.contract else None
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Observation:
        data = dict(data)
        if data.get("contract") is not None:
            data["contract"] = Contract(**data["contract"])
        return cls(**data)

    @property
    def id(self) -> str:
        return digest(self.to_dict())

    @property
    def raw_hash(self) -> str:
        return hashlib.sha256(self.raw_payload.encode()).hexdigest()
