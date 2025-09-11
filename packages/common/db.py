import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Prefer a SQLite default for dev/test to avoid requiring Postgres
_DEFAULT_URL = "sqlite:///./dev.db"
_ENGINE = None
_ENGINE_URL = None

def _current_url() -> str:
    return os.getenv("DATABASE_URL", _DEFAULT_URL)

def get_engine():
    global _ENGINE, _ENGINE_URL
    url = _current_url()
    if _ENGINE is None or _ENGINE_URL != url:
        _ENGINE = create_engine(url, echo=False, future=True)
        _ENGINE_URL = url
    return _ENGINE

class _EngineProxy:
    def __getattr__(self, name):
        return getattr(get_engine(), name)
    def __repr__(self) -> str:
        eng = get_engine()
        return f"<EngineProxy to {eng!r}>"

# Expose an engine-like proxy that always reflects the current DATABASE_URL
engine = _EngineProxy()

# Expose a callable that returns a new Session bound to the current engine
def SessionLocal():
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)()
