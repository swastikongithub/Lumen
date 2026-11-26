// A .svelte.test.js file, so the props can be a $state object that a test changes.
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { errorText } from '#lib/chat.js';
import Message from './Message.svelte';

let component;

const citations = [
	{ n: 1, title: 'Examination Policy', page: 12, page_end: 12, category: 'exams', text: 'A' },
	{ n: 2, title: 'Hostel Rules', page: 3, page_end: 3, category: 'hostel', text: 'B' }
];

function answer(patch = {}) {
	return {
		key: 'm2',
		id: 'msg-1',
		role: 'assistant',
		content: 'You need 75% attendance [1]. Shortage may be condoned [2]. See also [9].',
		citations,
		status: 'done',
		abstained: false,
		error: null,
		...patch
	};
}

/** Mounts a Message with reactive props and returns them, so a test can change them. */
function render(patch = {}) {
	const props = $state({
		message: answer(),
		selectedN: null,
		canRetry: true,
		onselectsource: vi.fn(),
		onrate: vi.fn(),
		onretry: vi.fn(),
		...patch
	});
	component = mount(Message, { target: document.body, props });
	flushSync();
	return props;
}

const chips = () => [...document.querySelectorAll('.answer .chip')];

afterEach(() => {
	if (component) unmount(component);
	component = null;
	document.body.innerHTML = '';
});

describe('Message', () => {
	it('shows a question as a bubble', () => {
		render({ message: { key: 'm1', id: null, role: 'user', content: 'Attendance rule?' } });
		expect(document.querySelector('.bubble').textContent).toBe('Attendance rule?');
		expect(document.querySelector('article')).toBeNull();
	});

	it('mounts a chip for each citation and skips markers with no citation', () => {
		const props = render();
		const buttons = chips();

		expect(buttons.map((chip) => chip.textContent.trim())).toEqual(['1', '2']);
		expect(buttons[0].tagName).toBe('BUTTON');
		expect(buttons[0].getAttribute('aria-label')).toBe('Source 1: Examination Policy');
		expect(document.querySelector('.answer').textContent).not.toContain('[9]');

		buttons[1].click();
		expect(props.onselectsource).toHaveBeenCalledWith('m2', 2, buttons[1]);
	});

	it('lists the sources under the answer and opens one on click', () => {
		const props = render();
		const rows = [...document.querySelectorAll('.sources .source')];

		expect(rows).toHaveLength(2);
		expect(rows[0].textContent).toContain('Examination Policy');
		expect(rows[0].textContent).toContain('p.12');

		rows[0].click();
		expect(props.onselectsource).toHaveBeenCalledWith('m2', 1, rows[0]);
	});

	it('updates the selected chip in place, so a focused chip keeps focus', () => {
		const props = render();
		const [first] = chips();
		first.focus();

		props.selectedN = 1;
		flushSync();

		expect(chips()[0]).toBe(first);
		expect(first.getAttribute('aria-pressed')).toBe('true');
		expect(chips()[1].getAttribute('aria-pressed')).toBe('false');
		expect(document.activeElement).toBe(first);
	});

	it('shows inert chips and the caret while streaming, without sources or feedback', () => {
		render({
			message: answer({ content: 'You need 75% [1]', citations: [], status: 'streaming' })
		});

		const [chip] = chips();
		expect(chip.tagName).toBe('SPAN');
		expect(chip.textContent).toBe('1');
		expect(document.querySelector('.caret')).not.toBeNull();
		expect(document.querySelector('.answer').getAttribute('aria-busy')).toBe('true');
		expect(document.querySelector('.sources')).toBeNull();
		expect(document.querySelector('.meta').textContent).toContain('writing the answer');
	});

	it('turns the chips into buttons when the citations arrive', () => {
		const props = render({
			message: answer({ content: 'You need 75% [1]', citations: [], status: 'streaming' })
		});

		props.message = answer({ content: 'You need 75% [1]', citations: [citations[0]] });
		flushSync();

		expect(chips().map((chip) => chip.tagName)).toEqual(['BUTTON']);
		expect(document.querySelector('.caret')).toBeNull();
	});

	it('shows the abstain card instead of an answer', () => {
		render({
			message: answer({
				content: "I couldn't find this in the indexed documents.",
				abstained: true
			})
		});
		expect(document.querySelector('.abstain')).not.toBeNull();
		expect(document.querySelector('.card')).toBeNull();
	});

	it('shows an error with a retry button', () => {
		const props = render({
			message: answer({
				content: '',
				citations: [],
				status: 'error',
				error: { code: 'unavailable' }
			})
		});
		const alert = document.querySelector('[role="alert"]');
		expect(alert.textContent).toContain(errorText('unavailable'));

		document.querySelector('.retry').click();
		expect(props.onretry).toHaveBeenCalledWith('m2');
	});

	it('disables retry while Lumen is busy', () => {
		render({
			canRetry: false,
			message: answer({ content: '', citations: [], status: 'error', error: { code: 'network' } })
		});
		expect(document.querySelector('.retry').disabled).toBe(true);
	});

	it('keeps a stopped answer without an alert', () => {
		render({ message: answer({ content: 'Partial', citations: [], status: 'stopped' }) });
		expect(document.querySelector('[role="alert"]')).toBeNull();
		expect(document.querySelector('.notice').textContent).toContain('You stopped this answer.');
	});
});
