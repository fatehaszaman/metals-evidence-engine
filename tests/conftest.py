from pathlib import Path

import pytest

from metals_evidence.archive import Archive
from metals_evidence.demo import records
from metals_evidence.evidence import Hypothesis

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def hypothesis():
    return Hypothesis.load(ROOT / "hypotheses/cn_copper_tightening.json")


@pytest.fixture
def archive():
    with Archive() as archive:
        for record in records():
            archive.append(record)
        yield archive
