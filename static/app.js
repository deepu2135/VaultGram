let currentParentId = null;
let currentTab = 'photosTab';

document.addEventListener('DOMContentLoaded', () => {
    checkAuthStatus();
});

function getServerUrl() {
    return localStorage.getItem('vaultgram_server_url') || (window.location.protocol.startsWith('http') ? '' : 'http://127.0.0.1:8000');
}
const SERVER_URL = getServerUrl();

function setServerUrl(url) {
    if (url) {
        url = url.trim().replace(/\/+$/, '');
        localStorage.setItem('vaultgram_server_url', url);
    }
}

function toggleServerConfig() {
    const group = document.getElementById('serverUrlGroup');
    if (group.style.display === 'none' || !group.style.display) {
        group.style.display = 'block';
        document.getElementById('serverUrlInput').value = getServerUrl();
    } else {
        group.style.display = 'none';
    }
}

function toggleBotConfig() {
    const group = document.getElementById('botConfigGroup');
    if (group.style.display === 'none' || !group.style.display) {
        group.style.display = 'block';
    } else {
        group.style.display = 'none';
    }
}

async function checkAuthStatus() {
    const serverUrl = getServerUrl();
    try {
        const res = await fetch(`${serverUrl}/api/auth/status`);
        const data = await res.json();

        const authOverlay = document.getElementById('authOverlay');
        const botGroup = document.getElementById('botConfigGroup');
        const authSubtitle = document.getElementById('authSubtitle');
        const authBtn = document.getElementById('authBtn');

        if (data.unlocked) {
            authOverlay.style.display = 'none';
            loadCurrentTabData();
            return;
        }

        authOverlay.style.display = 'flex';
        if (!data.configured || !data.bot_configured) {
            botGroup.style.display = 'block';
            authSubtitle.textContent = 'Setup: Enter Telegram Bot Credentials & Master Passphrase';
            if (authBtn) authBtn.innerHTML = '<i class="fa-solid fa-key"></i> Save & Unlock Gallery';
        } else {
            botGroup.style.display = 'none';
            authSubtitle.textContent = 'Vault is locked. Enter Master Passphrase';
            if (authBtn) authBtn.innerHTML = '<i class="fa-solid fa-lock-open"></i> Unlock Gallery';
        }
    } catch (err) {
        console.error('Error checking auth status:', err);
    }
}

async function handleAuthSubmit(e) {
    e.preventDefault();
    const passphrase = document.getElementById('passphraseInput').value;
    const botToken = document.getElementById('botTokenInput').value;
    const channelId = document.getElementById('channelIdInput')?.value;
    const customUrlInput = document.getElementById('serverUrlInput');
    const statusMsg = document.getElementById('authStatusMsg');

    if (customUrlInput && customUrlInput.value) {
        setServerUrl(customUrlInput.value);
    }

    const serverUrl = getServerUrl();
    statusMsg.style.color = 'var(--primary)';
    statusMsg.textContent = 'Connecting to VaultGram...';

    const isSetup = document.getElementById('botConfigGroup').style.display !== 'none';
    const endpoint = isSetup ? `${serverUrl}/api/auth/setup` : `${serverUrl}/api/auth/unlock`;
    const payload = isSetup ? { passphrase, bot_token: botToken, channel_id: channelId } : { passphrase };

    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (res.ok && data.unlocked) {
            document.getElementById('authOverlay').style.display = 'none';
            loadCurrentTabData();
        } else {
            statusMsg.textContent = data.detail || 'Authentication failed';
            statusMsg.style.color = 'var(--danger)';
        }
    } catch (err) {
        statusMsg.style.color = 'var(--danger)';
        statusMsg.innerHTML = '❌ <strong>Connection Error</strong>.<br><small>Could not connect to VaultGram server at ' + (serverUrl || 'http://127.0.0.1:8000') + '. Make sure server.py is running!</small>';
    }
}

