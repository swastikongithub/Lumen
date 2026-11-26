import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { busyUntil } from '#lib/stores.js';
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
	vi.useRealTimers();
	document.body.innerHTML = '';
});

function render() {
	component = mount(BusyBanner, { target: document.body });
	flushSync();
}

describe('BusyBanner', () => {
	it('shows nothing when Lumen is not busy', () => {
		render();
		expect(document.body.textContent.trim()).toBe('');
	});

	it('counts down and disappears when the wait is over', () => {
		busyUntil.set(Date.now() + 24_000);
		render();
		const visible = () => document.querySelector('[aria-hidden="true"]:not(svg)')?.textContent;
		expect(visible()).toContain('Try again in 0:24');
		expect(document.querySelector('.visually-hidden').textContent).toContain('24 seconds');

		vi.advanceTimersByTime(1000);
		flushSync();
		expect(visible()).toContain('0:23');
		// The announcement doesn't change every second.
		expect(document.querySelector('.visually-hidden').textContent).toContain('24 seconds');

		vi.advanceTimersByTime(23_000);
		flushSync();
		expect(document.body.textContent.trim()).toBe('');
	});

	it('is a status region for screen readers', () => {
		busyUntil.set(Date.now() + 5000);
		render();
		expect(document.querySelector('[role="status"]').textContent).toContain('busy');
	});
});
