/**
 * OpenBiliClaw — Background Service Worker
 *
 * Receives behavior events from content scripts,
 * buffers them, and forwards to the backend API.
 */

interface BehaviorEvent {
    type: string;
    url: string;
    title: string;
    timestamp: number;
    context: Record<string, unknown>;
    metadata: Record<string, unknown>;
}

// Event buffer for batch sending
let eventBuffer: BehaviorEvent[] = [];
const BUFFER_FLUSH_INTERVAL = 30_000; // 30 seconds
const BUFFER_MAX_SIZE = 50;

// Backend API endpoint (configurable)
const BACKEND_URL = 'http://localhost:8420/api/events';

/**
 * Flush buffered events to the backend.
 */
async function flushEvents(): Promise<void> {
    if (eventBuffer.length === 0) return;

    const events = [...eventBuffer];
    eventBuffer = [];

    try {
        const response = await fetch(BACKEND_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ events }),
        });

        if (!response.ok) {
            console.warn('[OpenBiliClaw] Backend returned', response.status);
            // Re-add events on failure
            eventBuffer.push(...events);
        }
    } catch {
        console.warn('[OpenBiliClaw] Backend not available, buffering events');
        eventBuffer.push(...events);
    }
}

// Listen for events from content scripts
chrome.runtime.onMessage.addListener((message, _sender, _sendResponse) => {
    if (message.action === 'BEHAVIOR_EVENT') {
        eventBuffer.push(message.data);

        if (eventBuffer.length >= BUFFER_MAX_SIZE) {
            flushEvents();
        }
    }
});

// Periodic flush
setInterval(flushEvents, BUFFER_FLUSH_INTERVAL);

console.log('[OpenBiliClaw] Service worker initialized');
