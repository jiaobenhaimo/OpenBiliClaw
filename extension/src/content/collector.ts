/**
 * OpenBiliClaw — Bilibili Behavior Collector (Content Script)
 *
 * Injected into Bilibili pages to capture user interactions:
 * - Clicks, scrolls, hover
 * - Video play/pause/seek
 * - Search queries
 * - Comments, likes, coins
 * - DOM page snapshots for context
 */

interface BehaviorEvent {
    type: string;
    url: string;
    title: string;
    timestamp: number;
    context: {
        pageType: string;       // "video" | "search" | "home" | "category" | "user"
        domSnapshot?: string;   // Simplified DOM snapshot
        viewport: { width: number; height: number };
        scrollPosition: number;
    };
    metadata: Record<string, unknown>;
}

/**
 * Detect the current Bilibili page type from the URL.
 */
function detectPageType(): string {
    const url = window.location.href;
    if (url.includes('/video/')) return 'video';
    if (url.includes('/search')) return 'search';
    if (url.includes('/space.bilibili.com') || url.includes('/space/')) return 'user';
    if (url.includes('/v/')) return 'category';
    return 'home';
}

/**
 * Create a simplified DOM snapshot (not the full DOM, just key elements).
 */
function createDOMSnapshot(): string {
    const snapshot: Record<string, string | null> = {
        title: document.title,
        h1: document.querySelector('h1')?.textContent?.trim() ?? null,
        description: document.querySelector('meta[name="description"]')?.getAttribute('content') ?? null,
    };
    return JSON.stringify(snapshot);
}

/**
 * Create a behavior event with current page context.
 */
function createEvent(type: string, metadata: Record<string, unknown> = {}): BehaviorEvent {
    return {
        type,
        url: window.location.href,
        title: document.title,
        timestamp: Date.now(),
        context: {
            pageType: detectPageType(),
            domSnapshot: createDOMSnapshot(),
            viewport: { width: window.innerWidth, height: window.innerHeight },
            scrollPosition: window.scrollY,
        },
        metadata,
    };
}

/**
 * Send event to the background service worker.
 */
function sendEvent(event: BehaviorEvent): void {
    chrome.runtime.sendMessage({ action: 'BEHAVIOR_EVENT', data: event });
}

// --- Event Listeners ---

// Click tracking
document.addEventListener('click', (e) => {
    const target = e.target as HTMLElement;
    const link = target.closest('a');
    const event = createEvent('click', {
        tagName: target.tagName,
        text: target.textContent?.trim().substring(0, 100),
        href: link?.href ?? null,
        classList: Array.from(target.classList),
    });
    sendEvent(event);
});

// Search tracking
const searchInput = document.querySelector('.nav-search-input') as HTMLInputElement | null;
if (searchInput) {
    searchInput.addEventListener('keydown', (e) => {
        if ((e as KeyboardEvent).key === 'Enter' && searchInput.value) {
            sendEvent(createEvent('search', { query: searchInput.value }));
        }
    });
}

console.log('[OpenBiliClaw] Behavior collector initialized on', detectPageType(), 'page');
