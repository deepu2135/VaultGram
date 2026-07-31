import os
import sys

for path in ['/data/data/com.termux/files/usr/lib/python3.14/site-packages', '/root/.local/lib/python3.14/site-packages']:
    if os.path.exists(path) and path not in sys.path:
        sys.path.append(path)

import asyncio
import uuid
import base64
from typing import Optional, Callable, Dict, Any

# Fix for Pyrogram import in Python 3.14 when no running loop exists
try:
    asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from pyrogram import Client, filters
from pyrogram.types import Message

class TelegramStorageEngine:
    """
    Telegram MTProto Client & Storage Engine.
    Handles authentication, chunked file upload/download, private channel setup, and progress callbacks.
    """
    def __init__(self, session_name: str = "vaultgram_session",
                 api_id: Optional[int] = None, api_hash: Optional[str] = None,
                 bot_token: Optional[str] = None):
        self.session_name = session_name
        self.api_id = api_id or int(os.environ.get("TELEGRAM_API_ID", 6))
        self.api_hash = api_hash or os.environ.get("TELEGRAM_API_HASH", "eb6 fragments test hash")
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.client: Optional[Client] = None
        self.channel_id: Optional[int] = None

    async def initialize(self) -> bool:
        """Initialize and start Pyrogram MTProto Client."""
        try:
            workdir = "/root/vaultgram"
            if self.bot_token:
                self.client = Client(
                    self.session_name,
                    api_id=self.api_id,
                    api_hash=self.api_hash,
                    bot_token=self.bot_token,
                    workdir=workdir
                )
            else:
                self.client = Client(
                    self.session_name,
                    api_id=self.api_id,
                    api_hash=self.api_hash,
                    workdir=workdir
                )
            await self.client.start()
            return True
        except Exception as e:
            print(f"[TelegramStorageEngine] Initialization error: {e}")
            return False

    async def stop(self):
        if self.client:
            await self.client.stop()

    async def upload_encrypted_file(self, file_path: str, caption_metadata: str,
                                    progress_callback: Optional[Callable[[int, int], None]] = None) -> Optional[Message]:
        """Upload an encrypted file document to Telegram with metadata caption."""
        if not self.client:
            raise RuntimeError("Telegram client is not initialized")
        
        chat_id = "me"  # Uploads to Saved Messages by default
        
        try:
            msg = await self.client.send_document(
                chat_id=chat_id,
                document=file_path,
                caption=caption_metadata,
                progress=progress_callback
            )
            return msg
        except Exception as e:
            print(f"[TelegramStorageEngine] Upload error: {e}")
            return None

    async def download_encrypted_file(self, message_id: int, output_path: str,
                                      progress_callback: Optional[Callable[[int, int], None]] = None) -> Optional[str]:
        """Download an encrypted document from Telegram by message ID."""
        if not self.client:
            raise RuntimeError("Telegram client is not initialized")

        try:
            msg = await self.client.get_messages("me", message_id)
            if not msg or not msg.document:
                return None

            downloaded_path = await self.client.download_media(
                msg.document,
                file_name=output_path,
                progress=progress_callback
            )
            return downloaded_path
        except Exception as e:
            print(f"[TelegramStorageEngine] Download error: {e}")
            return None
