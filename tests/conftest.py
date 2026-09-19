from pathlib import Path

import pytest

from app.data import MarketData

DATA_PATH = Path(__file__).resolve().parent.parent / "Data.xlsx"


@pytest.fixture(scope="session")
def market() -> MarketData:
    return MarketData(str(DATA_PATH))


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c
