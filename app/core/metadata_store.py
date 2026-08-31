import json
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

import aiosqlite

from app.core.config import settings

logger = logging.getLogger("kariyer_api.metadata_store")
DB_PATH = settings.export_dir.parent / "metadata.sqlite"


class MetadataStore:
    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    email TEXT,
                    status TEXT,
                    created_at TEXT,
                    expires_at TEXT,
                    metadata JSON
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    token TEXT,
                    status TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    result JSON
                )
                """
            )
            await db.commit()

    async def save_session(self, token: str, session_data: dict):
        email = session_data.get("email", "")
        status = session_data.get("status", "initiating")
        created_at = session_data.get("created_at") or datetime.now(timezone.utc).isoformat()
        expires_at = session_data.get("expires_at") or datetime.now(timezone.utc).isoformat()

        meta = {
            k: v for k, v in session_data.items() if k not in ("page", "lock", "browser", "context")
        }

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sessions (token, email, status, created_at, expires_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(token) DO UPDATE SET
                    status=excluded.status,
                    expires_at=excluded.expires_at,
                    metadata=excluded.metadata
                """,
                (token, email, status, created_at, expires_at, json.dumps(meta)),
            )
            await db.commit()

    async def get_session(self, token: str) -> Optional[dict]:
        """
        Loads the session metadata from SQLite.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT metadata FROM sessions WHERE token = ?", (token,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return json.loads(row[0])
        return None

    async def get_all_sessions(self) -> Dict[str, dict]:
        sessions = {}
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT token, metadata FROM sessions") as cursor:
                async for row in cursor:
                    sessions[row[0]] = json.loads(row[1])
        return sessions

    async def delete_session(self, token: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM sessions WHERE token = ?", (token,))
            await db.commit()


metadata_store = MetadataStore()
