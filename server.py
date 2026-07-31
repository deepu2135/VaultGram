import os
import sys
import json
import uuid
import base64
import tempfile
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

for path in ['/data/data/com.termux/files/usr/lib/python3.14/site-packages', '/root/.local/lib/python3.14/site-packages']:
    if os.path.exists(path) and path not in sys.path:
        sys.path.append(path)

from crypto_engine import CryptoEngine
from vfs_database import VFSDatabase
from tdlib_engine import TDLibEngine

# Initialize VFS & Engines
vfs = VFSDatabase()
tdlib = TDLibEngine()
tdlib.start()

MASTER_KEY = None
SALT = None

def upload_to_telegram_channel(bot_token: str, chat_id: str, file_path: str, caption: str, original_filename: str = "document.bin") -> Optional[int]:
    """Upload encrypted document to Telegram Channel using Telegram API."""
    try:
        import urllib.request

        url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
        boundary = '----VaultGramBoundary' + uuid.uuid4().hex
        
        body = []
        body.append(f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode())
        body.append(f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode())
        body.append(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{original_filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
        
        with open(file_path, 'rb') as f:
            file_bytes = f.read()
            
        full_body = b''.join(body) + file_bytes + f'\r\n--{boundary}--\r\n'.encode()

        req = urllib.request.Request(url, data=full_body, headers={
            'Content-Type': f'multipart/form-data; boundary={boundary}'
        })
        
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if res_data.get("ok"):
                result = res_data["result"]
                msg_id = result.get("message_id")
                file_id = result.get("document", {}).get("file_id")
                return msg_id, file_id
    except Exception as e:
        print(f"[TelegramUpload] Error posting to channel {chat_id}: {e}")
    return None, None

def download_from_telegram(bot_token: str, telegram_file_id: str, output_path: str) -> bool:
    """Download encrypted file from Telegram servers using Bot API getFile."""
    try:
        import urllib.request

        url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={telegram_file_id}"
        with urllib.request.urlopen(url) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if not res_data.get("ok"):
                return False
            file_path_tg = res_data["result"]["file_path"]

        download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path_tg}"
        with urllib.request.urlopen(download_url) as response:
            enc_data = response.read()

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(enc_data)
        return True
    except Exception as e:
        print(f"[TelegramDownload] Error downloading file_id {telegram_file_id}: {e}")
        return False

stored_salt_b64 = vfs.get_setting("salt")
if stored_salt_b64:
    SALT = base64.b64decode(stored_salt_b64)
else:
    SALT = CryptoEngine.generate_salt()
    vfs.set_setting("salt", base64.b64encode(SALT).decode('utf-8'))

class VaultGramHTTPHandler(BaseHTTPRequestHandler):
    """
    Pure Python HTTP & REST API Request Handler.
    Zero compiled C-dependencies (FastAPI/Pydantic-free for 100% compatibility).
    """

    def _set_headers(self, status=200, content_type="application/json"):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", content_type)
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(200)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        global MASTER_KEY

        if path == "/api/auth/status":
            has_passphrase = vfs.get_setting("passphrase_verifier") is not None
            unlocked = MASTER_KEY is not None
            bot_configured = vfs.get_setting("bot_token") is not None
            self._set_headers(200)
            res = {
                "configured": has_passphrase and bot_configured,
                "unlocked": unlocked,
                "bot_configured": bot_configured
            }
            self.wfile.write(json.dumps(res).encode('utf-8'))

        elif path == "/api/nodes":
            if MASTER_KEY is None:
                self._set_headers(401)
                self.wfile.write(json.dumps({"detail": "Locked"}).encode('utf-8'))
                return
            parent_id = query.get("parent_id", [None])[0]
            nodes = vfs.get_children(parent_id)
            self._set_headers(200)
            self.wfile.write(json.dumps({"nodes": nodes}).encode('utf-8'))

        elif path == "/api/media":
            if MASTER_KEY is None:
                self._set_headers(401)
                self.wfile.write(json.dumps({"detail": "Locked"}).encode('utf-8'))
                return
            media = vfs.get_all_media()
            self._set_headers(200)
            self.wfile.write(json.dumps({"media": media}).encode('utf-8'))

        elif path == "/api/settings":
            bot_token = vfs.get_setting("bot_token") or ""
            channel_id = vfs.get_setting("channel_id") or ""
            self._set_headers(200)
            self.wfile.write(json.dumps({"bot_token": bot_token, "channel_id": channel_id}).encode('utf-8'))

        elif path.startswith("/api/download/"):
            node_id = path.replace("/api/download/", "")
            node = vfs.get_node(node_id)
            if not node:
                self._set_headers(404)
                self.wfile.write(json.dumps({"detail": "Not found"}).encode('utf-8'))
                return

            enc_file_path = f"/root/vaultgram/storage/{node_id}.enc"
            if not os.path.exists(enc_file_path):
                # Fallback: Download from Telegram servers if file_id exists
                bot_token = vfs.get_setting("bot_token")
                telegram_file_id = node.get("telegram_file_id")
                if bot_token and telegram_file_id:
                    print(f"[Download] Fetching missing encrypted file {node_id} from Telegram cloud...")
                    downloaded_ok = download_from_telegram(bot_token, telegram_file_id, enc_file_path)
                    if not downloaded_ok:
                        self._set_headers(404)
                        self.wfile.write(json.dumps({"detail": "File missing on disk and Telegram cloud"}).encode('utf-8'))
                        return
                else:
                    self._set_headers(404)
                    self.wfile.write(json.dumps({"detail": "File content missing"}).encode('utf-8'))
                    return

            try:
                with open(enc_file_path, "rb") as f_enc:
                    enc_bytes = f_enc.read()
                
                decrypted_bytes = CryptoEngine.decrypt_bytes(enc_bytes, MASTER_KEY)
                self._set_headers(200, content_type=node["mime_type"] or "application/octet-stream")
                self.wfile.write(decrypted_bytes)
            except Exception as e:
                print(f"[Download] Connection or decryption note: {e}")

        else:
            # Serve Static Web UI Files
            static_file = path.lstrip("/") or "index.html"
            file_path = os.path.join("/root/vaultgram/static", static_file)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                content_type = "text/html"
                if file_path.endswith(".js"): content_type = "application/javascript"
                elif file_path.endswith(".css"): content_type = "text/css"
                
                self._set_headers(200, content_type=content_type)
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self._set_headers(404)
                self.wfile.write(b"404 Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get('Content-Length', 0))
        body_bytes = self.rfile.read(content_length)

        global MASTER_KEY

        if path == "/api/auth/setup":
            data = json.loads(body_bytes.decode('utf-8'))
            passphrase = data.get("passphrase")
            bot_token = data.get("bot_token")
            channel_id = data.get("channel_id")

            key = CryptoEngine.derive_key(passphrase, SALT)
            verifier = CryptoEngine.encrypt_metadata({"test": "ok"}, key)
            vfs.set_setting("passphrase_verifier", verifier)

            if bot_token:
                vfs.set_setting("bot_token", bot_token)
            if channel_id:
                vfs.set_setting("channel_id", channel_id)

            MASTER_KEY = key
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "success", "unlocked": True}).encode('utf-8'))

        elif path == "/api/auth/unlock":
            data = json.loads(body_bytes.decode('utf-8'))
            passphrase = data.get("passphrase")
            verifier = vfs.get_setting("passphrase_verifier")

            key = CryptoEngine.derive_key(passphrase, SALT)
            try:
                decrypted = CryptoEngine.decrypt_metadata(verifier, key)
                if decrypted.get("test") == "ok":
                    MASTER_KEY = key
                    self._set_headers(200)
                    self.wfile.write(json.dumps({"status": "success", "unlocked": True}).encode('utf-8'))
                    return
            except Exception:
                pass

            self._set_headers(401)
            self.wfile.write(json.dumps({"detail": "Incorrect Passphrase"}).encode('utf-8'))

        elif path == "/api/settings":
            data = json.loads(body_bytes.decode('utf-8'))
            bot_token = data.get("bot_token")
            channel_id = data.get("channel_id")
            if bot_token:
                vfs.set_setting("bot_token", bot_token)
            if channel_id:
                vfs.set_setting("channel_id", channel_id)
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))

        elif path == "/api/nodes/cleanup":
            bot_token = vfs.get_setting("bot_token")
            all_media = vfs.get_all_media()
            cleaned = 0
            
            for item in all_media:
                node_id = item["id"]
                enc_path = f"/root/vaultgram/storage/{node_id}.enc"
                telegram_file_id = item.get("telegram_file_id")

                is_valid = False
                if bot_token and telegram_file_id:
                    try:
                        import urllib.request
                        url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={telegram_file_id}"
                        req = urllib.request.Request(url)
                        with urllib.request.urlopen(req, timeout=2.5) as response:
                            res_data = json.loads(response.read().decode('utf-8'))
                            if res_data.get("ok"):
                                is_valid = True
                    except Exception:
                        is_valid = False
                elif os.path.exists(enc_path):
                    is_valid = True

                if not is_valid:
                    if os.path.exists(enc_path):
                        try:
                            os.remove(enc_path)
                        except Exception:
                            pass
                    vfs.delete_node(node_id)
                    cleaned += 1

            try:
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "success", "cleaned": cleaned}).encode('utf-8'))
            except Exception:
                pass

        elif path == "/api/nodes/wipe":
            with vfs._get_connection() as conn:
                conn.cursor().execute("DELETE FROM nodes")
                conn.commit()
            
            storage_dir = "/root/vaultgram/storage"
            if os.path.exists(storage_dir):
                for f in os.listdir(storage_dir):
                    try:
                        os.remove(os.path.join(storage_dir, f))
                    except Exception:
                        pass
            
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))

        elif path == "/api/nodes/delete":
            data = json.loads(body_bytes.decode('utf-8'))
            node_id = data.get("node_id")
            if node_id:
                enc_path = f"/root/vaultgram/storage/{node_id}.enc"
                if os.path.exists(enc_path):
                    try:
                        os.remove(enc_path)
                    except Exception:
                        pass
                vfs.delete_node(node_id)
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))

        elif path == "/api/folders/create":
            data = json.loads(body_bytes.decode('utf-8'))
            folder_id = f"folder_{uuid.uuid4().hex[:12]}"
            vfs.add_node(
                node_id=folder_id,
                name=data.get("name"),
                node_type="folder",
                parent_id=data.get("parent_id")
            )
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "success", "folder_id": folder_id}).encode('utf-8'))

        elif path == "/api/upload":
            if MASTER_KEY is None:
                self._set_headers(401)
                self.wfile.write(json.dumps({"detail": "Locked"}).encode('utf-8'))
                return

            content_type_header = self.headers.get('Content-Type', '')
            if 'boundary=' not in content_type_header:
                self._set_headers(400)
                self.wfile.write(json.dumps({"detail": "Invalid multipart data"}).encode('utf-8'))
                return

            boundary = content_type_header.split("boundary=")[-1].encode('utf-8')
            parts = body_bytes.split(b'--' + boundary)
            file_bytes = None
            filename = "uploaded_file"
            parent_id = None

            for part in parts:
                if b'filename="' in part:
                    header_part, content_part = part.split(b'\r\n\r\n', 1)
                    header_str = header_part.decode('utf-8', errors='ignore')
                    for line in header_str.split('\r\n'):
                        if 'filename="' in line:
                            filename = line.split('filename="')[1].split('"')[0]
                    file_bytes = content_part.rsplit(b'\r\n', 1)[0]
                elif b'name="parent_id"' in part:
                    header_part, content_part = part.split(b'\r\n\r\n', 1)
                    parent_id = content_part.rsplit(b'\r\n', 1)[0].decode('utf-8').strip()

            if not file_bytes:
                self._set_headers(400)
                self.wfile.write(json.dumps({"detail": "No file payload found"}).encode('utf-8'))
                return

            node_id = f"file_{uuid.uuid4().hex[:12]}"
            storage_dir = "/root/vaultgram/storage"
            os.makedirs(storage_dir, exist_ok=True)
            enc_storage_path = os.path.join(storage_dir, f"{node_id}.enc")

            with tempfile.TemporaryDirectory() as tmpdir:
                raw_path = os.path.join(tmpdir, "raw")

                with open(raw_path, "wb") as f_raw:
                    f_raw.write(file_bytes)

                # 1. Encrypt file locally using AES-256
                sha256_hash = CryptoEngine.encrypt_file(raw_path, enc_storage_path, MASTER_KEY)
                size_bytes = len(file_bytes)
                import mimetypes
                guessed_mime, _ = mimetypes.guess_type(filename)
                mime_type = guessed_mime or "application/octet-stream"

                # 1. Save node in local SQLite VFS immediately (instant upload!)
                vfs.add_node(
                    node_id=node_id,
                    name=filename,
                    node_type="file",
                    parent_id=parent_id,
                    telegram_msg_id=None,
                    telegram_file_id=None,
                    size_bytes=size_bytes,
                    mime_type=mime_type,
                    sha256=sha256_hash
                )

                # 2. Trigger Telegram Cloud Sync in background thread
                bot_token = vfs.get_setting("bot_token")
                channel_id = vfs.get_setting("channel_id")
                if bot_token and channel_id:
                    def background_telegram_sync(b_token, c_id, enc_path, n_id, f_name, f_size, s_hash, p_id, m_key):
                        try:
                            metadata = {
                                "node_id": n_id,
                                "name": f_name,
                                "size": f_size,
                                "sha256": s_hash,
                                "parent_id": p_id
                            }
                            caption = CryptoEngine.encrypt_metadata(metadata, m_key)
                            msg_id, file_id = upload_to_telegram_channel(b_token, c_id, enc_path, caption)
                            if msg_id and file_id:
                                with vfs._get_connection() as conn:
                                    conn.cursor().execute(
                                        "UPDATE nodes SET telegram_msg_id=?, telegram_file_id=? WHERE id=?",
                                        (msg_id, file_id, n_id)
                                    )
                                    conn.commit()
                                print(f"[CloudSync] Successfully synced {f_name} to Telegram Channel!")
                        except Exception as ex:
                            print(f"[BackgroundSyncError] {ex}")

                    import threading
                    threading.Thread(
                        target=background_telegram_sync,
                        args=(bot_token, channel_id, enc_storage_path, node_id, filename, size_bytes, sha256_hash, parent_id, MASTER_KEY),
                        daemon=True
                    ).start()

            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "success", "node_id": node_id, "name": filename}).encode('utf-8'))

class ReuseAddrHTTPServer(HTTPServer):
    allow_reuse_address = True

def run_server(port=8000):
    server_address = ('', port)
    httpd = ReuseAddrHTTPServer(server_address, VaultGramHTTPHandler)
    print(f"🚀 VaultGram TDLib Engine Server running on http://0.0.0.0:{port}")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()
