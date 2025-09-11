"""
Seed minimal data for MVP dev:
- Organization (if missing)
- Approved template 'welcome' (es)
- Active flow with simple intent map, wait, set_attribute and send_text actions

Usage:
  python scripts/seed_mvp.py [Org Name]

Respects DATABASE_URL from environment.
"""
import os
import sys
import json
import uuid
from datetime import datetime

from packages.common.db import SessionLocal  # type: ignore
from packages.common import models  # type: ignore


def get_or_create_org(db, name: str):
    org = db.query(models.Organization).filter(models.Organization.name == name).first()
    if org:
        return org
    org = models.Organization(id=str(uuid.uuid4()), name=name)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def get_or_create_template(db, org_id: str, name: str, language: str = "es"):
    tpl = (
        db.query(models.Template)
        .filter(models.Template.org_id == org_id)
        .filter(models.Template.name == name, models.Template.language == language)
        .first()
    )
    if tpl:
        if getattr(tpl, "status", None) != "approved":
            tpl.status = "approved"
            db.commit()
        return tpl
    tpl = models.Template(
        id=str(uuid.uuid4()),
        org_id=org_id,
        name=name,
        language=language,
        category="utility",
        body="Hola {{1}}",
        variables=[],
        status="approved",
    )
    db.add(tpl)
    db.commit()
    return tpl


def create_or_update_active_flow(db, org_id: str):
    # deactivate existing flows in org
    try:
        db.query(models.Flow).filter(models.Flow.org_id == org_id).update({models.Flow.status: "inactive"})
        db.commit()
    except Exception:
        db.rollback()

    graph = {
        "name": "MVP demo flow",
        "version": 1,
        "nodes": [
            {"id": "t1", "type": "trigger", "on": "message_in"},
            {
                "id": "n1",
                "type": "intent",
                "map": {
                    "pricing": "path_precio",
                    "precio": "path_precio",
                    "greeting": "path_hola",
                    "default": "path_default",
                },
            },
        ],
        "paths": {
            "path_hola": [
                {"type": "action", "action": "send_text", "text": "Hola! 👋"},
                {"type": "wait", "seconds": 2},
                {"type": "set_attribute", "key": "last_greet", "value": True},
                {"type": "action", "action": "send_text", "text": "¿En qué puedo ayudarte?"},
            ],
            "path_precio": [
                {"type": "action", "action": "send_template", "template": "welcome", "language": {"code": "es"}},
            ],
            "path_default": [
                {"type": "action", "action": "send_text", "text": "Gracias, un agente te responderá pronto."},
            ],
        },
    }

    flow = models.Flow(
        id=str(uuid.uuid4()),
        org_id=org_id,
        name="MVP demo flow",
        version=1,
        graph=graph,
        status="active",
        created_by="seed",
    )
    db.add(flow)
    db.commit()
    return flow


def main():
    org_name = sys.argv[1] if len(sys.argv) > 1 else "Acme"
    with SessionLocal() as db:
        org = get_or_create_org(db, org_name)
        tpl = get_or_create_template(db, org.id, "welcome", "es")
        flow = create_or_update_active_flow(db, org.id)
        print("Seeded:")
        print("  org:", org.id, org.name)
        print("  template:", tpl.id, tpl.name, tpl.language, tpl.status)
        print("  flow:", flow.id, flow.name, flow.status)


if __name__ == "__main__":
    main()

