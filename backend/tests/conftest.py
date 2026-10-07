import os

import pytest

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["DEMO_MODE"] = "true"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app import demo
    from app.db.session import SessionLocal
    from app.main import app

    with SessionLocal() as db:
        demo.build(db)
    yield TestClient(app)
    os.remove("test.db")
