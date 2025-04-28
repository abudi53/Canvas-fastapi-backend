import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app
from src.database.core import Base, get_db

# Use PostgreSQL for testing - requires TEST_DATABASE_URL environment variable
# Example: TEST_DATABASE_URL=postgresql://testuser:testpassword@localhost:5432/testdb
SQLALCHEMY_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://user:password@localhost/testdb_default"
)

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    # Fallback or specific handling if needed, though the goal is PostgreSQL
    # For now, let's raise an error if the env var isn't set correctly for Postgres
    raise ValueError(
        "TEST_DATABASE_URL environment variable must be set to a PostgreSQL connection string."
    )


engine = create_engine(SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Create tables in the database before tests run
# This fixture now targets the PostgreSQL test database
@pytest.fixture(scope="session", autouse=True)
def setup_db():
    # Ensure the database exists and is clean before creating tables
    # Depending on your setup, you might need more sophisticated logic here
    # For now, we assume the database exists and we just manage tables
    Base.metadata.drop_all(bind=engine)  # Ensure clean state
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)  # Clean up after tests


# Fixture to override the get_db dependency
@pytest.fixture(scope="function")
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session  # provide the session to the test

    session.close()
    transaction.rollback()
    connection.close()


# Fixture for the FastAPI TestClient
@pytest.fixture(scope="function")
def client(db_session):
    # Dependency override for get_db
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()  # Ensure session is closed even if test fails

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    # Clean up dependency overrides after test
    app.dependency_overrides.clear()
