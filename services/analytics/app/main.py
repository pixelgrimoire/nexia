from datetime import date
from enum import Enum

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from packages.common.db import SessionLocal


app = FastAPI(title="NexIA Analytics")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class KPIParams(BaseModel):
    start_date: date | None = Field(
        None, description="Fecha de inicio para el cálculo de KPIs"
    )
    end_date: date | None = Field(
        None, description="Fecha de fin para el cálculo de KPIs"
    )

    class Config:
        extra = "forbid"


@app.get("/api/analytics/kpis")
def get_kpis(params: KPIParams = Depends(), db: Session = Depends(get_db)):
    """Devuelve KPIs básicos."""
    try:
        total_messages = db.execute(text("SELECT COUNT(*) FROM messages"))
        total_messages = total_messages.scalar() or 0
    except Exception:
        total_messages = 0
    return {
        "total_messages": total_messages,
        "start_date": params.start_date,
        "end_date": params.end_date,
    }


class ExportFormat(str, Enum):
    csv = "csv"
    json = "json"


class ExportParams(BaseModel):
    format: ExportFormat = Field(
        ExportFormat.csv, description="Formato de exportación"
    )
    limit: int = Field(100, ge=1, le=1000, description="Número máximo de filas")

    class Config:
        extra = "forbid"


@app.get("/api/analytics/export")
def export_data(params: ExportParams = Depends(), db: Session = Depends(get_db)):
    """Exporta datos de conversaciones."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        pass
    return {"format": params.format, "limit": params.limit}


@app.get("/healthz")
async def healthz():
    return {"ok": True}

