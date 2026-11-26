import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import FeedbackButtons from './FeedbackButtons.svelte';

let component;

const baseMessage = {
	key: 'm2',
	id: 'a1',
	content: 'You need 75% [1].',
	citations: [{ n: 1, title: 'Exam Policy', url: 'https://x.org/a.pdf', page: 3 }],
	rating: 0,
	reason: null
};

function render(message, onrate = vi.fn()) {
	component = mount(FeedbackButtons, { target: document.body, props: { message, onrate } });
	flushSync();
	return { onrate, button: (label) => document.querySelector(`[aria-label="${label}"]`) };
}

const chipLabels = () =>
	[...document.querySelectorAll('[role="group"] button')].map((b) => b.textContent.trim());

afterEach(() => {
	if (component) unmount(component);
	component = null;
	document.body.innerHTML = '';
});

describe('FeedbackButtons', () => {
	it('rates with the thumbs', () => {
		const { onrate, button } = render(baseMessage);
		button('Helpful').click();
		expect(onrate).toHaveBeenCalledWith(1, null);
		button('Not helpful').click();
		expect(onrate).toHaveBeenCalledWith(-1, null);
	});

	it('does nothing when the selected thumb is tapped again', () => {
		const { onrate, button } = render({ ...baseMessage, rating: 1 });
		expect(button('Helpful').getAttribute('aria-pressed')).toBe('true');
		button('Helpful').click();
		expect(onrate).not.toHaveBeenCalled();
	});

	it('hides the reasons until thumbs down', () => {
		render(baseMessage);
		expect(document.body.textContent).not.toContain('What went wrong?');
	});

	it('always offers "Offensive or harmful" after thumbs down', () => {
		const { onrate } = render({ ...baseMessage, rating: -1 });
		expect(document.body.textContent).toContain('What went wrong?');
		expect(chipLabels()).toEqual([
			'Wrong',
			'Outdated',
			"Didn't find it",
			'Unclear',
			'Offensive or harmful'
		]);
		[...document.querySelectorAll('[role="group"] button')].at(-1).click();
		expect(onrate).toHaveBeenCalledWith(-1, 'offensive');
	});

	it('marks the chosen reason and thanks the student', () => {
		render({ ...baseMessage, rating: -1, reason: 'outdated' });
		const outdated = [...document.querySelectorAll('[role="group"] button')][1];
		expect(outdated.getAttribute('aria-pressed')).toBe('true');
		expect(document.body.textContent).toContain('Thanks.');
	});

	it('says when feedback could not be sent', () => {
		render({ ...baseMessage, feedbackError: true });
		expect(document.querySelector('[role="alert"]').textContent).toContain(
			"Couldn't send your feedback"
		);
	});

	it('copies the answer with its sources on the web', async () => {
		const writeText = vi.fn(async () => {});
		vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
		const { button } = render(baseMessage);
		button('Copy answer').click();
		await vi.waitFor(() => expect(writeText).toHaveBeenCalled());
		expect(writeText.mock.calls[0][0]).toContain('Sources:\n[1] Exam Policy, p.3');
		await vi.waitFor(() => expect(document.body.textContent).toContain('Answer copied'));
	});
});