function switchTab(tabId) {
    currentTab = tabId;
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.mobile-nav-item').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.content-tab').forEach(el => el.classList.remove('active'));

    document.getElementById(tabId).classList.add('active');

    const mobileNavItems = document.querySelectorAll('.mobile-nav-item');
    if (tabId === 'photosTab') {
        document.querySelectorAll('.nav-item')[0]?.classList.add('active');
        if (mobileNavItems[0]) mobileNavItems[0].classList.add('active');
    } else {
        document.querySelectorAll('.nav-item')[1]?.classList.add('active');
        if (mobileNavItems[1]) mobileNavItems[1].classList.add('active');
    }

    loadCurrentTabData();
}

function loadCurrentTabData() {
    if (currentTab === 'photosTab') {
        loadMediaVault();
    } else {
        loadDriveNodes(currentParentId);
    }
}

let activeFilter = 'all';
let allMediaItems = [];

function filterMedia(type) {
    activeFilter = type;
    document.querySelectorAll('.chip-item').forEach(el => el.classList.remove('active'));
    if (event && event.target) {
        event.target.classList.add('active');
    }
    renderMediaGrid();
}

async function syncTelegramChannel() {
    const toast = document.getElementById('uploadToast');
    const nameEl = document.getElementById('toastFileName');
    const subEl = document.getElementById('toastSubtext');
    if (nameEl) nameEl.textContent = 'Syncing Telegram Channel...';
    if (subEl) subEl.textContent = 'Scanning channel for videos & encrypted files...';
    if (toast) toast.style.display = 'flex';

    try {
        const res = await fetch(`${SERVER_URL}/api/sync`);
        const data = await res.json();
        if (res.ok) {
            alert(`Sync Complete! Imported ${data.synced || 0} new media files from your Telegram Channel.`);
            loadCurrentTabData();
        } else {
            alert('Failed to sync channel. Make sure Bot Token & Channel ID are configured.');
        }
    } catch (err) {
        console.error('Error syncing channel:', err);
        alert('Error connecting to Telegram server.');
    }
    if (toast) toast.style.display = 'none';
}

async function loadMediaVault() {
    try {
        const res = await fetch(`${SERVER_URL}/api/media`);
        const data = await res.json();
        allMediaItems = data.media || [];
        renderMediaGrid();
    } catch (err) {
        console.error('Failed to load media vault:', err);
    }
}

