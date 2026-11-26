import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import CitationChip from './CitationChip.svelte';

let component;

function render(props) {
	component = mount(CitationChip, { target: document.body, props });
	flushSync();
	return document.body;
}

afterEach(() => {
	if (component) unmount(component);
	component = null;
	document.body.innerHTML = '';
});

describe('CitationChip', () => {
	it('is a labelled button that reports its number and element', () => {
		const onselect = vi.fn();
		const body = render({ n: 2, title: 'Hostel Rules', onselect });
		const button = body.querySelector('button');

		expect(button.textContent.trim()).toBe('2');
		expect(button.getAttribute('aria-label')).toBe('Source 2: Hostel Rules');
		expect(button.getAttribute('aria-pressed')).toBe('false');

		button.click();
		expect(onselect).toHaveBeenCalledWith(2, button);
	});

	it('shows the selected state', () => {
		const body = render({ n: 1, title: 'Exam Policy', selected: true });
		expect(body.querySelector('button').getAttribute('aria-pressed')).toBe('true');
	});

	it('is not a button while the answer streams', () => {
		const body = render({ n: 3, pending: true });
		expect(body.querySelector('button')).toBeNull();
		expect(body.querySelector('span').textContent).toBe('3');
	});
});
