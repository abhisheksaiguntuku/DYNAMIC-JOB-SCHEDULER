import os
import tempfile
from pathlib import Path

os.environ.setdefault(
    "SQLITE_DB_PATH",
    str(Path(tempfile.gettempdir()) / "pytest_isolated_production_scheduler.db")
)

import pytest
from app.database.db import engine, Base

@pytest.fixture(autouse=True, scope="function")
def reset_db():
    """Drop all tables and recreate them before each test to ensure isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # No explicit teardown needed; next test will drop again.