function renderMediaGrid() {
    const grid = document.getElementById('mediaGrid');
    const emptyState = document.getElementById('emptyState');
    grid.innerHTML = '';

    let filtered = allMediaItems;
    if (activeFilter === 'photos') {
        filtered = allMediaItems.filter(i => i.mime_type && i.mime_type.startsWith('image'));
    } else if (activeFilter === 'videos') {
        filtered = allMediaItems.filter(i => i.mime_type && i.mime_type.startsWith('video'));
    } else if (activeFilter === 'audio') {
        filtered = allMediaItems.filter(i => i.mime_type && (i.mime_type.startsWith('audio') || i.name.endsWith('.mp3') || i.name.endsWith('.m4a') || i.name.endsWith('.wav') || i.name.endsWith('.ogg')));
    } else if (activeFilter === 'documents') {
        filtered = allMediaItems.filter(i => !i.mime_type || (!i.mime_type.startsWith('image') && !i.mime_type.startsWith('video') && !i.mime_type.startsWith('audio')));
    }

    document.getElementById('mediaCountBadge').textContent = `${filtered.length} Items`;

    if (filtered.length === 0) {
        emptyState.style.display = 'flex';
        grid.style.display = 'none';
        return;
    }

    emptyState.style.display = 'none';
    grid.style.display = 'grid';

    filtered.forEach(item => {
        const card = document.createElement('div');
        card.className = 'media-card';

        const isImage = item.mime_type && item.mime_type.startsWith('image');
        const isVideo = item.mime_type && item.mime_type.startsWith('video');
        const isAudio = item.mime_type && (item.mime_type.startsWith('audio') || item.name.endsWith('.mp3') || item.name.endsWith('.m4a') || item.name.endsWith('.wav') || item.name.endsWith('.ogg'));

        if (isImage) {
            card.innerHTML = `
                <img src="${SERVER_URL}/api/download/${item.id}" alt="${escapeHtml(item.name)}" loading="lazy" style="width:100%; height:100%; object-fit:cover; border-radius:12px;" />
                <button class="delete-btn" onclick="deleteFileNode(event, '${item.id}')" title="Delete file"><i class="fa-solid fa-trash"></i></button>
                <div class="media-name">${escapeHtml(item.name)}</div>
            `;
        } else if (isVideo) {
            card.innerHTML = `
                <video src="${SERVER_URL}/api/download/${item.id}" controls preload="metadata" style="width:100%; height:100%; object-fit:cover; border-radius:12px;"></video>
                <button class="delete-btn" onclick="deleteFileNode(event, '${item.id}')" title="Delete file"><i class="fa-solid fa-trash"></i></button>
                <div class="media-name">${escapeHtml(item.name)}</div>
            `;
        } else if (isAudio) {
            card.innerHTML = `
                <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; padding:14px; background: #271D1B; border-radius: 12px; border: 1px solid var(--border-color);">
                    <div style="width: 56px; height: 56px; border-radius: 50%; background: rgba(255, 180, 171, 0.15); display: flex; align-items: center; justify-content: center; margin-bottom: 8px;">
                        <i class="fa-solid fa-music" style="font-size: 24px; color: var(--primary);"></i>
                    </div>
                    <div class="media-name" style="position:static; margin-bottom: 6px; text-align:center; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(item.name)}</div>
                    <audio src="${SERVER_URL}/api/download/${item.id}" controls style="width: 100%; height: 36px;"></audio>
                </div>
                <button class="delete-btn" onclick="deleteFileNode(event, '${item.id}')" title="Delete file"><i class="fa-solid fa-trash"></i></button>
            `;
        } else {
            card.onclick = () => downloadFile(item.id, item.name);
            card.innerHTML = `
                <div class="media-placeholder" style="border-radius:12px;">
                    <i class="fa-solid fa-file-shield"></i>
                </div>
                <button class="delete-btn" onclick="deleteFileNode(event, '${item.id}')" title="Delete file"><i class="fa-solid fa-trash"></i></button>
                <div class="media-name">${escapeHtml(item.name)}</div>
            `;
        }
        grid.appendChild(card);
    });
}

async function loadDriveNodes(parentId = null) {
    try {
        let url = `${SERVER_URL}/api/nodes`;
        if (parentId) url += `?parent_id=${parentId}`;

        const res = await fetch(url);
        const data = await res.json();
        const grid = document.getElementById('driveGrid');
        grid.innerHTML = '';

        (data.nodes || []).forEach(item => {
            const el = document.createElement('div');
            el.className = 'drive-item';

            if (item.type === 'directory' || item.type === 'folder') {
                el.onclick = () => navigateToFolder(item.id, item.name);
                el.innerHTML = `
                    <i class="fa-solid fa-folder drive-icon folder"></i>
                    <div class="drive-info">
                        <div class="name">${escapeHtml(item.name)}</div>
                        <div class="meta">Folder</div>
                    </div>
                `;
            } else {
                el.onclick = () => downloadFile(item.id, item.name);
                el.innerHTML = `
                    <i class="fa-solid fa-file-shield drive-icon"></i>
                    <div class="drive-info">
                        <div class="name">${escapeHtml(item.name)}</div>
                        <div class="meta">${formatBytes(item.size_bytes)}</div>
                    </div>
                `;
            }
            grid.appendChild(el);
        });
    } catch (err) {
        console.error('Failed to load drive nodes:', err);
    }
}

async function handleFileUpload(event) {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    const toast = document.getElementById('uploadToast');
    const toastFileName = document.getElementById('toastFileName');
    const toastSubtext = document.getElementById('toastSubtext');

    toast.style.display = 'block';

    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        toastFileName.textContent = `Uploading ${file.name}`;
        toastSubtext.textContent = `Encrypting file locally (AES-256-GCM)...`;

        const formData = new FormData();
        formData.append('file', file);
        formData.append('filename', file.name);
        if (currentParentId) {
            formData.append('parent_id', currentParentId);
        }

        try {
            toastSubtext.textContent = `Uploading encrypted binary to Telegram...`;
            const res = await fetch(`${SERVER_URL}/api/upload`, {
                method: 'POST',
                body: formData
            });

            if (!res.ok) {
                const errData = await res.json();
                alert(`Upload failed: ${errData.detail}`);
            }
        } catch (err) {
            alert(`Error uploading file: ${err.message}`);
        }
    }

    toast.style.display = 'none';
    loadCurrentTabData();
}

