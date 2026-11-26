import { get } from 'svelte/store';
import { describe, expect, it, vi } from 'vitest';
import { createSourceIndex, formatDate } from './sources.js';

const documents = [
	{
		source_id: 'exam-policy',
		title: 'Examination Policy',
		category: 'exams',
		source_url: 'https://www.lpu.in/a.pdf',
		academic_year: '2025-26',
		ingested_at: '2026-11-25T18:30:00Z'
	}
];

describe('createSourceIndex', () => {
	it('loads once and indexes documents by source_id', async () => {
		const fetchSources = vi.fn(async () => documents);
		const index = createSourceIndex(fetchSources);
		expect(get(index).status).toBe('idle');

		await Promise.all([index.load(), index.load()]);
		await index.load();

		expect(fetchSources).toHaveBeenCalledTimes(1);
		const state = get(index);
		expect(state.status).toBe('ready');
		expect(state.documents).toEqual(documents);
		expect(state.byId.get('exam-policy').academic_year).toBe('2025-26');
	});

	it('reports an error and loads again on the next call', async () => {
		const fetchSources = vi
			.fn()
			.mockRejectedValueOnce(new Error('offline'))
			.mockResolvedValueOnce(documents);
		const index = createSourceIndex(fetchSources);

		await index.load();
		expect(get(index)).toMatchObject({ status: 'error', documents: [] });

		await index.load();
		expect(get(index)).toMatchObject({ status: 'ready', error: null });
		expect(fetchSources).toHaveBeenCalledTimes(2);
	});
});

describe('formatDate', () => {
	it('formats a date and ignores missing or bad ones', () => {
		// Midday UTC is the same date in every timezone from UTC-11 to UTC+11.
		expect(formatDate('2026-11-25T12:00:00Z')).toBe('25 Nov 2026');
		expect(formatDate(null)).toBe('');
		expect(formatDate('soon')).toBe('');
	});
});
