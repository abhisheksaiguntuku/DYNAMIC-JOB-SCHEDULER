import pytest
from app.database.db import engine, Base

@pytest.fixture(autouse=True, scope="function")
def reset_db():
    """Drop all tables and recreate them before each test to ensure isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # No explicit teardown needed; next test will drop again.
