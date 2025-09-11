import importlib.util
import os
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import declarative_base


DBBase = declarative_base()


class FlowModel(DBBase):
    __tablename__ = "flows"
    id = Column(String, primary_key=True)
    org_id = Column(String)
    name = Column(String)
    version = Column(Integer)
    graph = Column(JSON)
    status = Column(String)
    created_by = Column(String)


def make_token(role: str, org_id: str = "o1", sub: str = "u1") -> str:
    secret = os.environ["JWT_SECRET"]
    return jwt.encode({"sub": sub, "role": role, "org_id": org_id}, secret, algorithm="HS256")


@pytest.fixture
def client(tmp_path) -> TestClient:
    os.environ["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    os.environ["JWT_SECRET"] = "testsecret"

    service_root = Path(__file__).resolve().parents[1]
    module_path = service_root / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("api_gateway_main", module_path)
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)

    # Swap Flow model for sqlite-friendly version and create table
    main.DBFlow = FlowModel  # type: ignore
    from packages.common.db import engine

    DBBase.metadata.create_all(bind=engine)

    with TestClient(main.app) as c:
        yield c


def test_flows_crud_and_activation(client: TestClient):
    admin = make_token("admin", org_id="o1", sub="user-1")

    # create draft flow
    r = client.post(
        "/api/flows",
        headers={"Authorization": f"Bearer {admin}"},
        json={"name": "F1", "version": 1, "graph": {"nodes": []}},
    )
    assert r.status_code == 200
    f1 = r.json()
    assert f1["status"] == "draft"

    # create and activate second flow -> should mark others inactive
    r = client.post(
        "/api/flows",
        headers={"Authorization": f"Bearer {admin}"},
        json={"name": "F2", "version": 2, "graph": {"nodes": []}, "status": "active"},
    )
    assert r.status_code == 200
    f2 = r.json()
    assert f2["status"] == "active"

    # update f1 to active -> f2 becomes inactive
    r = client.put(
        f"/api/flows/{f1['id']}",
        headers={"Authorization": f"Bearer {admin}"},
        json={"status": "active"},
    )
    assert r.status_code == 200
    f1u = r.json()
    assert f1u["status"] == "active"

    # list and verify only one active
    r = client.get("/api/flows", headers={"Authorization": f"Bearer {admin}"})
    rows = r.json()
    actives = [x for x in rows if x.get("status") == "active"]
    assert len(actives) == 1

    # delete
    r = client.delete(f"/api/flows/{f2['id']}", headers={"Authorization": f"Bearer {admin}"})
    assert r.status_code == 200

