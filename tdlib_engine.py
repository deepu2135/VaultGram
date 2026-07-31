import os
import sys
import json
import ctypes
import asyncio
import threading
import time
from typing import Optional, Callable, Dict, Any

class TDLibEngine:
    """
    Official TDLib (Telegram Database Library) JSON C-FFI Interface.
    Communicates directly with TDLib via C-FFI functions:
      - td_json_client_create()
      - td_json_client_send()
      - td_json_client_receive()
      - td_json_client_execute()
    """
    def __init__(self, api_id: Optional[int] = None, api_hash: Optional[str] = None,
                 database_dir: str = "/root/vaultgram/tdlib_data"):
        self.api_id = api_id or int(os.environ.get("TELEGRAM_API_ID", 94575))
        self.api_hash = api_hash or os.environ.get("TELEGRAM_API_HASH", "a3406de8d171326e16e80d38b58e3e0d")
        self.database_dir = database_dir

        os.makedirs(self.database_dir, exist_ok=True)

        self._client = None
        self._lib = None
        self._is_running = False
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._auth_state = "uninitialized"

        self._load_tdlib_c_library()

    def _load_tdlib_c_library(self):
        """Locate and load libtdjson shared library using ctypes."""
        possible_paths = [
            "libtdjson.so",
            "/usr/lib/libtdjson.so",
            "/usr/local/lib/libtdjson.so",
            "/data/data/com.termux/files/usr/lib/libtdjson.so",
            os.path.join(self.database_dir, "libtdjson.so")
        ]

        for path in possible_paths:
            try:
                self._lib = ctypes.CDLL(path)
                print(f"[TDLibEngine] Successfully loaded TDLib shared library from: {path}")
                break
            except Exception:
                continue

        if self._lib:
            self._lib.td_json_client_create.restype = ctypes.c_void_p
            self._lib.td_json_client_create.argtypes = []

            self._lib.td_json_client_send.restype = None
            self._lib.td_json_client_send.argtypes = [ctypes.c_void_p, ctypes.c_char_p]

            self._lib.td_json_client_receive.restype = ctypes.c_char_p
            self._lib.td_json_client_receive.argtypes = [ctypes.c_void_p, ctypes.c_double]

            self._lib.td_json_client_execute.restype = ctypes.c_char_p
            self._lib.td_json_client_execute.argtypes = [ctypes.c_void_p, ctypes.c_char_p]

    def send_request_sync(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Synchronously execute instant TDLib JSON requests."""
        if not self._lib or not self._client:
            return None
        req_str = json.dumps(request).encode('utf-8')
        res_ptr = self._lib.td_json_client_execute(self._client, req_str)
        if res_ptr:
            return json.loads(res_ptr.decode('utf-8'))
        return None

    def send_request_async(self, request: Dict[str, Any]) -> asyncio.Future:
        """Asynchronously send TDLib JSON request and return Future for response."""
        if "extra" not in request:
            request["@extra"] = f"req_{time.time()}_{os.urandom(4).hex()}"
        extra = request["@extra"]

        if not self._event_loop:
            self._event_loop = asyncio.get_event_loop()

        fut = self._event_loop.create_future()
        self._pending_requests[extra] = fut

        req_str = json.dumps(request).encode('utf-8')
        if self._lib and self._client:
            self._lib.td_json_client_send(self._client, req_str)
        else:
            fut.set_exception(RuntimeError("TDLib client is not initialized"))

        return fut

    def start(self):
        """Start TDLib client instance and worker event thread."""
        if not self._lib:
            print("[TDLibEngine] Warning: libtdjson.so not found on system. Using TDLib API Client Wrapper mode.")
            return

        self._client = self._lib.td_json_client_create()
        self._is_running = True
        self._recv_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._recv_thread.start()

    def _receive_loop(self):
        """Background thread receiving continuous JSON updates from TDLib."""
        while self._is_running and self._client:
            res_ptr = self._lib.td_json_client_receive(self._client, 1.0)
            if res_ptr:
                try:
                    update = json.loads(res_ptr.decode('utf-8'))
                    self._handle_update(update)
                except Exception as e:
                    print(f"[TDLibEngine] Error handling update: {e}")

    def _handle_update(self, update: Dict[str, Any]):
        """Handle TDLib state updates and resolve pending futures."""
        extra = update.get("@extra")
        if extra and extra in self._pending_requests:
            fut = self._pending_requests.pop(extra)
            if not fut.done():
                if update.get("@type") == "error":
                    fut.set_exception(RuntimeError(update.get("message", "TDLib Error")))
                else:
                    fut.set_result(update)

        update_type = update.get("@type")

        # TDLib Authorization State Handler
        if update_type == "updateAuthorizationState":
            state = update.get("authorization_state", {}).get("@type")
            self._auth_state = state
            print(f"[TDLibEngine] Auth State -> {state}")

            if state == "authorizationStateWaitTdlibParameters":
                self.send_request_async({
                    "@type": "setTdlibParameters",
                    "database_directory": self.database_dir,
                    "use_message_database": True,
                    "use_secret_chats": True,
                    "api_id": self.api_id,
                    "api_hash": self.api_hash,
                    "system_language_code": "en",
                    "device_model": "VaultGram Cloud Engine",
                    "application_version": "1.0.0"
                })
            elif state == "authorizationStateWaitEncryptionKey":
                self.send_request_async({
                    "@type": "checkDatabaseEncryptionKey",
                    "encryption_key": ""
                })

    async def upload_document(self, file_path: str, caption: str) -> Dict[str, Any]:
        """Upload encrypted document using TDLib sendDocument JSON method."""
        request = {
            "@type": "sendMessage",
            "chat_id": 0, # Saved Messages chat ID
            "input_message_content": {
                "@type": "inputMessageDocument",
                "document": {
                    "@type": "inputFileLocal",
                    "path": file_path
                },
                "caption": {
                    "@type": "formattedText",
                    "text": caption
                }
            }
        }
        return await self.send_request_async(request)
