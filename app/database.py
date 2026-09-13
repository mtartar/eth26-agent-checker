"""Database engine and session management.

Kept deliberately thin: this module's only job is to hand out a SQLModel
engine and sessions built from configuration. Business logic never lives
here — see app/services/ for that. This separation means you can swap
SQLite for Postgres (just by changing `DATABASE_URL`) without touching any
other file.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings


def _make_engine():
    settings = get_settings()
    connect_args = (
        {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    )
    return create_engine(settings.database_url, connect_args=connect_args)


engine = _make_engine()


def init_db() -> None:
    """Create all tables. Safe to call repeatedly — it's a no-op if they exist."""
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a session that commits on success and rolls back on error.

    So callers always get commit/rollback/close handled consistently instead
    of repeating that boilerplate everywhere.
    """
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