async function openCreateFolderModal() {
    const folderName = prompt('Enter folder name:');
    if (!folderName) return;

    try {
        const res = await fetch(`${SERVER_URL}/api/folders/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: folderName,
                parent_id: currentParentId
            })
        });
        if (res.ok) {
            loadCurrentTabData();
        }
    } catch (err) {
        alert('Failed to create folder');
    }
}

function downloadFile(nodeId, filename) {
    const link = document.createElement('a');
    link.href = `${SERVER_URL}/api/download/${nodeId}`;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function navigateToFolder(folderId, folderName) {
    currentParentId = folderId;
    loadDriveNodes(folderId);
}

async function lockVault() {
    try {
        await fetch(`${SERVER_URL}/api/auth/lock`, { method: 'POST' });
    } catch (e) {}
    location.reload();
}

function formatBytes(bytes, decimals = 2) {
    if (!bytes || bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

function escapeHtml(str) {
    return str.replace(/[&<>"']/g, function(m) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m];
    });
}

async function openSettingsModal() {
    try {
        const res = await fetch(`${SERVER_URL}/api/settings`);
        if (res.ok) {
            const data = await res.json();
            document.getElementById('settingsBotToken').value = data.bot_token || '';
            document.getElementById('settingsChannelId').value = data.channel_id || '';
        }
    } catch (err) {
        console.error('Error loading settings:', err);
    }
    document.getElementById('settingsOverlay').style.display = 'flex';
}

function closeSettingsModal() {
    document.getElementById('settingsOverlay').style.display = 'none';
}

async function handleSettingsSave(e) {
    e.preventDefault();
    const bot_token = document.getElementById('settingsBotToken').value;
    const channel_id = document.getElementById('settingsChannelId').value;
    const statusMsg = document.getElementById('settingsStatusMsg');

    statusMsg.textContent = 'Saving...';
    try {
        const res = await fetch(`${SERVER_URL}/api/settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bot_token, channel_id })
        });
        if (res.ok) {
            statusMsg.textContent = 'Settings saved successfully! Future uploads will post to your channel.';
            statusMsg.style.color = '#22c55e';
            setTimeout(() => {
                closeSettingsModal();
            }, 1200);
        } else {
            statusMsg.textContent = 'Failed to save settings';
            statusMsg.style.color = '#ef4444';
        }
    } catch (err) {
        statusMsg.textContent = 'Connection error';
        statusMsg.style.color = '#ef4444';
    }
}

async function wipeVaultData() {
    if (!confirm("Are you sure you want to WIPE all local files and reset your Vault database? This cannot be undone.")) return;
    try {
        const res = await fetch(`${SERVER_URL}/api/nodes/wipe`, { method: 'POST' });
        if (res.ok) {
            alert('Vault database and local file cache successfully wiped clean!');
            loadCurrentTabData();
        }
    } catch (err) {
        alert('Failed to wipe vault data');
    }
}

async function cleanupPhantomFiles() {
    try {
        const res = await fetch(`${SERVER_URL}/api/nodes/cleanup`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            alert(`Cleaned up ${data.cleaned} broken test entries!`);
            loadCurrentTabData();
        }
    } catch (err) {
        alert('Failed to clean up phantom files');
    }
}

async function deleteFileNode(event, nodeId) {
    event.stopPropagation();
    if (!confirm('Are you sure you want to delete this file?')) return;
    try {
        const res = await fetch(`${SERVER_URL}/api/nodes/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ node_id: nodeId })
        });
        if (res.ok) {
            loadCurrentTabData();
        }
    } catch (err) {
        alert('Failed to delete file');
    }
}
