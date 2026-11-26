import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { busyReason, busyUntil } from '#lib/stores.js';
import BusyBanner from './BusyBanner.svelte';

let component;

beforeEach(() => {
	vi.useFakeTimers();
	vi.setSystemTime(new Date('2026-11-26T10:00:00Z'));
});

afterEach(() => {
	if (component) unmount(component);
	component = null;
	busyUntil.set(0);
	busyReason.set('rate_limited');
	vi.useRealTimers();
	document.body.innerHTML = '';
});

function render() {
	component = mount(BusyBanner, { target: document.body });
	flushSync();
}

const visible = () => document.querySelector('[aria-hidden="true"]:not(svg)')?.textContent;
const spoken = () => document.querySelector('.visually-hidden')?.textContent;

describe('BusyBanner', () => {
	it('shows nothing when Lumen is not busy', () => {
		render();
		expect(document.body.textContent.trim()).toBe('');
	});

	it('counts down and disappears when the wait is over', () => {
		busyUntil.set(Date.now() + 24_000);
		render();
		expect(visible()).toContain('Lumen is busy right now. Try again in 0:24');
		expect(spoken()).toContain('24 seconds');

		vi.advanceTimersByTime(1000);
		flushSync();
		expect(visible()).toContain('0:23');
		// The announcement doesn't change every second.
		expect(spoken()).toContain('24 seconds');

		vi.advanceTimersByTime(23_000);
		flushSync();
		expect(document.body.textContent.trim()).toBe('');
	});

	it("says when this device or network reached Lumen's question limit", () => {
		busyReason.set('too_many_requests');
		busyUntil.set(Date.now() + 42_000);
		render();
		expect(visible()).toContain('Too many questions from this device or network.');
		expect(visible()).toContain('0:42');
		expect(visible()).not.toContain('busy');
		expect(spoken()).toContain('Too many questions from this device or network.');
	});

	it('shows hours and speaks the wait in words when the daily limit is reached', () => {
		busyReason.set('too_many_requests');
		busyUntil.set(Date.now() + 3725_000);
		render();
		expect(visible()).toContain('Try again in 1:02:05');
		expect(spoken()).toContain('Try again in 1 hour 3 minutes.');
	});

	it('is a status region for screen readers', () => {
		busyUntil.set(Date.now() + 5000);
		render();
		expect(document.querySelector('[role="status"]').textContent).toContain('busy');
	});
});
