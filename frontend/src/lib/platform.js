/**
 * Every browser or device capability the app uses lives behind this module (CLAUDE.md rule 9).
 *
 * Components and the other lib modules import from here, never from Capacitor or straight
 * from `localStorage`, `navigator.share` and friends. This file has the web implementations
 * only. Phase 7 adds the native ones (Capacitor Preferences, Share, Browser, Network,
 * Haptics) behind the same functions, so no component has to change.
 *
 * Storage is async on purpose: Capacitor Preferences is async, so callers already `await`.
 */

/** "web" or "android". Sent as X-Client (src/lib/session.js). */
export const clientName = 'web';

/** This build's version, from package.json (Vite's `define` in vite.config.js). Sent as X-App-Version. */
export const appVersion = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : '0.0.0';

/** True inside the Android app. */
export const isNative = false;

/**
 * App-only features (DESIGN.md §4 FeedbackButtons, §7). The web shows Copy instead of
 * Save + Share; saved answers and the offline banner come with the Android app.
 */
export const features = Object.freeze({
	saveAnswers: false,
	share: false
});

/** Key-value storage that survives reloads: localStorage on the web. */
export const storage = {
	/** @param {string} key @returns {Promise<string | null>} */
	async get(key) {
		try {
			return globalThis.localStorage?.getItem(key) ?? null;
		} catch {
			// Storage can be blocked (private mode, disabled cookies): behave as empty.
			return null;
		}
	},

	/** @param {string} key @param {string} value */
	async set(key, value) {
		try {
			globalThis.localStorage?.setItem(key, value);
		} catch {
			// Quota exceeded or storage blocked: the value lives for this page load only.
		}
	},

	/** @param {string} key */
	async remove(key) {
		try {
			globalThis.localStorage?.removeItem(key);
		} catch {
			// Nothing stored, nothing to remove.
		}
	}
};

/**
 * Copy text to the clipboard. Resolves to false when the browser refuses.
 * @param {string} text
 */
export async function copyText(text) {
	try {
		await globalThis.navigator.clipboard.writeText(text);
		return true;
	} catch {
		return false;
	}
}

/**
 * Share text with the system share sheet. Resolves to false when sharing isn't
 * available or the user cancels.
 * @param {{ title?: string, text: string, url?: string }} data
 */
export async function share(data) {
	const navigator = globalThis.navigator;
	if (typeof navigator?.share !== 'function') return false;
	try {
		await navigator.share(data);
		return true;
	} catch {
		return false;
	}
}

/**
 * Open an external URL (a source document) outside the app.
 * @param {string} url
 */
export async function openUrl(url) {
	globalThis.open?.(url, '_blank', 'noopener,noreferrer');
}

/**
 * Click handler for links to external documents. On the web the link opens itself
 * (`target="_blank"`), so this does nothing; in the app it will cancel the click and
 * open the page in a Custom Tab with `openUrl`.
 * @param {MouseEvent} _event
 */
export function handleExternalLink(_event) {}

/** Network status: the browser's online/offline events. */
export const network = {
	/** @returns {Promise<boolean>} */
	async isOnline() {
		return globalThis.navigator?.onLine ?? true;
	},

	/**
	 * Call `callback(online)` whenever the connection changes. Returns an unsubscribe function.
	 * @param {(online: boolean) => void} callback
	 */
	onChange(callback) {
		const online = () => callback(true);
		const offline = () => callback(false);
		globalThis.addEventListener('online', online);
		globalThis.addEventListener('offline', offline);
		return () => {
			globalThis.removeEventListener('online', online);
			globalThis.removeEventListener('offline', offline);
		};
	}
};

/** Haptic feedback (DESIGN.md §7: light tap on send, thumbs and save). None on the web. */
export const haptics = {
	async tap() {}
};
