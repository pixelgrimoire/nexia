# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

- Fix: multiple `requirements.txt` files had markdown fences which prevented pip from parsing them in CI; fences removed across services.
- Fix: pin `psycopg[binary]` to `3.2.10` in services that require the binary extra to ensure installability.
- Chore: migrate `services/contacts` and `services/api-gateway` FastAPI startup logic from `@app.on_event("startup")` to `lifespan` handlers to avoid deprecated startup hooks and improve startup semantics.
- Chore: make Pydantic schemas and payload handling compatible with both Pydantic v1 and v2 (use `model_dump()` when available, fallback to `.dict()`), and update tests accordingly.
- Fix: tests updated to dispose SQLAlchemy engine in teardown to avoid Windows file-lock PermissionError on temporary SQLite files.
- Docs: added `services/api-gateway/README.md` describing optional `sse-starlette` dependency and Pydantic notes; updated `DevStack.md` to pin `psycopg` and note the API gateway changes.
- Chore: small cleanups and test name fixes to avoid pytest collection warnings.

## Notes
- CI should now be able to install all service dependencies and run tests successfully.
- If you rely on SSE inbox streaming, ensure `sse-starlette` is installed in your environment or in the api-gateway requirements (already added).

