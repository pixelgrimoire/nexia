API Gateway (NexIA)

Notes
- SSE inbox streaming uses the optional dependency `sse-starlette`. If you want inbox streaming available in your environment, install the dependencies in `requirements.txt` or add `sse-starlette` to your environment.
- To avoid import-time failures when `sse-starlette` is not installed, the application imports `EventSourceResponse` lazily and returns HTTP 501 for the `/api/inbox/stream` endpoint when the package is missing.

Pydantic compatibility
- The project aims to be compatible with both Pydantic v1 and v2. API handlers use `getattr(model, 'model_dump', model.dict)()` or a small `if hasattr(..., 'model_dump')` fallback to support both versions.

How to run locally (dev)

1. Create a virtualenv and install deps:

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r services/api-gateway/requirements.txt
```

2. Run the service (example):

```powershell
uvicorn services.api-gateway.app.main:app --reload --port 8000
```
