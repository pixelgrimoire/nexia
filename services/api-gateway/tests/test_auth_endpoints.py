import importlib.util
import os
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path) -> TestClient:
    db_file = (tmp_path / "test.db").as_posix()
    os.environ["DATABASE_URL"] = f"sqlite:///{db_file}"
    os.environ["JWT_SECRET"] = "testsecret"
    os.environ["DEV_LOGIN_ENABLED"] = "true"

    # Force reload of DB module to pick up new DATABASE_URL
    import importlib
    import packages.common.db as common_db  # type: ignore
    importlib.reload(common_db)

    service_root = Path(__file__).resolve().parents[1]
    module_path = service_root / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("api_gateway_main", module_path)
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)

    # Create only the tables we need (organizations, users)
    from packages.common.db import engine
    from packages.common.models import Base

    Base.metadata.create_all(
        bind=engine,
        tables=[Base.metadata.tables["organizations"], Base.metadata.tables["users"]],
    )

    with TestClient(main.app) as c:
        yield c


def test_dev_login_and_me(client: TestClient):
    # dev login
    r = client.post(
        "/api/auth/dev-login",
        json={"email": "admin@example.com", "org_name": "Acme", "role": "admin"},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    assert token

    # call /api/me with token
    r2 = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    data = r2.json()
    assert data["email"] == "admin@example.com"
    assert data["role"] == "admin"
