"""Transparent calendar-spread construction with exact arithmetic and parent lineage."""

from __future__ import annotations

from dataclasses import dataclass

from metals_evidence.model import Observation, decimal_text, number, utc


@dataclass(frozen=True)
class Spread:
    event_time: str
    value: str
    unit: str
    contracts: tuple[str, str]
    parents: tuple[str, str]
    quality: tuple[str, str]
    definitions: tuple[str, str]

    def to_dict(self) -> dict:
        return {
            "event_time": self.event_time,
            "value": self.value,
            "unit": self.unit,
            "contracts": list(self.contracts),
            "parent_ids": list(self.parents),
            "quality": list(self.quality),
            "definitions": list(self.definitions),
            "convention": "earlier_delivery_minus_later_delivery",
        }


def nearby_spread(observations: list[Observation], event_time: str) -> Spread:
    """M1/M2 means nearest two valid deliveries in supplied coverage, not the entire exchange."""
    event_time = utc(event_time)
    points = [
        o
        for o in observations
        if o.contract and o.event_time == event_time and o.contract.last_trade_time > event_time
    ]
    if len(points) < 2:
        raise ValueError("fewer than two unexpired contracts at the same observation time")
    semantics = {(o.source, o.metal, o.geography, o.unit, o.contract.exchange) for o in points}
    if len(semantics) != 1:
        raise ValueError("incompatible source, metal, geography, exchange, or units")
    if points[0].unit not in {"CNY/tonne", "USD/tonne", "USD/lb"}:
        raise ValueError("curve inputs must be price quotations")
    points.sort(key=lambda o: (o.contract.delivery_month, o.contract.code))
    deliveries = [o.contract.delivery_month for o in points]
    if len(set(deliveries)) != len(deliveries):
        raise ValueError("ambiguous duplicate delivery months")
    front, second = points[:2]
    if any(o.value is None or o.quality == "SUSPECT" for o in (front, second)):
        raise ValueError("nearby contract is missing or suspect; do not skip to a later contract")
    return Spread(
        event_time=event_time,
        value=decimal_text(number(front.value) - number(second.value)),
        unit=front.unit,
        contracts=(front.contract.code, second.contract.code),
        parents=(front.id, second.id),
        quality=(front.quality, second.quality),
        definitions=(front.definition, second.definition),
    )
