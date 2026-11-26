/**
 * UI state shared between components that aren't parent and child: the category filter,
 * the ☰ menu, which source card is selected, and the rate-limit countdown.
 * The conversation itself lives in src/lib/chat.js.
 */

import { derived, writable } from 'svelte/store';

/** Category the answers come from: "academics", "exams", ... or null for All. */
export const category = writable(/** @type {string | null} */ (null));

/** Whether the mobile ☰ category menu is open. */
export const menuOpen = writable(false);

/**
 * The source the user picked by tapping a citation chip or a source row:
 * `{ messageKey, n }`, or null. Its card gets the accent border.
 */
export const selectedSource = writable(
	/** @type {{ messageKey: string, n: number } | null} */ (null)
);

/** Whether the sources sheet (below 1024 px) is open. */
export const sheetOpen = writable(false);

/** Time (ms since the epoch) until which Lumen is rate-limited; 0 when it isn't. */
export const busyUntil = writable(0);

/** Whole seconds left on the busy countdown, updated every second; 0 when not busy. */
export const busySeconds = derived(
	busyUntil,
	($busyUntil, set) => {
		const tick = () => {
			const left = Math.max(0, Math.ceil(($busyUntil - Date.now()) / 1000));
			set(left);
			return left;
		};
		if (tick() === 0) return undefined;
		const timer = setInterval(() => {
			if (tick() === 0) clearInterval(timer);
		}, 1000);
		return () => clearInterval(timer);
	},
	0
);

/** "0:24", "1:05" */
export function formatCountdown(/** @type {number} */ seconds) {
	const s = Math.max(0, Math.ceil(seconds));
	return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}
