import asyncio
import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app
from app.core.metadata_store import metadata_store
from config import SESSIONS


@pytest_asyncio.fixture
async def client():
    # Setup test DB
    test_db = "test_metadata.sqlite"
    metadata_store.db_path = test_db
    if os.path.exists(test_db):
        try:
            os.remove(test_db)
        except Exception:
            pass
    await metadata_store.init_db()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    # Teardown
    SESSIONS.clear()
    if os.path.exists(test_db):
        try:
            os.remove(test_db)
        except Exception:
            pass


class MockPage:
    def __init__(self, url: str = "https://ats.kariyer.net/dashboard"):
        self.url = url
        self._closed = False

    def is_closed(self) -> bool:
        return self._closed

    async def close(self):
        self._closed = True


@pytest.fixture
def mock_page():
    return MockPage()
