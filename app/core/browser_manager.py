import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from app.core.config import settings
from app.core.metadata_store import metadata_store
from config import SESSIONS

logger = logging.getLogger("kariyer_api.browser_manager")


class BrowserManager:
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = SESSIONS

    async def update_session_meta(self, token: str, updates: dict):
        session = self.sessions.get(token)
        if not session:
            return

        for k, v in updates.items():
            session[k] = v

        await metadata_store.save_session(token, session)

    async def cleanup_session(self, token: str, close_status: str = "closed"):
        session = self.sessions.get(token)
        if not session:
            return

        logger.info("Cleaning up browser session for token: %s", token)

        session["status"] = close_status
        await metadata_store.save_session(token, session)

        page: Optional[Page] = session.get("page")
        context: Optional[BrowserContext] = session.get("context")
        browser: Optional[Browser] = session.get("browser")

        if page and not page.is_closed():
            try:
                await page.close()
            except Exception as e:
                logger.debug("Error closing page for %s: %s", token, e)

        if context:
            try:
                await context.close()
            except Exception as e:
                logger.debug("Error closing context for %s: %s", token, e)

        if browser:
            try:
                await browser.close()
            except Exception as e:
                logger.debug("Error closing browser for %s: %s", token, e)

        session.pop("page", None)
        session.pop("context", None)
        session.pop("browser", None)
        session.pop("playwright", None)

    async def terminate_all(self):
        logger.info("Terminating all active browser sessions for shutdown...")
        tokens = list(self.sessions.keys())
        for token in tokens:
            await self.cleanup_session(token, close_status="terminated_by_system")
        logger.info("All browser sessions terminated.")


browser_manager = BrowserManager()
