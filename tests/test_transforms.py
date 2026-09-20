from dataclasses import replace

import pytest

from metals_evidence.demo import records
from metals_evidence.transforms import nearby_spread

TIME = "2025-09-18T07:00:00Z"


def test_spread_sign_exactness_and_lineage():
    data = records()[2:4]
    spread = nearby_spread(data, TIME)
    assert spread.value == "200"
    assert spread.parents == (data[0].id, data[1].id)
    assert spread.contracts == ("DEMO-CU-202510", "DEMO-CU-202511")
    assert spread.unit == "CNY/tonne"


@pytest.mark.parametrize(
    "change",
    [
        {"source": "other"},
        {"unit": "USD/tonne"},
        {"metal": "ALUMINUM"},
        {"geography": "US"},
    ],
)
def test_incompatible_contracts_rejected(change):
    first, second = records()[2:4]
    with pytest.raises(ValueError, match="incompatible"):
        nearby_spread([first, replace(second, **change)], TIME)


def test_different_exchange_rejected():
    first, second = records()[2:4]
    second = replace(second, contract=replace(second.contract, exchange="OTHER"))
    with pytest.raises(ValueError, match="incompatible"):
        nearby_spread([first, second], TIME)


def test_missing_nearby_not_silently_skipped():
    first, second = records()[2:4]
    first = replace(first, value=None, quality="MISSING")
    with pytest.raises(ValueError, match="missing"):
        nearby_spread([first, second], TIME)


def test_duplicate_delivery_ambiguous():
    first, second = records()[2:4]
    second = replace(
        second, contract=replace(second.contract, delivery_month=first.contract.delivery_month)
    )
    with pytest.raises(ValueError, match="duplicate"):
        nearby_spread([first, second], TIME)


def test_expired_contract_not_eligible():
    first, second = records()[2:4]
    first = replace(first, contract=replace(first.contract, last_trade_time=TIME))
    with pytest.raises(ValueError, match="fewer than two"):
        nearby_spread([first, second], TIME)


def test_non_price_units_rejected():
    data = [replace(o, unit="tonne") for o in records()[2:4]]
    with pytest.raises(ValueError, match="price quotations"):
        nearby_spread(data, TIME)


def test_mismatched_observation_times_rejected():
    with pytest.raises(ValueError, match="fewer than two"):
        nearby_spread([records()[0], records()[3]], TIME)
