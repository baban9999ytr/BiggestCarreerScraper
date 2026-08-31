import asyncio
import os
import unittest
from datetime import datetime, timezone

from app.core.metadata_store import metadata_store
from app.core.browser_manager import browser_manager
from config import SESSIONS

class MockPage:
    def __init__(self):
        self._closed = False
        self.close_called = False

    def is_closed(self):
        return self._closed

    async def close(self):
        self._closed = True
        self.close_called = True


class MockContext:
    def __init__(self):
        self.close_called = False

    async def close(self):
        self.close_called = True


class MockBrowser:
    def __init__(self):
        self.close_called = False

    async def close(self):
        self.close_called = True


class TestPhase2Features(unittest.IsolatedAsyncioTestCase):
    
    async def asyncSetUp(self):
        # Override DB path for tests
        metadata_store.db_path = "test_metadata.sqlite"
        if os.path.exists("test_metadata.sqlite"):
            os.remove("test_metadata.sqlite")
        await metadata_store.init_db()

    async def asyncTearDown(self):
        if os.path.exists("test_metadata.sqlite"):
            try:
                os.remove("test_metadata.sqlite")
            except:
                pass
        SESSIONS.clear()

    async def test_sqlite_metadata_persistence(self):
        token = "test_persistence_token"
        test_session = {
            "token": token,
            "email": "test@example.com",
            "status": "waiting_for_2fa_code",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": datetime.now(timezone.utc).isoformat(),
            # These shouldn't be serialized:
            "page": MockPage(),
            "lock": asyncio.Lock()
        }
        
        # Save session
        await metadata_store.save_session(token, test_session)
        
        # Simulate a crash/restart by clearing memory
        SESSIONS.clear()
        
        # Reload from DB
        all_sessions = await metadata_store.get_all_sessions()
        self.assertIn(token, all_sessions)
        
        reloaded = all_sessions[token]
        self.assertEqual(reloaded["email"], "test@example.com")
        self.assertEqual(reloaded["status"], "waiting_for_2fa_code")
        
        # Ensure runtime objects were NOT serialized
        self.assertNotIn("page", reloaded)
        self.assertNotIn("lock", reloaded)

    async def test_browser_cleanup_and_status_update(self):
        token = "test_cleanup_token"
        page = MockPage()
        context = MockContext()
        browser = MockBrowser()
        
        session = {
            "token": token,
            "status": "authenticated",
            "page": page,
            "context": context,
            "browser": browser,
            "lock": asyncio.Lock()
        }
        SESSIONS[token] = session
        
        # Verify initial state
        self.assertFalse(page.close_called)
        self.assertFalse(context.close_called)
        self.assertFalse(browser.close_called)
        
        # Cleanup
        await browser_manager.cleanup_session(token, close_status="failed_due_to_error")
        
        # Verify Playwright objects were closed
        self.assertTrue(page.close_called)
        self.assertTrue(context.close_called)
        self.assertTrue(browser.close_called)
        
        # Verify runtime dictionary was cleansed of playwright objects
        self.assertNotIn("page", session)
        self.assertNotIn("context", session)
        self.assertNotIn("browser", session)
        
        # Verify status update in SQLite
        db_meta = await metadata_store.get_session(token)
        self.assertIsNotNone(db_meta)
        self.assertEqual(db_meta["status"], "failed_due_to_error")


if __name__ == "__main__":
    unittest.main()
