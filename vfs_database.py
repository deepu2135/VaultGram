import sqlite3
import time
from typing import List, Dict, Any, Optional

class VFSDatabase:
    """
    SQLite Database Manager for Virtual File System (VFS).
    Tracks virtual folders, file nodes, Telegram message references, and salt/passphrase states.
    """
    def __init__(self, db_path: str = "/root/vaultgram/vault.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # App Security & Settings Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """)

            # File System Nodes (Folders & Files)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT CHECK(type IN ('file', 'folder')),
                parent_id TEXT,
                telegram_msg_id INTEGER,
                telegram_file_id TEXT,
                size_bytes INTEGER DEFAULT 0,
                mime_type TEXT,
                sha256 TEXT,
                thumbnail_b64 TEXT,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(parent_id) REFERENCES nodes(id) ON DELETE CASCADE
            );
            """)
            conn.commit()

    def set_setting(self, key: str, value: str):
        with self._get_connection() as conn:
            conn.cursor().execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()

    def get_setting(self, key: str) -> Optional[str]:
        with self._get_connection() as conn:
            cur = conn.cursor().execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cur.fetchone()
            return row["value"] if row else None

    def add_node(self, node_id: str, name: str, node_type: str, parent_id: Optional[str],
                 telegram_msg_id: Optional[int] = None, telegram_file_id: Optional[str] = None,
                 size_bytes: int = 0, mime_type: Optional[str] = None, sha256: Optional[str] = None,
                 thumbnail_b64: Optional[str] = None):
        with self._get_connection() as conn:
            conn.cursor().execute("""
                INSERT OR REPLACE INTO nodes 
                (id, name, type, parent_id, telegram_msg_id, telegram_file_id, size_bytes, mime_type, sha256, thumbnail_b64, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (node_id, name, node_type, parent_id, telegram_msg_id, telegram_file_id, 
                  size_bytes, mime_type, sha256, thumbnail_b64, int(time.time())))
            conn.commit()

    def get_children(self, parent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            if parent_id is None:
                cur = conn.cursor().execute("SELECT * FROM nodes WHERE parent_id IS NULL ORDER BY type DESC, name ASC")
            else:
                cur = conn.cursor().execute("SELECT * FROM nodes WHERE parent_id = ? ORDER BY type DESC, name ASC", (parent_id,))
            return [dict(row) for row in cur.fetchall()]

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor().execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_all_media(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor().execute(
                "SELECT * FROM nodes WHERE type = 'file' ORDER BY created_at DESC"
            )
            return [dict(row) for row in cur.fetchall()]

    def delete_node(self, node_id: str):
        with self._get_connection() as conn:
            conn.cursor().execute("DELETE FROM nodes WHERE id = ?", (node_id,))
            conn.commit()
