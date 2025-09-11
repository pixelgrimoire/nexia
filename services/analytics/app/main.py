from datetime import date, datetime
from enum import Enum

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse, Response
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


def _dt_bounds(start: date | None, end: date | None):
    """Convert inclusive date range into datetime bounds (UTC)."""
    start_dt = datetime.combine(start, datetime.min.time()) if start else None
    end_dt = datetime.combine(end, datetime.max.time()) if end else None
    return start_dt, end_dt


def _where_range(column: str, has_start: bool, has_end: bool) -> str:
    if has_start and has_end:
        return f" AND {column} BETWEEN :start AND :end"
    if has_start:
        return f" AND {column} >= :start"
    if has_end:
        return f" AND {column} <= :end"
    return ""


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
    """KPIs básicos: conteos, conversaciones únicas, tiempo de primera respuesta y tasa de respuesta."""
    start_dt, end_dt = _dt_bounds(params.start_date, params.end_date)
    has_start, has_end = start_dt is not None, end_dt is not None
    binds = {}
    if has_start:
        binds["start"] = start_dt
    if has_end:
        binds["end"] = end_dt

    try:
        where = _where_range("created_at", has_start, has_end)
        total = db.execute(text(f"SELECT COUNT(*) FROM messages WHERE 1=1{where}"), binds).scalar() or 0
        inbound = db.execute(text(f"SELECT COUNT(*) FROM messages WHERE direction='in'{where}"), binds).scalar() or 0
        outbound = db.execute(text(f"SELECT COUNT(*) FROM messages WHERE direction='out'{where}"), binds).scalar() or 0
        uniq_conv = db.execute(text(f"SELECT COUNT(DISTINCT conversation_id) FROM messages WHERE 1=1{where}"), binds).scalar() or 0
    except Exception:
        total = inbound = outbound = uniq_conv = 0

    avg_resp_sec = None
    resp_rate = None
    try:
        dialect = str(getattr(db.bind.dialect, "name", "")) if getattr(db, "bind", None) else ""
        range_pred = _where_range("m.created_at", has_start, has_end)
        if dialect == "sqlite":
            sql = text(
                """
                WITH first_in AS (
                  SELECT conversation_id, MIN(created_at) AS first_in_at
                  FROM messages
                  WHERE direction='in' AND created_at IS NOT NULL
                  GROUP BY conversation_id
                ),
                first_out AS (
                  SELECT m.conversation_id, MIN(m.created_at) AS first_out_at
                  FROM messages m
                  JOIN first_in fi ON m.conversation_id = fi.conversation_id
                  WHERE m.direction='out' AND m.created_at IS NOT NULL
                        AND m.created_at >= fi.first_in_at
                  GROUP BY m.conversation_id
                )
                SELECT
                  AVG((julianday(fo.first_out_at) - julianday(fi.first_in_at)) * 86400.0) AS avg_sec,
                  CAST(COUNT(fo.conversation_id) AS REAL) / NULLIF(COUNT(fi.conversation_id), 0) AS rate
                FROM first_in fi
                LEFT JOIN first_out fo ON fi.conversation_id = fo.conversation_id;
                """
            )
            row = db.execute(sql).fetchone()
        else:
            sql = text(
                f"""
                WITH base AS (
                  SELECT * FROM messages m WHERE 1=1{range_pred}
                ),
                first_in AS (
                  SELECT conversation_id, MIN(created_at) AS first_in_at
                  FROM base
                  WHERE direction='in' AND created_at IS NOT NULL
                  GROUP BY conversation_id
                ),
                first_out AS (
                  SELECT b.conversation_id, MIN(b.created_at) AS first_out_at
                  FROM base b
                  JOIN first_in fi ON b.conversation_id = fi.conversation_id
                  WHERE b.direction='out' AND b.created_at >= fi.first_in_at
                  GROUP BY b.conversation_id
                )
                SELECT
                  AVG(EXTRACT(EPOCH FROM (fo.first_out_at - fi.first_in_at))) AS avg_sec,
                  CAST(COUNT(fo.conversation_id) AS DECIMAL) / NULLIF(COUNT(fi.conversation_id), 0) AS rate
                FROM first_in fi
                LEFT JOIN first_out fo ON fi.conversation_id = fo.conversation_id
                """
            )
            row = db.execute(sql, binds).fetchone()
        if row is not None:
            avg_resp_sec = float(row[0]) if row[0] is not None else None
            resp_rate = float(row[1]) if row[1] is not None else None
    except Exception:
        avg_resp_sec = None
        resp_rate = None

    return {
        "total_messages": int(total),
        "inbound_messages": int(inbound),
        "outbound_messages": int(outbound),
        "unique_conversations": int(uniq_conv),
        "avg_first_response_seconds": avg_resp_sec,
        "response_rate": resp_rate,
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
    """Exporta mensajes recientes en CSV o JSON (campos mínimos)."""
    try:
        rows = db.execute(
            text(
                """
                SELECT id, conversation_id, direction, type, created_at
                FROM messages
                ORDER BY COALESCE(created_at, id) DESC
                LIMIT :lim
                """
            ),
            {"lim": params.limit},
        ).fetchall()
    except Exception:
        rows = []

    items = [
        {
            "id": r._mapping.get("id"),
            "conversation_id": r._mapping.get("conversation_id"),
            "direction": r._mapping.get("direction"),
            "type": r._mapping.get("type"),
            "created_at": r._mapping.get("created_at").isoformat() if r._mapping.get("created_at") else None,
        }
        for r in rows
    ]

    if params.format == ExportFormat.json:
        return JSONResponse(items)

    # CSV
    import io, csv

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["id", "conversation_id", "direction", "type", "created_at"])
    w.writeheader()
    for it in items:
        w.writerow(it)
    data = buf.getvalue()
    return Response(content=data, media_type="text/csv")


@app.get("/healthz")
async def healthz():
    return {"ok": True}

