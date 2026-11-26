import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { busySeconds, busyUntil, formatCountdown } from './stores.js';

describe('formatCountdown', () => {
	it('formats minutes and zero-padded seconds', () => {
		expect(formatCountdown(24)).toBe('0:24');
		expect(formatCountdown(65)).toBe('1:05');
		expect(formatCountdown(0)).toBe('0:00');
		expect(formatCountdown(-3)).toBe('0:00');
		expect(formatCountdown(4.2)).toBe('0:05');
	});
});

describe('busySeconds', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2026-11-26T10:00:00Z'));
	});

	afterEach(() => {
		busyUntil.set(0);
		vi.useRealTimers();
	});

	it('is 0 when not busy', () => {
		expect(get(busySeconds)).toBe(0);
	});

	it('counts down every second and stops at 0', () => {
		const seen = [];
		const unsubscribe = busySeconds.subscribe((value) => seen.push(value));
		busyUntil.set(Date.now() + 3000);
		vi.advanceTimersByTime(3000);
		expect(seen).toEqual([0, 3, 2, 1, 0]);
		vi.advanceTimersByTime(5000);
		expect(seen.at(-1)).toBe(0);
		expect(vi.getTimerCount()).toBe(0);
		unsubscribe();
	});

	it('stops the timer when nobody listens', () => {
		busyUntil.set(Date.now() + 10_000);
		const unsubscribe = busySeconds.subscribe(() => {});
		expect(vi.getTimerCount()).toBe(1);
		unsubscribe();
		expect(vi.getTimerCount()).toBe(0);
	});
});
