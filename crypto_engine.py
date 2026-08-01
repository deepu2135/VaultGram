import os
import sys
import base64
import json
import hashlib
from typing import Dict, Any

# Ensure termux/custom site-packages are in sys.path
for path in ['/data/data/com.termux/files/usr/lib/python3.14/site-packages', '/root/.local/lib/python3.14/site-packages']:
    if os.path.exists(path) and path not in sys.path:
        sys.path.append(path)

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    USE_CRYPTOGRAPHY_LIB = True
except ImportError:
    import pyaes
    USE_CRYPTOGRAPHY_LIB = False

class CryptoEngine:
    """
    Zero-Knowledge Client-Side AES-256 Encryption Engine.
    Uses cryptography package (AES-GCM) or fallback pyaes (AES-CTR) + hashlib.
    """
    KEY_SIZE = 32  # 256 bits
    SALT_SIZE = 16 # 128 bits
    IV_SIZE = 12   # 96 bits for GCM / CTR counter

    @staticmethod
    def derive_key(passphrase: str, salt: bytes) -> bytes:
        """Derive a 256-bit AES key from user passphrase using PBKDF2-HMAC-SHA256."""
        if USE_CRYPTOGRAPHY_LIB:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=CryptoEngine.KEY_SIZE,
                salt=salt,
                iterations=600_000,
            )
            return kdf.derive(passphrase.encode('utf-8'))
        else:
            return hashlib.pbkdf2_hmac('sha256', passphrase.encode('utf-8'), salt, 600_000, dklen=32)

    @staticmethod
    def generate_salt() -> bytes:
        return os.urandom(CryptoEngine.SALT_SIZE)

    @staticmethod
    def encrypt_metadata(metadata: Dict[str, Any], key: bytes) -> str:
        """Encrypt JSON metadata dictionary to a secure Base64 string."""
        iv = os.urandom(CryptoEngine.IV_SIZE)
        plaintext = json.dumps(metadata).encode('utf-8')

        if USE_CRYPTOGRAPHY_LIB:
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(iv, plaintext, None)
        else:
            counter = pyaes.Counter(initial_value=int.from_bytes(iv, 'big'))
            aes = pyaes.AESModeOfOperationCTR(key, counter=counter)
            ciphertext = aes.encrypt(plaintext)

        payload = {
            "v": 1,
            "iv": base64.b64encode(iv).decode('utf-8'),
            "data": base64.b64encode(ciphertext).decode('utf-8')
        }
        return json.dumps(payload)

    @staticmethod
    def decrypt_metadata(encrypted_caption: str, key: bytes) -> Dict[str, Any]:
        """Decrypt Base64 encrypted caption back to JSON metadata dictionary."""
        payload = json.loads(encrypted_caption)
        iv = base64.b64decode(payload["iv"])
        ciphertext = base64.b64decode(payload["data"])

        if USE_CRYPTOGRAPHY_LIB:
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(iv, ciphertext, None)
        else:
            counter = pyaes.Counter(initial_value=int.from_bytes(iv, 'big'))
            aes = pyaes.AESModeOfOperationCTR(key, counter=counter)
            plaintext = aes.decrypt(ciphertext)

        return json.loads(plaintext.decode('utf-8'))

    @staticmethod
    def encrypt_file(input_path: str, output_path: str, key: bytes) -> str:
        """Encrypt a file using AES-256. Prepend IV. Returns SHA-256 hash."""
        iv = os.urandom(CryptoEngine.IV_SIZE)
        hasher = hashlib.sha256()

        with open(input_path, 'rb') as fin:
            plaintext = fin.read()
            hasher.update(plaintext)

        if USE_CRYPTOGRAPHY_LIB:
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(iv, plaintext, None)
        else:
            counter = pyaes.Counter(initial_value=int.from_bytes(iv, 'big'))
            aes = pyaes.AESModeOfOperationCTR(key, counter=counter)
            ciphertext = aes.encrypt(plaintext)

        with open(output_path, 'wb') as fout:
            fout.write(iv)
            fout.write(ciphertext)

        return hasher.hexdigest()

    @staticmethod
    def decrypt_file(input_path: str, output_path: str, key: bytes) -> None:
        """Decrypt an AES-256 encrypted file."""
        with open(input_path, 'rb') as fin:
            iv = fin.read(CryptoEngine.IV_SIZE)
            ciphertext = fin.read()

        if USE_CRYPTOGRAPHY_LIB:
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(iv, ciphertext, None)
        else:
            counter = pyaes.Counter(initial_value=int.from_bytes(iv, 'big'))
            aes = pyaes.AESModeOfOperationCTR(key, counter=counter)
            plaintext = aes.decrypt(ciphertext)

        with open(output_path, 'wb') as fout:
            fout.write(plaintext)

    @staticmethod
    def decrypt_bytes(encrypted_bytes: bytes, key: bytes) -> bytes:
        """Decrypt in-memory AES-256 encrypted bytes."""
        iv = encrypted_bytes[:CryptoEngine.IV_SIZE]
        ciphertext = encrypted_bytes[CryptoEngine.IV_SIZE:]

        if USE_CRYPTOGRAPHY_LIB:
            aesgcm = AESGCM(key)
            return aesgcm.decrypt(iv, ciphertext, None)
        else:
            counter = pyaes.Counter(initial_value=int.from_bytes(iv, 'big'))
            aes = pyaes.AESModeOfOperationCTR(key, counter=counter)
            return aes.decrypt(ciphertext)
