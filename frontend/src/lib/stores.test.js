import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { busySeconds, busyUntil, formatCountdown, spokenWait } from './stores.js';

describe('formatCountdown', () => {
	it('formats minutes and zero-padded seconds', () => {
		expect(formatCountdown(24)).toBe('0:24');
		expect(formatCountdown(65)).toBe('1:05');
		expect(formatCountdown(0)).toBe('0:00');
		expect(formatCountdown(-3)).toBe('0:00');
		expect(formatCountdown(4.2)).toBe('0:05');
	});

	it('adds hours for a long wait such as the daily limit', () => {
		expect(formatCountdown(3599)).toBe('59:59');
		expect(formatCountdown(3600)).toBe('1:00:00');
		expect(formatCountdown(3725)).toBe('1:02:05');
		expect(formatCountdown(86_400)).toBe('24:00:00');
	});
});

describe('spokenWait', () => {
	it('says seconds under a minute', () => {
		expect(spokenWait(1)).toBe('1 second');
		expect(spokenWait(24)).toBe('24 seconds');
		expect(spokenWait(0)).toBe('0 seconds');
	});

	it('rounds minutes up so the wait is never shorter than said', () => {
		expect(spokenWait(60)).toBe('1 minute');
		expect(spokenWait(61)).toBe('2 minutes');
		expect(spokenWait(3540)).toBe('59 minutes');
		expect(spokenWait(3541)).toBe('1 hour');
	});

	it('says hours and minutes for long waits', () => {
		expect(spokenWait(3600)).toBe('1 hour');
		expect(spokenWait(3725)).toBe('1 hour 3 minutes');
		expect(spokenWait(7200 + 60)).toBe('2 hours 1 minute');
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
