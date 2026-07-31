<div align="center">
  <h1>🛡️ VaultGram</h1>
  <h3>Zero-Knowledge Encrypted Telegram Cloud & Photo Vault</h3>
  <p><strong>Transform Telegram into your private, unlimited AES-256 encrypted Google Photos replacement!</strong></p>
  <p>🔒 <em>100% Zero-Knowledge • Client-Side AES-256-GCM • Mobile & Web Interface • Unlimited Storage</em></p>
</div>

---

## 🌟 Key Features

- 🔒 **Zero-Knowledge Encryption:** All media and files are encrypted locally on your device with **AES-256-GCM** before being uploaded. Telegram servers only store scrambled binary blobs.
- 🚀 **Bypasses 50 MB Download Limits:** Unlike standard Bot API clients, VaultGram maintains an encrypted local storage cache and streams decrypted bytes directly to your browser without 50 MB HTTP limits.
- ⚡ **Instant Background Uploads:** Files encrypt instantly on your device, giving immediate UI confirmation while Telegram cloud backup syncs asynchronously in a background thread.
- 🎨 **Material 3 CloudGallery UI:** Styled with warm dark terracotta aesthetics (`#1A110F`), floating action buttons (FAB), album filter chips (`Photos`, `Videos`, `Audio`, `Documents`), and built-in HTML5 audio/video playback.
- 📱 **Mobile & Desktop Compatible:** Includes a responsive mobile bottom navigation bar and mobile viewports.
- 📂 **Virtual File System (VFS):** Full folder tree hierarchies, nested directories, and custom tag indexing.

---

## 🛠️ Quick Start & Installation

### 1. Requirements
- Python 3.10+
- `cryptography` (or standard `hashlib` fallback)

### 2. Run Locally
```bash
git clone https://github.com/deepu2135/VaultGram.git
cd VaultGram
python3 server.py
```

Open **`http://localhost:8000`** in your web browser!

---

## ⚙️ Configuration

1. Launch **`http://localhost:8000`**.
2. Click **⚙️ Settings** in the app menu.
3. Enter your **Telegram Bot Token** (from `@BotFather`) and **Telegram Channel Username / ID** (e.g. `@my_private_channel`).
4. Ensure your Bot is added as an **Admin** in your private Telegram Channel.

---

## 🔒 Security Architecture

```
[ Your Device ]
  │  📁 Raw Media File
  │  🔒 AES-256-GCM Encryption (Client-side)
  ├─────────────────────────────────────────┐
  ▼                                         ▼
[ Local Encrypted Cache ]          [ Telegram Cloud ]
/storage/{id}.enc                  Scrambled .bin Document
```

* Master Passphrase derives a 256-bit AES key via PBKDF2-HMAC-SHA256 with 100,000 iterations.
* Encrypted file payload + encrypted metadata captions ensure Telegram servers cannot read your photo contents, filenames, or folder structures.

---

## 📄 License

Open-source under the MIT License.
