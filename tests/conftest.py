"""Shared pytest fixtures.

The `db_session` fixture creates a fresh, isolated SQLite database for each
test (using an in-memory database, not the on-disk agent_checker.db used by
`app.database`'s default) so tests never interfere with each other or with
whatever's in your local dev database.
"""

import pytest
from sqlmodel import Session, SQLModel, create_engine

# Import models so their tables are registered on SQLModel.metadata before
# create_all runs — otherwise this test engine wouldn't know about them.
import app.models  # noqa: F401


@pytest.fixture()
def db_session():
    """Yield a session against a fresh in-memory SQLite database."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
