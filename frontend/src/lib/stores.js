/**
 * UI state shared between components that aren't parent and child: the category filter,
 * the ☰ menu, which source card is selected, and the rate-limit countdown and its reason.
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

/**
 * Why the countdown runs, as the error code that started it: "rate_limited" (every LLM
 * provider is busy, so everyone waits) or "too_many_requests" (this device or network
 * reached Lumen's question limit).
 */
export const busyReason = writable('rate_limited');

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

const pad = (/** @type {number} */ n) => String(n).padStart(2, '0');

/** "0:24", "1:05", and "1:02:05" once the wait is an hour or more (the daily limit). */
export function formatCountdown(/** @type {number} */ seconds) {
	const s = Math.max(0, Math.ceil(seconds));
	const hours = Math.floor(s / 3600);
	const minutes = Math.floor((s % 3600) / 60);
	if (hours) return `${hours}:${pad(minutes)}:${pad(s % 60)}`;
	return `${minutes}:${pad(s % 60)}`;
}

const plural = (/** @type {number} */ n, /** @type {string} */ unit) =>
	`${n} ${unit}${n === 1 ? '' : 's'}`;

/**
 * The wait in words, for screen readers: "24 seconds", "2 minutes", "3 hours 5 minutes".
 * Minutes round up, so it never says a wait is over before it is.
 */
export function spokenWait(/** @type {number} */ seconds) {
	const s = Math.max(0, Math.ceil(seconds));
	if (s < 60) return plural(s, 'second');
	const totalMinutes = Math.ceil(s / 60);
	const hours = Math.floor(totalMinutes / 60);
	const minutes = totalMinutes % 60;
	if (!hours) return plural(minutes, 'minute');
	return minutes ? `${plural(hours, 'hour')} ${plural(minutes, 'minute')}` : plural(hours, 'hour');
}
