import { describe, expect, it } from 'vitest';
import {
	CATEGORIES,
	FEEDBACK_REASONS,
	answerMeta,
	categoryLabel,
	cleanAnswer,
	documentCount,
	openLabel,
	pageLabel,
	shareText,
	sourceHref,
	sourceMeta
} from './answer.js';

const examPolicy = {
	n: 1,
	title: 'Examination Policy',
	url: 'https://www.lpu.in/downloads/exam-policy.pdf',
	page: 12,
	page_end: 12,
	section: '4.2 Unfair Means',
	category: 'exams',
	document_id: 'd1'
};
const hostelPage = {
	n: 2,
	title: 'Hostel Rules',
	url: 'https://www.lpu.in/hostel/rules.php',
	page: null,
	page_end: null,
	section: null,
	category: 'hostel',
	document_id: 'd2'
};

describe('categories and reasons', () => {
	it('lists All first, then the five categories with hints', () => {
		expect(CATEGORIES.map((c) => c.label)).toEqual([
			'All',
			'Academics',
			'Exams',
			'Hostel',
			'Fees',
			'Placements'
		]);
		expect(CATEGORIES[0].value).toBeNull();
		expect(CATEGORIES.every((c) => c.hint)).toBe(true);
	});

	it('always offers "Offensive or harmful" (Google Play AI-content policy)', () => {
		expect(FEEDBACK_REASONS).toContainEqual({ value: 'offensive', label: 'Offensive or harmful' });
		expect(FEEDBACK_REASONS.map((r) => r.label)).toEqual([
			'Wrong',
			'Outdated',
			"Didn't find it",
			'Unclear',
			'Offensive or harmful'
		]);
	});

	it('labels categories, including other and unknown values', () => {
		expect(categoryLabel('exams')).toBe('Exams');
		expect(categoryLabel('other')).toBe('Other');
		expect(categoryLabel(null)).toBe('All');
		expect(categoryLabel('library')).toBe('Library');
	});
});

describe('page labels', () => {
	it('formats one page, a range and no pages', () => {
		expect(pageLabel(examPolicy)).toBe('p.12');
		expect(pageLabel({ page: 12, page_end: 13 })).toBe('pp.12–13');
		expect(pageLabel({ page: 12, page_end: 13 }, { long: true })).toBe('Pages 12–13');
		expect(pageLabel(examPolicy, { long: true })).toBe('Page 12');
		expect(pageLabel(hostelPage)).toBeNull();
	});

	it('builds the source meta line and skips empty parts', () => {
		expect(sourceMeta(examPolicy)).toBe('4.2 Unfair Means · p.12 · Exams');
		expect(sourceMeta(examPolicy, { long: true, academicYear: '2025-26' })).toBe(
			'4.2 Unfair Means · Page 12 · Exams · 2025-26'
		);
		expect(sourceMeta(hostelPage)).toBe('Hostel');
	});
});

describe('document links', () => {
	it('opens PDFs at the cited page', () => {
		expect(sourceHref(examPolicy)).toBe('https://www.lpu.in/downloads/exam-policy.pdf#page=12');
		expect(openLabel(examPolicy)).toBe('Open PDF at page 12');
	});

	it('links web pages as they are', () => {
		expect(sourceHref(hostelPage)).toBe('https://www.lpu.in/hostel/rules.php');
		expect(openLabel(hostelPage)).toBe('Open document');
	});

	it('keeps an existing fragment', () => {
		expect(sourceHref({ url: 'https://x.org/a.pdf#nameddest=s4', page: 3 })).toBe(
			'https://x.org/a.pdf#nameddest=s4'
		);
	});

	it('refuses links that are not http(s)', () => {
		expect(sourceHref({ url: 'javascript:alert(1)', page: null })).toBeNull();
		expect(sourceHref({ url: 'not a url', page: null })).toBeNull();
		expect(sourceHref({ url: null, page: 1 })).toBeNull();
	});
});

describe('answer meta', () => {
	const done = { status: 'done', content: 'x', abstained: false };

	it('describes the stream without inventing numbers', () => {
		expect(answerMeta({ status: 'streaming', content: '', citations: [] })).toBe(
			'searching the documents'
		);
		expect(answerMeta({ status: 'streaming', content: 'You', citations: [] })).toBe(
			'writing the answer'
		);
	});

	it('counts documents and passages from the citations', () => {
		expect(answerMeta({ ...done, citations: [examPolicy, hostelPage] })).toBe('from 2 documents');
		expect(
			answerMeta({ ...done, citations: [examPolicy, { ...examPolicy, n: 3 }, hostelPage] })
		).toBe('from 3 passages in 2 documents');
		expect(answerMeta({ ...done, citations: [examPolicy] })).toBe('from 1 document');
	});

	it('shows nothing for abstained, failed or uncited answers', () => {
		expect(answerMeta({ ...done, abstained: true, citations: [examPolicy] })).toBe('');
		expect(answerMeta({ ...done, status: 'error', citations: [] })).toBe('');
		expect(answerMeta({ ...done, citations: [] })).toBe('');
	});

	it('counts distinct documents', () => {
		expect(documentCount([examPolicy, { ...examPolicy, n: 4 }])).toBe(1);
	});
});

describe('copy and share text', () => {
	it('drops markers that point at no citation', () => {
		expect(cleanAnswer('A [1]. B [7].', [examPolicy])).toBe('A [1]. B .');
	});

	it('lists numbered sources with pages and links, then the attribution', () => {
		const text = shareText({
			content: 'You need 75% attendance [1]. Hostel gates close at 10 pm [2].',
			citations: [examPolicy, hostelPage]
		});
		expect(text).toBe(
			[
				'You need 75% attendance [1]. Hostel gates close at 10 pm [2].',
				'',
				'Sources:',
				'[1] Examination Policy, p.12: https://www.lpu.in/downloads/exam-policy.pdf#page=12',
				'[2] Hostel Rules: https://www.lpu.in/hostel/rules.php',
				'',
				'via Lumen (unofficial)'
			].join('\n')
		);
	});

	it('works without citations', () => {
		expect(shareText({ content: 'Hello', citations: [] })).toBe('Hello\n\nvia Lumen (unofficial)');
	});
});
