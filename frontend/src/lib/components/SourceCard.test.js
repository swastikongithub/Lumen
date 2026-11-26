import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import SourceCard from './SourceCard.svelte';

let component;

const citation = {
	n: 1,
	title: 'Examination Policy',
	url: 'https://www.lpu.in/downloads/exam-policy.pdf',
	page: 12,
	page_end: 12,
	section: '4.2 Eligibility',
	category: 'exams',
	source_id: 'exam-policy',
	text:
		'Students are assessed through continuous evaluation. A student must have at least 75% ' +
		'attendance in each course to sit the end-term examination. Shortage may be condoned.'
};

function render(props) {
	component = mount(SourceCard, { target: document.body, props: { citation, ...props } });
	flushSync();
	return document.querySelector('article');
}

afterEach(() => {
	if (component) unmount(component);
	component = null;
	document.body.innerHTML = '';
});

describe('SourceCard', () => {
	it('shows the title, the meta line and the passage with the cited sentence marked', () => {
		const card = render({ answer: 'You need 75% attendance in each course [1].', id: 'src-1' });

		expect(card.querySelector('.title').textContent).toContain('Examination Policy');
		expect(card.querySelector('.meta').textContent).toBe('4.2 Eligibility · Page 12 · Exams');
		expect(card.querySelector('mark').textContent).toBe(
			'A student must have at least 75% attendance in each course to sit the end-term examination.'
		);
		// The excerpt reads as the passage: no stray spaces or breaks around the highlight.
		expect(card.querySelector('.excerpt').textContent.replace(/\s+/g, ' ').trim()).toBe(
			citation.text
		);
		expect(card.getAttribute('aria-labelledby')).toBe('src-1-title');
	});

	it('links to the document at the cited page in a new tab', () => {
		const link = render().querySelector('a');
		expect(link.getAttribute('href')).toBe('https://www.lpu.in/downloads/exam-policy.pdf#page=12');
		expect(link.getAttribute('target')).toBe('_blank');
		expect(link.getAttribute('rel')).toBe('noopener noreferrer');
		expect(link.textContent).toContain('Open PDF at page 12');
	});

	it('shows no link for a URL that is not http(s)', () => {
		component = mount(SourceCard, {
			target: document.body,
			props: { citation: { ...citation, url: 'javascript:alert(1)' } }
		});
		flushSync();
		expect(document.querySelector('a')).toBeNull();
	});

	it('marks the selected card', () => {
		expect(render({ selected: true }).classList.contains('selected')).toBe(true);
	});
});
