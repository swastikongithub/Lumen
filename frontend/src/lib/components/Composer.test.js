import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Composer from './Composer.svelte';

let component;

beforeEach(() => {
	// jsdom has no matchMedia; the composer reads it for its placeholder.
	vi.stubGlobal('matchMedia', (query) => ({
		matches: false,
		media: query,
		addEventListener() {},
		removeEventListener() {}
	}));
});

afterEach(() => {
	if (component) unmount(component);
	component = null;
	document.body.innerHTML = '';
});

function render(props = {}) {
	const handlers = { onsend: vi.fn(), onstop: vi.fn() };
	component = mount(Composer, { target: document.body, props: { ...handlers, ...props } });
	flushSync();
	return handlers;
}

const textarea = () => document.querySelector('textarea');
const button = () => document.querySelector('button');

function type(text) {
	textarea().value = text;
	textarea().dispatchEvent(new Event('input', { bubbles: true }));
	flushSync();
}

function press(init) {
	const event = new KeyboardEvent('keydown', {
		key: 'Enter',
		bubbles: true,
		cancelable: true,
		...init
	});
	textarea().dispatchEvent(event);
	flushSync();
	return event;
}

describe('Composer', () => {
	it('has a label, a length limit and the short placeholder on phones', () => {
		render();
		expect(document.querySelector('label').textContent).toBe('Ask a question');
		expect(textarea().getAttribute('maxlength')).toBe('1000');
		expect(textarea().placeholder).toBe('Ask about exams, attendance, hostel…');
	});

	it('sends the trimmed question on Enter and clears the box', () => {
		const { onsend } = render();
		type('  Is there a minimum attendance?  ');

		const event = press();

		expect(event.defaultPrevented).toBe(true);
		expect(onsend).toHaveBeenCalledWith('Is there a minimum attendance?');
		expect(textarea().value).toBe('');
	});

	it('keeps Shift + Enter and IME composition as typing', () => {
		const { onsend } = render();
		type('Line one');

		expect(press({ shiftKey: true }).defaultPrevented).toBe(false);
		expect(press({ isComposing: true }).defaultPrevented).toBe(false);
		expect(onsend).not.toHaveBeenCalled();
	});

	it('sends with the button and ignores an empty question', () => {
		const { onsend } = render();
		button().click();
		expect(onsend).not.toHaveBeenCalled();
		expect(document.activeElement).toBe(textarea());

		type('Hostel timings?');
		button().click();
		expect(onsend).toHaveBeenCalledWith('Hostel timings?');
	});

	it('turns the button into Stop while an answer streams', () => {
		const { onsend, onstop } = render({ sending: true });
		type('Next question');
		press();
		expect(onsend).not.toHaveBeenCalled();
		expect(textarea().value).toBe('Next question');

		expect(button().getAttribute('aria-label')).toBe('Stop the answer');
		button().click();
		expect(onstop).toHaveBeenCalled();
	});

	it('disables the box and the button while Lumen is busy', () => {
		render({ disabled: true });
		expect(textarea().disabled).toBe(true);
		expect(button().disabled).toBe(true);
		expect(button().getAttribute('aria-label')).toBe('Send (unavailable)');
	});
});
