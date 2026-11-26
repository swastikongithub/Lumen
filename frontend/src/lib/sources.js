/**
 * The indexed documents (GET /api/v1/sources), fetched once and shared: the /sources page
 * lists them, and source cards read a document's academic year from them, since
 * citations don't carry it.
 */

import { writable } from 'svelte/store';
import { getSources } from './api.js';

/**
 * @typedef {{ source_id: string, title: string, category: string, source_url: string,
 *   academic_year: string | null, ingested_at: string }} SourceDocument
 * @typedef {{ status: 'idle' | 'loading' | 'ready' | 'error', documents: SourceDocument[],
 *   byId: Map<string, SourceDocument>, error: unknown }} SourceIndex
 */

/** @param {() => Promise<SourceDocument[]>} fetchSources */
export function createSourceIndex(fetchSources = getSources) {
	/** @type {import('svelte/store').Writable<SourceIndex>} */
	const state = writable({ status: 'idle', documents: [], byId: new Map(), error: null });
	/** @type {Promise<void> | null} */
	let pending = null;
	let loaded = false;

	/** Fetch the list unless it is loaded or loading. Call again after an error to retry. */
	function load() {
		if (loaded) return Promise.resolve();
		pending ??= (async () => {
			state.update((s) => ({ ...s, status: 'loading', error: null }));
			try {
				const documents = await fetchSources();
				loaded = true;
				state.set({
					status: 'ready',
					documents,
					byId: new Map(documents.map((document) => [document.source_id, document])),
					error: null
				});
			} catch (error) {
				state.update((s) => ({ ...s, status: 'error', error }));
			} finally {
				pending = null;
			}
		})();
		return pending;
	}

	return { subscribe: state.subscribe, load };
}

/** The app's document list. */
export const sourceIndex = createSourceIndex();

/**
 * "26 Nov 2026" in the reader's locale settings, or "" for a missing or bad date.
 * @param {string | null | undefined} iso
 */
export function formatDate(iso) {
	const date = iso ? new Date(iso) : null;
	if (!date || Number.isNaN(date.getTime())) return '';
	return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}
