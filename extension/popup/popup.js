/**
 * OpenBiliClaw — Extension Popup Script
 */

const BACKEND_URL = 'http://localhost:8420/api';

async function checkBackendStatus(): Promise<boolean> {
    try {
        const response = await fetch(`${BACKEND_URL}/health`, { method: 'GET' });
        return response.ok;
    } catch {
        return false;
    }
}

async function updateStatus(): Promise<void> {
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    if (!dot || !text) return;

    const online = await checkBackendStatus();
    if (online) {
        dot.classList.remove('offline');
        text.textContent = '已连接到后端';
    } else {
        dot.classList.add('offline');
        text.textContent = '后端未连接';
    }
}

// Check status on popup open
updateStatus();
